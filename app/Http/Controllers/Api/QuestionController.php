<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\Analysis\AnswerQuestionRequest;
use App\Models\Analysis;
use App\Services\AnalysisService;
use Illuminate\Http\JsonResponse;
use OpenApi\Attributes as OA;

class QuestionController extends Controller
{
    public function __construct(
        private readonly AnalysisService $analysisService
    ) {}

    #[OA\Get(
        path: '/api/analysis/{id}/questions',
        summary: 'Get the clarification questions for an analysis',
        security: [['bearerAuth' => []]],
        tags: ['Analysis'],
        parameters: [
            new OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'integer')),
        ],
        responses: [
            new OA\Response(response: 200, description: 'List of questions with stable ids (q-1 … q-n)'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 403, description: 'Not your analysis'),
            new OA\Response(response: 404, description: 'Not found'),
        ]
    )]
    public function index(Analysis $analysis): JsonResponse
    {
        $this->authorize('viewQuestions', $analysis);

        return $this->analysisService->getQuestions($analysis);
    }

    #[OA\Post(
        path: '/api/analysis/{id}/questions/{questionId}',
        summary: 'Answer a clarification question',
        description: 'Recording the answer recomputes the analysis confidence.',
        security: [['bearerAuth' => []]],
        tags: ['Analysis'],
        parameters: [
            new OA\Parameter(name: 'id', in: 'path', required: true, schema: new OA\Schema(type: 'integer')),
            new OA\Parameter(name: 'questionId', in: 'path', required: true, description: 'e.g. q-1', schema: new OA\Schema(type: 'string')),
        ],
        requestBody: new OA\RequestBody(
            required: true,
            content: new OA\JsonContent(
                required: ['answer'],
                properties: [
                    new OA\Property(property: 'answer', type: 'string', example: 'Yes, admins can also expire sessions'),
                ]
            )
        ),
        responses: [
            new OA\Response(response: 200, description: 'Updated analysis'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 403, description: 'Not your analysis'),
            new OA\Response(response: 404, description: 'Not found'),
            new OA\Response(response: 422, description: 'Validation failed'),
        ]
    )]
    public function answer(AnswerQuestionRequest $request, Analysis $analysis, string $questionId): JsonResponse
    {
        $this->authorize('viewQuestions', $analysis);

        return $this->analysisService->answerQuestion($analysis, $questionId, $request->validated('answer'));
    }
}
