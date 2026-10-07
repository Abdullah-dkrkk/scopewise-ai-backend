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
- Laravel 13
- PHP 8.3+
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
- `POST /api/requirements` - Create requirement, queues analysis (returns 201)
- `POST /api/requirements/{id}/analyze` - Re-run analysis (returns 202)
- `GET /api/requirements/{id}` - Get requirement details (requires auth)
- `GET /api/projects/{id}/requirements` - List project requirements (requires auth)
- `PUT /api/requirements/{id}` - Update requirement, re-queues if content changed
- `DELETE /api/requirements/{id}` - Delete requirement (requires auth)

### Analysis
- `GET /api/analysis/{id}` - Get analysis results (requires auth)
- `GET /api/analysis/{id}/questions` - Get generated questions (requires auth)
- `GET /api/history` - Get analysis history (requires auth)

All authenticated routes additionally require the matching Sanctum ability
(`projects:read`, `projects:write`, `requirements:read`, `requirements:write`,
`analysis:read`) and are scoped to the owner by policies.

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

QUEUE_CONNECTION=database

ML_SERVICE_URL=http://localhost:5000
# Shared secret; must equal the ML service's ML_SERVICE_API_KEY.
ML_SERVICE_TOKEN=
ML_SERVICE_TIMEOUT=30
# false makes ML failures surface instead of falling back to the heuristic.
ML_FALLBACK_ENABLED=true
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

# Start the queue worker (analysis happens here, not in the request)
php artisan queue:work --queue=analysis,default

# Start development server
php artisan serve

# Server runs at http://localhost:8000

# ML service (separate terminal, optional; the backend falls back without it)
cd ml-service && python app.py

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

# Code style check
vendor\bin\pint --test

# ML service tests
cd ml-service && pytest
```

---

## Analysis Pipeline (Wave 2+)

Requirement analysis is **asynchronous**. There is no synchronous ML call in a
controller or route.

### Flow

```
POST /api/requirements
  → RequirementService::store()
  → AnalyzeRequirement::dispatch()->afterCommit()  (queue: "analysis")
  → AnalysisPipeline::run()
      → MlClient::analyze()          (30s timeout, 3 attempts, X-Service-Token)
      → MlAnalysisResult::fromPayload()   (clamp + validate untrusted payload)
      → AnalysisWriter::persist()         (single transaction)
  → AnalysisWriter sets status = analyzed
```

### Non-negotiable rules

- **`estimation_method` must be honest.** `ml_service` only when the ML service
  answered. Any local heuristic result is `heuristic_fallback`. Never label a
  rule-based estimate as a model prediction.
- **Never call the ML service from a controller.** Use `AnalyzeRequirement`.
- **Always dispatch with `afterCommit()`.** A worker must never look up a
  requirement row that has not committed.
- **Clamp every ML value.** `MlAnalysisResult` is the only place that turns
  untrusted JSON into a persistable result. Do not bypass it.
- **Never store a partially written analysis.** `AnalysisWriter::persist()`
  wraps the parent, modules and risk factors in one `DB::transaction`.
- **A requirement has exactly one analysis.** `analyses.requirement_id` has a
  unique index. `AnalysisWriter::persist()` deletes the previous row *inside*
  the same transaction as the insert, so a failed re-analysis rolls back to the
  previous result rather than leaving the requirement with nothing.
- **Never pre-delete an analysis to "make room".** `POST .../analyze` clears the
  stale analysis in the request on purpose, so the UI cannot render an outdated
  estimate next to a `pending` status. That is a presentation decision, not a
  persistence one, and it is the only place it belongs.
- **The ML service must never block a user request.** Timeouts, retries and the
  queue exist for this reason.

### Failure behaviour

| Failure | Behaviour |
|---------|-----------|
| ML unreachable / 5xx / timeout | Retry (3 attempts), then heuristic fallback |
| ML 4xx | No retry, then heuristic fallback |
| Unrecognised ML payload | Heuristic fallback, payload discarded |
| Database failure | Transaction rolls back, job retries, previous analysis survives |
| Retries exhausted | Requirement reset to `pending` and re-analysable |
| `ML_FALLBACK_ENABLED=false` | Failure surfaces instead of falling back |

The job is `ShouldBeUnique` per requirement, so a double click or a duplicate
dispatch cannot queue two competing analyses. `failed()` removes any partial
analysis and resets the requirement to `pending` rather than leaving it looking
complete.

### Adding a field to the analysis

1. Add a migration.
2. Add it to `MlAnalysisResult` with clamping.
3. Add it to `AnalysisWriter::persist()`.
4. Add it to `AnalysisResource`.
5. Extend `MlPipelineTest` and `ml-service/tests/test_analyze_contract.py`.

The PHP and Python tests must be updated together: the Python side owns the
response shape, the PHP side owns the database shape.
