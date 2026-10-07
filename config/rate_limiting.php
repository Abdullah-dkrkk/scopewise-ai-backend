<?php

declare(strict_types=1);

return [

    /*
    |--------------------------------------------------------------------------
    | API Rate Limits
    |--------------------------------------------------------------------------
    |
    | Consumed by AppServiceProvider::configureRateLimiters(). Keeping the
    | numbers here rather than inline satisfies the "no magic numbers" rule
    | and lets a local checkout loosen a bucket through the environment
    | without editing code — the committed defaults stay strict.
    |
    | register_per_hour is env-overridable because 3/hour is right for
    | production but starves a developer who is creating test accounts.
    |
    */

    'api_per_minute' => 120,

    'login_per_minute' => 5,

    'register_per_hour' => (int) env('REGISTER_RATE_LIMIT_PER_HOUR', 3),

    'analyze_per_minute' => 20,
];
