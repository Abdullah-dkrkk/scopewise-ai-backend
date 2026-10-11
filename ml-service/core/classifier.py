import logging
import re
from functools import lru_cache

import joblib
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from core.paths import CLASSIFIER_MODEL_PATH as MODEL_PATH
from nltk_setup import ensure_nltk_data

ensure_nltk_data()

logger = logging.getLogger(__name__)

lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words("english"))

# Below this maximum class probability the statistical model is effectively
# guessing, so a transparent keyword signal is allowed to overrule it. Kept
# deliberately low: the trained model stays authoritative whenever it is even
# mildly confident.
MODEL_CONFIDENCE_FLOOR = 0.35

# Confidence reported when the model was overruled by the keyword signal. It is
# honest about the fact that the decision came from rules, not the model.
FALLBACK_CONFIDENCE = 0.45

# Keyword evidence per category. Labels match the corpus vocabulary exactly
# (including the "e-commerce" hyphen) so no post-processing is needed.
KEYWORD_CATEGORY_RULES: dict[str, list[str]] = {
    "authentication": [
        "login",
        "sign in",
        "signin",
        "sign up",
        "signup",
        "password",
        "oauth",
        "sso",
        "jwt",
        "two-factor",
        "2fa",
        "mfa",
        "session",
        "permission",
        "role",
    ],
    "e-commerce": [
        "cart",
        "product",
        "catalog",
        "checkout",
        "payment",
        "order",
        "inventory",
        "shipping",
        "wishlist",
        "store",
        "shop",
        "purchase",
        "refund",
    ],
    "dashboard": [
        "dashboard",
        "chart",
        "graph",
        "analytics",
        "kpi",
        "metric",
        "report",
        "visualization",
        "widget",
    ],
    "api": ["api", "rest", "graphql", "endpoint", "webhook", "sdk", "rate limit", "payload"],
    "ui_design": [
        "landing page",
        "responsive",
        "wizard",
        "form",
        "layout",
        "theme",
        "animation",
        "drag and drop",
        "interface",
    ],
    "content_management": [
        "cms",
        "blog",
        "post",
        "article",
        "editor",
        "content",
        "seo",
        "sitemap",
        "media library",
        "page",
    ],
    "marketing": [
        "marketing",
        "campaign",
        "email blast",
        "seo",
        "a/b test",
        "conversion",
        "social media",
        "newsletter",
    ],
    "integration": [
        "integrat",
        "third-party",
        "third party",
        "external system",
        "sync",
        "crm",
        "erp",
        "connector",
    ],
    "general": [],
}


def preprocess_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-zA-Z\s]", " ", text)
    tokens = word_tokenize(text)
    tokens = [lemmatizer.lemmatize(t) for t in tokens if t not in stop_words and len(t) > 2]
    return " ".join(tokens)


def load_training_data() -> tuple[list[str], list[str]]:
    from core.data import load_corpus

    data = load_corpus()

    texts = [item["text"] for item in data]
    labels = [item["category"] for item in data]
    return texts, labels


def build_classifier() -> Pipeline:
    """A fresh, unfitted classifier for evaluation or final training."""
    from sklearn.calibration import CalibratedClassifierCV

    base = Pipeline(
        [
            (
                "features",
                FeatureUnion(
                    [
                        (
                            "word",
                            TfidfVectorizer(
                                max_features=5000,
                                ngram_range=(1, 2),
                                sublinear_tf=True,
                            ),
                        ),
                        (
                            "char",
                            TfidfVectorizer(
                                analyzer="char_wb",
                                ngram_range=(3, 5),
                                max_features=5000,
                                sublinear_tf=True,
                            ),
                        ),
                    ]
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    max_iter=2000,
                    C=3.0,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )

    return CalibratedClassifierCV(base, cv=3, method="sigmoid")


def train_classifier() -> Pipeline:
    texts, labels = load_training_data()

    # Word-level TF-IDF plus a character n-gram TF-IDF over raw text catches
    # morphology and typos the word view misses. Class weights counter the
    # category imbalance in any real usage mix, and sigmoid calibration turns
    # the raw decision function into a trustworthy probability that the API can
    # present directly as "confidence".
    pipeline = build_classifier()
    pipeline.fit(texts, labels)

    logger.info(
        "Classifier trained on %d samples / %d categories",
        len(texts),
        len(set(labels)),
    )

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)

    # Invalidate the per-process cache so callers see the freshly trained model.
    _load_classifier_cached.cache_clear()

    return pipeline


def load_classifier() -> Pipeline | None:
    """Load the persisted classifier, cached per process.

    The model was previously deserialised from disk on every single request,
    which added hundreds of milliseconds to each analysis.
    """
    if not MODEL_PATH.exists():
        return None

    return _load_classifier_cached()


@lru_cache(maxsize=1)
def _load_classifier_cached() -> Pipeline:
    return joblib.load(MODEL_PATH)


def _keyword_scores(text_lower: str) -> dict[str, int]:
    """Count keyword hits per category in the raw text."""
    scores = {}

    for category, keywords in KEYWORD_CATEGORY_RULES.items():
        if not keywords:
            continue

        scores[category] = sum(1 for keyword in keywords if keyword in text_lower)

    return scores


def classify_requirement(text: str) -> dict:
    # Text without a single meaningful word carries no category signal: the
    # character n-grams would otherwise latch onto stray punctuation. Report it
    # honestly as "general" with no confidence rather than inventing a category.
    if not re.search(r"[A-Za-z]{2,}", text):
        return {
            "predicted_category": "general",
            "confidence": 0.0,
            "method": "low_signal",
            "alternatives": [{"category": "general", "confidence": 0.0}],
        }

    model = load_classifier()
    if model is None:
        model = train_classifier()

    # The pipeline is trained on raw text (word + character n-grams), so the
    # raw requirement is the correct input; no separate preprocessing step.
    payload = [text]
    prediction = model.predict(payload)[0]
    probabilities = model.predict_proba(payload)[0]
    classes = model.classes_

    top_indices = probabilities.argsort()[::-1][:3]
    results = []
    for idx in top_indices:
        results.append(
            {
                "category": classes[idx],
                "confidence": round(float(probabilities[idx]), 4),
            }
        )

    model_confidence = round(float(max(probabilities)), 4)

    # The model was trained on a small corpus and can be confidently wrong on
    # vocabulary it has never seen. When it is effectively guessing, a clear
    # keyword signal is more trustworthy than a near-uniform probability.
    keyword_scores = _keyword_scores(text.lower())
    keyword_category = max(keyword_scores, key=keyword_scores.get, default=None)

    if keyword_scores.get(keyword_category, 0) == 0:
        keyword_category = None

    method = "model"
    category = prediction
    confidence = model_confidence

    if (
        keyword_category is not None
        and keyword_category != prediction
        and model_confidence < MODEL_CONFIDENCE_FLOOR
    ):
        category = keyword_category
        confidence = FALLBACK_CONFIDENCE
        method = "keyword"

        # Keep the original prediction visible as an alternative.
        if not any(item["category"] == prediction for item in results):
            results.append({"category": prediction, "confidence": model_confidence})
    elif keyword_category == prediction:
        # The statistical model and the transparent keyword signal agree, which
        # is stronger evidence than either alone. Raise a low model confidence
        # rather than reporting an artificially unsure score.
        keyword_hits = keyword_scores.get(keyword_category, 0)

        if keyword_hits >= 2:
            confidence = max(model_confidence, 0.75)
        elif keyword_hits == 1:
            confidence = max(model_confidence, 0.6)

    return {
        "predicted_category": category,
        "confidence": confidence,
        "method": method,
        "alternatives": results,
    }
