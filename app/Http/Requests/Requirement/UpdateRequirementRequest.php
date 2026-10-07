<?php

declare(strict_types=1);

namespace App\Http\Requests\Requirement;

use Illuminate\Foundation\Http\FormRequest;
use Illuminate\Validation\Rule;

class UpdateRequirementRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true;
    }

    /**
     * Deliberately excludes `project_id`.
     *
     * Allowing it here would let a caller re-parent a requirement into another
     * user's project, because the payload is passed straight to Model::update().
     * Ownership is enforced by RequirementPolicy against the *stored* project.
     *
     * @return array<string, mixed>
     */
    public function rules(): array
    {
        return [
            'content' => ['sometimes', 'required', 'string', 'min:10', 'max:20000'],
            'category' => ['sometimes', 'nullable', 'string', 'max:100'],
            // Both columns are NOT NULL enums in the schema, so an explicit null
            // would reach the database and fail the write. Require a value.
            'priority' => ['sometimes', 'required', Rule::in(['low', 'medium', 'high', 'critical'])],
            'status' => ['sometimes', 'required', Rule::in(['pending', 'analyzed', 'approved', 'rejected'])],
        ];
    }
}
