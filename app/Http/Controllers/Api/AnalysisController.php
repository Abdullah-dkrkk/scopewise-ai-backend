<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Analysis;
use App\Services\AnalysisService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use OpenApi\Attributes as OA;

class AnalysisController extends Controller
{
    public function __construct(
        private readonly AnalysisService $analysisService
    ) {}

    #[OA\Get(
        path: '/api/analysis/{id}',
        summary: 'Get the full analysis for a requirement',
        security: [['bearerAuth' => []]],
        tags: ['Analysis'],
        parameters: [
            new OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'integer')),
        ],
        responses: [
            new OA\Response(response: 200, description: 'Analysis with modules, risk factors, breakdown and estimation'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 403, description: 'Not your analysis'),
            new OA\Response(response: 404, description: 'Not found'),
        ]
    )]
    public function show(Analysis $analysis): JsonResponse
    {
        $this->authorize('view', $analysis);

        return $this->analysisService->show($analysis);
    }

    #[OA\Get(
        path: '/api/history',
        summary: 'Analyse the current user\'s analysis history',
        description: 'Filterable by classification, risk_level, project_id and creation date. Paginated (§7).',
        security: [['bearerAuth' => []]],
        tags: ['Analysis'],
        parameters: [
            new OA\Parameter(name: 'classification', in: 'query', description: 'e.g. authentication, e_commerce', required: false, schema: new OA\Schema(type: 'string')),
            new OA\Parameter(name: 'risk_level', in: 'query', required: false, schema: new OA\Schema(type: 'string', enum: ['low', 'medium', 'high', 'critical'])),
            new OA\Parameter(name: 'project_id', in: 'query', required: false, schema: new OA\Schema(type: 'integer')),
            new OA\Parameter(name: 'date_from', in: 'query', description: 'Inclusive start date (Y-m-d)', required: false, schema: new OA\Schema(type: 'string', format: 'date')),
            new OA\Parameter(name: 'date_to', in: 'query', description: 'Inclusive end date (Y-m-d)', required: false, schema: new OA\Schema(type: 'string', format: 'date')),
            new OA\Parameter(name: 'sort', in: 'query', description: 'created_at (default) | complexity_score | confidence | estimated_hours', required: false, schema: new OA\Schema(type: 'string')),
            new OA\Parameter(name: 'direction', in: 'query', required: false, schema: new OA\Schema(type: 'string', enum: ['asc', 'desc'])),
            new OA\Parameter(name: 'page', in: 'query', schema: new OA\Schema(type: 'integer', minimum: 1, default: 1)),
            new OA\Parameter(name: 'per_page', in: 'query', description: '1–100, default 20', schema: new OA\Schema(type: 'integer', minimum: 1, maximum: 100, default: 20)),
        ],
        responses: [
            new OA\Response(response: 200, description: 'Paginated analysis history'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
        ]
    )]
    public function history(Request $request): JsonResponse
    {
        return $this->analysisService->history($request);
    }
}
