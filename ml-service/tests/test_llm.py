"""Unit tests for the optional Gemini refinement layer.

These cover the pure-python behaviour (wording of the prompt, JSON parsing,
sanitisation, vagueness rules, estimate bands) without making a network call.
The HTTP boundary itself is exercised by the analyze-contract probe instead.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

from core.llm import (  # noqa: E402
    build_prompt,
    call_gemini,
    estimate_margin,
    normalize_category,
    normalize_level,
    normalize_llm_output,
    parse_json_response,
    rule_based_vagueness,
    split_clarifications,
)


class TestParseJsonResponse:
    def test_plain_json_is_parsed(self):
        assert parse_json_response('{"a": 1}') == {"a": 1}

    def test_fenced_json_is_parsed(self):
        assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}

    def test_lowercase_json_fence_is_parsed(self):
        assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}

    def test_garbage_returns_none(self):
        assert parse_json_response("not json at all") is None

    def test_non_dict_json_returns_none(self):
        assert parse_json_response("[1, 2, 3]") is None


class TestNormalizeLlmOutput:
    def test_drops_empty_questions_and_deduplicates(self):
        raw = {
            "category": "e-commerce",
            "confidence": 0.99,
            "is_vague": True,
            "questions": [
                {"question": "  ", "category": "general", "priority": "high"},
                {"question": "Do you sell physical products?", "category": "general", "priority": "high"},
                {"question": "Do you sell physical products?", "category": "general", "priority": "medium"},
            ],
        }

        result = normalize_llm_output(raw)

        assert len(result["questions"]) == 1
        assert result["category"] == "e_commerce"
        assert result["is_vague"] is True

    def test_levels_and_priorities_are_clamped(self):
        raw = {
            "category": "totally_unknown",
            "confidence": 7,
            "questions": [{"question": "Q?", "category": "nope", "priority": "critical"}],
            "risk_factors": [{"factor": "F", "level": "extreme", "reason": None, "mitigation": "M"}],
        }

        result = normalize_llm_output(raw)

        assert result["category"] == "general"
        assert result["confidence"] == 1.0
        assert result["questions"][0]["priority"] == "high"
        assert result["risk_factors"][0]["level"] == "low"

    def test_question_and_factor_caps_are_enforced(self):
        raw = {
            "questions": [
                {"question": f"Question number {i}", "category": "general", "priority": "high"}
                for i in range(30)
            ],
            "risk_factors": [
                {"factor": f"Risk {i}", "level": "high", "reason": None, "mitigation": None}
                for i in range(30)
            ],
        }

        result = normalize_llm_output(raw, max_questions=5, max_risk_factors=3)

        assert len(result["questions"]) == 5
        assert len(result["risk_factors"]) == 3

    def test_returns_none_for_non_dict(self):
        assert normalize_llm_output(None) is None
        assert normalize_llm_output(["not", "a", "dict"]) is None

    def test_summary_and_feature_names_are_kept(self):
        raw = {
            "summary": "A customer portal with login.",
            "detected_features": [
                {"name": "Customer Login", "reason": "explicitly requested"},
                {"name": "", "reason": "empty name is dropped"},
            ],
        }

        result = normalize_llm_output(raw)

        assert result["summary"] == "A customer portal with login."
        assert len(result["detected_features"]) == 1
        assert result["detected_features"][0]["name"] == "Customer Login"


class TestNormalizeHelpers:
    def test_category_normalisation(self):
        assert normalize_category("E-Commerce") == "e_commerce"
        assert normalize_category("ui_design") == "ui_design"
        assert normalize_category("Nonsense") == "general"

    def test_level_normalisation(self):
        assert normalize_level("HIGH") == "high"
        assert normalize_level("critical") == "low"


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


class TestEstimateMargin:
    def test_band_sits_between_floor_and_celling(self):
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


class TestBuildPrompt:
    def test_prompt_contains_categories_and_text(self):
        prompt = build_prompt("users can log in", max_questions=6, max_risk_factors=4)

        assert "authentication" in prompt
        assert "users can log in" in prompt
        assert "Max 6 questions" in prompt


class FakeResponse:
    def __init__(self, raw: bytes):
        self._raw = raw

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestCallGemini:
    def test_uses_primary_model_when_it_answers(self):
        payload = b'{"candidates": [{"content": {"parts": [{"text": "{\\"ok\\": true}"}]}}]}'
        requested = []

        def fake_urlopen(request, timeout=25):
            requested.append(request.full_url)

            return FakeResponse(payload)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = call_gemini(
                "test-key",
                "gemini-3.8-flash",
                "build a login",
                fallbacks=("gemini-flash-latest",),
            )

        assert result == {"ok": True}
        assert "gemini-3.8-flash" in requested[0]
        assert len(requested) == 1

    def test_falls_back_when_primary_is_unavailable(self):
        payload = b'{"candidates": [{"content": {"parts": [{"text": "{\\"ok\\": true}"}]}}]}'
        requested = []

        def fake_urlopen(request, timeout=25):
            requested.append(request.full_url)

            if "gemini-3.8-flash" in request.full_url:
                raise urllib.error.HTTPError(request.full_url, 404, "gone", None, None)

            return FakeResponse(payload)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = call_gemini(
                "test-key",
                "gemini-3.8-flash",
                "build a login",
                fallbacks=("gemini-flash-latest", "gemini-2.5-flash"),
            )

        assert result == {"ok": True}
        assert len(requested) == 2
        assert "gemini-flash-latest" in requested[1]

    def test_auth_error_is_not_retried_on_fallback(self):
        requested = []

        def fake_urlopen(request, timeout=25):
            requested.append(request.full_url)

            raise urllib.error.HTTPError(request.full_url, 403, "forbidden", None, None)

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            result = call_gemini("bad-key", "gemini-3.8-flash", "hi", fallbacks=("gemini-flash-latest",))

        assert result is None
        assert len(requested) == 1