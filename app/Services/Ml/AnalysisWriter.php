<?php

declare(strict_types=1);

namespace App\Services\Ml;

use App\Enums\AnalysisStatus;
use App\Enums\RequirementStatus;
use App\Models\Analysis;
use App\Models\Requirement;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Owns the single write path that turns an ML/heuristic result into a
 * persisted Analysis with its Modules and Risk Factors.
 *
 * Every persistence operation runs inside one transaction so a failure part
 * way through can never leave an Analysis without its child rows.
 */
final class AnalysisWriter
{
    /**
     * Persist a result, replacing any previous analysis for the requirement.
     *
     * The replacement happens inside the same transaction as the insert, so the
     * requirement is never left without an analysis because of a failure, and
     * two competing workers cannot both insert against the unique index.
     */
    public function persist(Requirement $requirement, MlAnalysisResult $result): Analysis
    {
        return DB::transaction(function () use ($requirement, $result): Analysis {
            // Delete first, inside the transaction. Doing this before the
            // estimate would discard the last valid result on a failed
            // re-analysis; doing it here means a crash rolls back to the
            // previous analysis instead.
            $requirement->analysis()->delete();

            $analysis = Analysis::create([
                'requirement_id' => $requirement->id,
                // Denormalised so history can filter and render without a join.
                'project_id' => $requirement->project_id,
                'classification' => $result->classification,
                'complexity_score' => $result->complexityScore,
                'risk_level' => $result->riskLevel,
                'risk_score' => $result->riskScore,
                'estimated_hours' => $result->estimatedHours,
                // Records whether a model was involved, so an estimate can
                // never be misread as a machine prediction.
                'estimation_method' => $result->estimationMethod,
                'summary' => $result->summary,
                // Persisted once at write time; answering questions nudges it.
                'confidence' => $result->confidence,
                'questions' => $result->questions,
                'meta' => $this->meta($result),
                'status' => AnalysisStatus::Completed,
                'progress' => 100,
            ]);

            // When the service supplied no questions, the deterministic
            // defaults are derived from the row just written.
            if ($analysis->questions === null || $analysis->questions === []) {
                $analysis->forceFill(['questions' => $analysis->defaultQuestions()])->save();
            }

            foreach ($result->modules as $module) {
                $analysis->modules()->create([
                    'name' => $module['name'],
                    'description' => $module['description'],
                    'complexity' => $module['complexity'],
                    'estimated_hours' => $module['estimated_hours'],
                ]);
            }

            foreach ($result->riskFactors as $factor) {
                $analysis->riskFactors()->create([
                    'factor' => $factor['factor'],
                    'level' => $factor['level'],
                    'description' => $factor['description'] ?? null,
                    'mitigation' => $factor['mitigation'],
                ]);
            }

            $requirement->forceFill([
                'status' => RequirementStatus::Analyzed,
            ])->save();

            Log::info('Requirement analysis persisted', [
                'requirement_id' => $requirement->id,
                'analysis_id' => $analysis->id,
                'estimation_method' => $result->estimationMethod,
                'module_count' => count($result->modules),
                'risk_factor_count' => count($result->riskFactors),
            ]);

            return $analysis;
        });
    }

    /**
     * The auxiliary ML payload is stored as one JSON column so a schema change
     * per feature is not needed; only what the API contract reads is kept.
     *
     * @return array<string, mixed>|null
     */
    private function meta(MlAnalysisResult $result): ?array
    {
        $meta = [
            'breakdown' => $result->breakdown,
            'features' => $result->features,
            'keywords' => $result->keywords,
            'milestones' => $result->milestones,
            'timeline' => $result->timeline,
        ];

        foreach ($meta as $value) {
            if ($value !== null && $value !== []) {
                return $meta;
            }
        }

        return null;
    }
}
