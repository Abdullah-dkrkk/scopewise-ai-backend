<?php

namespace Tests\Feature;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class CorsConfigurationTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Origins shipped in .env.example. Any origin outside this list must be
     * refused by the CORS layer.
     */
    private const DEFAULT_ORIGINS = [
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ];

    public function test_cors_config_is_loaded_from_the_environment(): void
    {
        // No runtime mutation here: the point is to assert what a real
        // deployment resolves from .env.
        $this->assertSame(
            self::DEFAULT_ORIGINS,
            config('cors.allowed_origins'),
            'CORS_ALLOWED_ORIGINS must resolve to the documented allow-list.'
        );
    }

    public function test_wildcard_origins_are_not_configured(): void
    {
        $this->assertNotContains('*', config('cors.allowed_origins'));
        $this->assertNotContains('*', config('cors.allowed_origins_patterns'));
    }

    public function test_credentials_are_supported_so_cookie_sessions_work(): void
    {
        $this->assertTrue(config('cors.supports_credentials'));
        $this->assertSame(['*'], config('cors.allowed_methods'));
    }

    public function test_stateful_domains_match_the_cors_allow_list(): void
    {
        // Cookie authenticated SPA requests need both lists to agree.
        $this->assertNotEmpty(config('sanctum.stateful'));
        $this->assertSame(
            ['localhost', 'localhost:5173', '127.0.0.1', '127.0.0.1:5173'],
            config('sanctum.stateful'),
        );
    }

    public function test_retry_after_header_is_exposed_for_rate_limit_clients(): void
    {
        $this->assertContains('Retry-After', config('cors.exposed_headers'));
    }

    public function test_token_expiration_is_configured(): void
    {
        // A null expiration means a leaked bearer token never expires.
        $this->assertNotNull(config('sanctum.expiration'));
        $this->assertGreaterThan(0, config('sanctum.expiration'));
    }
}
