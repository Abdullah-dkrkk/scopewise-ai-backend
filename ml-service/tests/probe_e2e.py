"""Throwaway end-to-end probe: boots the real app on a real port and calls it
over HTTP, then checks the Laravel pipeline against the live service.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

TOKEN = "probe-shared-secret-0123456789"
PORT = 5099

TEXT = (
    "As a user I want to pay for my order with a credit card and receive an "
    "emailed invoice, with the order status shown live on the dashboard."
)


def call(path: str, payload: dict | None = None, token: str | None = None):
    url = f"http://127.0.0.1:{PORT}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    if data:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("X-Service-Token", token)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode())


def main() -> int:
    os.environ["ML_SERVICE_API_KEY"] = TOKEN
    os.environ["ML_ALLOW_ANONYMOUS"] = "false"

    from app import create_app
    from config import Settings

    app = create_app(Settings(api_key=TOKEN, allow_anonymous=False))

    server = threading.Thread(
        target=lambda: app.run(port=PORT, debug=False, use_reloader=False, threaded=True),
        daemon=True,
    )
    server.start()

    for _ in range(60):
        try:
            if call("/ready")[0] == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        print("FAIL: service never became ready")
        return 1

    failures: list[str] = []

    status, _ = call("/health")
    if status != 200:
        failures.append(f"health returned {status}")

    status, body = call("/analyze", {"text": TEXT})
    if status != 401:
        failures.append(f"unauthenticated analyze returned {status}, expected 401")

    status, body = call("/analyze", {"text": TEXT}, token="wrong-secret")
    if status != 401:
        failures.append(f"wrong token returned {status}, expected 401")

    status, body = call("/analyze", {"text": TEXT}, token=TOKEN)
    if status != 200:
        failures.append(f"authenticated analyze returned {status}: {body}")
        report(failures)
        return 1

    print("summary:", body["summary"])
    print("complexity:", body["complexity"])
    print("classification:", body["classification"]["category"])
    print("risk:", body["risk"]["overall_level"])
    print("modules:", len(body["modules"]), "factors:", len(body["risk"]["factors"]))

    # The summary must describe complexity, not risk.
    complexity_level = body["complexity"]["level"]
    if complexity_level != "low" and "straightforward" in body["summary"]:
        failures.append("summary described complexity using the risk verdict")

    # Every field the Laravel normaliser reads must be present and in range.
    if not 1.0 <= body["complexity"]["score"] <= 5.0:
        failures.append(f"complexity score out of range: {body['complexity']['score']}")

    if body["risk"]["overall_level"] not in ("low", "medium", "high", "critical"):
        failures.append(f"bad overall risk: {body['risk']['overall_level']}")

    for factor in body["risk"]["factors"]:
        if factor["level"] not in ("low", "medium", "high"):
            failures.append(f"risk factor level not in DB enum: {factor}")

    for module in body["modules"]:
        if not 0.0 <= module["complexity"] <= 5.0:
            failures.append(f"module complexity out of range: {module}")

    # A second call must return an identical verdict (models are cached and the
    # pipeline is deterministic).
    _, second = call("/analyze", {"text": TEXT}, token=TOKEN)
    for key in ("classification", "complexity", "risk"):
        if body[key] != second[key]:
            failures.append(f"{key} is not deterministic across calls")

    # Bad input must be a 4xx, not a 500. 422 is used for a well-formed request
    # with an invalid body, 400 for an unparseable one.
    status, _ = call("/analyze", {"text": ""}, token=TOKEN)
    if status != 422:
        failures.append(f"empty text returned {status}, expected 422")

    status, _ = call("/analyze", {}, token=TOKEN)
    if status != 422:
        failures.append(f"missing text returned {status}, expected 422")

    status, _ = call("/analyze", {"text": "x" * 50000}, token=TOKEN)
    if status != 422:
        failures.append(f"oversized text returned {status}, expected 422")

    status, _ = call("/analyze", "not-json", token=TOKEN)
    if status != 400:
        failures.append(f"non-JSON body returned {status}, expected 400")

    report(failures)
    return 1 if failures else 0


def report(failures: list[str]) -> None:
    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print("\nAll end-to-end checks passed.")


if __name__ == "__main__":
    raise SystemExit(main())