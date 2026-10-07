<?php

declare(strict_types=1);

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('risk_factors', function (Blueprint $table): void {
            if (! Schema::hasColumn('risk_factors', 'description')) {
                $table->text('description')->nullable()->after('level');
            }
        });
    }

    public function down(): void
    {
        Schema::table('risk_factors', function (Blueprint $table): void {
            if (Schema::hasColumn('risk_factors', 'description')) {
                $table->dropColumn('description');
            }
        });
    }
};
