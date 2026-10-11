"""Deterministic clarity analysis for raw requirements.

This module is the *entire* intelligence budget for vagueness: it decides
whether a requirement is too thin to estimate, explains why, and produces a
provisional estimate band instead of a false-precision single number.

There is deliberately no language-model or network call anywhere in this file.
Everything here is pure, rules-based and offline, so the service is fully
reproducible and testable without credentials or connectivity.
"""

from __future__ import annotations

import re

# Signals a lazy or vague client response tends to hide behind. These are the
# literal words the clarity questions quote back to the user.
VAGUE_WORDS = [
    "etc", "and so on", "and more", "something like", "kind of", "sort of",
    "basically", "probably", "stuff", "things", "some", "various", "several",
]

# Hedging / de-scoping language: the words that most often precede scope creep
# because they leave the boundary of the work undefined.
SCOPE_FILLERS = [
    "maybe", "perhaps", "possibly", "might", "could", "should",
    "nice to have", "nice-to-have", "stretch", "later", "phase 2", "phase two",
    "simple", "just", "easy", "quick", "basic", "as needed", "if time permits",
]

# Below this many words a requirement almost never carries enough signal to
# estimate honestly.
MIN_INFORMATIVE_WORDS = 12


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


def find_vague_terms(text: str) -> list[str]:
    """Return the vague filler words actually present, in the order they appear."""
    lower = text.lower()
    found = [word for word in VAGUE_WORDS if word in lower]

    # Longest match first so "and so on" is not reported as "and more" twice.
    return sorted(found, key=len, reverse=True)


def find_scope_terms(text: str) -> list[str]:
    """Return hedging / de-scoping phrases actually present in the text."""
    lower = text.lower()
    found = [word for word in SCOPE_FILLERS if word in lower]

    return sorted(found, key=len, reverse=True)


def rule_based_vagueness(text: str) -> tuple[bool, str | None]:
    """Local, dependency-free vagueness heuristics.

    Returns ``(is_vague, reason)``. The reason is phrased for a human reader
    because it is surfaced next to the provisional estimate band.
    """
    lower = text.lower()
    word_count = len(text.split())

    if word_count < MIN_INFORMATIVE_WORDS:
        return True, "The requirement is very brief and lacks sufficient detail."

    vague_hits = find_vague_terms(lower)
    filler_hits = find_scope_terms(lower)

    if len(vague_hits) >= 2:
        sample = ", ".join(vague_hits[:3])
        return True, f"The requirement leans on vague filler terms ({sample})."

    if len(filler_hits) >= 2:
        sample = ", ".join(filler_hits[:3])
        return True, f"The requirement uses hedging language ({sample}) that leaves scope undefined."

    # A single strong signal is still worth flagging: "etc" alone usually hides
    # an unbounded list.
    if "etc" in vague_hits and word_count < 60:
        return True, "The requirement defers detail to \"etc\", which hides an unbounded list of work."

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


def quote_term(term: str) -> str:
    """Format a detected term for safe inclusion in a question."""
    cleaned = re.sub(r"\s+", " ", term).strip()

    return f'"{cleaned}"' if cleaned else "that phrase"
