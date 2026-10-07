<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Jobs\AnalyzeRequirement;
use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Queue;
use Tests\TestCase;

class RequirementValidationTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Project $project;

    protected function setUp(): void
    {
        parent::setUp();

        $this->user = User::factory()->create();
        $this->project = Project::factory()->for($this->user)->create();
    }

    public function test_creating_a_requirement_without_content_is_rejected(): void
    {
        $this->actingAsWithFullToken($this->user)
            ->postJson('/api/requirements', ['project_id' => $this->project->id])
            ->assertStatus(422)
            ->assertJsonValidationErrors('content');
    }

    public function test_creating_a_requirement_with_null_priority_is_rejected(): void
    {
        // The column is a NOT NULL enum, so a null would break the write.
        $this->actingAsWithFullToken($this->user)
            ->postJson('/api/requirements', [
                'project_id' => $this->project->id,
                'content' => 'Users should be able to upload a profile picture',
                'priority' => null,
            ])
            ->assertStatus(422)
            ->assertJsonValidationErrors('priority');
    }

    public function test_creating_a_requirement_with_an_invalid_priority_is_rejected(): void
    {
        $this->actingAsWithFullToken($this->user)
            ->postJson('/api/requirements', [
                'project_id' => $this->project->id,
                'content' => 'Users should be able to upload a profile picture',
                'priority' => 'urgent',
            ])
            ->assertStatus(422)
            ->assertJsonValidationErrors('priority');
    }

    public function test_updating_a_requirement_with_null_status_is_rejected(): void
    {
        $requirement = Requirement::factory()->for($this->project)->create();

        $this->actingAsWithFullToken($this->user)
            ->putJson("/api/requirements/{$requirement->id}", ['status' => null])
            ->assertStatus(422)
            ->assertJsonValidationErrors('status');
    }

    public function test_updating_the_project_id_is_not_allowed(): void
    {
        Queue::fake();

        $otherProject = Project::factory()->for($this->user)->create();

        $requirement = Requirement::factory()->for($this->project)->create();

        // project_id is excluded from validation, so it is dropped rather than
        // applied. The requirement must stay in its original project.
        $this->actingAsWithFullToken($this->user)
            ->putJson("/api/requirements/{$requirement->id}", [
                'project_id' => $otherProject->id,
                'content' => 'A completely different requirement body here',
            ])
            ->assertOk();

        $this->assertSame(
            $this->project->id,
            $requirement->fresh()->project_id,
            'A requirement must never be re-parented to another project.'
        );
    }

    public function test_updating_content_resets_status_to_pending(): void
    {
        Queue::fake();

        $requirement = Requirement::factory()->for($this->project)->create([
            'status' => 'approved',
        ]);

        $this->actingAsWithFullToken($this->user)
            ->putJson("/api/requirements/{$requirement->id}", [
                'content' => 'Rewritten requirement text that is definitely different',
            ])
            ->assertOk();

        $this->assertSame('pending', $requirement->fresh()->status->value);

        Queue::assertPushed(AnalyzeRequirement::class);
    }

    public function test_updating_only_the_priority_keeps_the_status(): void
    {
        Queue::fake();

        $requirement = Requirement::factory()->for($this->project)->create([
            'status' => 'analyzed',
        ]);

        $this->actingAsWithFullToken($this->user)
            ->putJson("/api/requirements/{$requirement->id}", ['priority' => 'high'])
            ->assertOk();

        $this->assertSame('analyzed', $requirement->fresh()->status->value);

        // No re-analysis is needed when the analysed text did not change.
        Queue::assertNothingPushed();
    }
}
