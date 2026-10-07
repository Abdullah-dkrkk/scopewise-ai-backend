<?php

declare(strict_types=1);

namespace App\Services\Ml;

use App\Models\Requirement;
use Illuminate\Support\Facades\Log;
use Throwable;

/**
 * Orchestrates a single requirement analysis.
 *
 * Strategy: ask the ML service, and if anything goes wrong — unreachable,
 * timeout, malformed payload, unexpected exception — fall back to a
 * deterministic heuristic so the user always gets an analysis. The chosen
 * source is recorded on the analysis row so an estimate is never mistaken for
 * a model prediction.
 */
final class AnalysisPipeline
{
    public function __construct(
        private readonly MlClient $client,
        private readonly HeuristicEstimator $heuristic,
        private readonly AnalysisWriter $writer,
    ) {}

    /**
     * Analyze a requirement and persist the result.
     *
     * @param  list<array{question: string, answer: string}>  $context
     * @return array{analysis_id: int, source: string, fell_back: bool}
     */
    public function run(string $requirementId, array $context = []): array
    {
        $requirement = Requirement::find($requirementId);

        if (! $requirement instanceof Requirement) {
            Log::warning('Analysis skipped: requirement no longer exists', [
                'requirement_id' => $requirementId,
            ]);

            return [
                'analysis_id' => 0,
                'source' => 'skipped',
                'fell_back' => false,
            ];
        }

        // The previous analysis is replaced inside the writer's transaction, not
        // here. Deleting before the estimate would leave a requirement with no
        // analysis at all if the ML call failed and fallback was disabled.
        $result = $this->estimate($requirement->content, $context);

        $analysis = $this->writer->persist($requirement, $result);

        return [
            'analysis_id' => $analysis->id,
            'source' => $result->estimationMethod,
            'fell_back' => ! $result->isMachineGenerated(),
        ];
    }

    /**
     * Produce an estimate, preferring the ML service.
     *
     * @param  list<array{question: string, answer: string}>  $context
     */
    public function estimate(string $text, array $context = []): MlAnalysisResult
    {
        $fallbackEnabled = (bool) config('services.ml.fallback_to_heuristic', true);
        $prompt = $this->withContext($text, $context);

        try {
            $payload = $this->client->analyze($prompt);

            return MlAnalysisResult::fromPayload($payload);
        } catch (Throwable $exception) {
            Log::error('ML service unavailable, using heuristic fallback', [
                'message' => $exception->getMessage(),
                'exception' => $exception::class,
            ]);

            if (! $fallbackEnabled) {
                throw $exception;
            }

            return $this->heuristicResult($prompt);
        }
    }

    /**
     * Answers to the clarifying questions are folded into the text so both the
     * model and the heuristic can weigh them.
     *
     * @param  list<array{question: string, answer: string}>  $context
     */
    private function withContext(string $text, array $context): string
    {
        if ($context === []) {
            return $text;
        }

        $lines = array_map(
            static fn (array $item): string => vsprintf(
                '- %s: %s',
                [(string) $item['question'], (string) $item['answer']]
            ),
            $context,
        );

        return $text."\n\nClarifications:\n".implode("\n", $lines);
    }

    /**
     * Build a fallback result from the local heuristic.
     */
    private function heuristicResult(string $text): MlAnalysisResult
    {
        $estimate = $this->heuristic->estimate($text);

        return MlAnalysisResult::heuristic(
            classification: $estimate['classification'],
            complexityScore: $estimate['complexity_score'],
            riskLevel: $estimate['risk_level'],
            estimatedHours: $estimate['estimated_hours'],
            modules: $estimate['modules'],
            riskFactors: $estimate['risk_factors'],
        );
    }
}
