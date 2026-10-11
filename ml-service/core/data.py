"""Shared data access for the training pipeline.

Every trainer reads one merged view of all available data:

1. ``requirements.json`` — the curated, version-controlled corpus (hand-written
   seed entries plus generated coverage across every category).
2. ``user_feedback.jsonl`` — requirements that real users actually submitted
   through the live API. The service records every confident, non-vague
   analysis here, so the model keeps learning from real traffic between
   releases. Retraining merges this file automatically.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from core.paths import REQUIREMENTS_DATA_PATH, USER_FEEDBACK_PATH

logger = logging.getLogger(__name__)

# Feedback rows are only usable as weak labels when the model was confident and
# the requirement was specific enough that no clarification round was needed.
MIN_FEEDBACK_CONFIDENCE = 0.5


def load_corpus() -> list[dict]:
    """Return every usable training row, curated corpus first."""
    with REQUIREMENTS_DATA_PATH.open(encoding="utf-8") as handle:
        rows = json.load(handle)

    feedback = _load_feedback()
    existing_texts = {row["text"].strip().lower() for row in rows if row.get("text")}

    added = 0
    for item in feedback:
        text = item.get("text", "").strip()
        if not text or text.lower() in existing_texts:
            continue
        rows.append(item)
        existing_texts.add(text.lower())
        added += 1

    if added:
        logger.info("Merged %d user-feedback row(s) into the training corpus", added)

    return rows


def record_feedback(payload: dict) -> None:
    """Persist one analysed requirement for the next retraining run.

    Best-effort by design: feedback must never fail or slow down an analysis
    request, so every failure is swallowed and logged. Tenants' requirement
    text is the thing that has to be learned from; no account or tenant
    identifiers are stored.
    """
    classification = payload.get("classification") or {}
    complexity = payload.get("complexity") or {}
    timeline = payload.get("timeline") or {}

    confidence = float(classification.get("confidence") or 0.0)
    needs_clarification = bool(payload.get("needs_clarification"))

    if needs_clarification or confidence < MIN_FEEDBACK_CONFIDENCE:
        return

    text = (payload.get("_input_text") or "").strip()
    if not text:
        return

    row = {
        "text": text,
        "category": classification.get("category"),
        "complexity": complexity.get("score") or complexity.get("complexity_level"),
        "hours": timeline.get("total_estimated_hours"),
        "confidence": round(confidence, 4),
        "source": "user_feedback",
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }

    try:
        USER_FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with USER_FEEDBACK_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except OSError:
        logger.warning("Could not record user feedback for training", exc_info=True)


def _load_feedback() -> list[dict]:
    """Read the recorded feedback file, ignoring malformed lines."""
    if not USER_FEEDBACK_PATH.exists():
        return []

    rows = []
    with USER_FEEDBACK_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed feedback line: %r", line[:120])

    return rows


def feedback_file() -> Path:
    """Expose the feedback path (tests use this to point at a temp file)."""
    return USER_FEEDBACK_PATH
