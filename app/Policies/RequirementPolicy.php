<?php

declare(strict_types=1);

namespace App\Policies;

use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;

class RequirementPolicy
{
    public function viewAny(User $user): bool
    {
        return true;
    }

    public function view(User $user, Requirement $requirement): bool
    {
        return $this->ownsRequirement($user, $requirement);
    }

    /**
     * Guard the "create inside a project" action against cross-tenant writes.
     *
     * Resolving the project by id is safe here because the request validation
     * rules already reject unknown project ids with a 422 before the
     * controller body runs.
     */
    public function create(User $user, int $projectId): bool
    {
        if ($user->isAdmin()) {
            return true;
        }

        return Project::query()
            ->whereKey($projectId)
            ->where('user_id', $user->id)
            ->exists();
    }

    public function update(User $user, Requirement $requirement): bool
    {
        return $this->ownsRequirement($user, $requirement);
    }

    public function delete(User $user, Requirement $requirement): bool
    {
        return $this->ownsRequirement($user, $requirement);
    }

    private function ownsRequirement(User $user, Requirement $requirement): bool
    {
        if ($user->isAdmin()) {
            return true;
        }

        $project = $requirement->relationLoaded('project')
            ? $requirement->getRelation('project')
            : $requirement->project()->first();

        return $project instanceof Project && $project->user_id === $user->id;
    }
}
