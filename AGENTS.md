# AGENTS.md - ScopeWise AI Backend

## Project Overview
ScopeWise AI is an intelligent web-based system for software requirement analysis, scope creep prevention, and project estimation. This repository contains the **backend** built with Laravel and documented with Swagger (OpenAPI).

---

## Strict Rules

### 1. Code Style & Standards
- **PHP**: Follow PSR-12 coding standards
- **Naming**: PascalCase for classes, camelCase for methods/variables, snake_case for database columns
- **File naming**: PascalCase for class files (e.g., `RequirementController.php`)
- **One class per file** - No multiple classes in single file
- **No magic numbers** - Use constants or config files
- **Use strict types** - Add `declare(strict_types=1);` at top of PHP files

### 2. Controller Structure
- **Resource controllers** for CRUD operations
- **Maximum 7 methods per controller** (index, create, store, show, edit, update, destroy)
- **No business logic in controllers** - Use Services or Actions
- **Form Requests** for validation
- **API Resources** for JSON transformation
- **Maximum 100 lines per controller method**

### 3. File Organization
```
app/
├── Http/
│   ├── Controllers/
│   │   ├── Api/
│   │   │   ├── AuthController.php
│   │   │   ├── ProjectController.php
│   │   │   ├── RequirementController.php
│   │   │   ├── AnalysisController.php
│   │   │   └── QuestionController.php
│   │   └── Controller.php
│   ├── Middleware/
│   │   ├── Authenticate.php
│   │   └── Cors.php
│   ├── Requests/
│   │   ├── Auth/
│   │   │   ├── RegisterRequest.php
│   │   │   └── LoginRequest.php
│   │   ├── Project/
│   │   │   ├── StoreProjectRequest.php
│   │   │   └── UpdateProjectRequest.php
│   │   └── Requirement/
│   │       └── AnalyzeRequirementRequest.php
│   └── Resources/
│       ├── UserResource.php
│       ├── ProjectResource.php
│       ├── RequirementResource.php
│       └── AnalysisResource.php
├── Models/
│   ├── User.php
│   ├── Project.php
│   ├── Requirement.php
│   ├── Analysis.php
│   ├── Module.php
│   ├── Category.php
│   └── RiskFactor.php
├── Services/
│   ├── AuthService.php
│   ├── ProjectService.php
│   ├── RequirementService.php
│   └── AnalysisService.php
├── Enums/
│   ├── RequirementStatus.php
│   ├── RiskLevel.php
│   └── ComplexityLevel.php
└── Exceptions/
    ├── ValidationException.php
    └── NotFoundException.php
```

### 4. Database & Migrations
- **Use migrations** for all database changes
- **Naming convention**: `create_{table}_table`, `add_{column}_to_{table}_table`
- **Always include down() method** for rollback
- **Use foreign key constraints** for relationships
- **Index foreign keys** for performance
- **Use soft deletes** for user data

### 5. API Design (RESTful)
- **Resource routes** for CRUD
- **Consistent response format**:
```json
{
  "success": true,
  "data": {},
  "message": "Success message",
  "meta": {
    "current_page": 1,
    "last_page": 5,
    "per_page": 10,
    "total": 50
  }
}
```
- **Error response format**:
```json
{
  "success": false,
  "message": "Error message",
  "errors": {
    "field": ["Error detail"]
  }
}
```
- **Use proper HTTP status codes**: 200, 201, 400, 401, 403, 404, 422, 500

### 6. Authentication & Security
- **Laravel Sanctum** for API token authentication
- **Password hashing** with bcrypt
- **CSRF protection** for web routes
- **CORS configuration** for frontend domain
- **Rate limiting** on auth endpoints
- **Input validation** on all endpoints
- **SQL injection prevention** - Use Eloquent/Query Builder

### 7. Testing
- **PHPUnit** for unit tests
- **Feature tests** for API endpoints
- **Test naming**: `test_method_name_with_condition`
- **Minimum 70% code coverage**
- **Test database** - Use separate test database
- **Factories** for test data generation

### 8. Git Workflow
- **Branch naming**: `feature/short-description`, `fix/short-description`
- **Conventional commits**: `feat:`, `fix:`, `docs:`, `refactor:`
- **No direct commits to main** - All changes via pull requests
- **Database migrations** must be tested before commit

### 9. Performance
- **Eager loading** - Prevent N+1 query problems
- **Database indexing** - Index frequently queried columns
- **Caching** - Use Redis for frequently accessed data
- **Pagination** - Always paginate list responses
- **Queue jobs** - Use queues for heavy operations

### 10. Documentation
- **Swagger/OpenAPI** for all API endpoints
- **PHPDoc blocks** for all public methods
- **README.md** with setup instructions
- **CHANGELOG.md** for version changes

---

## Tech Stack
- Laravel 10
- PHP 8.1+
- MySQL/PostgreSQL
- Laravel Sanctum (Authentication)
- Swagger/OpenAPI (API Documentation)
- Composer (Dependencies)

---

## Database Schema

### Users Table
- id (bigint, primary key)
- name (string)
- email (string, unique)
- password (string, hashed)
- role (enum: 'user', 'admin')
- remember_token (string, nullable)
- created_at (timestamp)
- updated_at (timestamp)
- deleted_at (timestamp, nullable)

### Projects Table
- id (bigint, primary key)
- user_id (bigint, foreign key)
- name (string)
- description (text, nullable)
- status (enum: 'active', 'completed', 'archived')
- created_at (timestamp)
- updated_at (timestamp)
- deleted_at (timestamp, nullable)

### Requirements Table
- id (bigint, primary key)
- project_id (bigint, foreign key)
- content (text)
- category (string, nullable)
- priority (enum: 'low', 'medium', 'high', 'critical')
- status (enum: 'pending', 'analyzed', 'approved', 'rejected')
- created_at (timestamp)
- updated_at (timestamp)

### Analyses Table
- id (bigint, primary key)
- requirement_id (bigint, foreign key)
- classification (string)
- complexity_score (decimal)
- risk_level (enum: 'low', 'medium', 'high', 'critical')
- estimated_hours (decimal, nullable)
- estimation_method (string, nullable)
- created_at (timestamp)
- updated_at (timestamp)

### Modules Table
- id (bigint, primary key)
- analysis_id (bigint, foreign key)
- name (string)
- description (text, nullable)
- complexity (decimal)
- estimated_hours (decimal)
- created_at (timestamp)
- updated_at (timestamp)

### Categories Table
- id (bigint, primary key)
- name (string)
- description (text, nullable)
- parent_id (bigint, foreign key, nullable)
- created_at (timestamp)
- updated_at (timestamp)

### Risk Factors Table
- id (bigint, primary key)
- analysis_id (bigint, foreign key)
- factor (string)
- level (enum: 'low', 'medium', 'high')
- mitigation (text, nullable)
- created_at (timestamp)
- updated_at (timestamp)

---

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login
- `POST /api/auth/logout` - Logout (requires auth)
- `GET /api/auth/me` - Get current user (requires auth)

### Projects
- `GET /api/projects` - List projects (requires auth)
- `POST /api/projects` - Create project (requires auth)
- `GET /api/projects/{id}` - Get project (requires auth)
- `PUT /api/projects/{id}` - Update project (requires auth)
- `DELETE /api/projects/{id}` - Delete project (requires auth)

### Requirements
- `POST /api/requirements/analyze` - Submit requirement text (requires auth)
- `GET /api/requirements/{id}` - Get requirement details (requires auth)
- `GET /api/projects/{id}/requirements` - List project requirements (requires auth)
- `PUT /api/requirements/{id}` - Update requirement (requires auth)
- `DELETE /api/requirements/{id}` - Delete requirement (requires auth)

### Analysis
- `GET /api/analysis/{id}` - Get analysis results (requires auth)
- `GET /api/analysis/{id}/questions` - Get generated questions (requires auth)
- `GET /api/history` - Get analysis history (requires auth)

---

## Environment Variables
```env
APP_NAME=ScopeWise AI
APP_ENV=local
APP_KEY=
APP_DEBUG=true
APP_URL=http://localhost:8000

DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=scopewise_ai
DB_USERNAME=root
DB_PASSWORD=

SANCTUM_STATEFUL_DOMAINS=localhost:5173
SESSION_DRIVER=cookie
CACHE_DRIVER=file

ML_SERVICE_URL=http://localhost:5000
```

---

## Running the Project
```bash
# Install dependencies
composer install

# Copy environment file
cp .env.example .env

# Generate application key
php artisan key:generate

# Run migrations
php artisan migrate

# Seed database (optional)
php artisan db:seed

# Start development server
php artisan serve

# Server runs at http://localhost:8000

# Generate Swagger documentation
php artisan l5-swagger:generate

# Access Swagger UI
# http://localhost:8000/api/documentation
```

---

## Testing Commands
```bash
# Run all tests
php artisan test

# Run specific test file
php artisan test --filter=AuthTest

# Run with coverage
php artisan test --coverage

# Run feature tests only
php artisan test --testsuite=Feature
```
