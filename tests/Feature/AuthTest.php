<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AuthTest extends TestCase
{
    use RefreshDatabase;

    public function test_a_visitor_can_register(): void
    {
        $response = $this->postJson('/api/auth/register', [
            'name' => 'Test User',
            'email' => 'test@example.com',
            'password' => 'password123',
            'password_confirmation' => 'password123',
        ])->assertCreated();

        $this->assertNotEmpty($response->json('data.token'));

        $this->assertDatabaseHas('users', [
            'email' => 'test@example.com',
            'role' => 'user',
        ]);
    }

    public function test_registration_rejects_a_duplicate_email(): void
    {
        User::factory()->create(['email' => 'taken@example.com']);

        $this->postJson('/api/auth/register', [
            'name' => 'Duplicate',
            'email' => 'taken@example.com',
            'password' => 'password123',
            'password_confirmation' => 'password123',
        ])->assertStatus(422)
            ->assertJsonValidationErrors('email');
    }

    public function test_registration_requires_password_confirmation(): void
    {
        $this->postJson('/api/auth/register', [
            'name' => 'No Confirm',
            'email' => 'noconfirm@example.com',
            'password' => 'password123',
            'password_confirmation' => 'different123',
        ])->assertStatus(422)
            ->assertJsonValidationErrors('password');
    }

    public function test_a_user_can_log_in_with_valid_credentials(): void
    {
        $user = User::factory()->create([
            'email' => 'login@example.com',
            'password' => bcrypt('password123'),
        ]);

        $response = $this->postJson('/api/auth/login', [
            'email' => 'login@example.com',
            'password' => 'password123',
        ])->assertOk();

        $this->assertNotEmpty($response->json('data.token'));
        $this->assertSame($user->id, $response->json('data.user.id'));
    }

    public function test_login_fails_with_an_invalid_password(): void
    {
        User::factory()->create([
            'email' => 'login@example.com',
            'password' => bcrypt('password123'),
        ]);

        $this->postJson('/api/auth/login', [
            'email' => 'login@example.com',
            'password' => 'wrong-password',
        ])->assertUnauthorized()
            ->assertJson(['success' => false, 'message' => 'Invalid credentials']);
    }

    public function test_login_response_does_not_leak_user_enumeration(): void
    {
        User::factory()->create([
            'email' => 'exists@example.com',
            'password' => bcrypt('password123'),
        ]);

        $unknownUser = $this->postJson('/api/auth/login', [
            'email' => 'nobody@example.com',
            'password' => 'wrong-password',
        ]);

        $wrongPassword = $this->postJson('/api/auth/login', [
            'email' => 'exists@example.com',
            'password' => 'wrong-password',
        ]);

        // Identical status and message: an attacker cannot tell registered
        // addresses apart from unregistered ones.
        $this->assertSame($unknownUser->getStatusCode(), $wrongPassword->getStatusCode());
        $this->assertSame(
            $unknownUser->json('message'),
            $wrongPassword->json('message'),
        );
    }

    public function test_password_is_never_returned_by_the_api(): void
    {
        $response = $this->postJson('/api/auth/register', [
            'name' => 'Hashed',
            'email' => 'hashed@example.com',
            'password' => 'password123',
            'password_confirmation' => 'password123',
        ])->assertCreated();

        $this->assertArrayNotHasKey('password', $response->json('data.user'));

        $stored = User::where('email', 'hashed@example.com')->firstOrFail();

        // The password must be hashed, not stored verbatim.
        $this->assertNotSame('password123', $stored->password);
        $this->assertTrue(password_verify('password123', $stored->password));
    }

    public function test_the_me_endpoint_returns_the_authenticated_user(): void
    {
        $user = User::factory()->create();

        $this->actingAsWithFullToken($user)
            ->getJson('/api/auth/me')
            ->assertOk()
            ->assertJsonPath('data.id', $user->id);
    }

    public function test_logout_revokes_the_bearer_token(): void
    {
        $user = User::factory()->create();
        $token = $user->createToken('test-token');

        $this->withToken($token->plainTextToken)
            ->postJson('/api/auth/logout')
            ->assertOk();

        // The token row must be gone from the database.
        $this->assertDatabaseMissing('personal_access_tokens', [
            'id' => $token->accessToken->id,
        ]);
    }

    public function test_a_revoked_token_no_longer_authenticates(): void
    {
        $user = User::factory()->create();
        $token = $user->createToken('test-token');

        $this->withToken($token->plainTextToken)
            ->postJson('/api/auth/logout')
            ->assertOk();

        // Clear the resolved user cached by the guard between requests so the
        // second request re-authenticates from the (now deleted) token.
        $this->app['auth']->forgetGuards();

        $this->withToken($token->plainTextToken)
            ->getJson('/api/auth/me')
            ->assertUnauthorized();
    }

    public function test_the_role_field_is_not_mass_assignable(): void
    {
        $user = User::factory()->create();

        // `role` is absent from the model's fillable list, so a plain mass
        // assignment must not be able to promote the account.
        $user->update(['role' => 'admin']);

        $this->assertNotSame('admin', $user->fresh()->role->value);
        $this->assertFalse($user->fresh()->isAdmin());
    }
}
