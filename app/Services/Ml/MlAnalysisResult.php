<?php

declare(strict_types=1);

namespace App\Services\Ml;

use App\Enums\RiskLevel;

/**
 * Immutable, validated representation of a single ML analysis result.
 *
 * The service is untrusted input: every field is normalised and clamped here
 * so that a malformed or hostile response can never corrupt the database or
 * break the JSON contract of the API.
 */
final class MlAnalysisResult
{
    /**
     * Caps that keep a hostile payload from inflating row counts or storage.
     */
    private const MAX_QUESTIONS = 20;

    private const MAX_COLLECTION = 50;

    private const MAX_KEYWORDS = 20;

    /**
     * @param  list<array{name: string, description: string|null, complexity: float, estimated_hours: float}>  $modules
     * @param  list<array{factor: string, level: string, description: string|null, mitigation: string|null}>  $riskFactors
     * @param  list<array{id: string, question: string, category: string, priority: string, status: string, answer: string|null}>  $questions
     * @param  list<array{feature_type: string, match_count: int, estimated_hours: float}>  $features
     * @param  list<string>  $keywords
     * @param  list<array{phase: string, estimated_days: float, description: string|null}>  $milestones
     * @param  array{ml_score: float|null, keyword_score: float|null, weighted_final: float|null}|null  $breakdown
     * @param  array{working_days: int|null, calendar_days: int|null, team_size: int|null}|null  $timeline
     */
    private function __construct(
        public readonly string $classification,
        public readonly float $complexityScore,
        public readonly RiskLevel $riskLevel,
        public readonly float $estimatedHours,
        public readonly string $estimationMethod,
        public readonly array $modules,
        public readonly array $riskFactors,
        public readonly ?string $summary = null,
        public readonly ?int $confidence = null,
        public readonly ?float $riskScore = null,
        public readonly array $questions = [],
        public readonly array $features = [],
        public readonly array $keywords = [],
        public readonly array $milestones = [],
        public readonly ?array $breakdown = null,
        public readonly ?array $timeline = null,
    ) {}

    /**
     * Build a result from the raw `/analyze` payload.
     *
     * @param  array<string, mixed>  $payload
     *
     * @throws MlServiceException when the payload contains nothing this
     *                            application recognises as an analysis.
     */
    public static function fromPayload(array $payload): self
    {
        self::guardAgainstUnrecognisedPayload($payload);

        // The canonical label set uses underscores (§4.1); the ML service
        // emits `e-commerce` for one class, so both spellings collapse here.
        $classification = str_replace(
            '-',
            '_',
            self::stringOrDefault(data_get($payload, 'classification.category'), 'general', 100)
        );

        $complexityScore = self::clampFloat(
            data_get($payload, 'complexity.score'),
            1.0,
            5.0,
            1.0
        );

        // The risk level is taken from the overall risk verdict rather than the
        // complexity level, because the two are computed independently.
        $riskLevel = self::riskLevelOrDefault(
            data_get($payload, 'risk.overall_level')
        );

        $estimatedHours = self::clampFloat(
            data_get($payload, 'timeline.total_estimated_hours'),
            0.0,
            10000.0,
            self::defaultHours($complexityScore)
        );

        return new self(
            classification: $classification,
            complexityScore: $complexityScore,
            riskLevel: $riskLevel,
            estimatedHours: $estimatedHours,
            estimationMethod: 'ml_service',
            modules: self::normalizeModules(data_get($payload, 'modules')),
            riskFactors: self::normalizeRiskFactors(data_get($payload, 'risk.factors')),
            summary: self::stringOrNull(data_get($payload, 'summary'), 2000),
            confidence: self::normalizeConfidence(data_get($payload, 'classification.confidence')),
            riskScore: self::nullableFloat(data_get($payload, 'risk.score'), 0.0, 10.0),
            questions: self::normalizeQuestions(data_get($payload, 'questions')),
            features: self::normalizeFeatures(data_get($payload, 'features.detected')),
            keywords: self::normalizeKeywords(
                data_get($payload, 'features.summary'),
                data_get($payload, 'features.detected'),
            ),
            milestones: self::normalizeMilestones(data_get($payload, 'timeline.milestones')),
            breakdown: self::normalizeBreakdown(data_get($payload, 'complexity.breakdown')),
            timeline: self::normalizeTimeline($payload),
        );
    }

    /**
     * Build a result without contacting the ML service.
     *
     * @param  list<array{name: string, description: string|null, complexity: float, estimated_hours: float}>  $modules
     * @param  list<array{factor: string, level: string, mitigation: string|null}>  $riskFactors
     */
    public static function heuristic(
        string $classification,
        float $complexityScore,
        RiskLevel $riskLevel,
        float $estimatedHours,
        array $modules,
        array $riskFactors,
    ): self {
        return new self(
            classification: $classification,
            complexityScore: $complexityScore,
            riskLevel: $riskLevel,
            estimatedHours: $estimatedHours,
            // Honest attribution: no model was involved.
            estimationMethod: 'heuristic_fallback',
            modules: $modules,
            riskFactors: $riskFactors,
            // There is no model confidence to report, so none is invented.
            confidence: null,
            riskScore: null,
            questions: [],
            features: [],
            // The heuristic's own module names are the only keywords it has.
            keywords: array_values(array_unique(array_column($modules, 'name'))),
            milestones: [],
            breakdown: [
                'ml_score' => null,
                'keyword_score' => $complexityScore,
                'weighted_final' => $complexityScore,
            ],
            timeline: null,
        );
    }

    /**
     * Whether this result came from the real ML service.
     */
    public function isMachineGenerated(): bool
    {
        return $this->estimationMethod === 'ml_service';
    }

    /**
     * @return list<array{name: string, description: string|null, complexity: float, estimated_hours: float}>
     */
    private static function normalizeModules(mixed $modules): array
    {
        if (! is_array($modules)) {
            return [];
        }

        $normalized = [];
        $seen = [];

        foreach ($modules as $module) {
            if (! is_array($module)) {
                continue;
            }

            $name = self::stringOrDefault(data_get($module, 'name'), '', 150);

            if ($name === '') {
                continue;
            }

            // Guard against a degenerate model emitting the same module many
            // times, which would create unbounded rows.
            $key = mb_strtolower($name);

            if (isset($seen[$key])) {
                continue;
            }

            $seen[$key] = true;

            $normalized[] = [
                'name' => $name,
                'description' => self::stringOrNull(data_get($module, 'description'), 2000),
                'complexity' => self::clampFloat(
                    data_get($module, 'complexity'),
                    0.0,
                    5.0,
                    0.0
                ),
                'estimated_hours' => self::clampFloat(
                    data_get($module, 'estimated_hours'),
                    0.0,
                    10000.0,
                    0.0
                ),
            ];

            if (count($normalized) >= self::MAX_COLLECTION) {
                break;
            }
        }

        return $normalized;
    }

    /**
     * @return list<array{factor: string, level: string, description: string|null, mitigation: string|null}>
     */
    private static function normalizeRiskFactors(mixed $factors): array
    {
        if (! is_array($factors)) {
            return [];
        }

        $normalized = [];

        foreach ($factors as $factor) {
            if (! is_array($factor)) {
                continue;
            }

            $name = self::stringOrDefault(data_get($factor, 'factor'), '', 200);

            if ($name === '') {
                continue;
            }

            $description = self::stringOrNull(data_get($factor, 'description'), 2000);

            $normalized[] = [
                'factor' => $name,
                // The risk_factors table only allows low/medium/high, so a
                // "critical" verdict is clamped down to "high" here.
                'level' => self::factorLevelOrDefault(data_get($factor, 'level')),
                'description' => $description,
                // Some payloads describe the problem and the fix in one field;
                // in that case the description doubles as the mitigation.
                'mitigation' => self::stringOrNull(data_get($factor, 'mitigation') ?? $description, 2000),
            ];

            if (count($normalized) >= self::MAX_COLLECTION) {
                break;
            }
        }

        return $normalized;
    }

    /**
     * @return list<array{id: string, question: string, category: string, priority: string, status: string, answer: string|null}>
     */
    private static function normalizeQuestions(mixed $questions): array
    {
        if (! is_array($questions)) {
            return [];
        }

        $normalized = [];

        foreach ($questions as $question) {
            if (! is_array($question)) {
                continue;
            }

            $text = self::stringOrNull(data_get($question, 'question'), 1000);

            if ($text === null) {
                continue;
            }

            $normalized[] = [
                'id' => 'q-'.(count($normalized) + 1),
                'question' => $text,
                'category' => self::stringOrDefault(data_get($question, 'category'), 'general', 50),
                'priority' => self::priorityOrDefault(data_get($question, 'priority')),
                'status' => 'pending',
                'answer' => null,
            ];

            if (count($normalized) >= self::MAX_QUESTIONS) {
                break;
            }
        }

        return $normalized;
    }

    /**
     * @return list<array{feature_type: string, match_count: int, estimated_hours: float}>
     */
    private static function normalizeFeatures(mixed $features): array
    {
        if (! is_array($features)) {
            return [];
        }

        $normalized = [];

        foreach ($features as $feature) {
            if (! is_array($feature)) {
                continue;
            }

            $type = self::stringOrNull(data_get($feature, 'feature_type'), 150);

            if ($type === null) {
                continue;
            }

            $rawCount = data_get($feature, 'match_count');

            $normalized[] = [
                'feature_type' => $type,
                'match_count' => is_numeric($rawCount)
                    ? max(0, min(1000, (int) $rawCount))
                    : 0,
                'estimated_hours' => self::clampFloat(
                    data_get($feature, 'estimated_hours'),
                    0.0,
                    10000.0,
                    0.0
                ),
            ];

            if (count($normalized) >= self::MAX_COLLECTION) {
                break;
            }
        }

        return $normalized;
    }

    /**
     * Prefer the service's curated summary; otherwise fall back to the
     * unique detected feature types. Both are labels the service produced.
     *
     * @return list<string>
     */
    private static function normalizeKeywords(mixed $summary, mixed $detected): array
    {
        $keywords = [];

        if (is_array($summary)) {
            foreach ($summary as $keyword) {
                $value = self::stringOrNull($keyword, 150);

                if ($value !== null) {
                    $keywords[] = $value;
                }

                if (count($keywords) >= self::MAX_KEYWORDS) {
                    return $keywords;
                }
            }
        }

        if ($keywords === [] && is_array($detected)) {
            foreach ($detected as $feature) {
                $value = is_array($feature)
                    ? self::stringOrNull(data_get($feature, 'feature_type'), 150)
                    : null;

                if ($value !== null && ! in_array($value, $keywords, true)) {
                    $keywords[] = $value;
                }

                if (count($keywords) >= self::MAX_KEYWORDS) {
                    break;
                }
            }
        }

        return $keywords;
    }

    /**
     * @return list<array{phase: string, estimated_days: float, description: string|null}>
     */
    private static function normalizeMilestones(mixed $milestones): array
    {
        if (! is_array($milestones)) {
            return [];
        }

        $normalized = [];

        foreach ($milestones as $milestone) {
            if (! is_array($milestone)) {
                continue;
            }

            $phase = self::stringOrNull(data_get($milestone, 'phase'), 150);

            if ($phase === null) {
                continue;
            }

            $normalized[] = [
                'phase' => $phase,
                'estimated_days' => self::clampFloat(
                    data_get($milestone, 'estimated_days'),
                    0.0,
                    3650.0,
                    0.0
                ),
                'description' => self::stringOrNull(data_get($milestone, 'description'), 1000),
            ];

            if (count($normalized) >= 30) {
                break;
            }
        }

        return $normalized;
    }

    /**
     * @return array{ml_score: float|null, keyword_score: float|null, weighted_final: float|null}|null
     */
    private static function normalizeBreakdown(mixed $breakdown): ?array
    {
        if (! is_array($breakdown) || $breakdown === []) {
            return null;
        }

        $normalized = [
            'ml_score' => self::nullableFloat(data_get($breakdown, 'ml_score'), 0.0, 5.0),
            'keyword_score' => self::nullableFloat(data_get($breakdown, 'keyword_score'), 0.0, 5.0),
            'weighted_final' => self::nullableFloat(data_get($breakdown, 'weighted_final'), 0.0, 5.0),
        ];

        foreach ($normalized as $value) {
            if ($value !== null) {
                return $normalized;
            }
        }

        return null;
    }

    /**
     * @return array{working_days: int|null, calendar_days: int|null, team_size: int|null}|null
     */
    private static function normalizeTimeline(array $payload): ?array
    {
        $timeline = data_get($payload, 'timeline');

        if (! is_array($timeline)) {
            return null;
        }

        $workingDays = self::nullableInt(data_get($timeline, 'total_working_days'), 0, 3650);
        $calendarDays = self::nullableInt(data_get($timeline, 'total_calendar_days'), 0, 3650);
        $teamSize = self::nullableInt(data_get($timeline, 'recommended_team_size'), 1, 50);

        if ($workingDays === null && $calendarDays === null && $teamSize === null) {
            return null;
        }

        return [
            'working_days' => $workingDays,
            'calendar_days' => $calendarDays,
            'team_size' => $teamSize,
        ];
    }

    /**
     * The service reports confidence on a 0-1 scale; the API contract is
     * 0-100. Anything unrecognised becomes null rather than a fake number.
     */
    private static function normalizeConfidence(mixed $value): ?int
    {
        if (! is_numeric($value)) {
            return null;
        }

        return (int) round(max(0.0, min(1.0, (float) $value)) * 100);
    }

    private static function riskLevelOrDefault(mixed $value): RiskLevel
    {
        if ($value instanceof RiskLevel) {
            return $value;
        }

        if (is_string($value)) {
            return RiskLevel::tryFrom(mb_strtolower(trim($value))) ?? RiskLevel::Low;
        }

        return RiskLevel::Low;
    }

    private static function factorLevelOrDefault(mixed $value): string
    {
        if (! is_string($value)) {
            return 'low';
        }

        $normalized = mb_strtolower(trim($value));

        // The risk_factors table has no "critical" level, so a critical verdict
        // is reported as "high". Anything else unrecognised degrades to "low"
        // rather than inventing severity.
        return match ($normalized) {
            'low', 'medium', 'high' => $normalized,
            'critical' => 'high',
            default => 'low',
        };
    }

    private static function priorityOrDefault(mixed $value): string
    {
        if (! is_string($value)) {
            return 'medium';
        }

        $normalized = mb_strtolower(trim($value));

        return in_array($normalized, ['low', 'medium', 'high', 'critical'], true)
            ? $normalized
            : 'medium';
    }

    /**
     * A partially populated payload is tolerated and defaulted, but a payload
     * with none of the documented sections means the contract has changed or
     * the service returned an error body. Falling back is safer than silently
     * persisting an empty analysis labelled as machine generated.
     *
     * @param  array<string, mixed>  $payload
     */
    private static function guardAgainstUnrecognisedPayload(array $payload): void
    {
        $recognised = [
            'classification' => data_get($payload, 'classification'),
            'complexity' => data_get($payload, 'complexity'),
            'risk' => data_get($payload, 'risk'),
            'timeline' => data_get($payload, 'timeline'),
            'modules' => $payload['modules'] ?? null,
        ];

        foreach ($recognised as $section => $value) {
            if (is_array($value) && $value !== []) {
                return;
            }
        }

        throw new MlServiceException(sprintf(
            'ML service payload contained no recognisable analysis sections (received keys: %s)',
            implode(', ', array_keys($payload)) ?: 'none'
        ));
    }

    private static function stringOrDefault(mixed $value, string $default, int $maxLength): string
    {
        if (! is_string($value)) {
            return $default;
        }

        $trimmed = trim($value);

        if ($trimmed === '') {
            return $default;
        }

        return mb_substr($trimmed, 0, $maxLength);
    }

    private static function stringOrNull(mixed $value, int $maxLength): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $trimmed = trim($value);

        if ($trimmed === '') {
            return null;
        }

        return mb_substr($trimmed, 0, $maxLength);
    }

    private static function clampFloat(mixed $value, float $min, float $max, float $default): float
    {
        if (! is_numeric($value)) {
            return $default;
        }

        return (float) max($min, min($max, (float) $value));
    }

    private static function nullableFloat(mixed $value, float $min, float $max): ?float
    {
        if (! is_numeric($value)) {
            return null;
        }

        return (float) max($min, min($max, (float) $value));
    }

    private static function nullableInt(mixed $value, int $min, int $max): ?int
    {
        if (! is_numeric($value)) {
            return null;
        }

        return (int) max($min, min($max, (int) $value));
    }

    private static function defaultHours(float $complexityScore): float
    {
        return round(4.0 * $complexityScore, 2);
    }
}
