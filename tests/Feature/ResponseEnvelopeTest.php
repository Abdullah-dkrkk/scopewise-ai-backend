<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\User;
use App\Support\TokenAbility;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ResponseEnvelopeTest extends TestCase
{
    use RefreshDatabase;

    public function test_list_endpoints_use_the_pagination_envelope(): void
    {
        $user = User::factory()->create();

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects')
            ->assertOk()
            ->assertJsonStructure([
                'success',
                'data',
                'meta' => ['current_page', 'per_page', 'total', 'last_page'],
                'links' => ['first', 'last', 'prev', 'next'],
            ])
            ->assertJsonPath('success', true)
            ->assertJsonPath('meta.current_page', 1)
            ->assertJsonPath('meta.per_page', 20);
    }

    public function test_unauthenticated_requests_get_the_error_envelope(): void
    {
        $this->getJson('/api/projects')
            ->assertUnauthorized()
            ->assertJson([
                'success' => false,
                'message' => 'Unauthenticated.',
            ]);
    }

    public function test_missing_resources_get_a_404_error_envelope(): void
    {
        $user = User::factory()->create();

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects/999999')
            ->assertNotFound()
            ->assertJson([
                'success' => false,
                'message' => 'Resource not found.',
            ]);
    }

    public function test_api_responses_carry_security_headers(): void
    {
        $user = User::factory()->create();

        $this->actingAsWithFullToken($user)
            ->getJson('/api/projects')
            ->assertOk()
            ->assertHeader('X-Content-Type-Options', 'nosniff')
            ->assertHeader('X-Frame-Options', 'DENY')
            ->assertHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
    }

    public function test_ability_denials_get_a_403_error_envelope(): void
    {
        $user = User::factory()->create();

        $this->actingAsWithFullToken($user, [TokenAbility::PROJECTS_READ])
            ->postJson('/api/projects', ['name' => 'Nope'])
            ->assertForbidden()
            ->assertJsonPath('success', false)
            ->assertJsonStructure(['success', 'message']);
    }

    public function test_validation_failures_keep_per_field_errors(): void
    {
        $user = User::factory()->create();

        $this->actingAsWithFullToken($user)
            ->postJson('/api/projects', [])
            ->assertUnprocessable()
            ->assertJson([
                'success' => false,
                'message' => 'Please correct the highlighted fields.',
            ])
            ->assertJsonStructure(['errors' => ['name']]);
    }

    public function test_rate_limits_return_the_envelope_and_retry_after_header(): void
    {
        $user = User::factory()->create([
            'email' => 'throttle-envelope@example.com',
            'password' => bcrypt('secret123'),
        ]);

        $payload = ['email' => $user->email, 'password' => 'wrong-password'];

        for ($i = 0; $i < 5; $i++) {
            $this->postJson('/api/auth/login', $payload)->assertStatus(401);
        }

        $this->postJson('/api/auth/login', $payload)
            ->assertStatus(429)
            ->assertHeader('Retry-After')
            ->assertJsonPath('success', false);
    }
}
