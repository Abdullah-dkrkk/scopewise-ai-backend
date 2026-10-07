<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AuthRateLimitTest extends TestCase
{
    use RefreshDatabase;

    public function test_login_is_rate_limited_per_account_and_ip(): void
    {
        $user = User::factory()->create([
            'email' => 'ratelimit@example.com',
            'password' => bcrypt('secret123'),
        ]);

        $payload = [
            'email' => $user->email,
            'password' => 'wrong-password',
        ];

        // Hit the limiter repeatedly; with 5 attempts per minute the 6th
        // attempt should be rejected.
        for ($i = 0; $i < 5; $i++) {
            $this->postJson('/api/auth/login', $payload)
                ->assertStatus(401);
        }

        $this->postJson('/api/auth/login', $payload)
            ->assertStatus(429);
    }

    public function test_register_is_rate_limited_by_ip(): void
    {
        // Rate limiter key is solely by IP. Generate distinct emails to avoid
        // database unique collisions.
        for ($i = 0; $i < 3; $i++) {
            $this->postJson('/api/auth/register', [
                'name' => 'Test User',
                'email' => "test{$i}@example.com",
                'password' => 'password123',
                'password_confirmation' => 'password123',
            ])->assertStatus(201);
        }

        $this->postJson('/api/auth/register', [
            'name' => 'Test User',
            'email' => 'test-blocked@example.com',
            'password' => 'password123',
            'password_confirmation' => 'password123',
        ])->assertStatus(429);
    }
}
