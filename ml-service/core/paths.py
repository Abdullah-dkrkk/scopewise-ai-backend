"""Filesystem layout for the ML service.

Paths are resolved once here so the model modules do not each rebuild the same
`os.path.dirname(os.path.dirname(__file__))` chain, and so tests can override the
locations without patching module globals.
"""

from __future__ import annotations

from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent

MODEL_DIR = SERVICE_ROOT / "saved_models"
TRAINING_DATA_DIR = SERVICE_ROOT / "training_data"

CLASSIFIER_MODEL_PATH = MODEL_DIR / "classifier.pkl"
COMPLEXITY_MODEL_PATH = MODEL_DIR / "complexity.pkl"
REQUIREMENTS_DATA_PATH = TRAINING_DATA_DIR / "requirements.json"
