<?php

declare(strict_types=1);

namespace App\Services;

use App\Http\Resources\ProjectResource;
use App\Models\Project;
use App\Support\Pagination;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ProjectService
{
    public function index(Request $request): JsonResponse
    {
        $query = Project::where('user_id', $request->user()->id);

        $search = Pagination::likeTerm($request->query('search'));

        if ($search !== '') {
            $query->where(function ($builder) use ($search): void {
                $builder->where('name', 'like', "%{$search}%")
                    ->orWhere('description', 'like', "%{$search}%");
            });
        }

        $status = (string) $request->query('status');

        if (in_array($status, ['active', 'completed', 'archived'], true)) {
            $query->where('status', $status);
        }

        [$sort, $direction] = Pagination::sort($request, 'created_at', ['name', 'created_at']);

        $projects = $query
            ->withCount('requirements')
            ->orderBy($sort, $direction)
            ->orderBy('id', $direction)
            ->paginate(Pagination::perPage($request));

        // List envelope: { success, data, links, meta } (§3.2).
        $payload = ProjectResource::collection($projects)->response()->getData(true);

        return response()->json(array_merge(['success' => true], $payload));
    }

    public function store(array $data, $user): JsonResponse
    {
        $project = Project::create([
            'user_id' => $user->id,
            'name' => $data['name'],
            'description' => $data['description'] ?? null,
            'status' => $data['status'] ?? 'active',
        ]);

        return response()->json([
            'success' => true,
            'data' => new ProjectResource($project->load('requirements')),
            'message' => 'Project created successfully',
        ], 201);
    }

    public function show(Project $project): JsonResponse
    {
        $project->load('requirements.analysis');

        return response()->json([
            'success' => true,
            'data' => new ProjectResource($project),
        ]);
    }

    public function update(array $data, Project $project): JsonResponse
    {
        $project->update($data);

        return response()->json([
            'success' => true,
            'data' => new ProjectResource($project->fresh()->load('requirements')),
            'message' => 'Project updated successfully',
        ]);
    }

    public function destroy(Project $project): JsonResponse
    {
        $project->delete();

        return response()->json([
            'success' => true,
            'message' => 'Project deleted successfully',
        ]);
    }
}
