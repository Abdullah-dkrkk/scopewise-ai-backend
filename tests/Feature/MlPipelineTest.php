<?php

namespace Tests\Feature;

use App\Enums\RiskLevel;
use App\Jobs\AnalyzeRequirement;
use App\Models\Analysis;
use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;
use App\Services\Ml\AnalysisPipeline;
use App\Services\Ml\HeuristicEstimator;
use App\Services\Ml\MlAnalysisResult;
use App\Services\Ml\MlClient;
use Illuminate\Database\QueryException;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Client\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Facades\Schema;
use Tests\TestCase;

class MlPipelineTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_successful_ml_call_is_persisted_with_ml_attribution(): void
    {
        Http::fake([
            '*/analyze' => Http::response($this->mlPayload(), 200),
        ]);

        $requirement = Requirement::factory()->create([
            'content' => 'Add real-time websocket chat with presence indicators',
            'status' => 'pending',
        ]);

        app(AnalysisPipeline::class)->run((string) $requirement->id);

        $analysis = $requirement->fresh()->analysis;

        $this->assertNotNull($analysis);
        $this->assertSame('ml_service', $analysis->estimation_method);
        $this->assertSame('realtime', $analysis->classification);
        $this->assertEqualsWithDelta(4.25, $analysis->complexity_score, 0.01);
        $this->assertSame(RiskLevel::Critical, $analysis->risk_level);
        $this->assertEqualsWithDelta(64.0, $analysis->estimated_hours, 0.01);

        // Modules and risk factors written in the same transaction.
        $this->assertCount(2, $analysis->modules);
        $this->assertCount(2, $analysis->riskFactors);

        $this->assertSame('analyzed', $requirement->fresh()->status->value);
    }

    public function test_an_unreachable_ml_service_falls_back_to_the_heuristic(): void
    {
        Http::fake([
            '*' => Http::response(null, 503),
        ]);

        $requirement = Requirement::factory()->create([
            'content' => 'Build a secure payment integration with encryption and audit logging',
            'status' => 'pending',
        ]);

        $result = app(AnalysisPipeline::class)->run((string) $requirement->id);

        $analysis = $requirement->fresh()->analysis;

        $this->assertTrue($result['fell_back']);
        $this->assertNotNull($analysis);

        // Attribution must be honest: a heuristic is never labelled as ML.
        $this->assertSame('heuristic_fallback', $analysis->estimation_method);
        $this->assertNotSame('ml_service', $analysis->estimation_method);

        // The user still receives a usable analysis.
        $this->assertSame('analyzed', $requirement->fresh()->status->value);
        $this->assertNotEmpty($analysis->modules);
        $this->assertNotEmpty($analysis->riskFactors);

        Http::assertSentCount(3); // initial attempt + 2 retries on 5xx
    }

    public function test_a_malformed_ml_payload_is_rejected_and_falls_back(): void
    {
        Http::fake([
            '*/analyze' => Http::response([
                // Missing classification, complexity and risk entirely.
                'unexpected' => 'shape',
            ], 200),
        ]);

        $requirement = Requirement::factory()->create([
            'content' => 'The system shall process incoming records and store them for later retrieval',
            'status' => 'pending',
        ]);

        $result = app(AnalysisPipeline::class)->run((string) $requirement->id);

        $this->assertTrue($result['fell_back']);

        $analysis = $requirement->fresh()->analysis;

        $this->assertSame('heuristic_fallback', $analysis->estimation_method);
        // The unrecognised payload was discarded rather than persisted as-is.
        $this->assertSame('general', $analysis->classification);
        $this->assertNotNull($analysis->complexity_score);
        $this->assertInstanceOf(RiskLevel::class, $analysis->risk_level);
    }

    public function test_out_of_range_values_from_the_service_are_clamped(): void
    {
        $result = MlAnalysisResult::fromPayload([
            'classification' => ['category' => 'api_integration'],
            'complexity' => ['score' => 99.0],          // beyond the 1-5 range
            'risk' => ['overall_level' => 'catastrophic'], // not a valid enum
            'timeline' => ['total_estimated_hours' => -50.0],
            'modules' => [
                ['name' => 'API', 'complexity' => 500.0, 'estimated_hours' => -1.0],
            ],
            'risk' => [
                'overall_level' => 'high',
                'factors' => [
                    ['factor' => 'Weird', 'level' => 'critical'], // table allows low/medium/high
                ],
            ],
        ]);

        $this->assertEqualsWithDelta(5.0, $result->complexityScore, 0.001);
        $this->assertSame(RiskLevel::High, $result->riskLevel);
        $this->assertEqualsWithDelta(0.0, $result->estimatedHours, 0.001);
        $this->assertSame('high', $result->riskFactors[0]['level']);
        $this->assertEqualsWithDelta(5.0, $result->modules[0]['complexity'], 0.001);
    }

    public function test_duplicate_modules_from_the_service_are_collapsed(): void
    {
        $result = MlAnalysisResult::fromPayload([
            'modules' => [
                ['name' => 'Core Logic', 'complexity' => 2.0, 'estimated_hours' => 10.0],
                ['name' => 'core logic', 'complexity' => 3.0, 'estimated_hours' => 20.0],
                ['name' => 'Core Logic', 'complexity' => 4.0, 'estimated_hours' => 30.0],
            ],
        ]);

        $this->assertCount(1, $result->modules);
    }

    public function test_module_hours_from_the_heuristic_sum_to_the_headline_estimate(): void
    {
        $estimate = app(HeuristicEstimator::class)->estimate(
            'Implement OAuth login with password reset, two factor authentication and session management'
        );

        $sum = array_sum(array_column($estimate['modules'], 'estimated_hours'));

        $this->assertEqualsWithDelta($estimate['estimated_hours'], $sum, 0.01);
    }

    public function test_heuristic_complexity_stays_within_bounds(): void
    {
        $estimator = app(HeuristicEstimator::class);

        $short = $estimator->estimate('Add a login page');
        $long = $estimator->estimate(str_repeat('integration security payment realtime websocket ', 200));

        $this->assertGreaterThanOrEqual(1.0, $short['complexity_score']);
        $this->assertLessThanOrEqual(5.0, $short['complexity_score']);

        $this->assertLessThanOrEqual(5.0, $long['complexity_score']);
        $this->assertGreaterThan($short['complexity_score'], $long['complexity_score']);
    }

    public function test_fallback_can_be_disabled_to_surface_the_failure(): void
    {
        config()->set('services.ml.fallback_to_heuristic', false);

        Http::fake(['*' => Http::response(null, 503)]);

        $requirement = Requirement::factory()->create([
            'content' => 'Some requirement text that is long enough to validate',
            'status' => 'pending',
        ]);

        $this->expectException(\Throwable::class);

        app(AnalysisPipeline::class)->run((string) $requirement->id);
    }

    public function test_a_client_error_is_not_retried_but_still_falls_back(): void
    {
        Http::fake([
            '*' => Http::response(['error' => 'text too long'], 422),
        ]);

        $requirement = Requirement::factory()->create([
            'content' => 'Add a search feature to the project listing page with filters',
            'status' => 'pending',
        ]);

        $result = app(AnalysisPipeline::class)->run((string) $requirement->id);

        $this->assertTrue($result['fell_back']);
        $this->assertSame('heuristic_fallback', $requirement->fresh()->analysis->estimation_method);

        // A deterministic 4xx must not be hammered with retries.
        Http::assertSentCount(1);
    }

    public function test_a_partial_failure_leaves_no_orphan_analysis_rows(): void
    {
        Http::fake(['*/analyze' => Http::response($this->mlPayload(), 200)]);

        $requirement = Requirement::factory()->create(['status' => 'pending']);

        // Force the child insert to blow up mid-transaction.
        Schema::drop('modules');

        try {
            app(AnalysisPipeline::class)->run((string) $requirement->id);
        } catch (\Throwable) {
            // Expected.
        }

        // The Analysis row must have been rolled back with its children.
        $this->assertDatabaseCount('analyses', 0);
    }

    public function test_the_database_rejects_two_analyses_for_one_requirement(): void
    {
        Http::fake(['*/analyze' => Http::response($this->mlPayload(), 200)]);

        $requirement = Requirement::factory()->create(['status' => 'pending']);

        app(AnalysisPipeline::class)->run((string) $requirement->id);

        // The unique index is the real guard against a concurrent double-run;
        // application-level locking alone would not be enough.
        $this->expectException(QueryException::class);

        Analysis::create([
            'requirement_id' => $requirement->id,
            'classification' => 'duplicate',
            'complexity_score' => 2.0,
            'risk_level' => RiskLevel::Low,
            'estimated_hours' => 8.0,
            'estimation_method' => 'ml_service',
        ]);
    }

    public function test_reanalysis_replaces_the_previous_verdict(): void
    {
        Http::fake(['*/analyze' => Http::response($this->mlPayload(), 200)]);

        $requirement = Requirement::factory()->create(['status' => 'pending']);
        $pipeline = app(AnalysisPipeline::class);

        $pipeline->run((string) $requirement->id);
        $pipeline->run((string) $requirement->id);

        // A requirement has exactly one analysis; re-running must not duplicate.
        $this->assertDatabaseCount('analyses', 1);
        $this->assertCount(2, $requirement->fresh()->analysis->modules);
    }

    public function test_a_failed_reanalysis_keeps_the_previous_result(): void
    {
        // A single stateful stub: the first call succeeds, later ones fail, so
        // the service "goes down" between the two runs.
        $calls = 0;

        Http::fake(function () use (&$calls) {
            $calls++;

            return $calls === 1
                ? Http::response($this->mlPayload(), 200)
                : Http::response(null, 503);
        });

        $requirement = Requirement::factory()->create(['status' => 'pending']);
        $pipeline = app(AnalysisPipeline::class);

        $pipeline->run((string) $requirement->id);

        $firstAnalysisId = $requirement->fresh()->analysis->id;

        // The service is now down and fallback is disabled, so the run throws.
        // The requirement must keep the verdict it already had.
        config()->set('services.ml.fallback_to_heuristic', false);

        try {
            $pipeline->run((string) $requirement->id);
            $this->fail('Expected the pipeline to surface the ML failure.');
        } catch (\Throwable) {
            // Expected.
        }

        $this->assertDatabaseCount('analyses', 1);
        $this->assertSame($firstAnalysisId, $requirement->fresh()->analysis->id);
        $this->assertSame('analyzed', $requirement->fresh()->status->value);
    }

    public function test_the_service_token_is_sent_on_every_request(): void
    {
        Http::fake(['*/analyze' => Http::response($this->mlPayload(), 200)]);

        (new MlClient(5, 'http://ml.test:5000', 'shared-secret-value'))
            ->analyze('Build a login page for the existing application');

        Http::assertSent(fn (Request $request): bool => $request->hasHeader('X-Service-Token', 'shared-secret-value'));
    }

    public function test_no_token_header_is_sent_when_unconfigured(): void
    {
        Http::fake(['*/analyze' => Http::response($this->mlPayload(), 200)]);

        (new MlClient(5, 'http://ml.test:5000'))->analyze('Build a login page for the app');

        Http::assertSent(fn (Request $request): bool => ! $request->hasHeader('X-Service-Token'));
    }

    public function test_creating_a_requirement_dispatches_the_analysis_job(): void
    {
        Queue::fake();

        $user = User::factory()->create();
        $project = Project::factory()->for($user)->create();

        $this->actingAsWithFullToken($user)
            ->postJson('/api/requirements', [
                'project_id' => $project->id,
                'content' => 'The system should send email notifications to users',
                'priority' => 'medium',
            ])
            ->assertCreated();

        Queue::assertPushed(AnalyzeRequirement::class, function ($job): bool {
            return $job->requirementId > 0;
        });
    }

    public function test_reanalyze_queues_a_fresh_analysis_and_resets_status(): void
    {
        Queue::fake();

        $user = User::factory()->create();
        $project = Project::factory()->for($user)->create();

        $requirement = Requirement::factory()->for($project)->create([
            'status' => 'analyzed',
        ]);

        Analysis::create([
            'requirement_id' => $requirement->id,
            'classification' => 'general',
            'complexity_score' => 1.5,
            'risk_level' => RiskLevel::Low,
            'estimated_hours' => 6.0,
            'estimation_method' => 'heuristic_fallback',
        ]);

        $response = $this->actingAsWithFullToken($user)
            ->postJson("/api/requirements/{$requirement->id}/analyze");

        $response->assertStatus(202);
        $response->assertJsonPath('message', 'Analysis queued successfully');

        // The previous verdict is discarded so the UI shows a pending state.
        $this->assertSame(0, $requirement->analysis()->count());
        $this->assertSame('pending', $requirement->fresh()->status->value);

        Queue::assertPushed(AnalyzeRequirement::class);
    }

    public function test_reanalyze_is_tenant_scoped(): void
    {
        Queue::fake();

        $owner = User::factory()->create();
        $intruder = User::factory()->create();

        $requirement = Requirement::factory()
            ->for(Project::factory()->for($owner))
            ->create();

        $this->actingAsWithFullToken($intruder)
            ->postJson("/api/requirements/{$requirement->id}/analyze")
            ->assertForbidden();

        Queue::assertNothingPushed();
    }

    public function test_updating_requirement_content_requeues_the_analysis(): void
    {
        Queue::fake();

        $user = User::factory()->create();
        $project = Project::factory()->for($user)->create();

        $requirement = Requirement::factory()->for($project)->create([
            'content' => 'Original requirement content for the project',
        ]);

        $this->actingAsWithFullToken($user)
            ->putJson("/api/requirements/{$requirement->id}", [
                'content' => 'Completely rewritten requirement with different scope',
            ])
            ->assertOk();

        Queue::assertPushed(AnalyzeRequirement::class);
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
                'alternatives' => ['api_integration'],
            ],
            'complexity' => [
                'score' => 4.25,
                'level' => 'high',
                'breakdown' => ['ml_score' => 4.1, 'keyword_score' => 4.4],
            ],
            'features' => [
                'detected' => [],
                'total_count' => 3,
                'summary' => ['Real-Time Features'],
            ],
            'risk' => [
                'overall_level' => 'critical',
                'score' => 7.5,
                'factors' => [
                    [
                        'factor' => 'High Technical Complexity',
                        'level' => 'high',
                        'mitigation' => 'Break down into smaller tasks.',
                    ],
                    [
                        'factor' => 'External Dependencies',
                        'level' => 'medium',
                        'mitigation' => 'Verify third party API availability.',
                    ],
                ],
            ],
            'questions' => [],
            'timeline' => [
                'total_estimated_hours' => 64.0,
                'recommended_timeline_weeks' => 2.0,
            ],
            'modules' => [
                [
                    'name' => 'Realtime Transport',
                    'description' => 'Websocket layer',
                    'complexity' => 4.5,
                    'estimated_hours' => 40.0,
                ],
                [
                    'name' => 'Presence Service',
                    'description' => 'User presence tracking',
                    'complexity' => 3.2,
                    'estimated_hours' => 24.0,
                ],
            ],
            'summary' => 'A realtime requirement with significant risk.',
        ];
    }
}
