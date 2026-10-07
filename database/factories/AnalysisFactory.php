<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Analysis;
use App\Models\Requirement;
use Illuminate\Database\Eloquent\Factories\Factory;
use Illuminate\Database\Eloquent\Model;

/**
 * @extends Factory<Analysis>
 */
class AnalysisFactory extends Factory
{
    /**
     * @return class-string<Model>
     */
    protected $model = Analysis::class;

    /**
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'requirement_id' => Requirement::factory(),
            'classification' => fake()->randomElement(['authentication', 'reporting', 'general']),
            'complexity_score' => fake()->randomFloat(2, 1, 5),
            'risk_level' => fake()->randomElement(['low', 'medium', 'high', 'critical']),
            'estimated_hours' => fake()->randomFloat(2, 4, 200),
            'estimation_method' => 'heuristic',
        ];
    }
}
