<?php

declare(strict_types=1);

namespace App\Http\Requests\Requirement;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class AnalyzeRequirementRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    /**
     * @return array<string, mixed>
     */
    public function rules(): array
    {
        return [
            'project_id' => ['required', 'integer', 'exists:projects,id'],
            'content' => ['required', 'string', 'min:10', 'max:20000'],
            'category' => ['sometimes', 'nullable', 'string', 'max:100'],
            // The schema column is NOT NULL, so null must never be accepted.
            'priority' => ['sometimes', 'required', Rule::in(['low', 'medium', 'high', 'critical'])],
        ];
    }
}
