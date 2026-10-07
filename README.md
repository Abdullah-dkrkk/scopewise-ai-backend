# ScopeWise AI Backend

Laravel-based backend API for ScopeWise AI - an intelligent web-based system for software requirement analysis, scope creep prevention, and project estimation.

## Tech Stack
- Laravel 13
- PHP 8.3
- MySQL/PostgreSQL (SQLite for local development)
- Laravel Sanctum (Authentication)
- Swagger/OpenAPI (API Documentation)
- Flask + scikit-learn (ML inference service, separate container)

## Architecture

Requirement analysis is **asynchronous** and runs through a queue:

```
POST /api/requirements
  → RequirementService stores the requirement
  → AnalyzeRequirement dispatched on the "analysis" queue (after commit)
  → AnalysisPipeline calls the ML service
      ├─ success  → AnalysisWriter persists, estimation_method = "ml_service"
      └─ failure  → HeuristicEstimator, estimation_method = "heuristic_fallback"
  → GET /api/requirements/{id} returns the result
```

Three properties the design guarantees:

- **The user is never left waiting.** ML calls happen in a queue job, not in
  the request lifecycle.
- **The user is never left without an estimate.** If the ML service is
  unreachable, times out or returns something unusable, a deterministic local
  heuristic produces the analysis instead.
- **The source is always honest.** `estimation_method` is `ml_service` or
  `heuristic_fallback`. A rule-based estimate is never presented as a model
  prediction.

| Component | File |
|-----------|------|
| HTTP client, timeouts, retries, auth | `app/Services/Ml/MlClient.php` |
| Untrusted-payload normalisation | `app/Services/Ml/MlAnalysisResult.php` |
| Fallback estimator | `app/Services/Ml/HeuristicEstimator.php` |
| Orchestration | `app/Services/Ml/AnalysisPipeline.php` |
| Transactional persistence | `app/Services/Ml/AnalysisWriter.php` |
| Queue job | `app/Jobs/AnalyzeRequirement.php` |

The ML service itself lives in [`ml-service/`](ml-service/README.md).

## Quick Setup

### Prerequisites
- PHP 8.3 or higher
- Composer
- MySQL 8.0+ or PostgreSQL 14+ (optional for local dev, SQLite works)
- Python 3.13 (only if running the ML service locally)

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

5. Configure the ML connection in `.env`
```env
ML_SERVICE_URL=http://localhost:5000
# Must match ML_SERVICE_API_KEY in the ML service environment.
ML_SERVICE_TOKEN=
# Set false if you want ML failures to surface instead of falling back.
ML_FALLBACK_ENABLED=true
```

6. Run migrations
```bash
php artisan migrate
```

7. Start the queue worker
```bash
php artisan queue:work --queue=analysis,default
```
Without a worker running, requirements stay `pending` and no analysis is
produced.

8. Start development server
```bash
php artisan serve
```

API runs at: `http://localhost:8000`

### Running the ML service locally

```bash
cd ml-service
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # then set ML_SERVICE_API_KEY
python app.py
```

Without the ML service the backend still works: `ML_FALLBACK_ENABLED=true`
means every analysis is produced by the local heuristic and labelled as such.

## API Endpoints

All routes are under `/api` and require a Sanctum bearer token except
`register` and `login`.

| Method | Path | Ability | Purpose |
|--------|------|---------|---------|
| POST | `/auth/register` | – | Create an account |
| POST | `/auth/login` | – | Issue a token |
| POST | `/auth/logout` | – | Revoke the current token |
| GET | `/auth/me` | – | Current user |
| GET | `/projects` | `projects:read` | List projects |
| POST | `/projects` | `projects:write` | Create a project |
| GET | `/projects/{id}` | `projects:read` | Project detail |
| PUT | `/projects/{id}` | `projects:write` | Update a project |
| DELETE | `/projects/{id}` | `projects:write` | Delete a project |
| GET | `/projects/{id}/requirements` | `requirements:read` | List requirements |
| POST | `/requirements` | `requirements:write` | Create, queues analysis |
| GET | `/requirements/{id}` | `requirements:read` | Requirement with analysis |
| PUT | `/requirements/{id}` | `requirements:write` | Update |
| DELETE | `/requirements/{id}` | `requirements:write` | Delete |
| POST | `/requirements/{id}/analyze` | `requirements:write` | Re-run analysis |
| GET | `/analysis/{id}` | `analysis:read` | Analysis detail |
| GET | `/analysis/{id}/questions` | `analysis:read` | Clarification questions |
| GET | `/history` | `analysis:read` | Analysis history |

Ownership is enforced by policies on every route: a non-admin can only reach
their own projects, requirements and analyses.

### Rate limits

| Bucket | Limit |
|--------|-------|
| `login` | 5 per minute, keyed on email + IP |
| `register` | 3 per hour, keyed on IP |
| `analyze` | 20 per minute, keyed on user or IP |
| `api` | 120 per minute, keyed on user or IP |

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

Code style:
```bash
vendor\bin\pint --test
```

ML service tests:
```bash
cd ml-service && pytest
```

## Project Structure
- `app/Http/Controllers/Api/` - API Controllers
- `app/Policies/` - Ownership and authorisation rules
- `app/Models/` - Eloquent Models
- `app/Services/` - Business logic
- `app/Services/Ml/` - ML client, pipeline, fallback, persistence
- `app/Jobs/` - Queued background work
- `app/Http/Requests/` - Form validation
- `app/Http/Resources/` - API Resources
- `database/migrations/` - Database migrations
- `routes/api.php` - API routes
- `ml-service/` - Python inference service

## Production Notes

- Set `APP_DEBUG=false`. Debug mode leaks stack traces and environment values.
- Set `ML_SERVICE_TOKEN` from a secret manager and keep the ML service on a
  private network. The shared secret is its only authentication layer.
- Run `php artisan queue:work --queue=analysis,default` under Supervisor; a
  stopped worker silently stops all analysis.
- Watch for requirements stuck in `pending`. A permanently failed job logs and
  resets the requirement so it can be retried.
- Consider `SANCTUM_EXPIRATION` appropriate to your session policy; the default
  is 1440 minutes.
- `analyses.requirement_id` has a unique index, so a requirement can only ever
  hold one analysis. Re-analysis replaces it.

## License
MIT
