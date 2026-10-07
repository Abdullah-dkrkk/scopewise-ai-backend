<?php

declare(strict_types=1);

/*
|--------------------------------------------------------------------------
| Cross-Origin Resource Sharing (CORS) Configuration
|--------------------------------------------------------------------------
|
| Origins are driven by environment variables so the allow-list can be
| tightened per deployment without touching code. A wildcard origin is
| intentionally unsupported: the API authenticates with cookies and bearer
| tokens, and `*` is incompatible with `supports_credentials`.
|
| Keep CORS_ALLOWED_ORIGINS and SANCTUM_STATEFUL_DOMAINS in sync, otherwise the
| browser will send credentials that the server refuses to honour.
|
*/

/**
 * Parse a comma separated environment variable into a clean list of strings.
 *
 * @return list<string>
 */
$csv = static function (string $key, string $default = ''): array {
    return array_values(array_filter(
        array_map('trim', explode(',', (string) env($key, $default))),
        static fn (string $value): bool => $value !== '',
    ));
};

return [

    'paths' => ['api/*', 'sanctum/csrf-cookie'],

    'allowed_methods' => ['*'],

    'allowed_origins' => $csv('CORS_ALLOWED_ORIGINS'),

    'allowed_origins_patterns' => $csv('CORS_ALLOWED_ORIGINS_PATTERNS'),

    'allowed_headers' => ['*'],

    // Exposed so clients can honour the 429 backoff windows.
    'exposed_headers' => ['Retry-After'],

    'max_age' => 3600,

    'supports_credentials' => true,

];
