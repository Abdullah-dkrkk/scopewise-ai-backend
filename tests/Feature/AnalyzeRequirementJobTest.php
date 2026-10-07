<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Enums\RiskLevel;
use App\Jobs\AnalyzeRequirement;
use App\Models\Analysis;
use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;
use App\Services\Ml\AnalysisPipeline;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Queue;
use RuntimeException;
use Tests\TestCase;

class AnalyzeRequirementJobTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_persists_an_analysis_and_clears_pending_status(): void
    {
        Http::fake(['*/analyze' => Http::response($this->mlPayload(), 200)]);

        $requirement = $this->requirementInPendingState();

        $job = new AnalyzeRequirement($requirement->id);

        $this->assertSame((string) $requirement->id, $job->uniqueId());
        $this->assertSame('analysis', $job->queue);

        $job->handle(app(AnalysisPipeline::class));

        $analysis = $requirement->fresh()->analysis;

        $this->assertNotNull($analysis);
        $this->assertSame('ml_service', $analysis->estimation_method);
        $this->assertSame('analyzed', $requirement->fresh()->status->value);
    }

    public function test_it_does_nothing_when_the_requirement_was_deleted(): void
    {
        Http::fake();

        $result = app(AnalysisPipeline::class)->run('999999');

        $this->assertSame('skipped', $result['source']);
        $this->assertSame(0, $result['analysis_id']);

        Http::assertNothingSent();
    }

    public function test_duplicate_dispatches_for_one_requirement_collapse(): void
    {
        Queue::fake();

        $requirement = $this->requirementInPendingState();

        AnalyzeRequirement::dispatch($requirement->id);
        AnalyzeRequirement::dispatch($requirement->id);

        // ShouldBeUnique means the queue holds one job per requirement, so a
        // double click cannot queue two competing analyses.
        Queue::assertPushed(AnalyzeRequirement::class, 1);
    }

    public function test_failed_marks_the_requirement_back_to_pending(): void
    {
        Log::spy();

        $requirement = $this->requirementInPendingState();

        Analysis::create([
            'requirement_id' => $requirement->id,
            'classification' => 'stale',
            'complexity_score' => 3.0,
            'risk_level' => RiskLevel::Medium,
            'estimated_hours' => 12.0,
            'estimation_method' => 'heuristic_fallback',
        ]);

        $requirement->forceFill(['status' => 'analyzed'])->save();

        $job = new AnalyzeRequirement($requirement->id);
        $job->failed(new RuntimeException('database is on fire'));

        $requirement->refresh();

        // A partial analysis is removed and the requirement is visibly
        // incomplete rather than silently left as analyzed.
        $this->assertNull($requirement->analysis);
        $this->assertSame('pending', $requirement->status->value);
    }

    public function test_failed_tolerates_a_deleted_requirement(): void
    {
        $job = new AnalyzeRequirement(999999);

        // Must not throw: a requirement deleted mid-flight is not an error.
        $job->failed(new RuntimeException('gone'));

        $this->assertTrue(true);
    }

    public function test_the_job_retries_are_bounded(): void
    {
        $job = new AnalyzeRequirement(1);

        $this->assertSame(3, $job->tries);
        $this->assertSame([10, 45], $job->backoff);
        $this->assertGreaterThan(30, $job->timeout);
    }

    public function test_queue_outage_does_not_fail_the_user_write(): void
    {
        // Point the queue at a driver that does not exist so dispatch throws,
        // simulating a queue outage.
        config()->set('queue.default', 'driver-that-does-not-exist');

        $user = User::factory()->create();
        $project = Project::factory()->for($user)->create();

        $this->actingAsWithFullToken($user)
            ->postJson('/api/requirements', [
                'project_id' => $project->id,
                'content' => 'Users should be able to download their invoice as a PDF',
            ])
            ->assertCreated();

        $this->assertDatabaseHas('requirements', [
            'project_id' => $project->id,
            'status' => 'pending',
        ]);
    }

    private function requirementInPendingState(): Requirement
    {
        return Requirement::factory()
            ->for(Project::factory()->for(User::factory()))
            ->create([
                'status' => 'pending',
                'content' => 'Users can log in and reset their password via email',
            ]);
    }

    /**
     * @return array<string, mixed>
     */
    private function mlPayload(): array
    {
        return [
            'classification' => ['category' => 'authentication'],
            'complexity' => ['score' => 3.2, 'level' => 'medium'],
            'risk' => [
                'overall_level' => 'medium',
                'factors' => [
                    ['factor' => 'Access Control', 'level' => 'high', 'mitigation' => 'Security review'],
                ],
            ],
            'timeline' => ['total_estimated_hours' => 24.0],
            'modules' => [
                ['name' => 'Auth Service', 'complexity' => 3.2, 'estimated_hours' => 24.0],
            ],
        ];
    }
}
