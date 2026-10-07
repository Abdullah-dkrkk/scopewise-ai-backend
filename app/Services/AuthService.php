<?php

declare(strict_types=1);

namespace App\Services;

use App\Enums\UserRole;
use App\Http\Resources\UserResource;
use App\Models\User;
use App\Support\TokenAbility;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Laravel\Sanctum\PersonalAccessToken;

class AuthService
{
    /**
     * Create a user and issue a scoped API token.
     *
     * The role column is assigned explicitly and can never be influenced by
     * client input: it is absent from the User mass-assignment allow-list.
     *
     * @param  array{name: string, email: string, password: string}  $data
     */
    public function register(array $data): JsonResponse
    {
        $user = DB::transaction(static fn (): User => User::create([
            'name' => $data['name'],
            'email' => $data['email'],
            'password' => Hash::make($data['password']),
            'role' => UserRole::User,
        ]));

        return $this->tokenResponse($user, 'Registration successful', 201);
    }

    /**
     * Authenticate using an explicit credential allow-list.
     *
     * Passing the raw payload to Auth::attempt() would forward any unrelated
     * validated field into the credential lookup.
     *
     * @param  array{email: string, password: string}  $data
     */
    public function login(array $data): JsonResponse
    {
        $authenticated = Auth::attempt([
            'email' => $data['email'],
            'password' => $data['password'],
        ]);

        if (! $authenticated) {
            return response()->json([
                'success' => false,
                'message' => 'Invalid credentials',
            ], 401);
        }

        /** @var User $user */
        $user = Auth::user();

        return $this->tokenResponse($user, 'Login successful');
    }

    /**
     * Revoke the current access token and clear the session.
     *
     * Cookie authenticated (stateful SPA) requests resolve to a TransientToken,
     * which has no delete() method, so revocation only happens when a real
     * personal access token is present.
     */
    public function logout(User $user): JsonResponse
    {
        $token = $user->currentAccessToken();

        if ($token instanceof PersonalAccessToken) {
            $token->delete();
        }

        Auth::guard('web')->logout();

        return response()->json([
            'success' => true,
            'message' => 'Logged out successfully',
        ]);
    }

    public function me(User $user): JsonResponse
    {
        return response()->json([
            'success' => true,
            'data' => new UserResource($user),
        ]);
    }

    private function tokenResponse(User $user, string $message, int $status = 200): JsonResponse
    {
        $token = $user->createToken('auth-token', TokenAbility::ALL);

        return response()->json([
            'success' => true,
            'data' => [
                'user' => new UserResource($user),
                'token' => $token->plainTextToken,
                'abilities' => TokenAbility::ALL,
            ],
            'message' => $message,
        ], $status);
    }
}
