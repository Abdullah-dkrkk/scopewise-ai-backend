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
from core.data import record_feedback  # noqa: E402
from nltk_setup import ensure_nltk_data  # noqa: E402

logger = logging.getLogger(__name__)

TOKEN_HEADER = "X-Service-Token"  # noqa: S105 - header name, not a secret
AUTH_HEADER = "Authorization"


class ApiError(Exception):
    """Client error with a stable JSON body."""

    def __init__(self, message: str, status: int = 400, code: str = "bad_request") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def _models_are_ready() -> bool:
    """Whether every persisted model is present."""
    from core.paths import (
        CLASSIFIER_MODEL_PATH,
        COMPLEXITY_MODEL_PATH,
        HOURS_MODEL_PATH,
    )

    return (
        CLASSIFIER_MODEL_PATH.exists()
        and COMPLEXITY_MODEL_PATH.exists()
        and HOURS_MODEL_PATH.exists()
    )


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
        from core.hours import load_hours_model

        classifier = load_classifier()
        complexity = load_complexity_model()
        hours = load_hours_model()

        # NLTK resources are loaded on first use inside the classifier, so
        # exercise that path too rather than leaving it for a real request.
        from core.classifier import preprocess_text

        preprocess_text("users can log in and reset their password")

        if classifier is None or complexity is None or hours is None:
            logger.warning("Warm-up incomplete: a model failed to load")
            return False
    except Exception:
        logger.exception("Warm-up failed; models will load lazily on first request")
        return False

    logger.info(
        "Models warmed in %.2fs (classifier=%s, complexity=%s, hours=%s)",
        time.perf_counter() - started,
        type(classifier).__name__,
        type(complexity).__name__,
        type(hours).__name__,
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

        from core.clarity import (
            estimate_margin,
            rule_based_vagueness,
            split_clarifications,
        )
        from core.classifier import classify_requirement
        from core.complexity import predict_complexity
        from core.feature_extractor import extract_features
        from core.hours import estimate_total_hours
        from core.question_generator import generate_questions
        from core.risk_scorer import assess_risk
        from core.timeline_estimator import estimate_timeline

        # ------------------------------------------------------------------
        # 1. Deterministic pipeline (the whole engine — no network, no model
        #    API, fully reproducible).
        # ------------------------------------------------------------------
        classification = classify_requirement(text)
        category = classification["predicted_category"]

        complexity = predict_complexity(text)
        complexity_score = complexity["complexity_score"]

        features = extract_features(text)
        detected_features = features["feature_summary"]
        feature_count = features["total_features"]

        # Blend the corpus-trained regressor with the feature-based sum so the
        # headline hours are calibrated, then scale the per-module hours by the
        # same ratio so modules still reconcile with the total.
        hours = estimate_total_hours(text, features["total_estimated_hours"])
        total_hours = hours["hours"]
        feature_hours = max(hours["feature_hours"], 1.0)
        module_scale = total_hours / feature_hours

        risk = assess_risk(
            text=text,
            complexity_score=complexity_score,
            feature_count=feature_count,
            category=category,
        )

        timeline = estimate_timeline(
            complexity_score=complexity_score,
            feature_count=feature_count,
            total_estimated_hours=total_hours,
            risk_level=risk["overall_risk"],
            complexity_level=complexity["complexity_level"],
        )

        # ------------------------------------------------------------------
        # 2. Vagueness detection — deterministic rules only.
        #
        # The backend appends answered clarifying questions as a trailing
        # "Clarifications:" block. Once answers exist the requirement has been
        # clarified: judge vagueness on the original text only and do not flag
        # it again, even when the original phrasing was terse.
        # ------------------------------------------------------------------
        base_text, clarifications = split_clarifications(text)
        rule_vague, rule_reason = rule_based_vagueness(base_text)
        clarified = len(clarifications) > 0

        needs_clarification = rule_vague and not clarified
        clarification_reason = rule_reason if needs_clarification else None

        # ------------------------------------------------------------------
        # 3. Questions — deterministic, text-aware templates that quote the
        #    customer's own words. The vague path always carries them.
        # ------------------------------------------------------------------
        questions = generate_questions(
            text=base_text,
            category=category,
            complexity_score=complexity_score,
            detected_features=detected_features,
            max_questions=settings.max_questions,
        )

        summary = _generate_summary(
            category=category,
            complexity_score=complexity_score,
            complexity_level=complexity["complexity_level"],
            risk_level=risk["overall_risk"],
            feature_count=feature_count,
            estimated_hours=total_hours,
            timeline_weeks=timeline["recommended_timeline_weeks"],
        )

        # ------------------------------------------------------------------
        # 4. Risk factors — deterministic, category- and text-derived.
        # ------------------------------------------------------------------
        risk_factors = [
            {
                "factor": factor["factor"],
                "level": "high" if factor["level"] == "critical" else factor["level"],
                "description": factor.get("description"),
                "mitigation": factor.get("mitigation"),
            }
            for factor in risk["risk_factors"]
        ]

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
                    "estimated_hours": round(feat["estimated_hours"] * module_scale, 2),
                }
            )

        if not modules:
            modules.append(
                {
                    "name": "Core Implementation",
                    "description": "Basic implementation of the described requirement",
                    "complexity": complexity_score,
                    "estimated_hours": total_hours,
                }
            )

        response = {
            "engine": "local",
            "needs_clarification": needs_clarification,
            "clarification_reason": clarification_reason,
            "classification": {
                "category": category,
                "confidence": classification["confidence"],
                "alternatives": classification["alternatives"],
            },
            "complexity": {
                "score": complexity_score,
                "level": complexity["complexity_level"],
                "breakdown": {
                    **complexity["breakdown"],
                    "hours_model": hours["model_hours"],
                    "hours_features": hours["feature_hours"],
                },
            },
            "features": {
                "detected": features["features"],
                "total_count": feature_count,
                "summary": detected_features,
            },
            "risk": {
                "overall_level": risk["overall_risk"],
                "score": risk["risk_score"],
                "total_risk_factors": len(risk_factors),
                "factors": risk_factors,
            },
            "questions": questions,
            "timeline": timeline,
            "modules": modules,
            "summary": summary,
        }

        # --------------------------------------------------------------
        # 5. Vague input: instead of a fake-precise single number, return a
        #    realistic provisional band around the deterministic estimate.
        # --------------------------------------------------------------
        if needs_clarification:
            response["estimate_band"] = estimate_margin(total_hours)

        # ---------------------------------------------
        # 6. Learn from real traffic. Confident, specific analyses are
        #    recorded (anonymised — no account id) so the next retrain keeps
        #    improving on real user data. Never allowed to fail the request.
        # ---------------------------------------------
        record_feedback(
            {
                "_input_text": text,
                "needs_clarification": needs_clarification,
                "classification": {
                    "category": category,
                    "confidence": classification["confidence"],
                },
                "complexity": {"score": complexity_score},
                "timeline": {"total_estimated_hours": total_hours},
            }
        )

        return jsonify(response)

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
                    max_questions=settings.max_questions,
                )
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
        from core.evaluation import run_evaluation
        from core.hours import train_hours_model

        classifier = train_classifier()
        complexity_model = train_complexity_model()
        hours_model = train_hours_model()

        logger.info("Models retrained via the training endpoint")

        return jsonify(
            {
                "status": "Models trained successfully",
                "classifier_type": type(classifier).__name__,
                "complexity_type": type(complexity_model).__name__,
                "hours_type": type(hours_model).__name__,
                "evaluation": run_evaluation(),
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
    """Train all models (and evaluate) without starting the HTTP server."""
    from core.classifier import train_classifier
    from core.complexity import train_complexity_model
    from core.evaluation import run_evaluation
    from core.hours import train_hours_model

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logger.info("Training classifier...")
    train_classifier()

    logger.info("Training complexity model...")
    train_complexity_model()

    logger.info("Training hours model...")
    train_hours_model()

    logger.info("Running hold-out evaluation...")
    run_evaluation()

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
