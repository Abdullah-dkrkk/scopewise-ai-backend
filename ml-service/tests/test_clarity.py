"""Unit tests for the deterministic clarity module.

These cover the pure-python behaviour (vagueness rules, term detection,
clarification splitting, estimate bands) with no model, network or credentials
involved.
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from core.clarity import (  # noqa: E402
    estimate_margin,
    find_scope_terms,
    find_vague_terms,
    quote_term,
    rule_based_vagueness,
    split_clarifications,
)


class TestSplitClarifications:
    def test_no_clarifications_returns_original(self):
        base, lines = split_clarifications("Build a login page")

        assert base == "Build a login page"
        assert lines == []

    def test_splits_at_marker_and_strips_bullets(self):
        text = (
            "Build a login page\n\n"
            "Clarifications:\n"
            "- What login methods? SSO and email\n"
            "- MFA needed? Yes"
        )
        base, lines = split_clarifications(text)

        assert base == "Build a login page"
        assert lines == ["What login methods? SSO and email", "MFA needed? Yes"]

    def test_marker_is_case_insensitive(self):
        text = "Login page\n\nclarifications:\n- Team size? 3"
        base, lines = split_clarifications(text)

        assert base == "Login page"
        assert lines == ["Team size? 3"]


class TestRuleBasedVagueness:
    def test_short_text_is_vague(self):
        vague, reason = rule_based_vagueness("Make it fast")

        assert vague is True
        assert reason is not None

    def test_filler_words_flag_vagueness(self):
        vague, _ = rule_based_vagueness("login page and stuff, some other things and so on")

        assert vague is True

    def test_hedging_language_flags_vagueness(self):
        vague, _ = rule_based_vagueness("Maybe a simple dashboard, perhaps just charts, probably basic")

        assert vague is True

    def test_clear_requirement_is_not_vague(self):
        vague, _ = rule_based_vagueness(
            "Users must be able to log in with email and password, reset their password "
            "via a verified email link, and manage their profile with role-based access."
        )

        assert vague is False


class TestTermDetection:
    def test_vague_terms_are_found_longest_first(self):
        terms = find_vague_terms("do X, Y, etc and so on and more stuff")

        assert "etc" in terms
        assert "and so on" in terms
        # The longer phrase is reported before the shorter overlapping one.
        assert terms.index("and so on") < terms.index("etc") if "etc" in terms else True

    def test_scope_terms_are_found(self):
        terms = find_scope_terms("maybe add a nice to have dashboard later")

        assert "maybe" in terms
        assert "nice to have" in terms
        assert "later" in terms

    def test_quote_term_wraps_in_quotes(self):
        assert quote_term("etc") == '"etc"'

    def test_quote_term_handles_empty(self):
        assert quote_term("  ") == "that phrase"


class TestEstimateMargin:
    def test_band_sits_between_floor_and_ceiling(self):
        band = estimate_margin(100.0)

        assert band["low"] == 115.0
        assert band["high"] == 130.0
        assert band["low"] <= band["high"]
        assert "clarification" in band["note"]

    def test_band_scales_with_hours(self):
        small = estimate_margin(10.0)
        large = estimate_margin(200.0)

        assert large["low"] > small["low"]
        assert large["high"] > small["high"]

    def test_zero_hours_stays_sane(self):
        band = estimate_margin(0.0)

        assert band["low"] == 0.0
        assert band["high"] == 0.0
