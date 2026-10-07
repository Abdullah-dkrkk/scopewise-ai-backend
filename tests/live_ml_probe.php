<?php

declare(strict_types=1);

/*
 * Throwaway verification: drives the real Laravel pipeline against a live ML
 * service instead of an Http::fake, to prove the two sides genuinely agree on
 * the payload shape.
 *
 * Run with the service already listening; see tests/README_probe.md.
 */

use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;
use App\Services\Ml\AnalysisPipeline;
use App\Services\Ml\MlClient;
use Illuminate\Support\Facades\DB;

$url = (string) getenv('PROBE_ML_URL');
$token = (string) getenv('PROBE_ML_TOKEN');

if ($url === '' || $token === '') {
    fwrite(STDERR, "PROBE_ML_URL and PROBE_ML_TOKEN must be set.\n");

    exit(2);
}

config([
    'services.ml.base_uri' => $url,
    'services.ml.token' => $token,
    'services.ml.timeout' => 60,
    'services.ml.fallback_to_heuristic' => false,
]);

// The client is a singleton built from config at resolve time, so it must be
// re-bound after the overrides above are applied.
app()->forgetInstance(MlClient::class);

$probe = DB::transaction(function (): Requirement {
    $user = User::factory()->create();
    $project = Project::factory()->for($user)->create();

    return Requirement::factory()->for($project)->create([
        'content' => 'As a user I want to pay for my order with a credit card and '
            .'receive an emailed invoice, with the order status shown live on the dashboard.',
        'status' => 'pending',
    ]);
});

$startedAt = microtime(true);

try {
    $result = app(AnalysisPipeline::class)->run((string) $probe->id);
} catch (Throwable $exception) {
    fwrite(STDERR, 'PIPELINE FAILED: '.$exception::class.': '.$exception->getMessage()."\n");

    exit(1);
}

$elapsed = microtime(true) - $startedAt;
$analysis = $probe->fresh()->analysis;

$problems = [];

if ($result['source'] !== 'ml_service') {
    $problems[] = "source was {$result['source']}, expected ml_service";
}

if ($result['fell_back']) {
    $problems[] = 'pipeline reported a fallback against a live service';
}

if ($analysis === null) {
    $problems[] = 'no analysis persisted';
}

if ($analysis !== null) {
    if ($analysis->classification === '' || $analysis->classification === 'unknown') {
        $problems[] = "classification was '{$analysis->classification}'";
    }

    if ((float) $analysis->complexity_score < 1.0 || (float) $analysis->complexity_score > 5.0) {
        $problems[] = "complexity_score {$analysis->complexity_score} out of range";
    }

    if ((float) $analysis->estimated_hours <= 0.0) {
        $problems[] = "estimated_hours {$analysis->estimated_hours} was not positive";
    }

    if ($analysis->modules()->count() === 0) {
        $problems[] = 'no modules were written';
    }

    if ($analysis->riskFactors()->count() === 0) {
        $problems[] = 'no risk factors were written';
    }

    foreach ($analysis->riskFactors as $factor) {
        if (! in_array($factor->level, ['low', 'medium', 'high'], true)) {
            $problems[] = "risk factor level '{$factor->level}' is outside the DB enum";
        }
    }
}

printf("source=%s elapsed=%.2fs\n", $result['source'], $elapsed);

if ($analysis !== null) {
    printf(
        "analysis=%d classification=%s complexity=%s risk=%s hours=%s modules=%d factors=%d\n",
        $analysis->id,
        $analysis->classification,
        $analysis->complexity_score,
        $analysis->risk_level?->value,
        $analysis->estimated_hours,
        $analysis->modules()->count(),
        $analysis->riskFactors()->count(),
    );
}

$analysis?->delete();
$probe->delete();
$probe->project->delete();
$probe->project->user->delete();

if ($problems !== []) {
    fwrite(STDERR, "PROBLEMS:\n");

    foreach ($problems as $problem) {
        fwrite(STDERR, "  - {$problem}\n");
    }

    exit(1);
}

echo "Live Laravel -> ML service integration OK.\n";

exit(0);
