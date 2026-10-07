<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Http\Requests\Auth\UpdateMeRequest;
use App\Http\Requests\Auth\UpdatePasswordRequest;
use App\Http\Resources\UserResource;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Arr;
use OpenApi\Attributes as OA;

class ProfileController extends Controller
{
    #[OA\Put(
        path: '/api/auth/me',
        summary: 'Update the current user\'s profile',
        description: 'Password must be supplied whenever the email changes. Use PUT /api/auth/password to rotate the password separately.',
        security: [['bearerAuth' => []]],
        requestBody: new OA\RequestBody(
            required: true,
            content: new OA\JsonContent(
                properties: [
                    new OA\Property(property: 'name', type: 'string', maxLength: 255, example: 'Jane Doe'),
                    new OA\Property(property: 'email', type: 'string', format: 'email', example: 'jane@example.com'),
                    new OA\Property(property: 'current_password', type: 'string', description: 'Required when the email changes', example: 'secret123'),
                ]
            )
        ),
        tags: ['Authentication'],
        responses: [
            new OA\Response(response: 200, description: 'Profile updated'),
            new OA\Response(response: 401, description: 'Unauthenticated'),
            new OA\Response(response: 422, description: 'Validation failed'),
        ]
    )]
    public function updateMe(UpdateMeRequest $request): JsonResponse
    {
        $user = $request->user();
        $user->fill(Arr::except($request->validated(), ['current_password']))->save();

        return response()->json([
            'success' => true,
            'message' => 'Profile updated',
            'data' => new UserResource($user->fresh()),
        ]);
    }

    #[OA\Put(
        path: '/api/auth/password',
        summary: 'Change the current user\'s password',
        security: [['bearerAuth' => []]],
        requestBody: new OA\RequestBody(
            required: true,
            content: new OA\JsonContent(
                required: ['current_password', 'password', 'password_confirmation'],
                properties: [
                    new OA\Property(property: 'current_password', type: 'string', example: 'secret123'),
                    new OA\Property(property: 'password', type: 'string', minLength: 8, example: 'newsecret456'),
                    new OA\Property(property: 'password_confirmation', type: 'string', example: 'newsecret456'),
                ]
            )
        ),
        tags: ['Authentication'],
        responses: [
            new OA\Response(response: 200, description: 'Password updated; other sessions revoked'),
            new OA\Response(response: 401, description: 'Unauthenticated or wrong current password'),
            new OA\Response(response: 422, description: 'Validation failed'),
        ]
    )]
    public function updatePassword(UpdatePasswordRequest $request): JsonResponse
    {
        $user = $request->user();
        $validated = $request->validated();

        $user->update([
            'password' => $validated['password'],
        ]);

        $tokenId = $request->user()->currentAccessToken()?->id;
        if ($tokenId) {
            $user->tokens()->where('id', '!=', $tokenId)->delete();
        }

        return response()->json([
            'success' => true,
            'message' => 'Password updated',
            'data' => new UserResource($user->fresh()),
        ]);
    }
}
