<?php

declare(strict_types=1);

namespace App\Http\Controllers;

use Illuminate\Foundation\Auth\Access\AuthorizesRequests;
use Illuminate\Foundation\Validation\ValidatesRequests;
use OpenApi\Attributes as OA;

#[OA\Info(
    version: '1.0.0',
    title: 'ScopeWise AI API',
    description: 'REST API for software requirement analysis, scope-creep prevention and project estimation. Authenticate with a Sanctum bearer token obtained from POST /api/auth/login.',
)]
#[OA\Server(url: '{scheme}://{host}', description: 'Current environment', variables: [
    new OA\ServerVariable(serverVariable: 'scheme', enum: ['http', 'https'], default: 'http'),
    new OA\ServerVariable(serverVariable: 'host', default: 'localhost:8000'),
])]
#[OA\OpenApi(openapi: '3.0.0')]
abstract class Controller
{
    use AuthorizesRequests, ValidatesRequests;
}
