<?php

declare(strict_types=1);

namespace App\Services\Ml;

use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Throwable;

/**
 * Thin HTTP client for the Python inference service.
 *
 * Backed by Laravel's HTTP client so that tests can fake responses with
 * Http::fake() and so retries, timeouts and logging stay consistent with the
 * rest of the application.
 */
final class MlClient
{
    /**
     * Total attempts, so 3 means the initial request plus 2 retries. 5xx and
     * connection failures are retried; 4xx is deterministic and is surfaced
     * immediately.
     */
    private const MAX_ATTEMPTS = 3;

    private const RETRY_SLEEP_MS = 200;

    /**
     * Header the ML service reads its shared secret from.
     */
    private const TOKEN_HEADER = 'X-Service-Token';

    public function __construct(
        private readonly int $timeout = 30,
        private readonly string $baseUri = 'http://localhost:5000',
        private readonly ?string $token = null,
    ) {}

    /**
     * Analyze a natural language requirement.
     *
     * @param  array<string, mixed>  $context
     * @return array<string, mixed>
     */
    public function analyze(string $text, array $context = []): array
    {
        return $this->post('/analyze', array_merge($context, ['text' => $text]));
    }

    /**
     * @return array<string, mixed>
     */
    public function classify(string $text): array
    {
        return $this->post('/classify', ['text' => $text]);
    }

    /**
     * @return array<string, mixed>
     */
    public function complexity(string $text): array
    {
        return $this->post('/complexity', ['text' => $text]);
    }

    /**
     * @return array<string, mixed>
     */
    public function features(string $text): array
    {
        return $this->post('/features', ['text' => $text]);
    }

    /**
     * @return array<string, mixed>
     */
    public function risk(string $text): array
    {
        return $this->post('/risk', ['text' => $text]);
    }

    /**
     * @return array<string, mixed>
     */
    public function questions(string $text): array
    {
        return $this->post('/questions', ['text' => $text]);
    }

    /**
     * @return array<string, mixed>
     */
    public function timeline(string $text): array
    {
        return $this->post('/timeline', ['text' => $text]);
    }

    /**
     * Liveness probe used by the health check.
     */
    public function healthy(): bool
    {
        try {
            $response = Http::timeout(min($this->timeout, 5))
                ->acceptJson()
                ->get($this->url('/health'));

            return $response->successful();
        } catch (Throwable) {
            return false;
        }
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, mixed>
     */
    private function post(string $path, array $payload): array
    {
        $url = $this->url($path);

        try {
            $request = Http::timeout($this->timeout)
                ->connectTimeout(min($this->timeout, 10))
                ->acceptJson()
                ->asJson();

            // The service is internal-only and authenticates every caller.
            if ($this->token !== null && $this->token !== '') {
                $request = $request->withHeaders([self::TOKEN_HEADER => $this->token]);
            }

            $response = $request
                ->retry(
                    self::MAX_ATTEMPTS,
                    self::RETRY_SLEEP_MS,
                    fn (Throwable $exception): bool => $this->shouldRetry($exception),
                    throw: false
                )
                ->post($url, $payload);
        } catch (Throwable $exception) {
            Log::error('ML service request failed', [
                'path' => $path,
                'exception' => $exception::class,
                'message' => $exception->getMessage(),
            ]);

            throw $exception;
        }

        if ($response->failed()) {
            Log::warning('ML service returned an error status', [
                'path' => $path,
                'status' => $response->status(),
            ]);

            // throw() converts the failed response into an exception so the
            // caller handles every failure mode through one path.
            $response->throw();
        }

        $decoded = $response->json();

        if (! is_array($decoded)) {
            throw new MlServiceException('ML service returned a non-object JSON payload');
        }

        return $decoded;
    }

    /**
     * Only transport-level and server errors are worth retrying. A 4xx will
     * fail identically on every attempt, so it is surfaced immediately.
     */
    private function shouldRetry(Throwable $exception): bool
    {
        if ($exception instanceof ConnectionException) {
            return true;
        }

        if ($exception instanceof RequestException) {
            return $exception->response->serverError();
        }

        return false;
    }

    private function url(string $path): string
    {
        return rtrim($this->baseUri, '/').'/'.ltrim($path, '/');
    }
}
