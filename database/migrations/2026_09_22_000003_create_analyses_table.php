<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('analyses', function (Blueprint $table) {
            $table->id();
            $table->foreignId('requirement_id')->constrained()->cascadeOnDelete();
            $table->string('classification');
            $table->decimal('complexity_score', 5, 2);
            $table->enum('risk_level', ['low', 'medium', 'high', 'critical']);
            $table->decimal('estimated_hours', 8, 2)->nullable();
            $table->string('estimation_method')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('analyses');
    }
};
