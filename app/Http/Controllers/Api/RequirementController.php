<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\Requirement\AnalyzeRequirementRequest;
use App\Http\Requests\Requirement\UpdateRequirementRequest;
use App\Models\Project;
use App\Models\Requirement;
use App\Services\RequirementService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use OpenApi\Attributes as OA;

class RequirementController extends Controller
{
    public function __construct(
        private readonly RequirementService $requirementService
    ) {}

    #[OA\Get(
        path: '/api/projects/{id}/requirements',
        summary: 'List a project\'s requirements',
        security: [['bearerAuth' => []]],
        tags: ['Requirements'],
        parameters: [
            new OA\Parameter(name: 'id', in: 'path', required: true, description: 'Project id', schema: new OA\Schema(type: 'integer')),
            new OA\Parameter(name: 'search', in: 'query', description: 'Match on content', required: false, schema: new OA\Schema(type: 'string')),
            new OA\Parameter(name: 'status', in: 'query', description: 'pending | analyzed | approved | rejected', required: false, schema: new OA\Schema(type: 'string', enum: ['pending', 'analyzed', 'approved', 'rejected'])),
            new OA\Parameter(name: 'page', in: 'query', schema: new OA\Schema(type: 'integer', minimum: 1, default: 1)),
            new OA\Parameter(name: 'per_page', in: 'query', description: '1–100, default 20', schema: new OA\Schema(type: 'integer', minimum: 1, maximum: 100, default: 20)),
        ],
        responses: [
            new OA\Response(response: 200, description: 'Paginated requirement list'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 403, description: 'Not your project'),
            new OA\Response(response: 404, description: 'Not found'),
        ]
    )]
    public function index(Project $project, Request $request): JsonResponse
    {
        $this->authorize('view', $project);

        return $this->requirementService->index($project, $request);
    }

    #[OA\Post(
        path: '/api/requirements',
        summary: 'Create a requirement and queue its analysis',
        description: 'Returns 201 immediately; the analysis runs asynchronously via the queue. Poll GET /api/requirements/{id} until it appears.',
        security: [['bearerAuth' => []]],
        requestBody: new OA\RequestBody(
            required: true,
            content: new OA\JsonContent(
                required: ['project_id', 'content', 'priority'],
                properties: [
                    new OA\Property(property: 'project_id', type: 'integer', example: 1),
                    new OA\Property(property: 'content', type: 'string', minLength: 10, example: 'Users must be able to log in with their email and password'),
                    new OA\Property(property: 'category', type: 'string', nullable: true, example: 'authentication'),
                    new OA\Property(property: 'priority', type: 'string', enum: ['low', 'medium', 'high', 'critical'], example: 'high'),
                ]
            )
        ),
        tags: ['Requirements'],
        responses: [
            new OA\Response(response: 201, description: 'Requirement queued (status: pending, analysis: null)'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 403, description: 'Not your project'),
            new OA\Response(response: 422, description: 'Validation failed'),
        ]
    )]
    public function store(AnalyzeRequirementRequest $request): JsonResponse
    {
        $projectId = (int) $request->validated('project_id');

        $this->authorize('create', [Requirement::class, $projectId]);

        return $this->requirementService->store($request->validated());
    }

    #[OA\Get(
        path: '/api/requirements/{id}',
        summary: 'Get a requirement with its analysis if ready',
        security: [['bearerAuth' => []]],
        tags: ['Requirements'],
        parameters: [
            new OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'integer')),
        ],
        responses: [
            new OA\Response(response: 200, description: 'Requirement (analysis is null while pending)'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 403, description: 'Not your requirement'),
            new OA\Response(response: 404, description: 'Not found'),
        ]
    )]
    public function show(Requirement $requirement): JsonResponse
    {
        $this->authorize('view', $requirement);

        return $this->requirementService->show($requirement);
    }

    #[OA\Put(
        path: '/api/requirements/{id}',
        summary: 'Update a requirement (re-queues analysis when content changes)',
        security: [['bearerAuth' => []]],
        tags: ['Requirements'],
        parameters: [
            new OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'integer')),
        ],
        requestBody: new OA\RequestBody(
            required: true,
            content: new OA\JsonContent(
                properties: [
                    new OA\Property(property: 'content', type: 'string', minLength: 10),
                    new OA\Property(property: 'category', type: 'string', nullable: true),
                    new OA\Property(property: 'priority', type: 'string', enum: ['low', 'medium', 'high', 'critical']),
                ]
            )
        ),
        responses: [
            new OA\Response(response: 200, description: 'Requirement updated'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 403, description: 'Not your requirement'),
            new OA\Response(response: 404, description: 'Not found'),
            new OA\Response(response: 422, description: 'Validation failed'),
        ]
    )]
    public function update(UpdateRequirementRequest $request, Requirement $requirement): JsonResponse
    {
        $this->authorize('update', $requirement);

        return $this->requirementService->update($request->validated(), $requirement);
    }

    /**
     * Queue a fresh analysis for an existing requirement.
     *
     * Useful when a previous run fell back to the heuristic estimator and the
     * ML service has since become reachable.
     */
    #[OA\Post(
        path: '/api/requirements/{id}/analyze',
        summary: 'Re-run analysis for a requirement',
        description: 'Returns 202 and clears the stale analysis so the UI cannot render an outdated estimate next to a pending status.',
        security: [['bearerAuth' => []]],
        tags: ['Requirements'],
        parameters: [
            new OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'integer')),
        ],
        responses: [
            new OA\Response(response: 202, description: 'Analysis queued'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 403, description: 'Not your requirement'),
            new OA\Response(response: 404, description: 'Not found'),
            new OA\Response(response: 429, description: 'Too many analyse requests'),
        ]
    )]
    public function reanalyze(Requirement $requirement): JsonResponse
    {
        $this->authorize('update', $requirement);

        return $this->requirementService->reanalyze($requirement);
    }

    #[OA\Delete(
        path: '/api/requirements/{id}',
        summary: 'Delete a requirement',
        security: [['bearerAuth' => []]],
        tags: ['Requirements'],
        parameters: [
            new OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'integer')),
        ],
        responses: [
            new OA\Response(response: 200, description: 'Requirement deleted'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 403, description: 'Not your requirement'),
            new OA\Response(response: 404, description: 'Not found'),
        ]
    )]
    public function destroy(Requirement $requirement): JsonResponse
    {
        $this->authorize('delete', $requirement);

        return $this->requirementService->destroy($requirement);
    }
}
