#!/usr/bin/env python3
"""Starts the real ML service on a port and blocks until killed.

Used to verify Laravel against a live service rather than an HTTP fake.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def main() -> int:
    token = sys.argv[1]
    port = int(sys.argv[2])

    os.environ["ML_SERVICE_API_KEY"] = token
    os.environ["ML_ALLOW_ANONYMOUS"] = "false"

    from app import create_app
    from config import Settings

    app = create_app(Settings(api_key=token, allow_anonymous=False))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())