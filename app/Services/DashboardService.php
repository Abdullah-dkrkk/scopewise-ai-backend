<?php

declare(strict_types=1);

namespace App\Services;

use App\Enums\RiskLevel;
use App\Models\Analysis;
use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

class DashboardService
{
    public function stats(User $user): JsonResponse
    {
        $projectsQuery = Project::where('user_id', $user->id);
        $projectsCount = (clone $projectsQuery)->count();

        $projectStatuses = (clone $projectsQuery)
            ->select('status', DB::raw('count(*) as total'))
            ->groupBy('status')
            ->pluck('total', 'status')
            ->toArray();

        $requirementsCount = Requirement::whereHas('project', function ($q) use ($user) {
            $q->where('user_id', $user->id);
        })->count();

        $analysesQuery = Analysis::whereHas('requirement.project', function ($q) use ($user) {
            $q->where('user_id', $user->id);
        });

        $analysesCount = (clone $analysesQuery)->count();

        $analysesThisWeek = (clone $analysesQuery)
            ->where('created_at', '>=', Carbon::now()->startOfWeek())
            ->count();

        $avgConfidence = (int) ((clone $analysesQuery)
            ->whereNotNull('confidence')
            ->avg('confidence') ?? 0);

        $highRiskCount = (clone $analysesQuery)
            ->whereIn('risk_level', [RiskLevel::High, RiskLevel::Critical])
            ->count();

        return response()->json([
            'success' => true,
            'data' => [
                'projects' => $projectsCount,
                'requirements' => $requirementsCount,
                'analyses' => $analysesCount,
                'analysesThisWeek' => $analysesThisWeek,
                'avgConfidence' => $avgConfidence,
                'highRiskCount' => $highRiskCount,
                'projectStatuses' => [
                    'active' => $projectStatuses['active'] ?? 0,
                    'review' => $projectStatuses['review'] ?? 0,
                    'draft' => $projectStatuses['draft'] ?? 0,
                    'completed' => $projectStatuses['completed'] ?? 0,
                    'archived' => $projectStatuses['archived'] ?? 0,
                ],
            ],
        ]);
    }

    public function activity(User $user): JsonResponse
    {
        $activities = Analysis::whereHas('requirement.project', function ($q) use ($user) {
            $q->where('user_id', $user->id);
        })
            ->with(['requirement.project'])
            ->latest()
            ->limit(20)
            ->get()
            ->map(function (Analysis $analysis) {
                return [
                    'id' => $analysis->id,
                    'text' => 'New requirement analyzed',
                    'project' => $analysis->requirement?->project?->name,
                    'type' => 'analysis',
                    'at' => $analysis->created_at?->toISOString(),
                ];
            });

        return response()->json([
            'success' => true,
            'data' => $activities,
        ]);
    }
}
