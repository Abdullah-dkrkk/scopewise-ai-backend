<?php

declare(strict_types=1);

namespace App\Support;

use Illuminate\Http\Request;

/**
 * Shared query-string rules for list endpoints (§7).
 */
final class Pagination
{
    /**
     * A validated ?per_page= between 1 and the configured maximum.
     * Missing or non-numeric input falls back to the default page size.
     */
    public static function perPage(Request $request): int
    {
        $default = max(1, (int) config('pagination.per_page', 20));
        $max = max(1, (int) config('pagination.max_per_page', 100));

        $requested = $request->query('per_page');

        if (! is_numeric($requested)) {
            return min($default, $max);
        }

        return max(1, min($max, (int) $requested));
    }

    /**
     * A [column, direction] pair where the column must be in the allow-list
     * and the direction is either asc or desc.
     *
     * @param  list<string>  $allowed
     * @return array{0: string, 1: string}
     */
    public static function sort(Request $request, string $default, array $allowed): array
    {
        $column = (string) $request->query('sort', $default);
        $column = in_array($column, $allowed, true) ? $column : $default;

        $direction = $request->query('direction') === 'asc' ? 'asc' : 'desc';

        return [$column, $direction];
    }

    /**
     * User input made safe to embed in a LIKE pattern.
     */
    public static function likeTerm(?string $value): string
    {
        $trimmed = trim((string) $value);

        if ($trimmed === '') {
            return '';
        }

        return addcslashes($trimmed, '%_\\');
    }
}
