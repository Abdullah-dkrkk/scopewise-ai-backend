<?php

declare(strict_types=1);

namespace App\Jobs;

use App\Enums\RequirementStatus;
use App\Models\Requirement;
use App\Services\Ml\AnalysisPipeline;
use Illuminate\Contracts\Queue\ShouldBeUnique;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;
use Illuminate\Queue\Middleware\WithoutOverlapping;
use Illuminate\Support\Facades\Log;
use Throwable;

/**
 * Analyses a requirement through the ML pipeline off the request lifecycle.
 *
 * The pipeline already degrades to a heuristic when the ML service is down, so
 * a failure here means something more serious: a database problem or a bug. A
 * bounded retry is still worth it, and the requirement is marked failed so the
 * UI never leaves a user staring at a permanently "pending" requirement.
 */
class AnalyzeRequirement implements ShouldBeUnique, ShouldQueue
{
    use Queueable;

    /**
     * Retries are capped because the pipeline degrades gracefully; a repeated
     * failure will not fix itself quickly.
     */
    public int $tries = 3;

    /**
     * Generous relative to the 30s HTTP timeout so a retry plus its backoff
     * still fits inside this budget.
     */
    public int $timeout = 120;

    /**
     * Seconds before a duplicate dispatch may replace this job. Slightly longer
     * than the job timeout so a legitimate retry is never treated as a
     * duplicate.
     */
    public int $uniqueFor = 180;

    /**
     * How long the requirement stays claimed by this unique lock.
     */
    public int $uniqueViaLockFor = 120;

    /**
     * Backoff in seconds between attempts, applied by the queue worker.
     *
     * @var list<int>
     */
    public array $backoff = [10, 45];

    /**
     * Prevent two workers from analysing the same requirement concurrently.
     */
    public function middleware(): array
    {
        return [
            (new WithoutOverlapping($this->requirementId))
                ->expireAfter($this->timeout)
                ->dontRelease(),
        ];
    }

    public function __construct(
        public readonly int $requirementId,
        /**
         * Answers to the clarifying questions, appended to the requirement text
         * so a re-analysis after clarification produces a sharper estimate.
         *
         * @var list<array{question: string, answer: string}>|null
         */
        public readonly ?array $context = null,
    ) {
        $this->onQueue('analysis');
    }

    /**
     * The lock is keyed on the requirement, so only the newest job for a given
     * requirement is kept.
     */
    public function uniqueId(): string
    {
        return (string) $this->requirementId;
    }

    public function handle(AnalysisPipeline $pipeline): void
    {
        $pipeline->run((string) $this->requirementId, $this->context ?? []);
    }

    /**
     * Called when every retry has been exhausted.
     */
    public function failed(Throwable $exception): void
    {
        Log::error('Requirement analysis failed permanently', [
            'requirement_id' => $this->requirementId,
            'exception' => $exception::class,
            'message' => $exception->getMessage(),
        ]);

        $this->markRequirementAsFailed();

        report($exception);
    }

    /**
     * Record the failure on the requirement.
     *
     * The database enum has no "failed" state, so the requirement goes back to
     * pending: it is visibly incomplete, and the user can retry it with
     * POST /api/requirements/{id}/analyze.
     */
    private function markRequirementAsFailed(): void
    {
        $requirement = Requirement::find($this->requirementId);

        if (! $requirement instanceof Requirement) {
            return;
        }

        // An analysis may have landed before the failure, for example when
        // child row creation failed after the parent insert.
        $requirement->analysis()->delete();

        $requirement->forceFill([
            'status' => RequirementStatus::Pending->value,
        ])->save();
    }
}
