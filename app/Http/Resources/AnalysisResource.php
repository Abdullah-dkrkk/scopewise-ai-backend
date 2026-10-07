<?php

declare(strict_types=1);

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;
use Illuminate\Support\Str;

class AnalysisResource extends JsonResource
{
    private const MAX_MISSING_INFO = 10;

    private const REQUIREMENT_TEXT_LIMIT = 200;

    public function toArray(Request $request): array
    {
        $riskLevel = $this->risk_level?->value ?? (string) $this->risk_level;
        $hours = (float) ($this->estimated_hours ?? 0);
        $meta = is_array($this->meta) ? $this->meta : [];
        $timeline = is_array($meta['timeline'] ?? null) ? $meta['timeline'] : [];
        $questions = $this->resolvedQuestions();

        return [
            'id' => $this->id,
            'requirementId' => $this->requirement_id,
            'projectId' => $this->project_id ?? $this->requirement?->project_id,
            'projectName' => $this->requirement?->project?->name,
            'requirementText' => $this->requirement?->content !== null
                ? Str::limit((string) $this->requirement->content, self::REQUIREMENT_TEXT_LIMIT)
                : null,
            'classification' => $this->classification,
            'confidence' => (int) ($this->confidence ?? 0),
            'status' => $this->status?->value ?? $this->status ?? 'completed',
            'progress' => (int) ($this->progress ?? 100),
            'error' => $this->error,
            'needsClarification' => $this->needsClarification(),
            'clarificationReason' => $this->clarificationReason(),
            'estimateBand' => $this->estimateBand($hours, $meta),
            'complexity' => (int) round((float) $this->complexity_score * 20),
            'complexityLevel' => $this->getComplexityLevel((float) $this->complexity_score),
            'complexityBreakdown' => $this->getBreakdown($meta, (float) $this->complexity_score),
            'risk' => $this->getRiskScore($riskLevel),
            'riskLevel' => $riskLevel ?: 'low',
            'riskFactors' => RiskFactorResource::collection($this->whenLoaded('riskFactors')),
            'estimation' => [
                'effort' => $this->formatEffort($hours),
                'cost' => $this->formatCost($hours),
                'timeline' => $this->formatTimeline($hours),
                'hours' => $hours,
                'workingDays' => (int) ($timeline['working_days'] ?? round($hours / 8)),
                'calendarDays' => (int) ($timeline['calendar_days'] ?? round($hours / 6)),
                'recommendedTeamSize' => (int) ($timeline['team_size'] ?? config('estimation.default_team_size', 2)),
                'method' => $this->estimation_method ?? 'heuristic_fallback',
            ],
            'milestones' => $this->getMilestones($meta),
            'modules' => ModuleResource::collection($this->whenLoaded('modules')),
            'features' => $this->getFeatures($meta),
            'keywords' => is_array($meta['keywords'] ?? null) ? array_values($meta['keywords']) : [],
            'missingInfo' => $this->getMissingInfo($questions),
            'questions' => $questions,
            'summary' => $this->summary,
            'createdAt' => $this->created_at?->toISOString(),
            'updatedAt' => $this->updated_at?->toISOString(),
        ];
    }

    /**
     * A vague requirement produces a provisional result; the row is never
     * labelled "completed" until the owner answers the clarifying questions.
     */
    private function needsClarification(): bool
    {
        $status = (string) ($this->status?->value ?? $this->status ?? 'completed');

        if ($status === 'needs_clarification') {
            return true;
        }

        $meta = is_array($this->meta) ? $this->meta : [];
        $clarification = $meta['clarification'] ?? null;

        return is_array($clarification) && ! empty($clarification['needed']);
    }

    private function clarificationReason(): ?string
    {
        $meta = is_array($this->meta) ? $this->meta : [];
        $clarification = $meta['clarification'] ?? null;

        if (is_array($clarification) && ! empty($clarification['reason'])) {
            return (string) $clarification['reason'];
        }

        return $this->needsClarification()
            ? 'This requirement is too vague to estimate precisely yet.'
            : null;
    }

    /**
     * @param  array<string, mixed>  $meta
     * @return array{low: float|null, high: float|null, note: string|null}|null
     */
    private function estimateBand(float $hours, array $meta): ?array
    {
        if (! $this->needsClarification()) {
            return null;
        }

        $clarification = is_array($meta['clarification'] ?? null) ? $meta['clarification'] : [];
        $band = is_array($clarification['estimate_band'] ?? null) ? $clarification['estimate_band'] : [];

        $low = isset($band['low']) ? (float) $band['low'] : $hours;
        $high = isset($band['high']) ? (float) $band['high'] : $hours;

        return [
            'low' => $low,
            'high' => $high,
            'note' => is_array($band) && ! empty($band['note'])
                ? (string) $band['note']
                : 'Provisional range until the clarifying questions are answered.',
        ];
    }

    /**
     * Stored questions when present, otherwise the deterministic defaults, so
     * ids always line up with POST /analysis/{id}/questions/{questionId}.
     *
     * @return list<array{id: string, question: string, category: string, priority: string, status: string, answer: string|null}>
     */
    private function resolvedQuestions(): array
    {
        if (is_array($this->questions) && $this->questions !== []) {
            return array_values($this->questions);
        }

        return $this->defaultQuestions();
    }

    /**
     * Derive the clarification gaps from questions the user has not answered.
     *
     * @param  list<array{id: string, question: string, category: string, priority: string, status: string, answer: string|null}>  $questions
     * @return list<string>
     */
    private function getMissingInfo(array $questions): array
    {
        $missing = [];

        foreach ($questions as $question) {
            $answered = ($question['status'] ?? '') === 'answered' || ! empty($question['answer']);

            if (! $answered && isset($question['question']) && is_string($question['question'])) {
                $missing[] = $question['question'];
            }

            if (count($missing) >= self::MAX_MISSING_INFO) {
                break;
            }
        }

        return $missing;
    }

    /**
     * @param  array<string, mixed>  $meta
     * @return array{mlScore: float|null, keywordScore: float|null, weightedFinal: float|null}
     */
    private function getBreakdown(array $meta, float $score): array
    {
        $breakdown = is_array($meta['breakdown'] ?? null) ? $meta['breakdown'] : [];

        return [
            'mlScore' => isset($breakdown['ml_score']) ? (float) $breakdown['ml_score'] : null,
            'keywordScore' => isset($breakdown['keyword_score']) ? (float) $breakdown['keyword_score'] : null,
            'weightedFinal' => isset($breakdown['weighted_final']) ? (float) $breakdown['weighted_final'] : $score,
        ];
    }

    /**
     * The service reports risk on a 0-10 scale; the contract is 0-100.
     * Without a service score the level buckets are the honest fallback.
     */
    private function getRiskScore(string $level): int
    {
        $score = $this->risk_score;

        if ($score !== null) {
            return (int) round((float) $score * 10);
        }

        $bucket = match ($level) {
            'critical' => 10.0,
            'high' => 7.0,
            'medium' => 4.0,
            'low' => 1.0,
            default => 1.0,
        };

        return (int) round($bucket * 10);
    }

    /**
     * @param  array<string, mixed>  $meta
     * @return list<array{phase: string, estimatedDays: float, description: string|null}>
     */
    private function getMilestones(array $meta): array
    {
        if (! is_array($meta['milestones'] ?? null)) {
            return [];
        }

        return array_map(
            fn (array $milestone): array => [
                'phase' => (string) ($milestone['phase'] ?? ''),
                'estimatedDays' => (float) ($milestone['estimated_days'] ?? 0),
                'description' => $milestone['description'] ?? null,
            ],
            array_values(array_filter($meta['milestones'], 'is_array')),
        );
    }

    /**
     * @param  array<string, mixed>  $meta
     * @return list<array{featureType: string, matchCount: int, estimatedHours: float}>
     */
    private function getFeatures(array $meta): array
    {
        if (! is_array($meta['features'] ?? null)) {
            return [];
        }

        return array_map(
            fn (array $feature): array => [
                'featureType' => (string) ($feature['feature_type'] ?? ''),
                'matchCount' => (int) ($feature['match_count'] ?? 0),
                'estimatedHours' => (float) ($feature['estimated_hours'] ?? 0),
            ],
            array_values(array_filter($meta['features'], 'is_array')),
        );
    }

    private function getComplexityLevel(float $score): string
    {
        if ($score >= 4.0) {
            return 'high';
        }
        if ($score >= 2.5) {
            return 'medium';
        }

        return 'low';
    }

    private function formatEffort(float $hours): string
    {
        $pd = max(1, (int) round($hours / 8));

        return $pd.' PD';
    }

    private function formatCost(float $hours): string
    {
        $rate = (float) config('estimation.hourly_rate', 67.5);

        if ($rate <= 0) {
            $rate = (float) config('estimation.per_diem_rate', 540) / 8;
        }

        return '$'.number_format($hours * max(0.0, $rate), 0);
    }

    private function formatTimeline(float $hours): string
    {
        $days = max(1, (int) round($hours / 16));
        if ($days < 5) {
            return $days.' day'.($days === 1 ? '' : 's');
        }
        $weeks = round($days / 5, 1);

        return $weeks.' week'.($weeks == 1 ? '' : 's');
    }
}
