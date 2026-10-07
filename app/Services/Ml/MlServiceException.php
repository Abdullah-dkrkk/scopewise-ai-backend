<?php

declare(strict_types=1);

namespace App\Services\Ml;

use RuntimeException;

/**
 * Raised when the ML service responds in a way the application cannot use.
 */
final class MlServiceException extends RuntimeException {}
