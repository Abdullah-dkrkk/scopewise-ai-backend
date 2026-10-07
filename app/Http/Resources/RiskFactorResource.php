<?php

declare(strict_types=1);

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class RiskFactorResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'analysis_id' => $this->analysis_id,
            'factor' => $this->factor,
            'level' => $this->level,
            'description' => $this->description,
            'mitigation' => $this->mitigation,
            'created_at' => $this->created_at,
            'updated_at' => $this->updated_at,
        ];
    }
}
