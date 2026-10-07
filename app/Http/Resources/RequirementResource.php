<?php

declare(strict_types=1);

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class RequirementResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'projectId' => $this->project_id,
            'project_id' => $this->project_id,
            'text' => $this->content,
            'content' => $this->content,
            'category' => $this->category,
            'priority' => $this->priority,
            'status' => $this->status,
            'analysis' => new AnalysisResource($this->whenLoaded('analysis')),
            'createdAt' => $this->created_at?->toISOString(),
            'updatedAt' => $this->updated_at?->toISOString(),
        ];
    }
}
