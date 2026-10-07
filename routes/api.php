<?php

declare(strict_types=1);

use App\Http\Controllers\Api\AnalysisController;
use App\Http\Controllers\Api\AuthController;
use App\Http\Controllers\Api\DashboardController;
use App\Http\Controllers\Api\PasswordResetController;
use App\Http\Controllers\Api\ProfileController;
use App\Http\Controllers\Api\ProjectController;
use App\Http\Controllers\Api\QuestionController;
use App\Http\Controllers\Api\RequirementController;
use App\Support\TokenAbility;
use Illuminate\Support\Facades\Route;

Route::prefix('auth')->group(function (): void {
    Route::post('register', [AuthController::class, 'register'])
        ->middleware('throttle:register');

    Route::post('login', [AuthController::class, 'login'])
        ->middleware('throttle:login');

    // Password reset is public but shares the login bucket so the two
    // endpoints cannot be used to enumerate or brute force at scale.
    Route::post('forgot-password', [PasswordResetController::class, 'forgot'])
        ->middleware('throttle:login');

    Route::get('reset/{token}', [PasswordResetController::class, 'showResetForm'])
        ->middleware('throttle:login');

    Route::post('reset', [PasswordResetController::class, 'reset'])
        ->middleware('throttle:login');

    Route::middleware(['auth:sanctum', 'throttle:api'])->group(function (): void {
        Route::post('logout', [AuthController::class, 'logout']);
        Route::get('me', [AuthController::class, 'me']);

        Route::put('me', [ProfileController::class, 'updateMe']);
        Route::put('password', [ProfileController::class, 'updatePassword']);
    });
});

Route::middleware(['auth:sanctum', 'throttle:api'])->group(function (): void {
    Route::apiResource('projects', ProjectController::class)
        ->only(['index', 'show'])
        ->middleware('abilities:'.TokenAbility::PROJECTS_READ);

    Route::apiResource('projects', ProjectController::class)
        ->only(['store', 'update', 'destroy'])
        ->middleware('abilities:'.TokenAbility::PROJECTS_WRITE);

    Route::get('projects/{project}/requirements', [RequirementController::class, 'index'])
        ->middleware('abilities:'.TokenAbility::REQUIREMENTS_READ);

    // Submitting a requirement drives the ML pipeline, so it gets its own,
    // tighter bucket on top of the global API limit.
    Route::post('requirements', [RequirementController::class, 'store'])
        ->middleware(['abilities:'.TokenAbility::REQUIREMENTS_WRITE, 'throttle:analyze']);

    Route::get('requirements/{requirement}', [RequirementController::class, 'show'])
        ->middleware('abilities:'.TokenAbility::REQUIREMENTS_READ);

    Route::put('requirements/{requirement}', [RequirementController::class, 'update'])
        ->middleware('abilities:'.TokenAbility::REQUIREMENTS_WRITE);

    Route::delete('requirements/{requirement}', [RequirementController::class, 'destroy'])
        ->middleware('abilities:'.TokenAbility::REQUIREMENTS_WRITE);

    // Re-run the analysis for a requirement, for example to replace a
    // heuristic estimate once the ML service is reachable again.
    Route::post('requirements/{requirement}/analyze', [RequirementController::class, 'reanalyze'])
        ->middleware(['abilities:'.TokenAbility::REQUIREMENTS_WRITE, 'throttle:analyze']);

    Route::get('analysis/{analysis}', [AnalysisController::class, 'show'])
        ->middleware('abilities:'.TokenAbility::ANALYSIS_READ);

    Route::get('analysis/{analysis}/questions', [QuestionController::class, 'index'])
        ->middleware('abilities:'.TokenAbility::ANALYSIS_READ);

    Route::post('analysis/{analysis}/questions/{questionId}', [QuestionController::class, 'answer'])
        ->middleware('abilities:'.TokenAbility::ANALYSIS_WRITE);

    Route::get('history', [AnalysisController::class, 'history'])
        ->middleware('abilities:'.TokenAbility::ANALYSIS_READ);

    Route::get('dashboard/stats', [DashboardController::class, 'stats'])
        ->middleware('abilities:'.TokenAbility::ANALYSIS_READ);

    Route::get('dashboard/activity', [DashboardController::class, 'activity'])
        ->middleware('abilities:'.TokenAbility::ANALYSIS_READ);
});
