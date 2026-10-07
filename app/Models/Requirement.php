<?php

declare(strict_types=1);

namespace App\Models;

use App\Enums\RequirementStatus;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasOne;

class Requirement extends Model
{
    use HasFactory;

    protected $fillable = [
        'project_id',
        'content',
        'category',
        'priority',
        'status',
    ];

    protected function casts(): array
    {
        return [
            'status' => RequirementStatus::class,
        ];
    }

    public function project(): BelongsTo
    {
        return $this->belongsTo(Project::class);
    }

    public function analysis(): HasOne
    {
        return $this->hasOne(Analysis::class);
    }

    /**
     * Whether an analysis has been queued or completed for this requirement.
     */
    public function isPendingAnalysis(): bool
    {
        return $this->status === RequirementStatus::Pending;
    }
}
