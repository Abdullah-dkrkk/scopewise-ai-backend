<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('analyses', function (Blueprint $table): void {
            if (! Schema::hasColumn('analyses', 'summary')) {
                $table->text('summary')->nullable()->after('estimation_method');
            }
            if (! Schema::hasColumn('analyses', 'risk_score')) {
                $table->decimal('risk_score', 4, 2)->nullable()->after('risk_level');
            }
            if (! Schema::hasColumn('analyses', 'meta')) {
                $table->json('meta')->nullable()->after('questions');
            }
        });
    }

    public function down(): void
    {
        Schema::table('analyses', function (Blueprint $table): void {
            foreach (['summary', 'risk_score', 'meta'] as $column) {
                if (Schema::hasColumn('analyses', $column)) {
                    $table->dropColumn($column);
                }
            }
        });
    }
};
