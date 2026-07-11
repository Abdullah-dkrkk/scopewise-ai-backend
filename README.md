# ScopeWise AI Backend

Laravel-based backend API for ScopeWise AI - an intelligent web-based system for software requirement analysis, scope creep prevention, and project estimation.

## Tech Stack
- Laravel 10
- PHP 8.1+
- MySQL/PostgreSQL
- Laravel Sanctum (Authentication)
- Swagger/OpenAPI (API Documentation)

## Quick Setup

### Prerequisites
- PHP 8.1 or higher
- Composer
- MySQL 8.0+ or PostgreSQL 14+
- Node.js (for frontend)

### Installation

1. Clone the repository
```bash
git clone https://github.com/Abdullah-dkrkk/scopewise-ai-backend.git
cd scopewise-ai-backend
```

2. Install PHP dependencies
```bash
composer install
```

3. Environment setup
```bash
cp .env.example .env
php artisan key:generate
```

4. Configure database in `.env`
```env
DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=scopewise_ai
DB_USERNAME=root
DB_PASSWORD=
```

5. Run migrations
```bash
php artisan migrate
```

6. Start development server
```bash
php artisan serve
```

API runs at: `http://localhost:8000`

## API Documentation

After starting the server, access Swagger UI at:
```
http://localhost:8000/api/documentation
```

Generate Swagger docs:
```bash
php artisan l5-swagger:generate
```

## Testing
```bash
php artisan test
```

## Project Structure
- `app/Http/Controllers/Api/` - API Controllers
- `app/Models/` - Eloquent Models
- `app/Services/` - Business Logic
- `app/Http/Requests/` - Form Validation
- `app/Http/Resources/` - API Resources
- `database/migrations/` - Database Migrations
- `routes/api.php` - API Routes

## License
MIT
