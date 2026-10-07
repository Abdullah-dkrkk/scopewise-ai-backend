<?php

declare(strict_types=1);

return [

    /*
    |--------------------------------------------------------------------------
    | Estimation rates
    |--------------------------------------------------------------------------
    |
    | Used to render cost figures on the analysis object. The defaults match
    | the frontend's fallback ($540 per person-day, i.e. $67.50/hour at 8h)
    | so both sides agree until real rates are configured.
    |
    */

    'hourly_rate' => (float) env('ESTIMATION_HOURLY_RATE', 67.5),

    'per_diem_rate' => (float) env('ESTIMATION_PER_DIEM_RATE', 540),

    'default_team_size' => (int) env('DEFAULT_TEAM_SIZE', 2),

];
