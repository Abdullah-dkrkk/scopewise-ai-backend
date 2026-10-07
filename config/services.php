<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Third Party Services
    |--------------------------------------------------------------------------
    |
    | This file is for storing the credentials for third party services such
    | as Resend, Postmark, AWS, and more. This file provides the de facto
    | location for this type of information, allowing packages to have
    | a conventional file to locate the various service credentials.
    |
    */

    'postmark' => [
        'key' => env('POSTMARK_API_KEY'),
    ],

    'resend' => [
        'key' => env('RESEND_API_KEY'),
    ],

    'ses' => [
        'key' => env('AWS_ACCESS_KEY_ID'),
        'secret' => env('AWS_SECRET_ACCESS_KEY'),
        'region' => env('AWS_DEFAULT_REGION', 'us-east-1'),
    ],

    'slack' => [
        'notifications' => [
            'bot_user_oauth_token' => env('SLACK_BOT_USER_OAUTH_TOKEN'),
            'channel' => env('SLACK_BOT_USER_DEFAULT_CHANNEL'),
        ],
    ],

    /*
    |--------------------------------------------------------------------------
    | Machine Learning Service
    |--------------------------------------------------------------------------
    |
    | Base URL and timeout for the Python inference service. This service is
    | internal-only and must never be exposed on a public interface.
    |
    */

    'ml' => [
        'base_uri' => env('ML_SERVICE_URL', 'http://localhost:5000'),
        'timeout' => (int) env('ML_SERVICE_TIMEOUT', 30),

        // Shared secret presented to the ML service on every request. Must
        // match ML_SERVICE_API_KEY in the service's own environment. Leave
        // empty only for local development where the service runs anonymous.
        'token' => env('ML_SERVICE_TOKEN'),

        // When false, an unreachable or failing ML service surfaces the error
        // instead of falling back to the local heuristic estimator.
        'fallback_to_heuristic' => filter_var(
            env('ML_FALLBACK_ENABLED', true),
            FILTER_VALIDATE_BOOLEAN
        ),
    ],

];
