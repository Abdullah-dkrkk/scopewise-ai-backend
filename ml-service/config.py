"""Runtime configuration for the ScopeWise ML service.

Every value is read from the environment so the same image can run locally,
in CI and in production without code changes. Defaults are deliberately
conservative: the service fails closed rather than exposing inference or
training endpoints on a public network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Load ml-service/.env (if present) before anything reads settings. Real
# environment variables win so the file never overrides shell/CI values.
_ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_env_file() -> None:
    if not _ENV_FILE.is_file():
        return

    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file()

# Request bodies are capped well below anything a requirement analysis needs.
DEFAULT_MAX_CONTENT_LENGTH = 64 * 1024
DEFAULT_MIN_TEXT_LENGTH = 3
DEFAULT_MAX_TEXT_LENGTH = 20_000

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)

    if raw is None:
        return default

    value = raw.strip().lower()

    if value in _TRUE_VALUES:
        return True

    if value in _FALSE_VALUES:
        return False

    raise ValueError(f"{name} must be a boolean value, got {raw!r}")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero, got {value}")

    return value


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")

    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the service configuration."""

    environment: str = field(default_factory=lambda: os.getenv("ML_ENV", "production"))
    debug: bool = field(default_factory=lambda: _env_bool("ML_DEBUG", False))

    # Shared secret required by every endpoint except /health.
    api_key: str = field(default_factory=lambda: os.getenv("ML_SERVICE_API_KEY", "").strip())
    # Explicit opt-in for unauthenticated access, local development only.
    allow_anonymous: bool = field(default_factory=lambda: _env_bool("ML_ALLOW_ANONYMOUS", False))

    # /train retrains models from the checked-in corpus and is expensive, so it
    # is disabled unless explicitly enabled.
    enable_training: bool = field(default_factory=lambda: _env_bool("ML_ENABLE_TRAINING", False))

    # Browsers never call this service directly; the Laravel backend does.
    cors_origins: list[str] = field(default_factory=lambda: _env_list("ML_CORS_ORIGINS"))

    min_text_length: int = field(default_factory=lambda: _env_int("ML_MIN_TEXT_LENGTH", DEFAULT_MIN_TEXT_LENGTH))
    max_text_length: int = field(default_factory=lambda: _env_int("ML_MAX_TEXT_LENGTH", DEFAULT_MAX_TEXT_LENGTH))
    max_content_length: int = field(
        default_factory=lambda: _env_int("ML_MAX_CONTENT_LENGTH", DEFAULT_MAX_CONTENT_LENGTH)
    )

    # Binding all interfaces is correct inside a container. Never expose the
    # container's port publicly: the shared secret is the only auth layer.
    host: str = field(default_factory=lambda: os.getenv("ML_HOST", "0.0.0.0"))  # noqa: S104
    port: int = field(default_factory=lambda: _env_int("ML_PORT", 5000))

    # ------------------------------------------------------------------
    # Optional Gemini refinement layer (free tier).
    # ------------------------------------------------------------------
    # When GEMINI_API_KEY is empty the service runs the deterministic local
    # pipeline exactly as before. When set, Gemini refines classification,
    # risk factors and — most importantly — produces pinpointed, text-derived
    # scope-creep questions, and flags highly vague requirements.
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip())
    # gemini-3.8-flash is the current generateContent model; keep the older
    # aliases as fallbacks so a model retirement never breaks the service.
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip())
    gemini_model_fallbacks: list[str] = field(
        default_factory=lambda: _env_list("GEMINI_MODEL_FALLBACKS")
        or ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3-flash-preview"]
    )
    gemini_timeout: int = field(default_factory=lambda: _env_int("GEMINI_TIMEOUT", 25))
    gemini_max_questions: int = field(default_factory=lambda: _env_int("GEMINI_MAX_QUESTIONS", 8))
    gemini_max_risk_factors: int = field(default_factory=lambda: _env_int("GEMINI_MAX_RISK_FACTORS", 8))

    @property
    def requires_authentication(self) -> bool:
        return not self.allow_anonymous

    def validate(self) -> list[str]:
        """Return a list of configuration problems that should fail startup."""
        problems: list[str] = []

        if self.requires_authentication and not self.api_key:
            problems.append(
                "ML_SERVICE_API_KEY must be set when ML_ALLOW_ANONYMOUS is not enabled. "
                "Set ML_ALLOW_ANONYMOUS=true for local development only."
            )

        if self.gemini_timeout <= 0:
            problems.append("GEMINI_TIMEOUT must be greater than zero")

        if self.min_text_length > self.max_text_length:
            problems.append("ML_MIN_TEXT_LENGTH cannot be greater than ML_MAX_TEXT_LENGTH")

        return problems


def load_settings() -> Settings:
    return Settings()
