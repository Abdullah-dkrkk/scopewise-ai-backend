<?php

declare(strict_types=1);

namespace App\Providers;

use App\Models\Analysis;
use App\Models\Project;
use App\Models\Requirement;
use App\Policies\AnalysisPolicy;
use App\Policies\ProjectPolicy;
use App\Policies\RequirementPolicy;
use App\Services\Ml\AnalysisWriter;
use App\Services\Ml\HeuristicEstimator;
use App\Services\Ml\MlClient;
use Illuminate\Auth\Notifications\ResetPassword;
use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\ServiceProvider;
use Illuminate\Support\Str;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register application services.
     */
    public function register(): void
    {
        $this->app->singleton(MlClient::class, static fn (): MlClient => new MlClient(
            (int) config('services.ml.timeout', 30),
            (string) config('services.ml.base_uri', 'http://localhost:5000'),
            config('services.ml.token') ?: null,
        ));

        $this->app->singleton(HeuristicEstimator::class);
        $this->app->singleton(AnalysisWriter::class);
    }

    /**
     * Bootstrap application services.
     */
    public function boot(): void
    {
        $this->configurePolicies();
        $this->configureRateLimiters();
        $this->configurePasswordResetUrl();
    }

    /**
     * Point reset links at the SPA. The stock notification builds a route
     * named `password.reset`, which does not exist in this API-only app and
     * would otherwise throw while sending the mail.
     */
    private function configurePasswordResetUrl(): void
    {
        ResetPassword::createUrlUsing(
            static fn (object $notifiable, string $token): string => sprintf(
                '%s/reset-password?token=%s&email=%s',
                (string) config('app.frontend_url'),
                urlencode($token),
                urlencode($notifiable->getEmailForPasswordReset()),
            )
        );
    }

    /**
     * Explicit policy registration so authorisation never silently falls back
     * to "allow" if a policy class is renamed or moved.
     */
    private function configurePolicies(): void
    {
        Gate::policy(Project::class, ProjectPolicy::class);
        Gate::policy(Requirement::class, RequirementPolicy::class);
        Gate::policy(Analysis::class, AnalysisPolicy::class);
    }

    /**
     * Rate limits are applied per authenticated user where possible so one
     * noisy client cannot exhaust the quota of everyone behind a shared IP.
     */
    private function configureRateLimiters(): void
    {
        RateLimiter::for('api', function (Request $request): Limit {
            return Limit::perMinute((int) config('rate_limiting.api_per_minute'))
                ->by($this->throttleKey($request));
        });

        RateLimiter::for('login', function (Request $request): Limit {
            return Limit::perMinute((int) config('rate_limiting.login_per_minute'))
                ->by(Str::lower((string) $request->input('email')).'|'.$request->ip());
        });

        RateLimiter::for('register', function (Request $request): Limit {
            return Limit::perHour((int) config('rate_limiting.register_per_hour'))
                ->by($request->ip());
        });

        RateLimiter::for('analyze', function (Request $request): Limit {
            return Limit::perMinute((int) config('rate_limiting.analyze_per_minute'))
                ->by($this->throttleKey($request));
        });
    }

    /**
     * Throttle by user id for authenticated callers, falling back to the IP
     * address for guests.
     */
    private function throttleKey(Request $request): string
    {
        $userId = $request->user()?->id;

        return $userId !== null ? 'user:'.$userId : 'ip:'.$request->ip();
    }
}
