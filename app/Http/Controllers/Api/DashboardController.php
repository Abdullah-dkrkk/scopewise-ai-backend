<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Services\DashboardService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use OpenApi\Attributes as OA;

class DashboardController extends Controller
{
    public function __construct(
        private readonly DashboardService $dashboardService
    ) {}

    #[OA\Get(
        path: '/api/dashboard/stats',
        summary: 'Aggregate statistics for the current user',
        security: [['bearerAuth' => []]],
        tags: ['Dashboard'],
        responses: [
            new OA\Response(response: 200, description: 'Project and analysis totals, status counts'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
        ]
    )]
    public function stats(Request $request): JsonResponse
    {
        return $this->dashboardService->stats($request->user());
    }

    #[OA\Get(
        path: '/api/dashboard/activity',
        summary: 'Recent activity for the current user',
        security: [['bearerAuth' => []]],
        tags: ['Dashboard'],
        responses: [
            new OA\Response(response: 200, description: 'Recent projects and analysed requirements'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
        ]
    )]
    public function activity(Request $request): JsonResponse
    {
        return $this->dashboardService->activity($request->user());
    }
}
