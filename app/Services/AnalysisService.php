<?php

declare(strict_types=1);

namespace App\Services;

use App\Http\Resources\AnalysisResource;
use App\Models\Analysis;
use App\Support\Pagination;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;

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
        } catch (\Throwable) {
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

        $analysis->update([
            'questions' => $questions,
            'confidence' => $this->calculateConfidence($analysis, $questions),
        ]);

        $fresh = $analysis->fresh();
        $fresh->load('modules', 'riskFactors', 'requirement');

        return response()->json([
            'success' => true,
            'message' => 'Answer recorded',
            'data' => new AnalysisResource($fresh),
        ]);
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
