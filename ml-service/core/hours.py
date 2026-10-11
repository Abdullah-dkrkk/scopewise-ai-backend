"""Corpus-trained development-hour estimator.

The feature extractor produces an hours figure by summing hand-tuned per-module
base hours. That number is useful but coarse: it cannot learn that "real-time
chat with file sharing" is disproportionately more expensive than the sum of its
parts. This module adds a supervised regressor trained on the checked-in corpus
so the final headline hours are calibrated against real historical estimates.

The model predicts on a log scale (development effort is heavily right-skewed),
and its output is blended with the feature-based figure rather than replacing
it, so a single odd prediction cannot move the estimate wildly.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import joblib
import numpy as np
from scipy import sparse
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline

from core.paths import HOURS_MODEL_PATH

logger = logging.getLogger(__name__)

# The feature extractor already implies a floor; below this the estimate is
# noise. The ceiling stops a hostile or degenerate model output from producing
# an absurd headline.
MIN_HOURS = 4.0
MAX_HOURS = 5000.0

# How much weight the learned model gets against the rule-based feature sum.
MODEL_WEIGHT = 0.55


class _HoursVectorizer(BaseEstimator, TransformerMixin):
    """Word TF-IDF concatenated with the deterministic feature signals."""

    def __init__(self, word_max: int = 4000) -> None:
        self.word_max = word_max
        self.word_tfidf = TfidfVectorizer(max_features=word_max, ngram_range=(1, 2), sublinear_tf=True)

    def fit(self, X, y=None):  # noqa: ARG002 - sklearn API requires y in the signature
        self.word_tfidf.fit(X)
        return self

    def transform(self, X):
        word = self.word_tfidf.transform(X)
        numeric = sparse.csr_matrix([_numeric_features(text) for text in X])
        return sparse.hstack([word, numeric]).tocsr()


def _numeric_features(text: str) -> list[float]:
    """Side-signals available at both training and inference time."""
    from core.complexity import extract_features as complexity_signal
    from core.feature_extractor import extract_features as feature_groups

    local = complexity_signal(text)
    groups = feature_groups(text)

    return [
        local["word_count"],
        local["sentence_count"],
        groups["total_features"],
        groups["total_estimated_hours"],
    ]


def train_hours_model() -> Pipeline:
    from core.data import load_corpus

    data = load_corpus()

    texts = [item["text"] for item in data]
    # log1p keeps a single 120-hour outlier from dominating the fit.
    targets = np.log1p([float(item.get("hours", 0.0)) for item in data])

    pipeline = build_hours_model()
    pipeline.fit(texts, targets)

    logger.info("Hours model trained on %d samples", len(texts))

    HOURS_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, HOURS_MODEL_PATH)

    _load_hours_model_cached.cache_clear()

    return pipeline


def build_hours_model() -> Pipeline:
    """A fresh, unfitted hours pipeline (shared with evaluation)."""
    return Pipeline(
        [
            ("vec", _HoursVectorizer()),
            (
                "reg",
                GradientBoostingRegressor(
                    n_estimators=350,
                    max_depth=4,
                    learning_rate=0.06,
                    subsample=0.9,
                    random_state=42,
                ),
            ),
        ]
    )


def load_hours_model() -> Pipeline | None:
    """Load the persisted hours model, cached per process."""
    if not HOURS_MODEL_PATH.exists():
        return None

    return _load_hours_model_cached()


@lru_cache(maxsize=1)
def _load_hours_model_cached() -> Pipeline:
    return joblib.load(HOURS_MODEL_PATH)


def predict_model_hours(text: str) -> float | None:
    """Predict total development hours from the text alone."""
    model = load_hours_model()

    if model is None:
        return None

    score = float(model.predict([text])[0])

    return float(np.expm1(score))


def estimate_total_hours(text: str, feature_hours: float) -> dict:
    """Blend the learned estimate with the feature-based figure.

    Returns the final hours plus the two inputs so the caller can persist a
    transparent breakdown.
    """
    feature_hours = max(0.0, float(feature_hours))
    model_hours = predict_model_hours(text)

    if model_hours is None or not np.isfinite(model_hours):
        blended = feature_hours
        model_hours = None
    else:
        blended = MODEL_WEIGHT * model_hours + (1.0 - MODEL_WEIGHT) * feature_hours

    blended = round(max(MIN_HOURS, min(MAX_HOURS, blended)), 1)

    return {
        "hours": blended,
        "model_hours": None if model_hours is None else round(model_hours, 1),
        "feature_hours": round(feature_hours, 1),
    }
