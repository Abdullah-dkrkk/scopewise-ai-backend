<?php

declare(strict_types=1);

namespace App\Policies;

use App\Models\Analysis;
use App\Models\Project;
use App\Models\Requirement;
use App\Models\User;

class AnalysisPolicy
{
    public function view(User $user, Analysis $analysis): bool
    {
        return $this->ownsAnalysis($user, $analysis);
    }

    /**
     * Reading generated questions is the same sensitive read as the analysis
     * itself, so it is guarded separately but shares the ownership rule.
     */
    public function viewQuestions(User $user, Analysis $analysis): bool
    {
        return $this->ownsAnalysis($user, $analysis);
    }

    public function delete(User $user, Analysis $analysis): bool
    {
        return $this->ownsAnalysis($user, $analysis);
    }

    private function ownsAnalysis(User $user, Analysis $analysis): bool
    {
        if ($user->isAdmin()) {
            return true;
        }

        $requirement = $analysis->relationLoaded('requirement')
            ? $analysis->getRelation('requirement')
            : $analysis->requirement()->first();

        if (! $requirement instanceof Requirement) {
            return false;
        }

        $project = $requirement->relationLoaded('project')
            ? $requirement->getRelation('project')
            : $requirement->project()->first();

        return $project instanceof Project && $project->user_id === $user->id;
    }
}
