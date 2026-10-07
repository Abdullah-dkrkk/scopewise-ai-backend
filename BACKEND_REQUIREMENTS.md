# Backend Requirements — ScopeWise AI

**Audience:** backend team (`scopewise-ai-backend`)
**Status:** frontend is built and ready. This document is the complete contract the frontend needs in order to switch from mocks to live data with zero frontend code changes.

Frontend repo: `scopewise-ai-frontend` · Backend repo: `scopewise-ai-backend`

---

## 0. TL;DR

The frontend currently runs against an in-browser mock (`src/services/mock/`). It is **not** integrated with Laravel at all. There are 17 contract mismatches and 5 missing endpoints. Every screen is currently written against the view models in [`src/api/viewModels.js`](src/api/viewModels.js) — that file is the single source of truth for what the frontend expects.

**The fastest path to integration** is for `POST /api/requirements` to return the ML service's `/analyze` payload (which already contains almost everything the UI renders) in the envelope described in §3. That single change unblocks the entire application.

---

## 1. Current backend inventory (audit of `scopewise-ai-backend`)

Stack: Laravel 11, Sanctum (Bearer **and** stateful cookie via `bootstrap/app.php` → `statefulApi()`), Eloquent, plus a standalone Flask ML service on port 5000.

Base prefix: `/api` (Laravel auto-prefix on `routes/api.php`).

### 1.1 Endpoints that exist today

| Method | Path | Auth | Request body | Response |
|---|---|---|---|---|
| POST | `/api/auth/register` | public | `{name,email,password}` | `201 {success,data:{user,token},message}` |
| POST | `/api/auth/login` | public | `{email,password}` | `200 {success,data:{user,token},message}` / `401 {success:false,message}` |
| POST | `/api/auth/logout` | sanctum | — | `{success,message}` |
| GET | `/api/auth/me` | sanctum | — | `{success,data:{user}}` |
| GET | `/api/projects` | sanctum | — | paginated `ProjectResource` (10/page) |
| POST | `/api/projects` | sanctum | `{name,description?,status?}` | `201 {success,data,message}` |
| GET | `/api/projects/{id}` | sanctum | — | `{success,data}` |
| PUT/PATCH | `/api/projects/{id}` | sanctum | partial | `{success,data,message}` |
| DELETE | `/api/projects/{id}` | sanctum | — | `{success,message}` |
| GET | `/api/projects/{id}/requirements` | sanctum | — | paginated `RequirementResource` |
| POST | `/api/requirements` | sanctum | `{project_id,content,category?,priority?}` | `201 {success,data,message}` |
| GET | `/api/requirements/{id}` | sanctum | — | `{success,data}` |
| PUT | `/api/requirements/{id}` | sanctum | partial | `{success,data,message}` |
| DELETE | `/api/requirements/{id}` | sanctum | — | `{success,message}` |
| GET | `/api/analysis/{id}` | sanctum | — | `{success,data:AnalysisResource}` |
| GET | `/api/analysis/{id}/questions` | sanctum | — | `{success,data:[{category,question,priority}]}` |
| GET | `/api/history` | sanctum | — | paginated `AnalysisResource` |

### 1.2 Resource shapes today (snake_case)

```jsonc
// ProjectResource  — NOTE: requirements_count is computed via withCount() but NOT exposed
{ "id":1, "user_id":1, "name":"...", "description":"...", "status":"active",
  "created_at":"2026-09-22T10:00:00.000000Z", "updated_at":"..." }

// RequirementResource
{ "id":1, "project_id":1, "content":"...", "category":null, "priority":"medium",
  "status":"analyzed", "analysis":{...}|null, "created_at":"...", "updated_at":"..." }

// AnalysisResource
{ "id":1, "requirement_id":1,
  "classification":"authentication",        // string, NOT one of the 3 the UI knows
  "complexity_score":3.4,                  // float 1.0–5.0
  "risk_level":"high",                      // low|medium|high|critical
  "estimated_hours":13.6,                  // number
  "estimation_method":"ai_analysis",
  "modules":[{ "id":1,"analysis_id":1,"name":"Core Logic","description":"...",
               "complexity":1.36,"estimated_hours":4.08, "created_at":"...","updated_at":"..." }],
  "risk_factors":[{ "id":1,"analysis_id":1,"factor":"Scope Creep Risk","level":"high",
                    "mitigation":"...", "created_at":"...","updated_at":"..." }],
  "created_at":"...", "updated_at":"..." }

// UserResource
{ "id":1, "name":"...", "email":"...", "role":"user", "created_at":"...", "updated_at":"..." }
```

### 1.3 Flask ML service (`ml-service/app.py`, port 5000)

Not called by Laravel. Open `CORS(app)`, binds `0.0.0.0`, runs `debug=True`.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/health` | — | `{status,service}` |
| POST | `/analyze` | `{text}` | full analysis (see below) |
| POST | `/classify` | `{text}` | `{predicted_category, confidence, alternatives[]}` |
| POST | `/complexity` | `{text}` | `{complexity_score, complexity_level, features, breakdown}` |
| POST | `/features` | `{text}` | `{features[], total_features, total_estimated_hours, feature_summary[]}` |
| POST | `/risk` | `{text}` | `{overall_risk, risk_score, risk_factors[], total_risk_factors}` |
| POST | `/questions` | `{text}` | `{questions[]}` |
| POST | `/timeline` | `{text}` | timeline object |
| POST | `/train` | — | `{status, classifier_type, complexity_type}` |

`POST /analyze` returns:

```jsonc
{
  "classification": {
    "category": "authentication",              // one of the 9 labels below
    "confidence": 0.9231,                     // 0.0–1.0
    "alternatives": [{ "category": "api", "confidence": 0.0412 }]
  },
  "complexity": {
    "score": 3.4,                             // 1.0–5.0
    "level": "medium",                        // low|medium|high|critical
    "breakdown": { "ml_score": 3.2, "keyword_score": 3.8, "weighted_final": 3.4 }
  },
  "features": {
    "detected": [{ "feature_type":"Authentication & Authorization",
                   "matches":["login","password"], "match_count":2, "estimated_hours":10 }],
    "total_count": 3,
    "summary": ["Authentication & Authorization", "Notifications"]
  },
  "risk": {
    "overall_level": "high",                  // low|medium|high|critical
    "score": 5.6,                             // 0.0–10.0
    "factors": [{ "factor":"High Technical Complexity", "level":"high",
                  "description":"...", "mitigation":"..." }],
    "total_risk_factors": 3,             // number, count of {risk_factors}
  },
  "questions": [{ "question":"...", "category":"authentication", "priority":"high" }],
  "timeline": {
    "total_estimated_hours": 92.4,
    "total_working_days": 16,
    "total_calendar_days": 22,
    "phases": { "planning_hours":…, "development_hours":…, "testing_hours":…,
                "deployment_hours":…, "buffer_hours":…, "total_adjusted_hours":… },
    "milestones": [{ "phase":"Planning & Requirements", "estimated_days":3, "description":"..." }],
    "team_configs": [{ "size":2, "description":"Small team (1 dev + 1 QA)",
                       "estimated_days":8, "estimated_weeks":1.6 }],
    "recommended_team_size": 2,
    "recommended_timeline_weeks": 1.6
  },
  "modules": [{ "name":"...", "description":"...", "complexity":1.7, "estimated_hours":10 }],
  "summary": "This is a moderately complex authentication requirement with 3 detected features…"
}
```

**Classifier label set** (from `ml-service/training_data/requirements.json`, 44 rows):
`e-commerce` (6) · `ui_design` (5) · `general` (5) · `integration` (5) · `authentication` (5) · `dashboard` (5) · `api` (5) · `marketing` (4) · `content_management` (4)

---

## 2. Mismatch register (17 items)

### 2.1 Blockers — app does not function

| # | Issue | Detail |
|---|---|---|
| B1 | **Envelope inconsistent** | Some endpoints return `{success,data}`; paginated ones return `{data,meta,links}`. Frontend unwraps both, but errors differ: Laravel returns `{message,errors}` on 422, `{message}` on 401. |
| B2 | **List endpoints return an object** | `GET /projects` → `{data:[…],meta,links}`. Frontend previously did `setProjects(res.data)` → crash. **Fixed on the frontend** (unwraps pagination), but see §3 for the recommended standard. |
| B3 | **No analyze endpoint** | Frontend calls `POST /requirements/analyze {projectId,text}` → `{analysisId}`. Backend has `POST /requirements {project_id,content}`. **Path, payload and response all differ.** |
| B4 | **Analysis is never created** | `RequirementController::store` never calls `AnalysisService::analyze()`. No `Analysis` row is ever written. The core feature is dead server-side. |
| B5 | **`GET /dashboard/stats` missing** | Called by `Dashboard.jsx`. 404 → entire Dashboard fails. |
| B6 | **`GET /dashboard/activity` missing** | Same. |
| B7 | **`PUT /auth/me` missing** | Called by `Profile.jsx` to save name/email and to change password. 404. |
| B8 | **`POST /auth/forgot-password` missing** | `ForgotPassword.jsx` depends on it. 404. |
| B9 | **`POST /analysis/{id}/questions/{qid}` missing** | Frontend posts an answer. Backend has GET-only. Q&A loop is broken. |
| B10 | **`analysis.questions` does not exist** | Questions are a separate endpoint with no `id` and no `status` field. Frontend's Q&A UI is driven by `questions[].status`. |

### 2.2 Field-level mismatches

| Frontend expects | Backend returns | Fix |
|---|---|---|
| `complexity` (int 0–100, drives a `%` bar) | `complexity_score` (float 1.0–5.0) | Frontend maps `score × 20` today. **Backend should return 0–100 directly.** |
| `confidence` (0–100 int) | absent; ML has `classification.confidence` (0.0–1.0) | Backend should return `confidence` as 0–100 int. |
| `risk` (int 0–100) | absent; ML has `risk.score` (0.0–10.0) | Backend should return `risk` as 0–100 int. |
| `estimation.{effort,cost,timeline}` | `estimated_hours` only | Frontend derives today. **Backend should return all three.** |
| `keywords[]` | absent | Derive from `features.detected[].feature_type`, or return explicitly. |
| `missingInfo[]` | absent | Derive from unanswered questions, or return explicitly. |
| `requirementId` | `requirement_id` | Frontend normalises snake→camel. |
| `text` | `content` | Frontend normalises. |
| `projectName` (History) | not exposed — `AnalysisResource` has no project relation | Backend should include `project_name`. |
| `requirementsCount` | computed via `withCount()` but not in `ProjectResource` | Add to resource. |
| `id` types | ints | Frontend treats as strings; consistent. |

### 2.3 Enum mismatches (silent wrong rendering — highest severity)

| Concept | Frontend handles | Backend / ML returns | Consequence |
|---|---|---|---|
| classification | `functional`, `technical`, `non-functional` | `authentication`, `e-commerce`, `ui_design`, `general`, `integration`, `dashboard`, `api`, `marketing`, `content_management` | Badge **always falls back to "Functional"** |
| risk level | `low`, `medium`, `high` | `low`, `medium`, `high`, **`critical`** | **`critical` renders as "Low Risk" with a green bar** |

The frontend now ships a canonical mapping in [`src/api/enums.js`](src/api/enums.js) and degrades gracefully on unknown values. **The backend should adopt the canonical values in §4.**

---

## 3. Required response standard

### 3.1 Success envelope

```jsonc
{ "success": true, "data": <T>, "message": "optional human string" }
```

`data` is either a single object or an array. **No more bare `AnonymousResourceCollection` returns** — wrap them.

### 3.2 List envelope (pagination)

```jsonc
{
  "success": true,
  "data": [ /* items */ ],
  "meta": { "current_page": 1, "per_page": 20, "total": 87, "last_page": 5 },
  "links": { "first": null, "last": "...", "prev": null, "next": "..." }
}
```

Frontend already tolerates Laravel's native shape, but please switch for consistency.

### 3.3 Error envelope

Every non-2xx response:

```jsonc
{ "success": false, "message": "Human readable sentence.", "errors": { "field": ["reason"] } }
```

- `401` — invalid/expired credentials
- `403` — authenticated but not the owner (**use this consistently — see §5**)
- `404` — resource not found **or** not visible to this user
- `422` — validation, with per-field `errors`
- `429` — rate limited, include `Retry-After` header
- `500`/`503` — generic message, log the detail server-side

Register a global handler in `bootstrap/app.php`:

```php
->withExceptions(function (Exceptions $exceptions): void {
    $exceptions->shouldRenderJsonWhen(fn (Request $r) => $r->is('api/*') || $r->expectsJson());
    $exceptions->render(function (Throwable $e, Request $request) {
        if (! $request->is('api/*')) return null;
        return response()->json([
            'success' => false,
            'message' => $e instanceof ValidationException
                ? 'Please correct the highlighted fields.'
                : ($e->getMessage() ?: 'Something went wrong.'),
            'errors'  => $e instanceof ValidationException ? $e->errors() : null,
        ], $e instanceof ValidationException ? 422 : ($e->getStatusCode() ?: 500));
    });
})
```

### 3.4 Naming convention

**Pick camelCase for all JSON keys.** The frontend normalises snake→camel defensively so it works either way, but camelCase removes an entire class of bugs. Easiest path: a response middleware that snake→camel-cases all keys.

---

## 4. Canonical enums

### 4.1 `classification`

| Value | Display | Bucket |
|---|---|---|
| `functional` | Functional | functional |
| `technical` | Technical | technical |
| `non_functional` | Non-Functional | non-functional |
| `authentication` | Authentication | technical |
| `api` | API | technical |
| `integration` | Integration | technical |
| `data_model` | Data Model | technical |
| `ui_design` | UI/UX Design | functional |
| `reporting` | Reporting | functional |
| `e_commerce` | E-Commerce | functional |
| `content_management` | Content Management | functional |
| `security` | Security | technical |
| `performance` | Performance | non-functional |
| `general` | General | functional |

Unknown values must degrade to a neutral badge, never a crash, and never silently mislabel.

### 4.2 `risk_level` / `complexity_level`

`low` · `medium` · `high` · `critical`

`critical` **must** be handled everywhere. Frontend now renders it distinctly (red, "Critical Risk").

---

## 5. Security — blocking issues

### 5.1 IDOR (insecure direct object reference) — **critical**

These endpoints perform **no ownership check**. Any authenticated user can read, modify, or delete any other user's data by incrementing the integer ID.

| Endpoint | File | Status |
|---|---|---|
| `GET /analysis/{id}` | `AnalysisController::show` | **no check** |
| `GET /analysis/{id}/questions` | `QuestionController::index` | **no check** |
| `GET /requirements/{id}` | `RequirementController::show` | **no check** |
| `PUT /requirements/{id}` | `RequirementController::update` | **no check** |
| `DELETE /requirements/{id}` | `RequirementController::destroy` | **no check** |
| `GET /projects/{id}` + write | `ProjectController` | ✅ checked |
| `GET /projects/{id}/requirements` | `RequirementController::index` | ✅ checked |

Fix — add a policy and use route model binding scoping:

```php
// app/Policies/AnalysisPolicy.php
public function view(User $user, Analysis $analysis): bool
{
    return $analysis->requirement->project->user_id === $user->id;
}
// register in AuthServiceProvider / bootstrap, then in the controller:
public function show(Analysis $analysis) { $this->authorize('view', $analysis); }
```

Or scope the binding globally in `AppServiceProvider::boot()`:

```php
Analysis::resolveChildRouteBindingQueryUsing(fn ($q, $id) =>
    $q->whereHas('requirement.project', fn ($p) => $p->where('user_id', auth()->id())));
```

Return **404, not 403**, for other users' resources — 403 confirms the ID exists.

### 5.2 No rate limiting — **critical**

`/api/auth/login` and `/api/auth/register` are unthrottled → brute force + mass account creation.

```php
// routes/api.php
Route::middleware('throttle:10,1')->group(function () {
    Route::post('auth/login',    [AuthController::class, 'login']);
    Route::post('auth/register', [AuthController::class, 'register']);
});
Route::middleware('throttle:60,1')->group(function () {
    Route::post('requirements', [RequirementController::class, 'store']); // expensive ML call
});
```

### 5.3 ML service is wide open — **critical**

`CORS(app)` allows every origin, `host='0.0.0.0'`, `debug=True`, and it is **never called by Laravel**. It is an unauthenticated, publicly-reachable inference endpoint. Worse, the frontend `.env.example` exposes `VITE_ML_API_URL`, which would make the browser call it directly and bypass Laravel auth entirely.

Required:
1. **Laravel is the only caller.** Never expose `ml-service` publicly.
2. Remove `CORS(app)` or pin it to nothing; bind `127.0.0.1` only.
3. `debug=False`; serve via gunicorn/uwsgi, not the Flask dev server.
4. Add an internal shared-secret header (`X-Internal-Key`) verified by Laravel.
5. Remove `VITE_ML_API_URL` from the frontend env — the browser never needs it.
6. Add a timeout + circuit breaker on the Laravel→ML call, and a graceful fallback when ML is down.

### 5.4 Production config

`.env.example` ships `APP_DEBUG=true` and `DB_CONNECTION=sqlite`. For production:

```env
APP_ENV=production
APP_DEBUG=false
APP_URL=https://app.yourdomain.com
LOG_LEVEL=warning
SESSION_DRIVER=redis
CACHE_STORE=redis
QUEUE_CONNECTION=redis
DB_CONNECTION=mysql        # not sqlite
SESSION_SECURE_COOKIE=true
SESSION_HTTP_ONLY=true
SESSION_SAME_SITE=lax
BCRYPT_ROUNDS=12
```

Also required: publish and pin `config/cors.php` to the exact frontend origin with `supports_credentials => true` (needed for Sanctum cookie auth). Serve over HTTPS only.

### 5.5 Headers

Send `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and a CSP. Note that Google Fonts is loaded from the CDN on the frontend — either self-host the fonts or allow `fonts.googleapis.com`/`fonts.gstatic.com` in the CSP.

---

## 6. Missing endpoints — exact spec

### 6.1 `POST /api/requirements` (modify existing)

The single most important change. Must create the requirement, run analysis, persist everything, and return the analysis.

**Request**
```jsonc
{ "project_id": 1, "content": "Users should be able to reset…", "category": null, "priority": "medium" }
```

**Response `201`**
```jsonc
{
  "success": true,
  "message": "Requirement analyzed successfully",
  "data": {
    "id": 1,                       // requirement id
    "projectId": 1,
    "text": "Users should be able to reset…",
    "category": null,
    "priority": "medium",
    "status": "analyzed",
    "createdAt": "2026-09-22T10:00:00Z",
    "updatedAt": "2026-09-22T10:00:00Z",
    "analysis": { /* full analysis object, §6.2 */ }
  }
}
```

The frontend navigates to `/app/analysis/{id}` using `data.analysis.id`, and `/api/analysis/{id}` must return the same object.

### 6.2 Analysis object (canonical)

This is the shape `src/api/viewModels.js` maps to. Return it verbatim from `GET /api/analysis/{id}`, `POST /api/requirements`, and `GET /api/history`.

```jsonc
{
  "id": 1,
  "requirementId": 1,
  "projectId": 1,
  "projectName": "Customer Portal",

  "classification": "authentication",     // §4.1
  "confidence": 92,                        // int 0–100

  "complexity": 68,                        // int 0–100  (ML complexity_score × 20)
  "complexityLevel": "medium",             // low|medium|high|critical
  "complexityBreakdown": { "mlScore": 3.2, "keywordScore": 3.8, "weightedFinal": 3.4 },

  "risk": 56,                              // int 0–100  (ML risk_score × 10)
  "riskLevel": "high",                     // §4.2
  "riskFactors": [
    { "id": 1, "factor": "High Technical Complexity", "level": "high",
      "description": "...", "mitigation": "..." }
  ],

  "estimation": {
    "effort": "16 PD",                      // person-days
    "cost": "$8,640",                       // requires a configured rate
    "timeline": "2 weeks",
    "hours": 92.4,
    "workingDays": 16,
    "calendarDays": 22,
    "recommendedTeamSize": 2,
    "method": "ai_analysis"
  },
  "milestones": [
    { "phase": "Planning & Requirements", "estimatedDays": 3, "description": "..." }
  ],

  "modules": [
    { "id": 1, "name": "Authentication & Authorization",
      "description": "...", "complexity": 1.7, "estimatedHours": 10 }
  ],

  "features": [
    { "featureType": "Authentication & Authorization", "matchCount": 2, "estimatedHours": 10 }
  ],

  "keywords": ["Authentication & Authorization", "Notifications"],   // from features
  "missingInfo": ["Expected traffic volume is unclear", "No acceptance criteria defined"],

  "questions": [
    { "id": "q-1", "question": "What authentication methods do you need?",
      "category": "authentication", "priority": "high",
      "status": "pending", "answer": null }
  ],

  "summary": "This is a moderately complex authentication requirement…",
  "createdAt": "2026-09-22T10:00:00Z",
  "updatedAt": "2026-09-22T10:00:00Z"
}
```

**Minimum viable subset** — if you can only ship some of this, ship in this order:
`id`, `classification`, `confidence`, `complexity`, `risk`, `riskLevel`, `estimation.{effort,cost,timeline}`, `questions[]`, `createdAt`.
Everything else degrades gracefully in the UI.

`cost` requires a configurable blended rate. Add `ESTIMATION_HOURLY_RATE` / `ESTIMATION_PER_DIEM_RATE` / `DEFAULT_TEAM_SIZE` to `.env` and document the defaults. Frontend currently falls back to **$540/PD** and a 2-person team.

### 6.3 `GET /api/dashboard/stats`

```jsonc
{ "success": true, "data": {
  "projects": 3, "requirements": 12, "analyses": 9,
  "analysesThisWeek": 4,
  "avgConfidence": 88,
  "highRiskCount": 2,
  "projectStatuses": { "active": 1, "review": 1, "draft": 1 }
} }
```

`highRiskCount` counts `riskLevel` in `high|critical`. `avgConfidence` is an integer 0–100, `0` when there are no analyses.

### 6.4 `GET /api/dashboard/activity`

```jsonc
{ "success": true, "data": [
  { "id": 1, "text": "New requirement analyzed", "project": "Customer Portal",
    "type": "analysis", "at": "2026-09-22T09:00:00Z" }
] }
```

Frontend renders `text`, optional `project`, and a relative timestamp from `at`. Recommend newest-first, cap at 20. **Prefer a real audit log** (`activity` table + model) over deriving it — it is also needed for compliance.

### 6.5 `PUT /api/auth/me`

```jsonc
// request — either field
{ "name": "New Name" }
{ "email": "new@example.com" }

// response
{ "success": true, "message": "Profile updated", "data": { /* UserResource */ } }
```

Rules: `email` must be unique; changing it should require current-password confirmation. Return `422` with `errors.email` on conflict.

### 6.6 `PUT /api/auth/password`

```jsonc
// request
{ "current_password": "old", "password": "new", "password_confirmation": "new" }
// response
{ "success": true, "message": "Password updated", "data": { /* UserResource */ } }
```

Frontend currently sends only `{password}` — **update it to send all three.** On success, revoke all other tokens (`$user->tokens()->where('id','!=',$tokenId)->delete()`).

Note: the frontend calls `changePassword({currentPassword, newPassword})` and sends `{password: newPassword}` to `PUT /auth/me`. Either add `PUT /auth/password` (preferred) or accept `password` on `/auth/me` with `current_password` required.

### 6.7 `POST /api/auth/forgot-password`

```jsonc
// request
{ "email": "user@example.com" }
// response — ALWAYS 200, regardless of whether the email exists (no user enumeration)
{ "success": true, "message": "If an account exists for that email, a reset link has been sent." }
```

Needs a `password_reset_tokens` table (present in the default Laravel migration) and mail. Also add `GET /api/auth/reset/{token}` + `POST /api/auth/reset` to complete the loop, or the `ForgotPassword` page is a dead end.

### 6.8 `POST /api/analysis/{id}/questions/{questionId}`

```jsonc
// request
{ "answer": "Email + password with SSO" }
// response — return the recalculated analysis so confidence can rise
{ "success": true, "message": "Answer recorded", "data": { /* full analysis object, §6.2 */ } }
```

Persist answers on the `Analysis` (JSON column `questions` is fine). Recompute `confidence` upward as questions are answered. Ownership check required. Return `422` for an empty answer.

---

## 7. Queries & pagination

Currently every list hardcodes `->paginate(10)` and ignores query params.

**Required on `GET /projects`:** `?search=`, `?status=`, `?page=`, `?per_page=` (max 100), `?sort=name|created_at`, `?direction=asc|desc`.

**Required on `GET /projects/{id}/requirements`:** `?page=`, `?per_page=`, `?status=`, `?search=`.

**Required on `GET /history`:** `?page=`, `?per_page=`, `?classification=`, `?risk_level=`, `?project_id=`, `?date_from=`, `?date_to=`, `?sort=`.

Notes:
- Default `per_page` should be **20**, and it must be **configurable** — the current hardcoded 10 means a user can never see past their first 10 projects.
- `GET /history` must include `projectName` and `requirementText` (truncated server-side, e.g. 200 chars) or the History table renders blank cells.
- Any endpoint that can grow without bound needs pagination. The frontend has no "load more" UI yet and will need `meta` to drive it.

---

## 8. Data model notes

1. `Analysis` has no `status` column. Long ML calls need one — see §9.
2. `Analysis` has no `project_id`. Add it (denormalised) so History can filter and display without a join.
3. `Analysis.confidence` does not exist as a column. Persist it, don't recompute on every read.
4. `ProjectResource` should expose `requirements_count` — it is already loaded via `withCount()` and then discarded.
5. Add a `categories` lookup table usage — it exists as a migration but is unused; the ML returns free-text `feature_type` strings.
6. Index for the hot paths: `analyses.created_at`, `analyses.risk_level`, `requirements.project_id`, `projects.user_id`.

---

## 9. Long-running analysis (recommended)

Analysis is a synchronous ML call today. At production volume it will exceed gateway timeouts. Recommended: make it a queued job with status polling.

```jsonc
// POST /api/requirements -> 202
{ "success": true, "data": { "id": 1, "status": "pending" } }

// GET /api/analysis/{id} -> 200
{ "success": true, "data": { "id": 1, "status": "processing", "progress": 45, /* … */ } }
// … once done
{ "success": true, "data": { "id": 1, "status": "completed", /* full analysis */ } }
```

`status`: `pending` → `processing` → `completed` | `failed` (with `error`).

The frontend currently assumes synchronous completion and navigates straight to the results page. **If you go async, tell me** and I will add polling + a skeleton state. Budget ~1 hour of frontend work.

Add to `analyses`:
```php
$table->string('status')->default('pending')->index();
$table->unsignedTinyInteger('progress')->default(0);
$table->text('error')->nullable();
$table->json('questions')->nullable();
$table->unsignedTinyInteger('confidence')->nullable();
```

Requires `QUEUE_CONNECTION=redis` and a worker: `php artisan queue:work`.

---

## 10. ML service bugs found during audit

Fixed:

1. ~~**`e-commerce` vs `e_commerce` mismatch.**~~ `generate_questions` now normalises `-` → `_` on the category and every feature key before matching the templates, and the template question categories themselves now use `e_commerce`. Covered by `test_e_commerce_requirements_get_category_specific_questions`.
2. ~~**`total_risk_factors` missing from `/analyze`**~~ — now returned and asserted equal to `len(risk.factors)` in the contract test.

Still open:

3. **`/train` is unauthenticated and re-trains on every process start** (`if __name__ == '__main__'`). Gate it behind an internal key, or delete it from the deployed image.
4. **Only 44 training rows.** Far too few for a production classifier, and the class distribution is 4–6 per label. Expect poor accuracy; plan for retraining with real user data.
5. **`debug=True` + `host=0.0.0.0`** on the Flask dev server. See §5.3.
6. **No timeout or retry** on the Laravel → ML hop. One slow inference blocks a PHP worker.
7. `nltk.download()` runs at import time on every cold start. Move to a build step.

---

## 11. Integration checklist

Backend team — in priority order:

- [ ] Add ownership policies for `Analysis`, `Requirement`, `Question` (§5.1)
- [ ] Add rate limiting to auth + requirements (§5.2)
- [ ] Lock down the ML service; Laravel-only access (§5.3)
- [ ] Wire `RequirementController::store` → `AnalysisService::analyze()` or ML proxy (§6.1)
- [ ] Global JSON exception handler + error envelope (§3.3)
- [ ] Unify the response envelope on all endpoints (§3)
- [ ] Adopt camelCase keys, or add a snake→camel middleware (§3.4)
- [ ] Add `confidence`, `risk_score`, `risk_level`, `project_id`, `status` to `analyses`
- [ ] Expose `requirements_count` on `ProjectResource`
- [ ] Add `GET /dashboard/stats` (§6.3)
- [ ] Add `GET /dashboard/activity` (§6.4) + an activity log
- [ ] Add `PUT /auth/me` (§6.5) and `PUT /auth/password` (§6.6)
- [ ] Add `POST /auth/forgot-password` + reset flow (§6.7)
- [ ] Add `POST /analysis/{id}/questions/{questionId}` (§6.8)
- [ ] Configurable pagination + `search`/`filter` query params (§7)
- [ ] Configure estimation rates in `.env` (§6.2)
- [ ] Publish and pin `config/cors.php` to the frontend origin with credentials
- [ ] Production `.env`: `APP_DEBUG=false`, MySQL, Redis, secure cookies (§5.4)
- [ ] Fix `e-commerce` label mismatch (§10.1)
- [ ] Decide sync vs queued analysis and tell the frontend team (§9)

Frontend team — already done or in progress:

- [x] `src/api/` layer: envelope unwrapping, pagination, snake→camel, view-model mappers
- [x] `src/config/env.js` — fails loudly on missing/invalid env
- [x] `src/components/common/ErrorBoundary.jsx` — no more white screens
- [x] Canonical enum maps (`src/api/enums.js`) covering all backend values incl. `critical`
- [x] Mock layer gated behind an explicit opt-in flag, excluded from prod bundles
- [x] Text overflow / `break-words` / clamping pass
- [x] Graceful handling of every field the backend does not provide
- [ ] Pagination UI (needs §7 to land)
- [ ] Async analysis polling (blocked on §9 decision)

---

## 12. Open questions

1. **Sync or queued analysis?** (§9) — blocks frontend polling work.
2. **Is `critical` risk in scope?** Frontend renders it. Backend already emits it. Confirm.
3. **Where do estimation rates live?** Currently frontend falls back to $540/PD, 2-person team. Should be backend config.
4. **Do we need file upload** (requirement docs, PDFs)? No endpoint or frontend surface exists yet.
5. **Is `VITE_ML_API_URL` meant to exist at all?** Frontend recommendation: **remove it.** The browser must never reach ML directly.
6. **Multi-user / team projects?** Current model is strictly single-tenant (`projects.user_id`). Shared projects would change every ownership check.