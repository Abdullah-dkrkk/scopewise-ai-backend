<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * The application models one analysis per requirement (Requirement::analysis()
 * is a hasOne) and the writer relies on that invariant to replace a stale
 * verdict on re-analysis. A unique index turns that assumption into a
 * database-enforced guarantee, which also makes a concurrent double-run fail
 * loudly instead of silently storing two conflicting analyses.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('analyses', function (Blueprint $table) {
            $table->unique('requirement_id');
        });
    }

    public function down(): void
    {
        Schema::table('analyses', function (Blueprint $table) {
            $table->dropUnique(['requirement_id']);
        });
    }
};
