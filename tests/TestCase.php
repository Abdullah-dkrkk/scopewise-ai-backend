<?php

namespace Tests;

use App\Models\User;
use App\Support\TokenAbility;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    /**
     * Authenticate as $user with a real bearer token holding every ability.
     *
     * `actingAs($user, 'sanctum')` cannot be used for API tests here: it only
     * binds the user to the guard and leaves `currentAccessToken()` empty, so
     * the `abilities` middleware rejects the request with a 401 before the
     * policy is ever consulted.
     */
    protected function actingAsWithFullToken(
        User $user,
        ?array $abilities = null,
    ): static {
        $token = $user->createToken('test-token', $abilities ?? TokenAbility::ALL);

        // The sanctum guard is cached in the application instance together
        // with the request (and user) it first saw. Switching to a second
        // user in the same test would otherwise still resolve the first one.
        $this->app->make('auth')->forgetGuards();

        $this->withToken($token->plainTextToken);

        return $this;
    }
}
