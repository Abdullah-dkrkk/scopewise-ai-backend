<?php

namespace Tests\Feature;

use App\Models\Analysis;
use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class OwnershipAndIdorTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_user_cannot_view_another_users_project(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $project = Project::factory()->for($owner)->create();

        $this->actingAsWithFullToken($other)
            ->getJson("/api/projects/{$project->id}")
            ->assertForbidden();
    }

    public function test_a_user_cannot_update_another_users_project(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $project = Project::factory()->for($owner)->create();

        $this->actingAsWithFullToken($other)
            ->putJson("/api/projects/{$project->id}", ['name' => 'hacked'])
            ->assertForbidden();
    }

    public function test_a_user_cannot_delete_another_users_project(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $project = Project::factory()->for($owner)->create();

        $this->actingAsWithFullToken($other)
            ->deleteJson("/api/projects/{$project->id}")
            ->assertForbidden();
    }

    public function test_owner_can_perform_full_project_lifecycle(): void
    {
        $owner = User::factory()->create();

        $created = $this->actingAsWithFullToken($owner)
            ->postJson('/api/projects', ['name' => 'My Project'])
            ->assertCreated()
            ->json('data');

        $this->actingAsWithFullToken($owner)
            ->getJson("/api/projects/{$created['id']}")
            ->assertOk();

        $this->actingAsWithFullToken($owner)
            ->putJson("/api/projects/{$created['id']}", ['name' => 'Renamed'])
            ->assertOk();

        $this->actingAsWithFullToken($owner)
            ->deleteJson("/api/projects/{$created['id']}")
            ->assertOk();
    }

    public function test_cross_tenant_requirement_creation_is_forbidden(): void
    {
        $owner = User::factory()->create();
        $attacker = User::factory()->create();
        $victimProject = Project::factory()->for($owner)->create();

        $this->actingAsWithFullToken($attacker)
            ->postJson('/api/requirements', [
                'project_id' => $victimProject->id,
                'content' => 'This is a long enough requirement description to pass validation',
                'priority' => 'medium',
            ])
            ->assertForbidden();

        $this->assertDatabaseCount('requirements', 0);
    }

    public function test_user_cannot_view_another_users_requirement(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $project = Project::factory()->for($owner)->create();
        $requirement = Requirement::factory()->for($project)->create();

        $this->actingAsWithFullToken($other)
            ->getJson("/api/requirements/{$requirement->id}")
            ->assertForbidden();
    }

    public function test_user_cannot_update_another_users_requirement(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $project = Project::factory()->for($owner)->create();
        $requirement = Requirement::factory()->for($project)->create();

        $this->actingAsWithFullToken($other)
            ->putJson("/api/requirements/{$requirement->id}", [
                'content' => 'Attacker supplied replacement content',
            ])
            ->assertForbidden();

        $this->assertSame(
            $requirement->content,
            $requirement->fresh()->content,
            'Requirement content must be untouched after a rejected update.'
        );
    }

    public function test_user_cannot_delete_another_users_requirement(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $project = Project::factory()->for($owner)->create();
        $requirement = Requirement::factory()->for($project)->create();

        $this->actingAsWithFullToken($other)
            ->deleteJson("/api/requirements/{$requirement->id}")
            ->assertForbidden();

        $this->assertDatabaseHas('requirements', ['id' => $requirement->id]);
    }

    public function test_requirement_cannot_be_reparented_to_another_users_project(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $projectA = Project::factory()->for($owner)->create();
        $projectB = Project::factory()->for($other)->create();
        $requirement = Requirement::factory()->for($projectA)->create();

        // `project_id` is not part of UpdateRequirementRequest, so Laravel
        // silently drops the unvalidated key and the request succeeds while
        // leaving the requirement on its original project. The guarantee that
        // matters is the unchanged project_id, asserted below.
        $this->actingAsWithFullToken($owner)
            ->putJson("/api/requirements/{$requirement->id}", [
                'project_id' => $projectB->id,
                'content' => 'Attempting to move this requirement across tenants',
            ])
            ->assertOk();

        $this->assertSame(
            $projectA->id,
            $requirement->fresh()->project_id,
            'Requirement must remain attached to its original project.'
        );
    }

    public function test_a_user_cannot_read_another_users_analysis(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();
        $project = Project::factory()->for($owner)->create();
        $requirement = Requirement::factory()->for($project)->create();
        $analysis = Analysis::factory()->for($requirement)->create();

        $this->actingAsWithFullToken($other)
            ->getJson("/api/analysis/{$analysis->id}")
            ->assertForbidden();

        $this->actingAsWithFullToken($other)
            ->getJson("/api/analysis/{$analysis->id}/questions")
            ->assertForbidden();
    }

    public function test_the_owner_can_read_their_analysis_and_questions(): void
    {
        $owner = User::factory()->create();
        $project = Project::factory()->for($owner)->create();
        $requirement = Requirement::factory()->for($project)->create();
        $analysis = Analysis::factory()->for($requirement)->create();

        $this->actingAsWithFullToken($owner)
            ->getJson("/api/analysis/{$analysis->id}")
            ->assertOk();

        $this->actingAsWithFullToken($owner)
            ->getJson("/api/analysis/{$analysis->id}/questions")
            ->assertOk();
    }

    public function test_history_only_exposes_the_callers_own_analyses(): void
    {
        $owner = User::factory()->create();
        $other = User::factory()->create();

        $ownerProject = Project::factory()->for($owner)->create();
        $otherProject = Project::factory()->for($other)->create();

        $ownerAnalysis = Analysis::factory()
            ->for(Requirement::factory()->for($ownerProject))
            ->create();

        Analysis::factory()
            ->for(Requirement::factory()->for($otherProject))
            ->create();

        $response = $this->actingAsWithFullToken($owner)
            ->getJson('/api/history')
            ->assertOk()
            ->json();

        $ids = array_column($response['data'], 'id');

        $this->assertContains($ownerAnalysis->id, $ids);
        $this->assertCount(1, $ids);
    }

    public function test_guest_is_rejected(): void
    {
        $project = Project::factory()->create();

        $this->getJson("/api/projects/{$project->id}")->assertUnauthorized();
    }

    public function test_role_cannot_be_escalated_through_registration(): void
    {
        $this->postJson('/api/auth/register', [
            'name' => 'Escalator',
            'email' => 'escalator@example.com',
            'password' => 'password123',
            'password_confirmation' => 'password123',
            'role' => 'admin',
        ])->assertCreated();

        $this->assertDatabaseHas('users', [
            'email' => 'escalator@example.com',
            'role' => 'user',
        ]);
    }
}
