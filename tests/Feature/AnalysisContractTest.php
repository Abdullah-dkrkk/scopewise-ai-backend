<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Analysis;
use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;
use App\Services\Ml\AnalysisPipeline;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class AnalysisContractTest extends TestCase
{
    use RefreshDatabase;

    public function test_ml_results_are_persisted_with_every_field_the_contract_needs(): void
    {
        Http::fake(['*/analyze' => Http::response($this->mlPayload(), 200)]);

        $requirement = $this->requirementForNewOwner();

        app(AnalysisPipeline::class)->run((string) $requirement->id);

        $analysis = $requirement->fresh()->analysis;

        $this->assertNotNull($analysis);
        $this->assertSame($requirement->project_id, $analysis->project_id);
        $this->assertSame(91, $analysis->confidence);
        $this->assertEqualsWithDelta(7.5, (float) $analysis->risk_score, 0.01);
        $this->assertSame('A realtime requirement with significant risk.', $analysis->summary);
        $this->assertSame('completed', $analysis->status->value);
        $this->assertSame(100, $analysis->progress);

        $questions = $analysis->questions;
        $this->assertCount(2, $questions);
        $this->assertSame('q-1', $questions[0]['id']);
        $this->assertSame('pending', $questions[0]['status']);
        $this->assertNull($questions[0]['answer']);
        $this->assertSame('high', $questions[0]['priority']);

        $meta = $analysis->meta;
        $this->assertSame(['Real-Time Features'], $meta['keywords']);
        $this->assertSame('Planning & Requirements', $meta['milestones'][0]['phase']);
        $this->assertSame(16, $meta['timeline']['working_days']);
        $this->assertSame(2, $meta['timeline']['team_size']);
        $this->assertEqualsWithDelta(4.1, (float) $meta['breakdown']['ml_score'], 0.01);
        $this->assertSame('Real-Time Features', $meta['features'][0]['feature_type']);
        $this->assertSame(2, $meta['features'][0]['match_count']);

        $this->assertSame(
            'A third party service dependency.',
            $analysis->riskFactors()->first()->description
        );
    }

    public function test_a_heuristic_fallback_still_returns_a_complete_contract_object(): void
    {
        Http::fake(['*' => Http::response(null, 503)]);

        $requirement = $this->requirementForNewOwner();

        app(AnalysisPipeline::class)->run((string) $requirement->id);

        $analysis = $requirement->fresh()->analysis;

        $this->assertNotNull($analysis);

        // No model ran, so no confidence is invented.
        $this->assertNull($analysis->confidence);
        $this->assertSame('heuristic_fallback', $analysis->estimation_method);
        $this->assertNull($analysis->risk_score);
        $this->assertSame('completed', $analysis->status->value);

        $questions = $analysis->questions;
        $this->assertCount(4, $questions);
        $this->assertSame('q-1', $questions[0]['id']);
        $this->assertSame('q-4', $questions[3]['id']);

        $meta = $analysis->meta;
        $this->assertNotEmpty($meta['keywords']);
        $this->assertNull($meta['breakdown']['ml_score']);
        $this->assertNotNull($meta['breakdown']['keyword_score']);
    }

    public function test_get_analysis_returns_the_canonical_object_shape(): void
    {
        Http::fake(['*/analyze' => Http::response($this->mlPayload(), 200)]);

        [$owner, $requirement] = $this->requirementForOwner();
        app(AnalysisPipeline::class)->run((string) $requirement->id);

        $analysis = $requirement->fresh()->analysis;

        $this->actingAsWithFullToken($owner)
            ->getJson("/api/analysis/{$analysis->id}")
            ->assertOk()
            ->assertJsonStructure([
                'success',
                'data' => [
                    'id',
                    'requirementId',
                    'projectId',
                    'projectName',
                    'requirementText',
                    'classification',
                    'confidence',
                    'status',
                    'progress',
                    'complexity',
                    'complexityLevel',
                    'complexityBreakdown' => ['mlScore', 'keywordScore', 'weightedFinal'],
                    'risk',
                    'riskLevel',
                    'riskFactors',
                    'estimation' => [
                        'effort',
                        'cost',
                        'timeline',
                        'hours',
                        'workingDays',
                        'calendarDays',
                        'recommendedTeamSize',
                        'method',
                    ],
                    'milestones',
                    'modules',
                    'features',
                    'keywords',
                    'missingInfo',
                    'questions',
                    'summary',
                    'createdAt',
                    'updatedAt',
                ],
            ])
            ->assertJsonPath('data.confidence', 91)
            ->assertJsonPath('data.status', 'completed')
            ->assertJsonPath('data.riskLevel', 'critical')
            ->assertJsonPath('data.risk', 75)
            ->assertJsonPath('data.estimation.workingDays', 16)
            ->assertJsonPath('data.estimation.recommendedTeamSize', 2)
            ->assertJsonPath('data.milestones.0.phase', 'Planning & Requirements')
            ->assertJsonPath('data.features.0.featureType', 'Real-Time Features')
            ->assertJsonPath('data.questions.0.id', 'q-1')
            ->assertJsonPath('data.questions.0.status', 'pending')
            ->assertJsonPath('data.questions.0.answer', null)
            ->assertJsonPath('data.missingInfo.0', 'Which transport guarantees are required?')
            ->assertJsonPath('data.summary', 'A realtime requirement with significant risk.');
    }

    public function test_question_ids_returned_by_the_api_can_be_answered(): void
    {
        Http::fake(['*/analyze' => Http::response($this->mlPayload(), 200)]);

        [$owner, $requirement] = $this->requirementForOwner();
        app(AnalysisPipeline::class)->run((string) $requirement->id);

        $analysis = $requirement->fresh()->analysis;

        $questions = $this->actingAsWithFullToken($owner)
            ->getJson("/api/analysis/{$analysis->id}/questions")
            ->assertOk()
            ->json('data');

        $this->assertSame('q-1', $questions[0]['id']);

        $this->actingAsWithFullToken($owner)
            ->postJson("/api/analysis/{$analysis->id}/questions/q-1", [
                'answer' => 'WebSocket with at-least-once delivery is enough.',
            ])
            ->assertOk()
            ->assertJsonPath('message', 'Answer recorded')
            ->assertJsonPath('data.questions.0.status', 'answered')
            ->assertJsonPath('data.questions.0.answer', 'WebSocket with at-least-once delivery is enough.')
            ->assertJsonPath('data.missingInfo.0', 'How often should presence be refreshed?')
            ->assertJsonPath('data.confidence', 96);

        $this->actingAsWithFullToken($owner)
            ->postJson("/api/analysis/{$analysis->id}/questions/q-99", [
                'answer' => 'An id that does not exist.',
            ])
            ->assertNotFound();
    }

    public function test_a_legacy_analysis_without_stored_questions_gets_answerable_defaults(): void
    {
        $analysis = $this->legacyAnalysis();

        $questions = $this->actingAsWithFullToken($analysis->owner)
            ->getJson("/api/analysis/{$analysis->model->id}/questions")
            ->assertOk()
            ->json('data');

        $this->assertCount(4, $questions);
        $this->assertSame('q-1', $questions[0]['id']);
        $this->assertSame('q-4', $questions[3]['id']);
        $this->assertSame('pending', $questions[0]['status']);

        $this->actingAsWithFullToken($analysis->owner)
            ->postJson("/api/analysis/{$analysis->model->id}/questions/q-3", [
                'answer' => 'Mitigate by splitting delivery into phases.',
            ])
            ->assertOk()
            ->assertJsonPath('data.questions.2.status', 'answered')
            ->assertJsonPath('data.questions.3.status', 'pending');

        $this->actingAsWithFullToken($analysis->owner)
            ->postJson("/api/analysis/{$analysis->model->id}/questions/q-404", [
                'answer' => 'This id was never issued.',
            ])
            ->assertNotFound();
    }

    public function test_answering_with_an_empty_answer_is_rejected(): void
    {
        $analysis = $this->legacyAnalysis();

        $this->actingAsWithFullToken($analysis->owner)
            ->postJson("/api/analysis/{$analysis->model->id}/questions/q-1", [
                'answer' => '',
            ])
            ->assertJsonValidationErrors('answer');
    }

    private function requirementForNewOwner(): Requirement
    {
        [, $requirement] = $this->requirementForOwner();

        return $requirement;
    }

    /**
     * @return array{0: User, 1: Requirement}
     */
    private function requirementForOwner(): array
    {
        $owner = User::factory()->create();
        $project = Project::factory()->for($owner)->create();

        $requirement = Requirement::factory()->for($project)->create([
            'content' => 'Add real-time websocket chat with presence indicators',
            'status' => 'pending',
        ]);

        return [$owner, $requirement];
    }

    /**
     * An analysis row the way it existed before stored questions, as a stand-in
     * for rows written by an older deployment.
     *
     * @return object{owner: User, model: Analysis}
     */
    private function legacyAnalysis(): object
    {
        [$owner, $requirement] = $this->requirementForOwner();

        $requirement->forceFill(['status' => 'analyzed'])->save();

        $analysis = Analysis::create([
            'requirement_id' => $requirement->id,
            'project_id' => $requirement->project_id,
            'classification' => 'general',
            'complexity_score' => 2.0,
            'risk_level' => 'medium',
            'estimated_hours' => 8.0,
            'estimation_method' => 'heuristic_fallback',
            'questions' => null,
            'confidence' => 70,
        ]);

        return (object) ['owner' => $owner, 'model' => $analysis];
    }

    /**
     * @return array<string, mixed>
     */
    private function mlPayload(): array
    {
        return [
            'classification' => [
                'category' => 'realtime',
                'confidence' => 0.91,
            ],
            'complexity' => [
                'score' => 4.25,
                'level' => 'high',
                'breakdown' => [
                    'ml_score' => 4.1,
                    'keyword_score' => 4.4,
                    'weighted_final' => 4.25,
                ],
            ],
            'features' => [
                'detected' => [
                    [
                        'feature_type' => 'Real-Time Features',
                        'matches' => ['websocket', 'presence'],
                        'match_count' => 2,
                        'estimated_hours' => 20.0,
                    ],
                ],
                'total_count' => 1,
                'summary' => ['Real-Time Features'],
            ],
            'risk' => [
                'overall_level' => 'critical',
                'score' => 7.5,
                'factors' => [
                    [
                        'factor' => 'External Dependencies',
                        'level' => 'medium',
                        'description' => 'A third party service dependency.',
                        'mitigation' => 'Verify third party API availability.',
                    ],
                ],
            ],
            'questions' => [
                [
                    'question' => 'Which transport guarantees are required?',
                    'category' => 'realtime',
                    'priority' => 'high',
                ],
                [
                    'question' => 'How often should presence be refreshed?',
                    'category' => 'realtime',
                    'priority' => 'medium',
                ],
            ],
            'timeline' => [
                'total_estimated_hours' => 64.0,
                'total_working_days' => 16,
                'total_calendar_days' => 22,
                'recommended_team_size' => 2,
                'milestones' => [
                    [
                        'phase' => 'Planning & Requirements',
                        'estimated_days' => 3,
                        'description' => 'Align on transport and delivery guarantees.',
                    ],
                ],
            ],
            'modules' => [
                [
                    'name' => 'Realtime Transport',
                    'description' => 'Websocket layer',
                    'complexity' => 4.5,
                    'estimated_hours' => 64.0,
                ],
            ],
            'summary' => 'A realtime requirement with significant risk.',
        ];
    }
}
