<?php

declare(strict_types=1);

namespace App\Services;

use App\Enums\RequirementStatus;
use App\Http\Resources\RequirementResource;
use App\Jobs\AnalyzeRequirement;
use App\Models\Project;
use App\Models\Requirement;
use App\Support\Pagination;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Throwable;

class RequirementService
{
    /**
     * The only columns a client is ever allowed to change on an existing
     * requirement. `project_id` is intentionally absent so a requirement can
     * never be moved into another user's project.
     *
     * @var list<string>
     */
    private const MUTABLE_FIELDS = ['content', 'category', 'priority', 'status'];

    public function index(Project $project, Request $request): JsonResponse
    {
        $query = Requirement::where('project_id', $project->id);

        $search = Pagination::likeTerm($request->query('search'));

        if ($search !== '') {
            $query->where('content', 'like', "%{$search}%");
        }

        $status = (string) $request->query('status');

        if (in_array($status, ['pending', 'analyzed', 'approved', 'rejected'], true)) {
            $query->where('status', $status);
        }

        $requirements = $query
            ->with('analysis')
            ->latest()
            ->paginate(Pagination::perPage($request));

        // List envelope: { success, data, links, meta } (§3.2).
        $payload = RequirementResource::collection($requirements)->response()->getData(true);

        return response()->json(array_merge(['success' => true], $payload));
    }

    /**
     * @param  array{project_id: int, content: string, category?: string|null, priority?: string|null}  $data
     */
    public function store(array $data): JsonResponse
    {
        $requirement = Requirement::create([
            'project_id' => $data['project_id'],
            'content' => $data['content'],
            'category' => $data['category'] ?? null,
            'priority' => $data['priority'] ?? 'medium',
            'status' => 'pending',
        ]);

        $this->dispatchAnalysis($requirement);

        return response()->json([
            'success' => true,
            'data' => new RequirementResource($requirement->fresh()->load('analysis')),
            'message' => 'Requirement created successfully',
        ], 201);
    }

    public function show(Requirement $requirement): JsonResponse
    {
        $requirement->load('analysis.modules', 'analysis.riskFactors');

        return response()->json([
            'success' => true,
            'data' => new RequirementResource($requirement),
        ]);
    }

    /**
     * @param  array<string, mixed>  $data
     */
    public function update(array $data, Requirement $requirement): JsonResponse
    {
        $originalContent = $requirement->content;

        $requirement->fill(
            array_intersect_key($data, array_flip(self::MUTABLE_FIELDS))
        )->save();

        // Content drives the analysis, so changing it invalidates the previous
        // verdict. Reset to pending and re-run rather than leaving a stale
        // estimate attached to new text.
        if (array_key_exists('content', $data) && $data['content'] !== $originalContent) {
            $requirement->forceFill(['status' => 'pending'])->save();
            $requirement->analysis()->delete();

            $this->dispatchAnalysis($requirement);
        }

        return response()->json([
            'success' => true,
            'data' => new RequirementResource($requirement->fresh()->load('analysis')),
            'message' => 'Requirement updated successfully',
        ]);
    }

    /**
     * Queue a new analysis for a requirement, discarding the previous verdict.
     *
     * The stale analysis is removed here, in the request, rather than being left
     * in place until the job finishes. A previous estimate attached to a
     * requirement the user just asked to re-run is misleading: the UI would
     * render an outdated number next to a "pending" status. Clearing it makes
     * the honest state visible ("no current estimate") until the new one lands.
     *
     * `AnalysisWriter` still replaces atomically, so a job that runs against a
     * requirement which *does* have an analysis — a retry, or a duplicate
     * dispatch — never leaves two rows or a half-written one behind.
     */
    public function reanalyze(Requirement $requirement): JsonResponse
    {
        $requirement->analysis()->delete();

        $requirement->forceFill(['status' => RequirementStatus::Pending->value])->save();

        $this->dispatchAnalysis($requirement);

        return response()->json([
            'success' => true,
            'data' => new RequirementResource($requirement->fresh()->load('analysis')),
            'message' => 'Analysis queued successfully',
        ], 202);
    }

    public function destroy(Requirement $requirement): JsonResponse
    {
        $requirement->delete();

        return response()->json([
            'success' => true,
            'message' => 'Requirement deleted successfully',
        ]);
    }

    /**
     * Queue the analysis job for a requirement.
     *
     * Dispatched after the transaction commits so a worker can never look up a
     * requirement row that has not landed yet.
     */
    private function dispatchAnalysis(Requirement $requirement): void
    {
        try {
            AnalyzeRequirement::dispatch($requirement->id)->afterCommit();
        } catch (Throwable $exception) {
            // A queue outage must not fail the user's write. The requirement is
            // stored and an operator can re-trigger the analysis later.
            Log::error('Failed to dispatch analysis job', [
                'requirement_id' => $requirement->id,
                'message' => $exception->getMessage(),
            ]);
        }
    }
}
