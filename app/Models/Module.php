<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Module extends Model
{
    use HasFactory;

    protected $fillable = [
        'analysis_id',
        'name',
        'description',
        'complexity',
        'estimated_hours',
    ];

    protected function casts(): array
    {
        return [
            'complexity' => 'decimal:2',
            'estimated_hours' => 'decimal:2',
        ];
    }

    public function analysis(): BelongsTo
    {
        return $this->belongsTo(Analysis::class);
    }
}
