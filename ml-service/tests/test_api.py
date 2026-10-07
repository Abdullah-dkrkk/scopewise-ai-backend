"""Contract and security tests for the ML service HTTP layer.

The heavy model files are only touched by the endpoints that need them, so the
security and validation tests stay fast by using routes that never load a
model.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow importing the service modules regardless of the working directory.
SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app import create_app  # noqa: E402
from config import Settings  # noqa: E402

API_KEY = "test-service-key"
AUTH_HEADERS = {"X-Service-Token": API_KEY}
VALID_TEXT = (
    "As a user I want to reset my password via an emailed link so that I can "
    "regain access to my account, including two factor authentication."
)


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings(api_key=API_KEY, allow_anonymous=False, enable_training=False, debug=False)


@pytest.fixture()
def client(settings: Settings):
    app = create_app(settings)
    app.config.update(TESTING=True)

    with app.test_client() as test_client:
        yield test_client


class TestHealth:
    def test_health_is_public(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.get_json()["status"] == "healthy"

    def test_ready_reports_status(self, client):
        response = client.get("/ready")

        # 200 when the persisted models exist, 503 otherwise. Both are valid
        # answers; the contract is the JSON body, not the code alone.
        assert response.status_code in (200, 503)
        assert response.get_json()["status"] in ("ready", "unavailable")


class TestAuthentication:
    @pytest.mark.parametrize(
        "path", ["/analyze", "/classify", "/complexity", "/features", "/risk", "/questions", "/timeline"]
    )
    def test_endpoints_require_a_token(self, client, path):
        response = client.post(path, json={"text": VALID_TEXT})

        assert response.status_code == 401
        assert response.get_json()["code"] == "unauthorized"

    def test_wrong_token_is_rejected(self, client):
        response = client.post(
            "/analyze", json={"text": VALID_TEXT}, headers={"X-Service-Token": "wrong"}
        )

        assert response.status_code == 401

    def test_bearer_token_is_accepted(self, client):
        response = client.post("/analyze", json={"text": VALID_TEXT}, headers={"Authorization": f"Bearer {API_KEY}"})

        assert response.status_code == 200

    def test_anonymous_mode_is_opt_in(self):
        anonymous = Settings(api_key="", allow_anonymous=True)
        app = create_app(anonymous)
        app.config.update(TESTING=True)

        with app.test_client() as anonymous_client:
            response = anonymous_client.post("/analyze", json={"text": VALID_TEXT})

        assert response.status_code == 200


class TestConfiguration:
    def test_missing_api_key_fails_closed(self):
        insecure = Settings(api_key="", allow_anonymous=False)

        assert insecure.requires_authentication is True
        assert any("ML_SERVICE_API_KEY" in problem for problem in insecure.validate())

    def test_invalid_length_configuration_is_reported(self):
        bad = Settings(
            api_key=API_KEY,
            allow_anonymous=False,
            min_text_length=100,
            max_text_length=10,
        )

        assert bad.validate()

    def test_a_failing_configuration_prevents_startup(self):
        with pytest.raises(RuntimeError):
            create_app(Settings(api_key="", allow_anonymous=False))


class TestInputValidation:
    @pytest.fixture(autouse=True)
    def _auth(self, client):
        return AUTH_HEADERS

    def test_missing_text_is_rejected(self, client):
        response = client.post("/analyze", json={}, headers=AUTH_HEADERS)

        assert response.status_code == 422
        assert "text" in response.get_json()["error"]

    def test_non_string_text_is_rejected(self, client):
        response = client.post("/analyze", json={"text": 12345}, headers=AUTH_HEADERS)

        assert response.status_code == 422

    def test_too_short_text_is_rejected(self, client):
        response = client.post("/analyze", json={"text": "hi"}, headers=AUTH_HEADERS)

        assert response.status_code == 422

    def test_too_long_text_is_rejected(self, client):
        response = client.post("/analyze", json={"text": "a" * 20_001}, headers=AUTH_HEADERS)

        assert response.status_code == 422

    def test_non_json_body_is_rejected(self, client):
        response = client.post("/analyze", data="text=hello", headers=AUTH_HEADERS)

        assert response.status_code == 415

    def test_malformed_json_is_rejected(self, client):
        response = client.post(
            "/analyze", data="{not json", headers={**AUTH_HEADERS, "Content-Type": "application/json"}
        )

        assert response.status_code == 400

    def test_json_array_body_is_rejected(self, client):
        response = client.post("/analyze", json=["not", "an", "object"], headers=AUTH_HEADERS)

        assert response.status_code == 400

    def test_oversized_body_is_rejected(self):
        strict = Settings(api_key=API_KEY, allow_anonymous=False, max_content_length=1024)
        app = create_app(strict)
        app.config.update(TESTING=True)

        with app.test_client() as strict_client:
            response = strict_client.post(
                "/analyze", json={"text": "a" * 5000}, headers=AUTH_HEADERS
            )

        assert response.status_code in (413, 422)


class TestErrorContract:
    def test_unknown_route_returns_json(self, client):
        response = client.get("/does-not-exist")

        assert response.status_code == 404
        assert response.is_json
        assert "error" in response.get_json()

    def test_wrong_method_returns_json(self, client):
        response = client.get("/analyze", headers=AUTH_HEADERS)

        assert response.status_code == 405
        assert response.is_json

    def test_internal_errors_do_not_leak_details(self, client, monkeypatch):
        import core.classifier as classifier

        def boom(_text):
            raise ValueError("internal detail that must not escape")

        monkeypatch.setattr(classifier, "classify_requirement", boom)

        response = client.post("/analyze", json={"text": VALID_TEXT}, headers=AUTH_HEADERS)

        assert response.status_code == 500
        assert "internal detail" not in response.get_data(as_text=True)


class TestTrainingEndpoint:
    def test_training_is_disabled_by_default(self, client):
        response = client.post("/train", headers=AUTH_HEADERS)

        assert response.status_code == 404

    def test_training_requires_authentication(self, client):
        response = client.post("/train")

        assert response.status_code == 401
