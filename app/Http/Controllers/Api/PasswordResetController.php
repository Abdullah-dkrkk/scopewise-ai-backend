<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\Auth\ForgotPasswordRequest;
use App\Http\Requests\Auth\ResetPasswordRequest;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Password;
use OpenApi\Attributes as OA;

class PasswordResetController extends Controller
{
    /**
     * Upper bound for the email-less token scan (see tokenByScan()).
     */
    private const MAX_TOKEN_SCAN = 20;

    #[OA\Post(
        path: '/api/auth/forgot-password',
        summary: 'Request a password reset link',
        description: 'Always answers 200 when the payload is valid, regardless of whether the account exists, to avoid leaking addresses.',
        requestBody: new OA\RequestBody(
            required: true,
            content: new OA\JsonContent(
                required: ['email'],
                properties: [
                    new OA\Property(property: 'email', type: 'string', format: 'email', example: 'jane@example.com'),
                ]
            )
        ),
        tags: ['Authentication'],
        responses: [
            new OA\Response(response: 200, description: 'Reset link sent (or deliberately undisclosed)'),
            new OA\Response(response: 422, description: 'Validation failed'),
            new OA\Response(response: 429, description: 'Too many requests'),
        ]
    )]
    public function forgot(ForgotPasswordRequest $request): JsonResponse
    {
        Password::sendResetLink($request->only('email'));

        return response()->json([
            'success' => true,
            'message' => 'If an account exists for that email, a reset link has been sent.',
        ]);
    }

    /**
     * Validate a reset link before the user fills in the form, so a stale or
     * tampered token fails early instead of at the final submit.
     *
     * The emailed link carries `?email=`; when it is present the lookup is a
     * single indexed row check. Without it the recent tokens are scanned,
     * bounded so the endpoint cannot become a bcrypt workhorse.
     */
    #[OA\Get(
        path: '/api/auth/reset/{token}',
        summary: 'Validate a password reset token',
        description: 'The link in the email points here with ?email= for a direct lookup; without it the most recent tokens are scanned.',
        tags: ['Authentication'],
        parameters: [
            new OA\Parameter(name: 'token', in: 'path', required: true, schema: new OA\Schema(type: 'string')),
            new OA\Parameter(name: 'email', in: 'query', description: 'The address the link was sent to', required: false, schema: new OA\Schema(type: 'string', format: 'email')),
        ],
        responses: [
            new OA\Response(response: 200, description: 'Token valid; email echoed for form prefill'),
            new OA\Response(response: 404, description: 'Invalid, expired or unknown token'),
            new OA\Response(response: 429, description: 'Too many requests'),
        ]
    )]
    public function showResetForm(Request $request): JsonResponse
    {
        $token = (string) $request->route('token');
        $email = trim((string) $request->query('email'));

        $record = $email !== ''
            ? $this->tokenForEmail($token, $email)
            : $this->tokenByScan($token);

        if ($record === null) {
            return $this->invalidTokenResponse();
        }

        return response()->json([
            'success' => true,
            'data' => [
                'valid' => true,
                'email' => $record->email,
            ],
        ]);
    }

    #[OA\Post(
        path: '/api/auth/reset',
        summary: 'Reset the password with the emailed token',
        description: 'On success every previously issued api token is revoked.',
        requestBody: new OA\RequestBody(
            required: true,
            content: new OA\JsonContent(
                required: ['token', 'email', 'password', 'password_confirmation'],
                properties: [
                    new OA\Property(property: 'token', type: 'string'),
                    new OA\Property(property: 'email', type: 'string', format: 'email'),
                    new OA\Property(property: 'password', type: 'string', minLength: 8),
                    new OA\Property(property: 'password_confirmation', type: 'string'),
                ]
            )
        ),
        tags: ['Authentication'],
        responses: [
            new OA\Response(response: 200, description: 'Password reset'),
            new OA\Response(response: 404, description: 'Invalid or expired token'),
            new OA\Response(response: 422, description: 'Validation failed or token/email mismatch'),
        ]
    )]
    public function reset(ResetPasswordRequest $request): JsonResponse
    {
        $status = Password::reset(
            $request->only('email', 'password', 'password_confirmation', 'token'),
            function (User $user, string $password): void {
                $user->password = $password;
                $user->save();

                // Every previously issued token dies with the old password.
                $user->tokens()->delete();
            }
        );

        if ($status !== Password::PASSWORD_RESET) {
            return response()->json([
                'success' => false,
                'message' => $this->statusMessage($status),
                'errors' => [
                    'token' => [$this->statusMessage($status)],
                ],
            ], 422);
        }

        return response()->json([
            'success' => true,
            'message' => 'Password has been reset. You can now sign in.',
        ]);
    }

    /**
     * Verify the token against the row belonging to one email address.
     */
    private function tokenForEmail(string $token, string $email): ?object
    {
        $record = DB::table('password_reset_tokens')->where('email', $email)->first();

        if ($record === null || ! $this->isValidToken($token, $record)) {
            return null;
        }

        return $record;
    }

    /**
     * Fallback when the caller did not supply the email from the link.
     */
    private function tokenByScan(string $token): ?object
    {
        if ($token === '') {
            return null;
        }

        $expireMinutes = (int) config('auth.passwords.users.expire', 60);

        $candidates = DB::table('password_reset_tokens')
            ->where('created_at', '>=', Carbon::now()->subMinutes($expireMinutes))
            ->orderByDesc('created_at')
            ->limit(self::MAX_TOKEN_SCAN)
            ->get();

        foreach ($candidates as $record) {
            if ($this->isValidToken($token, $record)) {
                return $record;
            }
        }

        return null;
    }

    private function isValidToken(string $token, object $record): bool
    {
        if ($token === '' || $record->created_at === null) {
            return false;
        }

        $expireMinutes = (int) config('auth.passwords.users.expire', 60);

        $expired = Carbon::parse($record->created_at)
            ->addMinutes($expireMinutes)
            ->isPast();

        return ! $expired && Hash::check($token, $record->token);
    }

    private function invalidTokenResponse(): JsonResponse
    {
        return response()->json([
            'success' => false,
            'message' => 'This password reset link is invalid or has expired.',
        ], 404);
    }

    private function statusMessage(string $status): string
    {
        // No lang/ directory ships with this app, so the broker's translation
        // keys are mapped here instead of leaking raw keys to clients.
        return match ($status) {
            Password::INVALID_TOKEN,
            Password::INVALID_USER => 'This password reset link is invalid or has expired.',
            Password::RESET_THROTTLED => 'Too many reset attempts. Please try again later.',
            default => 'Password has been reset. You can now sign in.',
        };
    }
}
