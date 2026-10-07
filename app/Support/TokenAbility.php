<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Canonical list of Sanctum token abilities used across the API.
 *
 * Tokens are issued with a scoped subset of these abilities and enforced by
 * the `abilities` / `ability` middleware registered in bootstrap/app.php.
 */
final class TokenAbility
{
    public const PROJECTS_READ = 'projects:read';

    public const PROJECTS_WRITE = 'projects:write';

    public const REQUIREMENTS_READ = 'requirements:read';

    public const REQUIREMENTS_WRITE = 'requirements:write';

    public const ANALYSIS_READ = 'analysis:read';

    public const ANALYSIS_WRITE = 'analysis:write';

    /**
     * Every ability the application knows about.
     *
     * @var list<string>
     */
    public const ALL = [
        self::PROJECTS_READ,
        self::PROJECTS_WRITE,
        self::REQUIREMENTS_READ,
        self::REQUIREMENTS_WRITE,
        self::ANALYSIS_READ,
        self::ANALYSIS_WRITE,
    ];

    /**
     * Class is a constant holder and must never be instantiated.
     */
    private function __construct() {}
}
