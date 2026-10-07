<?php

declare(strict_types=1);

return [

    /*
    |--------------------------------------------------------------------------
    | Pagination defaults
    |--------------------------------------------------------------------------
    |
    | Default page size for list endpoints and the maximum a client may
    | request with ?per_page=. Keeps one unbounded ?per_page=100000 from
    | turning a list endpoint into a full table dump.
    |
    */

    'per_page' => (int) env('PAGINATION_PER_PAGE', 20),

    'max_per_page' => (int) env('PAGINATION_MAX_PER_PAGE', 100),

];
