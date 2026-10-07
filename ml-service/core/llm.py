"""Optional Gemini refinement layer (free tier).

The local sklearn pipeline (a 44-sample TF-IDF classifier plus regex rules) is
fast and free but weak at *understanding* a vague requirement. This module adds
an optional language-model layer: when ``GEMINI_API_KEY`` is configured, Gemini
refines the classification, flags highly vague requirements, extracts genuine
risk factors and — most importantly — produces **pinpointed** scope-creep
questions derived from the exact words the customer wrote, instead of the fixed
templates used by the local pipeline.

Design rules:

* Zero new hard dependencies — the Gemini REST API is called with ``urllib``.
* Every failure is degraded gracefully: a missing key, a network error, a
  rejected prompt or a malformed JSON response all return ``None`` so the
  caller falls back to the deterministic pipeline without showing an error.
* The model never invents numbers. Hours and timelines stay in
  ``timeline_estimator.py``; Gemini only reasons about meaning.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# Canonical vocabulary the frontend understands (src/api/enums.js). Everything
# must pass through this list so Gemini cannot invent a label the UI cannot
# render.
CATEGORIES = [
    "functional",
    "authentication",
    "api",
    "integration",
    "data_model",
    "security",
    "technical",
    "performance",
    "non_functional",
    "ui_design",
    "reporting",
    "dashboard",
    "marketing",
    "e_commerce",
    "content_management",
    "general",
]

VALID_LEVELS = {"low", "medium", "high"}
VALID_PRIORITIES = {"low", "medium", "high"}

# Signals the local rules understand even when Gemini is off. These are the
# words a lazy or vague client response tends to hide behind.
VAGUE_WORDS = [
    "etc", "and so on", "and more", "something like", "kind of", "sort of",
    "basically", "probably", "stuff", "things",
]
SCOPE_FILLERS = [
    "maybe", "perhaps", "possibly", "might", "could", "should",
    "nice to have", "nice-to-have", "stretch", "later", "phase 2",
    "simple", "just", "easy", "quick", "basic",
]

SYSTEM_INSTRUCTION = """You are ScopeWise, a senior software project estimator \
and scope-creep analyst. A customer has pasted a raw, unedited requirement. \
Read it strictly and answer in JSON.

Rules you must follow:
1. `category` must be exactly one of: {categories}. Choose the closest.
2. `confidence` is 0-1: how sure you are this single response is enough to \
estimate. Be harsh: a short or vague requirement gets a low score.
3. `is_vague` is true ONLY when the text is genuinely too thin to estimate \
(very short, full of filler words like "etc/stuff/and so on", contradictory, \
or missing who/what/how entirely). Do not over-flag useful requirements.
4. `questions` are the most important part. Ask PINPOINTED questions that \
target gaps visible in THIS text — mention the exact words the customer used. \
Never ask anything already answered, never ask generic canned questions. Focus \
on scope-creep traps: undefined acceptance criteria, missing actors/roles, \
integration or data-migration dependencies, scale/performance assumptions, \
security, ambiguity in words like "etc/stuff/and more", and anything listed as \
"later/phase 2/nice to have". Max {max_questions} questions, ordered by what \
moves the estimate most.
5. `risk_factors`: only genuine, text-derived risks (ambiguity, unknown \
integrations, security/privacy, scale, single-source data). Max \
{max_risk_factors}. level is low/medium/high.
6. `detected_features`: the concrete capabilities this requirement implies, \
named from the text (e.g. "Customer Login", "Order Tracking").
7. `summary`: 1-3 professional sentences summarising the requirement.
8. Never invent numbers, hours, prices or dates. Never add required fields.

Respond with a single JSON object shaped exactly like this:
{{
  "category": "general",
  "confidence": 0.0,
  "is_vague": false,
  "vagueness_reason": null,
  "summary": "",
  "detected_features": [{{"name": "", "reason": ""}}],
  "risk_factors": [{{"factor": "", "level": "low", "reason": "", "mitigation": ""}}],
  "questions": [{{"question": "", "category": "general", "priority": "high"}}]
}}"""


def build_prompt(text: str, *, max_questions: int = 8, max_risk_factors: int = 8) -> str:
    """Compose the model prompt from a requirement text."""
    categories = ", ".join(CATEGORIES)
    instruction = SYSTEM_INSTRUCTION.format(
        categories=categories,
        max_questions=max_questions,
        max_risk_factors=max_risk_factors,
    )
    return f"{instruction}\n\nCUSTOMER REQUIREMENT:\n\"\"\"\n{text}\n\"\"\""


def _endpoint(model: str) -> str:
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )


def call_gemini(
    api_key: str,
    model: str,
    prompt: str,
    timeout: int = 25,
    fallbacks: tuple[str, ...] = (),
) -> dict | None:
    """Call Gemini ``generateContent`` and return parsed JSON, or ``None``.

    ``responseMimeType: application/json`` makes the model emit machine
    readable JSON; even so the text is run through ``parse_json_response``
    because models occasionally wrap output in fences.

    Only models that actually answer are used: when the configured model is
    retired for this API key (or is rate-limited or down), the next candidate
    in ``fallbacks`` is tried instead. Auth and request-shape errors are not
    retryable, so they fail fast.
    """
    candidates = _model_candidates(model, fallbacks)
    last_error = None

    for candidate in candidates:
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        }

        request = urllib.request.Request(
            _endpoint(candidate),
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - pinned API URL
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code in _RETRYABLE_HTTP_CODES:
                logger.warning(
                    "Gemini model %s unavailable (%s), trying next fallback",
                    candidate,
                    exc.code,
                )
                continue
            logger.warning("Gemini HTTP %s while analyzing text (%s)", exc.code, exc.reason)
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.warning("Gemini request failed: %s", exc)
            return None

        parsed = _parse_generate_response(raw, candidate)

        if parsed is not None or not candidates[1:]:
            return parsed

        logger.warning("Gemini model %s produced no usable output, trying next fallback", candidate)

    logger.warning("No Gemini model succeeded; last error: %s", last_error)
    return None


def _model_candidates(model: str, fallbacks: tuple[str, ...]) -> list[str]:
    """The configured model first, then deduplicated fallbacks."""
    ordered = [model, *fallbacks]
    seen: set[str] = set()
    result: list[str] = []

    for name in ordered:
        name = name.strip().strip("/")
        if name and name not in seen:
            seen.add(name)
            result.append(name)

    return result


_RETRYABLE_HTTP_CODES = frozenset({404, 429, 500, 502, 503, 504})


def _parse_generate_response(raw: str, model: str) -> dict | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Gemini returned non-JSON transport payload")
        return None

    try:
        candidates = payload.get("candidates", [])

        if not candidates:
            block = payload.get("promptFeedback", {})
            reason = block.get("blockReason", "no candidates")
            logger.warning("Gemini returned no candidates (%s)", reason)

            return None

        text = candidates[0]["content"]["parts"][0].get("text", "")
    except (TypeError, KeyError, IndexError):
        logger.warning("Gemini response was missing expected keys")
        return None

    parsed = parse_json_response(text)

    if parsed is None:
        logger.warning("Gemini returned unparseable JSON: %.200s", text)

    return parsed


def parse_json_response(text: str) -> dict | None:
    """Extract a JSON object from the model output."""
    if not isinstance(text, str):
        return None

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def normalize_category(value: str) -> str:
    key = str(value or "general").strip().lower().replace("-", "_").replace(" ", "_")
    return key if key in CATEGORIES else "general"


def normalize_level(value: str) -> str:
    key = str(value or "low").strip().lower()
    return key if key in VALID_LEVELS else "low"


def normalize_priority(value: str) -> str:
    key = str(value or "medium").strip().lower()

    if key == "critical":
        return "high"

    return key if key in VALID_PRIORITIES else "medium"


def clamp_number(value, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def normalize_llm_output(
    payload: dict | None,
    *,
    max_questions: int = 8,
    max_risk_factors: int = 8,
) -> dict | None:
    """Turn raw (possibly hostile) model output into a safe, typed dict."""
    if not isinstance(payload, dict):
        return None

    questions = []
    seen_questions = set()

    for item in payload.get("questions", []):
        if not isinstance(item, dict):
            continue

        question = str(item.get("question", "")).strip()

        if not question:
            continue

        key = question.lower()

        if key in seen_questions:
            continue

        seen_questions.add(key)
        questions.append(
            {
                "question": question[:500],
                "category": normalize_category(item.get("category")),
                "priority": normalize_priority(item.get("priority")),
            }
        )

        if len(questions) >= max_questions:
            break

    risk_factors = []
    for item in payload.get("risk_factors", []):
        if not isinstance(item, dict):
            continue

        factor = str(item.get("factor", "")).strip()

        if not factor:
            continue

        risk_factors.append(
            {
                "factor": factor[:200],
                "level": normalize_level(item.get("level")),
                "reason": str(item.get("reason", "")).strip()[:500] or None,
                "mitigation": str(item.get("mitigation", "")).strip()[:500] or None,
            }
        )

        if len(risk_factors) >= max_risk_factors:
            break

    detected_features = []
    for item in payload.get("detected_features", []):
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()

        if not name:
            continue

        detected_features.append(
            {
                "name": name[:150],
                "reason": str(item.get("reason", "")).strip()[:500] or None,
            }
        )

    summary = str(payload.get("summary", "")).strip()[:1200] or None

    return {
        "category": normalize_category(payload.get("category")),
        "confidence": round(clamp_number(payload.get("confidence"), 0.0, 0.0, 1.0), 4),
        "is_vague": bool(payload.get("is_vague")),
        "vagueness_reason": str(payload.get("vagueness_reason", "")).strip()[:500] or None,
        "summary": summary,
        "detected_features": detected_features[:12],
        "risk_factors": risk_factors,
        "questions": questions,
    }


def split_clarifications(text: str) -> tuple[str, list[str]]:
    """Split a requirement into the original text and its answered clarifications.

    The Laravel backend appends answered clarifying questions as a trailing
    "Clarifications:" block before re-analysing. Vagueness must be judged on the
    original text only, and once answers exist the requirement is no longer
    pending clarification, even if the original phrasing was terse.
    """
    marker = "clarifications:"
    lower = text.lower()
    index = lower.find(marker)

    if index == -1:
        return text, []

    base = text[:index].rstrip()
    section = text[index + len(marker):].strip()

    lines = []
    for raw in section.splitlines():
        item = raw.strip()
        if not item:
            continue
        lines.append(item[2:].strip() if item[:2] in ("- ", "• ") else item)

    return (base or text, lines)


def rule_based_vagueness(text: str) -> tuple[bool, str | None]:
    """Local, dependency-free vagueness heuristics.

    These run regardless of whether Gemini is available so the behaviour is
    deterministic and testable offline.
    """
    lower = text.lower()
    word_count = len(text.split())

    if word_count < 15:
        return True, "The requirement is very brief and lacks sufficient detail."

    vague_hits = sum(1 for word in VAGUE_WORDS if word in lower)
    filler_hits = sum(1 for word in SCOPE_FILLERS if word in lower)

    if vague_hits >= 2:
        return True, "The requirement uses vague filler terms (etc, and so on, stuff)."

    if filler_hits >= 2:
        return True, "The requirement uses hedging language (maybe, perhaps, simple, quick)."

    return False, None


def estimate_margin(hours: float) -> dict:
    """Realistic band around a provisional estimate for vague input.

    Deliberately neither inflated (which would scare the client away) nor
    optimistic (which would set a false commitment): a 15% contingency floor
    and a 30% ceiling, both applied to the deterministic estimate.
    """
    base = max(0.0, float(hours))
    low = round(base * 1.15, 1)
    high = round(base * 1.30, 1)

    return {
        "low": low,
        "high": high,
        "note": (
            "This requirement was flagged as needing clarification, so the estimate "
            "is a provisional range. Answers to the clarifying questions above will "
            "narrow it into a single, more confident estimate."
        ),
    }