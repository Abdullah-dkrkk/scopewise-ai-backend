"""ScopeWise ML inference service.

Internal HTTP service consumed by the Laravel backend. It is never called
directly from a browser, so it authenticates callers with a shared secret,
returns JSON for every outcome, and never runs a debug server in production.
"""

from __future__ import annotations

import hmac
import logging
import sys
import time
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

# Allow "python app.py" and "gunicorn app:create_app()" from any working
# directory to import the local modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Settings, load_settings  # noqa: E402
from nltk_setup import ensure_nltk_data  # noqa: E402

logger = logging.getLogger(__name__)

TOKEN_HEADER = "X-Service-Token"  # noqa: S105 - header name, not a secret
AUTH_HEADER = "Authorization"
MAX_QUESTION_COUNT = 15


class ApiError(Exception):
    """Client error with a stable JSON body."""

    def __init__(self, message: str, status: int = 400, code: str = "bad_request") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def _models_are_ready() -> bool:
    """Whether both persisted models are present."""
    from core.paths import CLASSIFIER_MODEL_PATH, COMPLEXITY_MODEL_PATH

    return CLASSIFIER_MODEL_PATH.exists() and COMPLEXITY_MODEL_PATH.exists()


def warm_up_models() -> bool:
    """Load both models and tokenise a sample string.

    Deserialising the two GradientBoosting pipelines costs several seconds. Both
    are behind ``lru_cache`` and would otherwise be loaded lazily, so the very
    first caller would pay that cost while the Laravel side is already holding a
    request open with a 30 second timeout. Paying it here moves the expense into
    process startup, which is what ``/ready`` already gates on.

    Returns True when the models were loaded successfully.
    """
    if not _models_are_ready():
        logger.warning("Warm-up skipped: model files are missing")
        return False

    started = time.perf_counter()

    try:
        from core.classifier import load_classifier
        from core.complexity import load_complexity_model

        classifier = load_classifier()
        complexity = load_complexity_model()

        # NLTK resources are loaded on first use inside the classifier, so
        # exercise that path too rather than leaving it for a real request.
        from core.classifier import preprocess_text

        preprocess_text("users can log in and reset their password")

        if classifier is None or complexity is None:
            logger.warning("Warm-up incomplete: a model failed to load")
            return False
    except Exception:
        logger.exception("Warm-up failed; models will load lazily on first request")
        return False

    logger.info(
        "Models warmed in %.2fs (classifier=%s, complexity=%s)",
        time.perf_counter() - started,
        type(classifier).__name__,
        type(complexity).__name__,
    )

    return True


def create_app(settings: Settings | None = None, *, warm_up: bool = True) -> Flask:
    """Build the Flask application.

    ``warm_up`` is disabled in tests that assert on model-missing behaviour, so
    they do not each pay the load cost.
    """
    settings = settings or load_settings()

    # Fail fast on an insecure or unusable configuration rather than serving
    # traffic with authentication silently disabled.
    problems = settings.validate()

    if problems:
        for problem in problems:
            logger.error("Configuration problem: %s", problem)

        raise RuntimeError("Invalid ML service configuration: " + "; ".join(problems))

    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = settings.max_content_length
    app.config["JSON_SORT_KEYS"] = False
    # Never leak stack traces to callers; the log keeps them for operators.
    app.config["PROPAGATE_EXCEPTIONS"] = settings.debug

    if settings.cors_origins:
        # Only relevant when the service is exposed to a browser; the backend
        # talks to it server-to-server.
        CORS(app, resources={r"/analyze": {"origins": settings.cors_origins}})
    else:
        logger.info("ML_CORS_ORIGINS is empty: no CORS headers will be sent.")

    ensure_nltk_data()

    if warm_up:
        warm_up_models()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def _presented_token() -> str:
        token = request.headers.get(TOKEN_HEADER, "").strip()

        if token:
            return token

        authorization = request.headers.get(AUTH_HEADER, "").strip()

        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip()

        return ""

    @app.before_request
    def authenticate() -> None:
        """Require the shared secret on every endpoint except health checks."""
        if request.endpoint in {"health", "ready"}:
            return

        if request.endpoint is None:
            # Unmatched path: let Flask's own 404 handler produce the JSON
            # error rather than reporting it as an authentication failure.
            return

        if not settings.requires_authentication:
            return

        if not settings.api_key:
            # Fail closed: a misconfigured deployment must not serve inference.
            logger.error("Rejecting request: ML_SERVICE_API_KEY is not configured")
            raise ApiError("Service is not configured", status=503, code="not_configured")

        # Constant-time comparison avoids leaking the secret through timing.
        if not hmac.compare_digest(_presented_token(), settings.api_key):
            logger.warning(
                "Rejecting %s %s from %s: invalid service token",
                request.method,
                request.path,
                request.remote_addr,
            )
            raise ApiError("Invalid or missing service token", status=401, code="unauthorized")

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------
    def extract_text() -> str:
        """Validate the request body and return the requirement text."""
        if not request.is_json:
            raise ApiError("Request body must be JSON", status=415, code="unsupported_media_type")

        payload = request.get_json(silent=True)

        if payload is None:
            raise ApiError("Request body is not valid JSON", status=400, code="invalid_json")

        if not isinstance(payload, dict):
            raise ApiError("Request body must be a JSON object", status=400, code="invalid_json")

        if "text" not in payload:
            raise ApiError("Missing required field: text", status=422, code="validation_error")

        text = payload["text"]

        if not isinstance(text, str):
            raise ApiError("Field 'text' must be a string", status=422, code="validation_error")

        text = text.strip()

        if len(text) < settings.min_text_length:
            raise ApiError(
                f"Field 'text' must be at least {settings.min_text_length} characters",
                status=422,
                code="validation_error",
            )

        if len(text) > settings.max_text_length:
            raise ApiError(
                f"Field 'text' must be at most {settings.max_text_length} characters",
                status=422,
                code="validation_error",
            )

        return text

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return jsonify({"error": error.message, "code": error.code}), error.status

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        # Werkzeug exposes the HTTP status and description; both are safe to
        # return, unlike the unhandled-exception path below.
        return (
            jsonify({"error": error.description, "code": error.name.lower().replace(" ", "_")}),
            error.code or 500,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception):
        # Log the detail, return an opaque message: internal errors must not
        # leak stack traces, paths or model internals to callers. Flask passes
        # the original exception to the handler and re-raises it afterwards
        # only when PROPAGATE_EXCEPTIONS is on.
        logger.exception(
            "Unhandled %s while processing %s %s",
            type(error).__name__,
            request.method,
            request.path,
        )
        return jsonify({"error": "Internal server error", "code": "internal_error"}), 500

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @app.route("/health", methods=["GET"])
    def health():
        """Liveness probe: the process is up."""
        return jsonify({"status": "healthy", "service": "ScopeWise ML Service"})

    @app.route("/ready", methods=["GET"])
    def ready():
        """Readiness probe: models are available, so traffic can be routed here."""
        if not _models_are_ready():
            return (
                jsonify(
                    {
                        "status": "unavailable",
                        "service": "ScopeWise ML Service",
                        "reason": "models_missing",
                    }
                ),
                503,
            )

        return jsonify({"status": "ready", "service": "ScopeWise ML Service"})

    @app.route("/analyze", methods=["POST"])
    def analyze():
        text = extract_text()

        from core.classifier import classify_requirement
        from core.complexity import predict_complexity
        from core.feature_extractor import extract_features
        from core.question_generator import generate_questions
        from core.risk_scorer import assess_risk
        from core.timeline_estimator import estimate_timeline

        classification = classify_requirement(text)
        category = classification["predicted_category"]

        complexity = predict_complexity(text)
        complexity_score = complexity["complexity_score"]

        features = extract_features(text)
        detected_features = features["feature_summary"]
        feature_count = features["total_features"]

        risk = assess_risk(
            text=text,
            complexity_score=complexity_score,
            feature_count=feature_count,
            category=category,
        )

        questions = generate_questions(
            text=text,
            category=category,
            complexity_score=complexity_score,
            detected_features=detected_features,
        )[:MAX_QUESTION_COUNT]

        timeline = estimate_timeline(
            complexity_score=complexity_score,
            feature_count=feature_count,
            total_estimated_hours=features["total_estimated_hours"],
            risk_level=risk["overall_risk"],
            complexity_level=complexity["complexity_level"],
        )

        modules = []
        for feat in features["features"]:
            modules.append(
                {
                    "name": feat["feature_type"],
                    "description": (
                        f"Implementation of {feat['feature_type'].lower()} "
                        f"with {feat['match_count']} sub-features"
                    ),
                    "complexity": round(
                        min(5.0, complexity_score * (feat["match_count"] / max(feature_count, 1))), 2
                    ),
                    "estimated_hours": feat["estimated_hours"],
                }
            )

        if not modules:
            modules.append(
                {
                    "name": "Core Implementation",
                    "description": "Basic implementation of the described requirement",
                    "complexity": complexity_score,
                    "estimated_hours": max(4.0, complexity_score * 4),
                }
            )

        return jsonify(
            {
                "classification": {
                    "category": category,
                    "confidence": classification["confidence"],
                    "alternatives": classification["alternatives"],
                },
                "complexity": {
                    "score": complexity_score,
                    "level": complexity["complexity_level"],
                    "breakdown": complexity["breakdown"],
                },
                "features": {
                    "detected": features["features"],
                    "total_count": feature_count,
                    "summary": detected_features,
                },
                "risk": {
                    "overall_level": risk["overall_risk"],
                    "score": risk["risk_score"],
                    "total_risk_factors": len(risk["risk_factors"]),
                    "factors": [
                        {
                            "factor": factor["factor"],
                            # risk_factors.level only permits low/medium/high,
                            # so a critical verdict is reported as high.
                            "level": "high" if factor["level"] == "critical" else factor["level"],
                            "description": factor.get("description"),
                            "mitigation": factor.get("mitigation"),
                        }
                        for factor in risk["risk_factors"]
                    ],
                },
                "questions": questions,
                "timeline": timeline,
                "modules": modules,
                "summary": _generate_summary(
                    category=category,
                    complexity_score=complexity_score,
                    complexity_level=complexity["complexity_level"],
                    risk_level=risk["overall_risk"],
                    feature_count=feature_count,
                    estimated_hours=timeline["total_estimated_hours"],
                    timeline_weeks=timeline["recommended_timeline_weeks"],
                ),
            }
        )

    @app.route("/classify", methods=["POST"])
    def classify():
        from core.classifier import classify_requirement

        return jsonify(classify_requirement(extract_text()))

    @app.route("/complexity", methods=["POST"])
    def complexity():
        from core.complexity import predict_complexity

        return jsonify(predict_complexity(extract_text()))

    @app.route("/features", methods=["POST"])
    def features():
        from core.feature_extractor import extract_features

        return jsonify(extract_features(extract_text()))

    @app.route("/risk", methods=["POST"])
    def risk():
        from core.classifier import classify_requirement
        from core.complexity import predict_complexity
        from core.feature_extractor import extract_features
        from core.risk_scorer import assess_risk

        text = extract_text()
        classification = classify_requirement(text)
        complexity = predict_complexity(text)
        features = extract_features(text)

        return jsonify(
            assess_risk(
                text=text,
                complexity_score=complexity["complexity_score"],
                feature_count=features["total_features"],
                category=classification["predicted_category"],
            )
        )

    @app.route("/questions", methods=["POST"])
    def questions():
        from core.classifier import classify_requirement
        from core.complexity import predict_complexity
        from core.feature_extractor import extract_features
        from core.question_generator import generate_questions

        text = extract_text()
        classification = classify_requirement(text)
        complexity = predict_complexity(text)
        features = extract_features(text)

        return jsonify(
            {
                "questions": generate_questions(
                    text=text,
                    category=classification["predicted_category"],
                    complexity_score=complexity["complexity_score"],
                    detected_features=features["feature_summary"],
                )[:MAX_QUESTION_COUNT]
            }
        )

    @app.route("/timeline", methods=["POST"])
    def timeline():
        from core.classifier import classify_requirement
        from core.complexity import predict_complexity
        from core.feature_extractor import extract_features
        from core.risk_scorer import assess_risk
        from core.timeline_estimator import estimate_timeline

        text = extract_text()
        complexity = predict_complexity(text)
        features = extract_features(text)
        risk = assess_risk(
            text=text,
            complexity_score=complexity["complexity_score"],
            feature_count=features["total_features"],
            category=classify_requirement(text)["predicted_category"],
        )

        return jsonify(
            estimate_timeline(
                complexity_score=complexity["complexity_score"],
                feature_count=features["total_features"],
                total_estimated_hours=features["total_estimated_hours"],
                risk_level=risk["overall_risk"],
                complexity_level=complexity["complexity_level"],
            )
        )

    @app.route("/train", methods=["POST"])
    def train():
        """Retrain the models from the checked-in corpus.

        Expensive and mutates the model files, so it stays disabled unless
        ML_ENABLE_TRAINING is explicitly set. Prefer running the training
        script as a one-off job in production.
        """
        if not settings.enable_training:
            raise ApiError("Training is disabled on this instance", status=404, code="not_found")

        from core.classifier import train_classifier
        from core.complexity import train_complexity_model

        classifier = train_classifier()
        complexity_model = train_complexity_model()

        logger.info("Models retrained via the training endpoint")

        return jsonify(
            {
                "status": "Models trained successfully",
                "classifier_type": type(classifier).__name__,
                "complexity_type": type(complexity_model).__name__,
            }
        )

    return app


def _generate_summary(
    category: str,
    complexity_score: float,
    complexity_level: str,
    risk_level: str,
    feature_count: int,
    estimated_hours: float,
    timeline_weeks: float,
) -> str:
    complexity_desc = {
        "low": "straightforward",
        "medium": "moderately complex",
        "high": "complex",
        "critical": "highly complex",
    }

    risk_desc = {
        "low": "minimal",
        "medium": "moderate",
        "high": "significant",
        "critical": "critical",
    }

    category_label = category.replace("_", " ")

    return (
        f"This is a {complexity_desc.get(complexity_level, 'moderately complex')} "
        f"{category_label} requirement with {feature_count} detected features. "
        f"The estimated complexity score is {complexity_score}/5.0 with "
        f"{risk_desc.get(risk_level, 'unknown')} risk. "
        f"Estimated development time: {estimated_hours:.0f} hours "
        f"(~{timeline_weeks:.1f} weeks with a 2-person team). "
        "We recommend breaking this into phases and clearly defining acceptance "
        "criteria to manage scope."
    )


def train_models_from_cli() -> None:
    """Train both models without starting the HTTP server."""
    from core.classifier import train_classifier
    from core.complexity import train_complexity_model

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logger.info("Training classifier...")
    train_classifier()

    logger.info("Training complexity model...")
    train_complexity_model()

    logger.info("Training complete.")


if __name__ == "__main__":
    settings = load_settings()

    if "--train" in sys.argv:
        train_models_from_cli()
    else:
        application = create_app(settings)
        # Debug stays off regardless of environment: the Werkzeug reloader and
        # debugger must never be reachable in a deployed instance.
        application.run(host=settings.host, port=settings.port, debug=False)
