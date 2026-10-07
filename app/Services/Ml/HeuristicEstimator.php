<?php

declare(strict_types=1);

namespace App\Services\Ml;

use App\Enums\RiskLevel;

/**
 * Deterministic, dependency-free estimator used when the ML service cannot be
 * reached, and as the last line of defence so a requirement is never left
 * without an analysis.
 *
 * This is intentionally conservative and clearly labelled as a fallback: the
 * resulting rows carry `estimation_method = heuristic_fallback` so the estimate
 * is never mistaken for a model prediction.
 */
final class HeuristicEstimator
{
    private const MAX_COMPLEXITY = 5.0;

    private const COMPLEX_KEYWORDS = [
        'integrate', 'integration', 'authentication', 'payment', 'security',
        'real-time', 'realtime', 'concurrent', 'distributed', 'websocket',
        'encryption', 'webhook', 'microservice', 'machine learning', 'blockchain',
    ];

    private const MEDIUM_KEYWORDS = [
        'dashboard', 'analytics', 'report', 'export', 'import', 'search',
        'filter', 'notification', 'email', 'upload', 'download', 'calendar',
    ];

    /**
     * @var list<string>
     */
    private const CATEGORY_RULES = [
        'authentication' => ['login', 'sign in', 'signin', 'signup', 'sign up', 'password', 'oauth', 'sso', 'jwt', '2fa', 'mfa'],
        'payment' => ['payment', 'checkout', 'billing', 'subscription', 'invoice', 'stripe', 'paypal'],
        'e_commerce' => ['cart', 'product', 'catalog', 'order', 'inventory', 'shipping', 'wishlist'],
        'dashboard_analytics' => ['dashboard', 'chart', 'report', 'analytics', 'kpi', 'metric', 'visualization'],
        'content_management' => ['cms', 'blog', 'post', 'article', 'editor', 'seo', 'sitemap'],
        'api_integration' => ['api', 'rest', 'graphql', 'webhook', 'endpoint', 'sdk', 'third-party'],
        'notification' => ['notification', 'notify', 'alert', 'reminder', 'push'],
        'realtime' => ['websocket', 'live', 'streaming', 'chat', 'presence'],
        'geolocation' => ['map', 'location', 'geo', 'address', 'distance', 'route'],
        'security' => ['encrypt', 'security', 'firewall', 'vulnerability', 'audit', 'gdpr', 'hipaa', 'pci'],
        'search_filter' => ['search', 'filter', 'sort', 'autocomplete', 'facet'],
    ];

    /**
     * @return array{
     *     classification: string,
     *     complexity_score: float,
     *     risk_level: RiskLevel,
     *     estimated_hours: float,
     *     modules: list<array{name: string, description: string|null, complexity: float, estimated_hours: float}>,
     *     risk_factors: list<array{factor: string, level: string, mitigation: string|null}>
     * }
     */
    public function estimate(string $text): array
    {
        $lower = mb_strtolower($text);

        $classification = $this->classify($lower);
        $complexity = $this->complexity($lower);
        $riskLevel = $this->riskFromComplexity($complexity);
        $estimatedHours = round(4.0 * $complexity, 2);

        return [
            'classification' => $classification,
            'complexity_score' => $complexity,
            'risk_level' => $riskLevel,
            'estimated_hours' => $estimatedHours,
            'modules' => $this->modules($classification, $complexity, $estimatedHours),
            'risk_factors' => $this->riskFactors($riskLevel, $lower),
        ];
    }

    private function classify(string $lower): string
    {
        foreach (self::CATEGORY_RULES as $category => $keywords) {
            foreach ($keywords as $keyword) {
                if (str_contains($lower, $keyword)) {
                    return $category;
                }
            }
        }

        return 'general';
    }

    private function complexity(string $lower): float
    {
        $score = 1.0;

        // Length signal, deliberately shallow: past ~250 words the extra text
        // adds little information about difficulty.
        $wordCount = str_word_count($lower);

        if ($wordCount > 60) {
            $score += 0.75;
        }

        if ($wordCount > 150) {
            $score += 0.75;
        }

        $high = $this->countMatches($lower, self::COMPLEX_KEYWORDS);
        $medium = $this->countMatches($lower, self::MEDIUM_KEYWORDS);

        $score += min(1.5, $high * 0.3);
        $score += min(0.75, $medium * 0.15);

        return round(min(self::MAX_COMPLEXITY, $score), 2);
    }

    /**
     * @param  list<string>  $keywords
     */
    private function countMatches(string $lower, array $keywords): int
    {
        $matches = 0;

        foreach ($keywords as $keyword) {
            if (str_contains($lower, $keyword)) {
                $matches++;
            }
        }

        return $matches;
    }

    private function riskFromComplexity(float $complexity): RiskLevel
    {
        return match (true) {
            $complexity >= 4.0 => RiskLevel::Critical,
            $complexity >= 3.0 => RiskLevel::High,
            $complexity >= 2.0 => RiskLevel::Medium,
            default => RiskLevel::Low,
        };
    }

    /**
     * @return list<array{name: string, description: string|null, complexity: float, estimated_hours: float}>
     */
    private function modules(string $classification, float $complexity, float $estimatedHours): array
    {
        // Split the estimate across the layers that every deliverable needs.
        $split = [
            'Core Logic' => 0.40,
            'Data Layer' => 0.20,
            'API Layer' => 0.20,
            'Testing' => 0.15,
        ];

        $modules = [];
        $allocated = 0.0;

        foreach ($split as $name => $share) {
            $hours = round($estimatedHours * $share, 2);
            $allocated += $hours;

            $modules[] = [
                'name' => $name,
                'description' => sprintf('%s work for the %s requirement', $name, $classification),
                'complexity' => round($complexity * $share * 2, 2),
                'estimated_hours' => $hours,
            ];
        }

        // Give the rounding remainder to the largest slice so the module
        // estimates always sum exactly to the headline number.
        $remainder = round($estimatedHours - $allocated, 2);

        if ($remainder !== 0.0 && $modules !== []) {
            $lastIndex = array_key_last($modules);
            $modules[$lastIndex]['estimated_hours'] = round(
                $modules[$lastIndex]['estimated_hours'] + $remainder,
                2
            );
        }

        return $modules;
    }

    /**
     * @return list<array{factor: string, level: string, mitigation: string|null}>
     */
    private function riskFactors(RiskLevel $riskLevel, string $lower): array
    {
        $level = match ($riskLevel) {
            RiskLevel::Critical, RiskLevel::High => 'high',
            RiskLevel::Medium => 'medium',
            RiskLevel::Low => 'low',
        };

        $factors = [
            [
                'factor' => 'Scope Creep Risk',
                'level' => $level,
                'mitigation' => 'Define clear acceptance criteria and use MoSCoW prioritisation.',
            ],
            [
                'factor' => 'Estimation Confidence',
                'level' => 'high',
                'mitigation' => 'This estimate was produced by a rule-based fallback because the ML service was unavailable. Re-run the analysis once it is reachable before committing to a delivery date.',
            ],
        ];

        if (str_word_count($lower) < 15) {
            $factors[] = [
                'factor' => 'Insufficient Detail',
                'level' => 'high',
                'mitigation' => 'Request more detailed requirements, including user stories and acceptance criteria.',
            ];
        }

        return $factors;
    }
}
