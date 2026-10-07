<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Auth\Notifications\ResetPassword;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Notification;
use Tests\TestCase;

class PasswordResetTest extends TestCase
{
    use RefreshDatabase;

    public function test_forgot_password_always_reports_success_to_prevent_enumeration(): void
    {
        Notification::fake();

        $this->postJson('/api/auth/forgot-password', [
            'email' => 'nobody@example.com',
        ])->assertOk()->assertJson([
            'success' => true,
            'message' => 'If an account exists for that email, a reset link has been sent.',
        ]);

        $this->postJson('/api/auth/forgot-password', [
            'email' => 'invalid-email',
        ])->assertJsonValidationErrors('email');
    }

    public function test_the_full_reset_loop_works(): void
    {
        Notification::fake();

        $user = User::factory()->create([
            'email' => 'reset-me@example.com',
            'password' => 'original-password',
        ]);

        $this->postJson('/api/auth/forgot-password', [
            'email' => $user->email,
        ])->assertOk();

        $token = null;
        Notification::assertSentTo($user, ResetPassword::class, function (ResetPassword $notification) use (&$token): bool {
            $token = $notification->token;

            return true;
        });

        $this->assertNotNull($token);

        // The link validates before the form is filled in.
        $this->getJson("/api/auth/reset/{$token}")
            ->assertOk()
            ->assertJsonPath('success', true)
            ->assertJsonPath('data.valid', true)
            ->assertJsonPath('data.email', $user->email);

        // The emailed link carries ?email= for a direct lookup.
        $this->getJson("/api/auth/reset/{$token}?email=".urlencode($user->email))
            ->assertOk()
            ->assertJsonPath('data.valid', true);

        // A token from one account does not validate against another email.
        $otherEmail = User::factory()->create()->email;
        $this->getJson("/api/auth/reset/{$token}?email=".urlencode($otherEmail))
            ->assertNotFound();

        $this->postJson('/api/auth/reset', [
            'token' => $token,
            'email' => $user->email,
            'password' => 'brand-new-password',
            'password_confirmation' => 'brand-new-password',
        ])->assertOk()->assertJson([
            'success' => true,
            'message' => 'Password has been reset. You can now sign in.',
        ]);

        // The old password no longer works, the new one does.
        $this->postJson('/api/auth/login', [
            'email' => $user->email,
            'password' => 'original-password',
        ])->assertUnauthorized();

        $this->postJson('/api/auth/login', [
            'email' => $user->email,
            'password' => 'brand-new-password',
        ])->assertOk();

        // The token is single use.
        $this->getJson("/api/auth/reset/{$token}")->assertNotFound();
    }

    public function test_an_unknown_or_tampered_token_is_rejected_early(): void
    {
        $this->getJson('/api/auth/reset/not-a-real-token')
            ->assertNotFound()
            ->assertJson([
                'success' => false,
                'message' => 'This password reset link is invalid or has expired.',
            ]);
    }

    public function test_reset_with_a_bad_token_returns_422_with_errors(): void
    {
        Notification::fake();

        $user = User::factory()->create([
            'email' => 'bad-token@example.com',
            'password' => 'original-password',
        ]);

        $this->postJson('/api/auth/forgot-password', ['email' => $user->email])->assertOk();

        $this->postJson('/api/auth/reset', [
            'token' => 'tampered-token',
            'email' => $user->email,
            'password' => 'brand-new-password',
            'password_confirmation' => 'brand-new-password',
        ])->assertUnprocessable()
            ->assertJsonPath('success', false)
            ->assertJsonStructure(['errors' => ['token']]);

        // Password untouched.
        $this->postJson('/api/auth/login', [
            'email' => $user->email,
            'password' => 'original-password',
        ])->assertOk();
    }

    public function test_reset_validation_requires_all_fields(): void
    {
        $this->postJson('/api/auth/reset', [])
            ->assertUnprocessable()
            ->assertJsonStructure(['errors' => ['token', 'email', 'password']]);
    }

    public function test_reset_links_point_at_the_spa_instead_of_a_missing_route(): void
    {
        $user = User::factory()->create();

        // The stock notification resolves a route named `password.reset`,
        // which does not exist here; the configured callback must take over.
        $callback = ResetPassword::$createUrlCallback;
        $url = $callback($user, 'plain-token');

        $this->assertSame(
            config('app.frontend_url').'/reset-password?token=plain-token&email='.urlencode($user->email),
            $url
        );
    }
}
