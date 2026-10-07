<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Analysis;
use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Str;
use Tests\TestCase;

class QueryFiltersTest extends TestCase
{
    use RefreshDatabase;

    private function makeProject(User $user, array $attributes = []): Project
    {
        return Project::factory()->for($user)->create($attributes);
    }

    public function test_project_list_filters_by_search_status_and_sort(): void
    {
        $user = User::factory()->create();
        $this->makeProject($user, ['name' => 'Alpha Portal', 'status' => 'active']);
        $this->makeProject($user, ['name' => 'Beta Portal', 'status' => 'completed']);
        $this->makeProject($user, ['name' => 'Gamma Other', 'status' => 'active']);

        // Another user's project matching the search must never leak.
        $this->makeProject(User::factory()->create(), ['name' => 'Alpha Secret']);

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects?search=Alpha')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.name', 'Alpha Portal')
            ->assertJsonPath('meta.total', 1);

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects?status=completed')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.name', 'Beta Portal');

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects?sort=name&direction=asc')
            ->assertOk()
            ->assertJsonPath('data.0.name', 'Alpha Portal')
            ->assertJsonPath('data.1.name', 'Beta Portal')
            ->assertJsonPath('data.2.name', 'Gamma Other');

        // Unknown sort columns fall back to the default.
        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects?sort=password&direction=asc')
            ->assertOk()
            ->assertJsonPath('meta.per_page', 20);
    }

    public function test_per_page_is_clamped_between_1_and_the_configured_maximum(): void
    {
        $user = User::factory()->create();
        $this->makeProject($user);

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects?per_page=500')
            ->assertOk()
            ->assertJsonPath('meta.per_page', 100);

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects?per_page=0')
            ->assertOk()
            ->assertJsonPath('meta.per_page', 1);

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects?per_page=abc')
            ->assertOk()
            ->assertJsonPath('meta.per_page', 20);
    }

    public function test_project_list_paginates_with_links_and_meta(): void
    {
        $user = User::factory()->create();

        foreach (range(1, 15) as $i) {
            $this->makeProject($user, ['name' => 'Project '.$i]);
        }

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects?per_page=10&page=2')
            ->assertOk()
            ->assertJsonCount(5, 'data')
            ->assertJsonPath('meta.current_page', 2)
            ->assertJsonPath('meta.last_page', 2)
            ->assertJsonPath('meta.per_page', 10)
            ->assertJsonPath('meta.total', 15)
            ->assertJsonStructure(['links' => ['first', 'last', 'prev', 'next']]);
    }

    public function test_requirement_list_filters_by_status_and_search(): void
    {
        $user = User::factory()->create();
        $project = $this->makeProject($user);

        Requirement::factory()->for($project)->create([
            'content' => 'Users must be able to reset passwords',
            'status' => 'pending',
        ]);
        Requirement::factory()->for($project)->create([
            'content' => 'Admin dashboard with charts',
            'status' => 'analyzed',
        ]);

        $this->actingAsWithFullToken($user)
            ->getJson("/api/projects/{$project->id}/requirements?status=analyzed")
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.content', 'Admin dashboard with charts');

        $this->actingAsWithFullToken($user)
            ->getJson("/api/projects/{$project->id}/requirements?search=passwords")
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.status', 'pending');

        // Invalid status values are ignored rather than erroring.
        $this->actingAsWithFullToken($user)
            ->getJson("/api/projects/{$project->id}/requirements?status=nonsense")
            ->assertOk()
            ->assertJsonCount(2, 'data');
    }

    public function test_history_filters_by_classification_risk_project_and_date(): void
    {
        $user = User::factory()->create();
        $project = $this->makeProject($user);
        $otherProject = $this->makeProject($user, ['name' => 'Other']);

        $requirement = Requirement::factory()->for($project)->create([
            'content' => str_repeat('Requirement text ', 30),
        ]);

        $analysis = Analysis::create([
            'requirement_id' => $requirement->id,
            'project_id' => $project->id,
            'classification' => 'e_commerce',
            'complexity_score' => 7.5,
            'risk_level' => 'high',
            'estimated_hours' => 40.0,
            'confidence' => 85,
            'status' => 'completed',
        ]);

        $otherRequirement = Requirement::factory()->for($otherProject)->create();

        Analysis::create([
            'requirement_id' => $otherRequirement->id,
            'project_id' => $otherProject->id,
            'classification' => 'authentication',
            'complexity_score' => 3.0,
            'risk_level' => 'low',
            'estimated_hours' => 8.0,
            'confidence' => 60,
            'status' => 'completed',
        ]);

        $token = $this->actingAsWithFullToken($user);

        $token->getJson('/api/history?classification=e-commerce')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.classification', 'e_commerce');

        $token->getJson('/api/history?risk_level=low')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.classification', 'authentication');

        $token->getJson("/api/history?project_id={$project->id}")
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.id', $analysis->id);

        $token->getJson('/api/history?date_from='.now()->addDay()->toDateString())
            ->assertOk()
            ->assertJsonCount(0, 'data');

        $token->getJson('/api/history?date_from='.now()->subDay()->toDateString())
            ->assertOk()
            ->assertJsonCount(2, 'data');

        $token->getJson('/api/history?date_to='.now()->subDay()->toDateString())
            ->assertOk()
            ->assertJsonCount(0, 'data');

        // Invalid dates are ignored instead of failing the request.
        $token->getJson('/api/history?date_from=not-a-date')
            ->assertOk()
            ->assertJsonCount(2, 'data');

        // Mixed-classification leak guard: both analyses belong to $user;
        // another user must see nothing.
        $this->actingAsWithFullToken(User::factory()->create())
            ->getJson('/api/history')
            ->assertOk()
            ->assertJsonCount(0, 'data');
    }

    public function test_history_items_include_truncated_requirement_text(): void
    {
        $user = User::factory()->create();
        $project = $this->makeProject($user);

        $longContent = str_repeat('abcdefghij', 30); // 300 chars
        $requirement = Requirement::factory()->for($project)->create([
            'content' => $longContent,
        ]);

        Analysis::create([
            'requirement_id' => $requirement->id,
            'project_id' => $project->id,
            'classification' => 'realtime',
            'complexity_score' => 5.0,
            'risk_level' => 'medium',
            'estimated_hours' => 20.0,
            'confidence' => 70,
            'status' => 'completed',
        ]);

        $this->actingAsWithFullToken($user)
            ->getJson('/api/history')
            ->assertOk()
            ->assertJsonPath('data.0.requirementText', Str::limit($longContent, 200));
    }
}
