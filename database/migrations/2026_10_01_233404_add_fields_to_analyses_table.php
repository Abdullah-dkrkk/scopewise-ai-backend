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
            if (! Schema::hasColumn('analyses', 'project_id')) {
                $table->foreignId('project_id')->nullable()->after('requirement_id')->constrained()->nullOnDelete();
            }
            if (! Schema::hasColumn('analyses', 'confidence')) {
                $table->unsignedTinyInteger('confidence')->nullable()->after('estimated_hours');
            }
            if (! Schema::hasColumn('analyses', 'questions')) {
                $table->json('questions')->nullable()->after('confidence');
            }
            if (! Schema::hasColumn('analyses', 'status')) {
                $table->string('status')->default('completed')->index()->after('questions');
            }
            if (! Schema::hasColumn('analyses', 'progress')) {
                $table->unsignedTinyInteger('progress')->default(100)->after('status');
            }
            if (! Schema::hasColumn('analyses', 'error')) {
                $table->text('error')->nullable()->after('progress');
            }
        });
    }

    public function down(): void
    {
        Schema::table('analyses', function (Blueprint $table): void {
            if (Schema::hasColumn('analyses', 'project_id')) {
                $table->dropConstrainedForeignId('project_id');
            }
            foreach (['confidence', 'questions', 'status', 'progress', 'error'] as $column) {
                if (Schema::hasColumn('analyses', $column)) {
                    $table->dropColumn($column);
                }
            }
        });
    }
};
