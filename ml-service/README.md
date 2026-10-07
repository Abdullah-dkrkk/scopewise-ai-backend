# ScopeWise ML Service

Internal Flask inference service for ScopeWise AI. It classifies requirements,
scores complexity, detects features, assesses risk, generates clarification
questions and estimates a delivery timeline.

The Laravel backend is the only intended caller. The service authenticates every
request with a shared secret and must never be exposed on a public interface.

## How analysis flows

1. `POST /api/requirements` stores the requirement and dispatches
   `AnalyzeRequirement` on the `analysis` queue (after commit).
2. The job calls `AnalysisPipeline`, which asks `MlClient` for `/analyze`.
3. On success the payload is normalised by `MlAnalysisResult` and persisted by
   `AnalysisWriter` inside a single transaction, and
   `analyses.estimation_method` is set to `ml_service`.
4. If the service is unreachable, times out, or returns something unusable, the
   pipeline falls back to `HeuristicEstimator` and records
   `heuristic_fallback`. A heuristic estimate is never labelled as a model
   prediction.
5. `POST /api/requirements/{id}/analyze` re-runs the analysis, which is how a
   user upgrades a fallback estimate once the ML service is healthy again.

## Endpoints

| Method | Path          | Auth | Purpose                                  |
|--------|---------------|------|------------------------------------------|
| GET    | `/health`     | no   | Liveness probe                           |
| GET    | `/ready`      | no   | Readiness probe; 503 when models are missing |
| POST   | `/analyze`    | yes  | Full analysis (used by the backend)      |
| POST   | `/classify`   | yes  | Category, confidence, alternatives       |
| POST   | `/complexity` | yes  | Complexity score, level, breakdown       |
| POST   | `/features`   | yes  | Detected features and hour estimate      |
| POST   | `/risk`       | yes  | Risk score, level and risk factors       |
| POST   | `/questions`  | yes  | Clarification questions                  |
| POST   | `/timeline`   | yes  | Phased delivery timeline                 |
| POST   | `/train`      | yes  | Retrain models; disabled by default      |

Authentication uses the `X-Service-Token` header, falling back to
`Authorization: Bearer <token>`. The comparison is constant-time.

## Configuration

Copy `.env.example` and set at least `ML_SERVICE_API_KEY`. The service refuses to
start when authentication is required but no key is configured, rather than
serving inference unauthenticated.

| Variable | Default | Notes |
|----------|---------|-------|
| `ML_SERVICE_API_KEY` | – | Required unless anonymous mode is on |
| `ML_ALLOW_ANONYMOUS` | `false` | Local development only |
| `ML_ENABLE_TRAINING` | `false` | Enables `POST /train` |
| `ML_CORS_ORIGINS` | empty | Leave empty; browsers do not call this |
| `ML_MIN_TEXT_LENGTH` | `3` | |
| `ML_MAX_TEXT_LENGTH` | `20000` | Must match the Laravel request rule |
| `ML_MAX_CONTENT_LENGTH` | `65536` | Whole-body cap in bytes |
| `ML_HOST` / `ML_PORT` | `0.0.0.0` / `5000` | |
| `ML_DEBUG` | `false` | Never enable in production |

The Laravel side is configured with `ML_SERVICE_URL`, `ML_SERVICE_TOKEN`,
`ML_SERVICE_TIMEOUT` and `ML_FALLBACK_ENABLED`.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

export ML_ALLOW_ANONYMOUS=true   # Windows: $env:ML_ALLOW_ANONYMOUS="true"
python app.py
```

`python app.py --train` retrains both models from
`training_data/requirements.json` without starting the server.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

`tests/test_api.py` covers the HTTP contract: authentication, input validation,
the JSON error contract and non-leakage of internal errors. `tests/test_core.py`
covers the deterministic modules: feature extraction, risk scoring, timeline
reconciliation and question generation.

## Production deployment

```bash
docker build -t scopewise-ml:latest ml-service
docker run -d --name scopewise-ml \
  -p 5000:5000 \
  -e ML_ENV=production \
  -e ML_SERVICE_API_KEY="<long random secret>" \
  scopewise-ml:latest
```

The image is a single stage by design: models are trained from the checked-in
corpus and the NLTK corpora are downloaded at build time, so the running
container needs no network access and serves the first request at full speed.

Gunicorn runs one worker with four threads. The models are memory-heavy, so
multiple workers would duplicate them; threads handle concurrent analysis calls
because inference releases the GIL inside scikit-learn and joblib.

Requirements for a real deployment:

- Run behind a private network or service mesh; the shared secret is the only
  authentication layer.
- Set `ML_SERVICE_API_KEY` from a secret manager, never in the image.
- Monitor `/ready`, not just `/health`: `/health` only proves the process is up.
- Retrain by running `python app.py --train` as a one-off job, not via the HTTP
  endpoint.

## Model retraining

```bash
docker run --rm -v "$PWD/saved_models:/app/saved_models" \
  scopewise-ml:latest python app.py --train
```

`classifier.pkl` and `complexity.pkl` are loaded once per process and cached.
Retraining clears the cache so subsequent requests in the same process see the
new model.