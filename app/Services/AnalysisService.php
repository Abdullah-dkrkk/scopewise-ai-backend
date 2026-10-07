<?php

declare(strict_types=1);

namespace App\Services;

use App\Enums\AnalysisStatus;
use App\Enums\RequirementStatus;
use App\Http\Resources\AnalysisResource;
use App\Jobs\AnalyzeRequirement;
use App\Models\Analysis;
use App\Models\Requirement;
use App\Support\Pagination;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Log;
use Throwable;

class AnalysisService
{
    public function show(Analysis $analysis): JsonResponse
    {
        $analysis->load('modules', 'riskFactors', 'requirement.project');

        return response()->json([
            'success' => true,
            'data' => new AnalysisResource($analysis),
        ]);
    }

    public function getQuestions(Analysis $analysis): JsonResponse
    {
        $questions = is_array($analysis->questions) && $analysis->questions !== []
            ? array_values($analysis->questions)
            : $analysis->defaultQuestions();

        return response()->json([
            'success' => true,
            'data' => $questions,
        ]);
    }

    public function history(Request $request): JsonResponse
    {
        $user = $request->user();

        $query = Analysis::whereHas('requirement', function ($builder) use ($user): void {
            $builder->whereHas('project', function ($project) use ($user): void {
                $project->where('user_id', $user->id);
            });
        });

        // The ML service labels e-commerce with a hyphen; the canonical value
        // (and the heuristic's) uses an underscore, so accept both spellings.
        $classification = str_replace('-', '_', trim((string) $request->query('classification')));

        if ($classification !== '') {
            $query->where('classification', $classification);
        }

        $riskLevel = (string) $request->query('risk_level');

        if (in_array($riskLevel, ['low', 'medium', 'high', 'critical'], true)) {
            $query->where('risk_level', $riskLevel);
        }

        $projectId = (int) $request->query('project_id');

        if ($projectId > 0) {
            $query->where('project_id', $projectId);
        }

        $dateFrom = $this->parseDate($request->query('date_from'));

        if ($dateFrom !== null) {
            $query->where('created_at', '>=', $dateFrom);
        }

        $dateTo = $this->parseDate($request->query('date_to'));

        if ($dateTo !== null) {
            $query->where('created_at', '<=', $dateTo->endOfDay());
        }

        [$sort, $direction] = Pagination::sort(
            $request,
            'created_at',
            ['created_at', 'complexity_score', 'confidence', 'estimated_hours'],
        );

        $analyses = $query
            ->with('requirement.project')
            ->orderBy($sort, $direction)
            ->orderBy('id', $direction)
            ->paginate(Pagination::perPage($request));

        // List envelope: { success, data, links, meta } (Â§3.2).
        $payload = AnalysisResource::collection($analyses)->response()->getData(true);

        return response()->json(array_merge(['success' => true], $payload));
    }

    private function parseDate(mixed $value): ?Carbon
    {
        if (! is_string($value) || trim($value) === '') {
            return null;
        }

        try {
            return Carbon::parse($value);
        } catch (Throwable) {
            return null;
        }
    }

    public function answerQuestion(Analysis $analysis, string $questionId, string $answer): JsonResponse
    {
        $questions = is_array($analysis->questions) && $analysis->questions !== []
            ? array_values($analysis->questions)
            : $analysis->defaultQuestions();

        $found = false;

        foreach ($questions as $index => $question) {
            if ((string) ($question['id'] ?? '') === $questionId) {
                $questions[$index]['answer'] = $answer;
                $questions[$index]['status'] = 'answered';
                $found = true;
                break;
            }
        }

        if (! $found) {
            // Ids are deterministic (q-1 â€¦ q-n); an unknown id means the
            // caller guessed or the analysis changed underneath them.
            abort(404, 'Question not found');
        }

        // Only a clarification job re-runs; a completed analysis just gets a
        // slightly higher confidence from the extra answers.
        $willRerun = $this->isPendingClarification($analysis)
            && $this->allAnswered($questions);

        $analysis->update([
            'questions' => $questions,
            'confidence' => $this->calculateConfidence($analysis, $questions),
        ]);

        if ($willRerun) {
            $this->rerunWithAnswers($analysis, $questions);
        }

        $fresh = $analysis->fresh();
        $fresh->load('modules', 'riskFactors', 'requirement');

        return response()->json([
            'success' => true,
            'message' => $willRerun ? 'All answers recorded, refining analysis' : 'Answer recorded',
            'data' => new AnalysisResource($fresh),
        ]);
    }

    /**
     * The requirements pointed at a provisional result that needs answers
     * before a final estimate.
     */
    private function isPendingClarification(Analysis $analysis): bool
    {
        $status = (string) ($analysis->status?->value ?? $analysis->status ?? 'completed');
        $meta = is_array($analysis->meta) ? $analysis->meta : [];
        $clarification = is_array($meta['clarification'] ?? null) ? $meta['clarification'] : [];

        return $status === 'needs_clarification'
            || ($status === 'completed' && ! empty($clarification['needed']));
    }

    /**
     * @param  list<array{id: string, question: string, category: string, priority: string, status: string, answer: string|null}>  $questions
     */
    private function allAnswered(array $questions): bool
    {
        foreach ($questions as $question) {
            if ((string) ($question['status'] ?? '') !== 'answered') {
                return false;
            }
        }

        return $questions !== [];
    }

    /**
     * Every answer in, so re-queue with the q&a as context and let the
     * pipeline replace the provisional estimate with a sharper one.
     *
     * @param  list<array{id: string, question: string, category: string, priority: string, status: string, answer: string|null}>  $questions
     */
    private function rerunWithAnswers(Analysis $analysis, array $questions): void
    {
        $requirement = Requirement::find($analysis->requirement_id);

        if (! $requirement instanceof Requirement) {
            return;
        }

        // Answers turn into "Clarifications:" lines appended to the text the
        // pipeline sends on. Empty answers (skipped questions) are dropped.
        $context = array_values(array_filter(array_map(
            static fn (array $q): ?array => ! empty($q['answer'])
                ? ['question' => (string) $q['question'], 'answer' => (string) $q['answer']]
                : null,
            $questions,
        )));

        $requirement->forceFill(['status' => RequirementStatus::Pending->value])->save();

        $analysis->forceFill([
            'status' => AnalysisStatus::Processing->value,
        ])->save();

        try {
            AnalyzeRequirement::dispatch($requirement->id, $context)->afterCommit();
        } catch (Throwable $exception) {
            Log::error('Failed to dispatch refinement analysis', [
                'requirement_id' => $requirement->id,
                'message' => $exception->getMessage(),
            ]);
        }
    }

    private function calculateConfidence(Analysis $analysis, array $questions): int
    {
        $answered = 0;
        foreach ($questions as $q) {
            if (! empty($q['answer']) || ($q['status'] ?? '') === 'answered') {
                $answered++;
            }
        }
        $base = $analysis->confidence ?? 70;
        $gain = min(25, $answered * 5);

        return min(100, max(0, $base + $gain));
    }
}
