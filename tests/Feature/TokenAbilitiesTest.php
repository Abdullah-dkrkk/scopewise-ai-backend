<?php

namespace Tests\Feature;

use App\Models\Project;
use App\Models\User;
use App\Support\TokenAbility;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class TokenAbilitiesTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_token_without_the_required_ability_is_rejected(): void
    {
        $user = User::factory()->create();
        $project = Project::factory()->for($user)->create();

        $token = $user->createToken('read-only', [TokenAbility::PROJECTS_READ]);

        // Read is permitted.
        $this->withToken($token->plainTextToken)
            ->getJson("/api/projects/{$project->id}")
            ->assertOk();

        // Write is not covered by the granted abilities.
        $this->withToken($token->plainTextToken)
            ->putJson("/api/projects/{$project->id}", ['name' => 'nope'])
            ->assertForbidden();

        $this->assertSame(
            $project->name,
            $project->fresh()->name,
            'Project name must be unchanged when the ability check rejects the call.'
        );
    }

    public function test_a_requirement_write_token_cannot_read_analyses(): void
    {
        $user = User::factory()->create();

        $this->actingAsWithFullToken($user, [TokenAbility::REQUIREMENTS_WRITE])
            ->getJson('/api/history')
            ->assertForbidden();
    }

    public function test_tokens_issued_by_the_api_carry_every_ability(): void
    {
        $response = $this->postJson('/api/auth/register', [
            'name' => 'Ability Holder',
            'email' => 'abilities@example.com',
            'password' => 'password123',
            'password_confirmation' => 'password123',
        ])->assertCreated();

        $abilities = $response->json('data.abilities');

        $this->assertSame(TokenAbility::ALL, $abilities);

        // The issued token must work against a protected read endpoint.
        $this->withToken($response->json('data.token'))
            ->getJson('/api/history')
            ->assertOk();
    }

    public function test_an_expired_token_is_rejected(): void
    {
        $user = User::factory()->create();
        $token = $user->createToken('expired', TokenAbility::ALL);

        $token->accessToken->forceFill([
            'expires_at' => now()->subMinute(),
        ])->save();

        $this->withToken($token->plainTextToken)
            ->getJson('/api/history')
            ->assertUnauthorized();
    }
}
