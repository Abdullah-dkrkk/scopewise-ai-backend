"""Unit tests for the deterministic core modules.

These cover the pure-python components (feature extraction, risk scoring,
timeline estimation, question generation) without loading any ML model.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow importing the core modules regardless of the working directory.
SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from core.feature_extractor import DEFAULT_BASE_HOURS, extract_features  # noqa: E402
from core.question_generator import generate_questions  # noqa: E402
from core.risk_scorer import assess_risk  # noqa: E402
from core.timeline_estimator import (  # noqa: E402
    COMPLEXITY_MULTIPLIERS,
    PHASE_SHARES,
    estimate_timeline,
)


class TestFeatureExtractor:
    def test_detects_multiple_feature_groups(self):
        result = extract_features(
            "The user can log in with OAuth, then pay by card and see a live dashboard of orders"
        )

        summary = result["feature_summary"]

        assert "Authentication & Authorization" in summary
        assert "Payment Processing" in summary
        assert "Real-Time Features" in summary

    def test_unmatched_text_still_returns_a_module(self):
        result = extract_features("qwerty zxcvb")

        # Previously this leaked the last loop variable as the base hours.
        assert result["total_features"] == 1
        assert result["total_estimated_hours"] == DEFAULT_BASE_HOURS
        assert result["total_estimated_hours"] > 0

    def test_total_hours_matches_detected_features(self):
        result = extract_features("Login, password reset, email notifications and file upload")

        expected = sum(feature["estimated_hours"] for feature in result["features"])

        assert result["total_estimated_hours"] == expected


class TestRiskScorer:
    def test_low_risk_input(self):
        result = assess_risk(
            text="Display a static landing page with the company address and contact form",
            complexity_score=1.2,
            feature_count=0,
            category="general",
        )

        assert result["overall_risk"] in ("low", "medium")
        assert result["risk_score"] <= 10.0

    def test_high_risk_input(self):
        result = assess_risk(
            text=(
                "Implement everything and also add payments, encryption, gdpr, pci, hipaa, "
                "webhooks, third party apis, maybe perhaps possibly etc and so on"
            ),
            complexity_score=4.8,
            feature_count=12,
            category="payment",
        )

        assert result["overall_risk"] in ("high", "critical")

    def test_short_requirement_is_flagged(self):
        result = assess_risk(
            text="Make it fast",
            complexity_score=2.0,
            feature_count=1,
            category="general",
        )

        factors = [factor["factor"] for factor in result["risk_factors"]]

        assert "Insufficient Detail" in factors

    def test_factor_levels_are_within_the_persisted_enum(self):
        result = assess_risk(
            text="Secure payment processing with encryption and pci compliance for a complete solution",
            complexity_score=4.9,
            feature_count=10,
            category="payment",
        )

        assert all(
            factor["level"] in ("low", "medium", "high") for factor in result["risk_factors"]
        )


class TestTimelineEstimator:
    def test_phase_shares_sum_to_one(self):
        assert abs(sum(PHASE_SHARES.values()) - 1.0) < 1e-9

    def test_complexity_multiplier_uses_complexity_not_risk(self):
        """A low-complexity, high-risk item must not get the complexity-1.6x bump."""
        result = estimate_timeline(
            complexity_score=1.2,
            feature_count=1,
            total_estimated_hours=10.0,
            risk_level="high",
            complexity_level="low",
        )

        # 10 * 1.0 (complexity low) * 1.25 (risk high)
        assert result["total_estimated_hours"] == 12.5

    def test_critical_complexity_and_risk_compound(self):
        result = estimate_timeline(
            complexity_score=4.9,
            feature_count=9,
            total_estimated_hours=10.0,
            risk_level="critical",
            complexity_level="critical",
        )

        expected = round(10.0 * COMPLEXITY_MULTIPLIERS["critical"] * 1.5, 1)

        assert result["total_estimated_hours"] == expected

    def test_phases_reconcile_with_total(self):
        result = estimate_timeline(
            complexity_score=3.0,
            feature_count=5,
            total_estimated_hours=40.0,
            risk_level="medium",
            complexity_level="medium",
        )

        phases = result["phases"]
        phase_sum = (
            phases["planning_hours"]
            + phases["development_hours"]
            + phases["testing_hours"]
            + phases["deployment_hours"]
            + phases["buffer_hours"]
        )

        assert abs(phase_sum - phases["total_hours"]) < 0.15
        assert phases["total_hours"] == result["total_estimated_hours"]

    def test_zero_hours_does_not_produce_a_zero_day_plan(self):
        result = estimate_timeline(
            complexity_score=1.0,
            feature_count=0,
            total_estimated_hours=0.0,
            risk_level="low",
            complexity_level="low",
        )

        assert result["total_working_days"] >= 1
        assert result["total_estimated_hours"] == 0.0

    def test_team_configs_stay_positive(self):
        result = estimate_timeline(
            complexity_score=2.0,
            feature_count=2,
            total_estimated_hours=5.0,
            risk_level="low",
            complexity_level="medium",
        )

        assert all(config["estimated_days"] >= 1 for config in result["team_configs"])


class TestQuestionGenerator:
    def test_returns_bounded_unique_questions(self):
        questions = generate_questions(
            text="Users can log in, reset passwords and receive email notifications",
            category="authentication",
            complexity_score=4.0,
            detected_features=["Authentication & Authorization", "Notifications"],
        )

        assert 0 < len(questions) <= 15
        assert len({q["question"] for q in questions}) == len(questions)

    def test_high_complexity_adds_scope_questions(self):
        questions = generate_questions(
            text="Distributed payment platform with encryption and realtime processing",
            category="payment",
            complexity_score=4.8,
            detected_features=[],
        )

        categories = {q["category"] for q in questions}

        assert "scope" in categories

    def test_every_question_has_the_expected_shape(self):
        questions = generate_questions(
            text="Build a dashboard with charts and reports",
            category="dashboard",
            complexity_score=2.0,
            detected_features=[],
        )

        for question in questions:
            assert set(question) == {"question", "category", "priority"}
            assert question["priority"] in ("high", "medium", "low")
