<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Project;
use App\Models\Requirement;
use Illuminate\Database\Eloquent\Factories\Factory;
use Illuminate\Database\Eloquent\Model;

/**
 * @extends Factory<Requirement>
 */
class RequirementFactory extends Factory
{
    /**
     * @return class-string<Model>
     */
    protected $model = Requirement::class;

    /**
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'project_id' => Project::factory(),
            // The API enforces a 10 character minimum, so the default must
            // satisfy it for tests to exercise the happy path.
            'content' => fake()->paragraph(),
            'category' => fake()->randomElement(['authentication', 'reporting', 'integration']),
            'priority' => 'medium',
            'status' => 'pending',
        ];
    }

    public function forProject(Project $project): static
    {
        return $this->state(fn (): array => [
            'project_id' => $project->id,
        ]);
    }
}
