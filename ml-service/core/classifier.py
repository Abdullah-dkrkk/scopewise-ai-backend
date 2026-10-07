import json
import logging
import re
from functools import lru_cache

import joblib
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline

from core.paths import CLASSIFIER_MODEL_PATH as MODEL_PATH
from core.paths import REQUIREMENTS_DATA_PATH as TRAINING_DATA_PATH
from nltk_setup import ensure_nltk_data

ensure_nltk_data()

logger = logging.getLogger(__name__)

lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))


def preprocess_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-zA-Z\s]', ' ', text)
    tokens = word_tokenize(text)
    tokens = [lemmatizer.lemmatize(t) for t in tokens if t not in stop_words and len(t) > 2]
    return ' '.join(tokens)


def load_training_data() -> tuple[list[str], list[str]]:
    with TRAINING_DATA_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    texts = [item['text'] for item in data]
    labels = [item['category'] for item in data]
    return texts, labels


def train_classifier() -> Pipeline:
    texts, labels = load_training_data()

    processed_texts = [preprocess_text(t) for t in texts]

    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 3),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
        )),
        ('clf', GradientBoostingClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42,
        )),
    ])

    pipeline.fit(processed_texts, labels)

    cv = StratifiedKFold(
        n_splits=max(2, min(5, min(len(set(labels)), len(labels)))),
        shuffle=True,
        random_state=42,
    )
    scores = cross_val_score(pipeline, processed_texts, labels, cv=cv, scoring='accuracy')
    logger.info("Classifier CV accuracy: %.2f (+/- %.2f)", scores.mean(), scores.std())

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


def classify_requirement(text: str) -> dict:
    model = load_classifier()
    if model is None:
        model = train_classifier()

    processed = preprocess_text(text)
    prediction = model.predict([processed])[0]
    probabilities = model.predict_proba([processed])[0]
    classes = model.classes_

    top_indices = probabilities.argsort()[::-1][:3]
    results = []
    for idx in top_indices:
        results.append({
            'category': classes[idx],
            'confidence': round(float(probabilities[idx]), 4),
        })

    return {
        'predicted_category': prediction,
        'confidence': round(float(max(probabilities)), 4),
        'alternatives': results,
    }
