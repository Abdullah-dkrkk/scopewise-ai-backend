<?php

declare(strict_types=1);

use App\Http\Middleware\SecurityHeaders;
use Illuminate\Auth\Access\AuthorizationException;
use Illuminate\Auth\AuthenticationException;
use Illuminate\Database\Eloquent\ModelNotFoundException;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Http\Exceptions\ThrottleRequestsException;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Middleware\HandleCors;
use Illuminate\Http\Request;
use Illuminate\Validation\ValidationException;
use Laravel\Sanctum\Http\Middleware\CheckAbilities;
use Laravel\Sanctum\Http\Middleware\CheckForAnyAbility;
use Symfony\Component\HttpKernel\Exception\HttpException;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        api: __DIR__.'/../routes/api.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        $middleware->statefulApi();

        $middleware->api(prepend: [
            HandleCors::class,
        ], append: [
            SecurityHeaders::class,
        ]);

        // Sanctum does not register these aliases with the application, so the
        // `abilities:` / `ability:` route middleware would otherwise fail to
        // resolve at runtime.
        $middleware->alias([
            'abilities' => CheckAbilities::class,
            'ability' => CheckForAnyAbility::class,
        ]);
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        $exceptions->shouldRenderJsonWhen(
            fn (Request $request) => $request->is('api/*') || $request->expectsJson(),
        );

        // One error envelope for every non-2xx API response, per §3.3:
        // { success: false, message: string, errors?: { field: [reasons] } }
        $exceptions->render(function (Throwable $exception, Request $request): ?JsonResponse {
            if (! $request->is('api/*')) {
                return null;
            }

            if ($exception instanceof ValidationException) {
                return response()->json([
                    'success' => false,
                    'message' => 'Please correct the highlighted fields.',
                    'errors' => $exception->errors(),
                ], 422);
            }

            if ($exception instanceof AuthenticationException) {
                return response()->json([
                    'success' => false,
                    'message' => 'Unauthenticated.',
                ], 401);
            }

            // Covers both policy denials and token-ability denials.
            if ($exception instanceof AuthorizationException) {
                return response()->json([
                    'success' => false,
                    'message' => $exception->getMessage() ?: 'This action is unauthorized.',
                ], 403);
            }

            if ($exception instanceof ModelNotFoundException) {
                return response()->json([
                    'success' => false,
                    'message' => 'Resource not found.',
                ], 404);
            }

            if ($exception instanceof ThrottleRequestsException) {
                return response()->json([
                    'success' => false,
                    'message' => $exception->getMessage() ?: 'Too many requests. Please try again later.',
                ], 429, $exception->getHeaders());
            }

            if ($exception instanceof HttpException) {
                $status = $exception->getStatusCode();
                $message = $exception->getMessage();

                // Route binding failures expose internal class names; replace
                // them with the neutral sentence clients expect.
                if (str_starts_with($message, 'No query results for model')) {
                    $message = '';
                }

                $fallback = match ($status) {
                    401 => 'Unauthenticated.',
                    403 => 'This action is unauthorized.',
                    404 => 'Resource not found.',
                    405 => 'Method not allowed.',
                    429 => 'Too many requests. Please try again later.',
                    default => 'Request failed.',
                };

                // 5xx bodies never leak internals; anything else keeps its
                // specific message (route binding failures, abort() calls).
                return response()->json([
                    'success' => false,
                    'message' => $status >= 500
                        ? 'Something went wrong.'
                        : ($message ?: $fallback),
                ], $status, $exception->getHeaders());
            }

            // Unexpected failure: the detail is logged by the framework, the
            // client only ever sees a generic sentence.
            return response()->json([
                'success' => false,
                'message' => 'Something went wrong.',
            ], 500);
        });
    })->create();
