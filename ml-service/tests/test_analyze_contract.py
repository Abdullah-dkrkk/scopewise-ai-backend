"""End-to-end contract tests for the /analyze response.

These assert the shape the Laravel `MlAnalysisResult` normaliser depends on, so
a change to the payload cannot silently break the backend.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app import create_app  # noqa: E402
from config import Settings  # noqa: E402

API_KEY = "test-service-key"
AUTH_HEADERS = {"X-Service-Token": API_KEY}

PAYMENT_REQUIREMENT = (
    "As a user I want to pay for my order with a credit card and receive an "
    "emailed invoice, with the order status shown live on the dashboard."
)

COMPLIANCE_EXPECTED = {
    "e-commerce": "Regulated Payment Handling",
    "authentication": "Access Control Exposure",
    "api": "Breaking Contract Risk",
    "integration": "Third-Party Availability Dependency",
    "ui_design": "Accessibility Compliance",
    "content_management": "Untrusted Content Injection",
}


@pytest.fixture(scope="module")
def client():
    settings = Settings(api_key=API_KEY, allow_anonymous=False)
    app = create_app(settings)
    app.config.update(TESTING=True)

    with app.test_client() as test_client:
        yield test_client


class TestAnalyzeContract:
    def test_response_contains_every_section_the_backend_reads(self, client):
        response = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS)

        assert response.status_code == 200
        body = response.get_json()

        for section in (
            "classification",
            "complexity",
            "features",
            "risk",
            "questions",
            "timeline",
            "modules",
            "summary",
            "engine",
            "needs_clarification",
            "clarification_reason",
        ):
            assert section in body, f"missing {section}"

        assert "category" in body["classification"]
        assert "score" in body["complexity"]
        assert "overall_level" in body["risk"]
        assert "total_risk_factors" in body["risk"]
        assert body["risk"]["total_risk_factors"] == len(body["risk"]["factors"])
        assert "total_estimated_hours" in body["timeline"]

    def test_engine_is_an_honest_source_label(self, client):
        body = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS).get_json()

        assert body["engine"] in ("local", "gemini")

    def test_needs_clarification_is_always_a_boolean(self, client):
        body = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS).get_json()

        assert isinstance(body["needs_clarification"], bool)

    def test_vague_input_gets_a_realistic_estimate_band(self, client):
        body = client.post(
            "/analyze",
            json={"text": "make it fast sort of like a shop and stuff"},
            headers=AUTH_HEADERS,
        ).get_json()

        assert body["needs_clarification"] is True
        assert body["clarification_reason"]

        band = body["estimate_band"]
        hours = body["timeline"]["total_estimated_hours"]

        assert band["low"] <= band["high"]
        assert band["low"] >= hours
        assert band["note"]

    def test_clear_input_has_no_estimate_band(self, client):
        body = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS).get_json()

        assert body["needs_clarification"] is False
        assert "estimate_band" not in body

    def test_complexity_score_is_within_the_persisted_range(self, client):
        body = client.post(
            "/analyze",
            json={"text": "Build a simple static landing page with basic text"},
            headers=AUTH_HEADERS,
        ).get_json()

        assert 1.0 <= body["complexity"]["score"] <= 5.0

    def test_risk_factor_levels_match_the_database_enum(self, client):
        body = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS).get_json()

        assert body["risk"]["overall_level"] in ("low", "medium", "high", "critical")

        for factor in body["risk"]["factors"]:
            # risk_factors.level only allows low/medium/high, so a critical
            # verdict must already be reported as high by the service.
            assert factor["level"] in ("low", "medium", "high"), factor

    def test_modules_are_present_and_bounded(self, client):
        body = client.post(
            "/analyze",
            json={"text": "qwerty zxcvb nonsense with no known feature"},
            headers=AUTH_HEADERS,
        ).get_json()

        assert len(body["modules"]) >= 1

        for module in body["modules"]:
            assert module["name"]
            assert 0.0 <= module["complexity"] <= 5.0
            assert module["estimated_hours"] >= 0

    def test_timeline_phases_reconcile_with_the_headline_hours(self, client):
        body = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS).get_json()

        phases = body["timeline"]["phases"]
        phase_sum = (
            phases["planning_hours"]
            + phases["development_hours"]
            + phases["testing_hours"]
            + phases["deployment_hours"]
            + phases["buffer_hours"]
        )

        assert abs(phase_sum - body["timeline"]["total_estimated_hours"]) < 0.15

    def test_questions_are_bounded_and_well_formed(self, client):
        body = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS).get_json()

        assert 0 < len(body["questions"]) <= 15

        for question in body["questions"]:
            assert set(question) == {"question", "category", "priority"}
            assert question["priority"] in ("high", "medium", "low")

    def test_summary_reports_the_complexity_level_not_the_risk_level(self, client):
        body = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS).get_json()

        complexity_level = body["complexity"]["level"]

        # The summary must not describe complexity using a risk verdict.
        if complexity_level == "low":
            assert "straightforward" in body["summary"]
        else:
            assert "straightforward" not in body["summary"]

    def test_analysis_is_deterministic_for_the_same_input(self, client):
        first = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS).get_json()
        second = client.post("/analyze", json={"text": PAYMENT_REQUIREMENT}, headers=AUTH_HEADERS).get_json()

        assert first["classification"]["category"] == second["classification"]["category"]
        assert first["complexity"]["score"] == second["complexity"]["score"]
        assert first["risk"]["overall_level"] == second["risk"]["overall_level"]

    def test_e_commerce_questions_match_despite_the_hyphenated_corpus_label(self):
        # The trained classifier emits the corpus label "e-commerce" (hyphen),
        # while the question templates key on "e_commerce". The suffix logic
        # must kill that collision or e-commerce requirements silently lose
        # every category-specific question.
        from core.question_generator import generate_questions

        questions = generate_questions(
            text="Provide a shop where customers can browse and make purchases.",
            category="e-commerce",
            complexity_score=2.0,
            detected_features=["e_commerce"],
        )

        categories = [question["category"] for question in questions]

        assert "e_commerce" in categories or "payment" in categories


class TestCategoryRiskMapping:
    """Category-driven risk factors must use the real corpus vocabulary."""

    @pytest.mark.parametrize("category,factor", COMPLIANCE_EXPECTED.items())
    def test_every_mapped_category_is_a_real_corpus_category(self, category, factor):
        import json

        from core.paths import REQUIREMENTS_DATA_PATH

        with REQUIREMENTS_DATA_PATH.open(encoding="utf-8") as handle:
            corpus = json.load(handle)

        categories = {item["category"] for item in corpus}

        # Guards against a stale mapping that can never fire.
        assert category in categories
        assert factor

    def test_compliance_factor_is_added_for_a_mapped_category(self):
        from core.risk_scorer import assess_risk

        result = assess_risk(
            text=PAYMENT_REQUIREMENT,
            complexity_score=2.0,
            feature_count=2,
            category="e-commerce",
        )

        factors = [factor["factor"] for factor in result["risk_factors"]]

        assert "Regulated Payment Handling" in factors

    def test_unmapped_category_adds_no_compliance_factor(self):
        from core.risk_scorer import assess_risk

        result = assess_risk(
            text="Display a static marketing landing page with basic text",
            complexity_score=1.5,
            feature_count=1,
            category="marketing",
        )

        factors = [factor["factor"] for factor in result["risk_factors"]]

        assert not any(factor in COMPLIANCE_EXPECTED.values() for factor in factors)
