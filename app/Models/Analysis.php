<?php

declare(strict_types=1);

namespace App\Models;

use App\Enums\AnalysisStatus;
use App\Enums\RiskLevel;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Analysis extends Model
{
    use HasFactory;

    /**
     * @var list<string>
     */
    protected $fillable = [
        'requirement_id',
        'project_id',
        'classification',
        'complexity_score',
        'risk_level',
        'risk_score',
        'estimated_hours',
        'estimation_method',
        'summary',
        'confidence',
        'questions',
        'meta',
        'status',
        'progress',
        'error',
    ];

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'complexity_score' => 'decimal:2',
            'estimated_hours' => 'decimal:2',
            'risk_level' => RiskLevel::class,
            'risk_score' => 'decimal:2',
            'questions' => 'array',
            'meta' => 'array',
            'confidence' => 'integer',
            'progress' => 'integer',
            'status' => AnalysisStatus::class,
        ];
    }

    public function requirement(): BelongsTo
    {
        return $this->belongsTo(Requirement::class);
    }

    public function modules(): HasMany
    {
        return $this->hasMany(Module::class);
    }

    public function riskFactors(): HasMany
    {
        return $this->hasMany(RiskFactor::class);
    }

    /**
     * The clarification questions shown to the user.
     *
     * The ML service supplies its own questions; when it did not answer (or
     * the analysis predates stored questions) a deterministic default set is
     * derived from the persisted verdict. Ids are stable across reads so an
     * answer can always be matched back to its question.
     *
     * @return list<array{id: string, question: string, category: string, priority: string, status: string, answer: string|null}>
     */
    public function defaultQuestions(): array
    {
        $riskLevel = $this->risk_level instanceof RiskLevel
            ? $this->risk_level->value
            : (string) $this->risk_level;

        $classification = (string) $this->classification;
        $complexity = (string) $this->complexity_score;
        $hours = (string) ($this->estimated_hours ?? '0');

        return [
            [
                'id' => 'q-1',
                'category' => 'scope',
                'question' => "What is the expected scope of the {$classification} feature?",
                'priority' => 'high',
                'status' => 'pending',
                'answer' => null,
            ],
            [
                'id' => 'q-2',
                'category' => 'complexity',
                'question' => "Are there any specific requirements that might affect the complexity score of {$complexity}?",
                'priority' => 'medium',
                'status' => 'pending',
                'answer' => null,
            ],
            [
                'id' => 'q-3',
                'category' => 'risk',
                'question' => sprintf('How should we mitigate the %s risk level identified in this analysis?', $riskLevel),
                'priority' => 'high',
                'status' => 'pending',
                'answer' => null,
            ],
            [
                'id' => 'q-4',
                'category' => 'estimation',
                'question' => sprintf('Does the estimated %s hours align with your team capacity?', $hours),
                'priority' => 'medium',
                'status' => 'pending',
                'answer' => null,
            ],
        ];
    }
}
