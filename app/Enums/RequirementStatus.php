<?php

declare(strict_types=1);

namespace App\Enums;

enum RequirementStatus: string
{
    case Pending = 'pending';
    case Analyzed = 'analyzed';
    case Approved = 'approved';
    case Rejected = 'rejected';
}
