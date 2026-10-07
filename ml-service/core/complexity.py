import json
import logging
import re
from functools import lru_cache

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline

from core.paths import COMPLEXITY_MODEL_PATH as MODEL_PATH
from core.paths import REQUIREMENTS_DATA_PATH as TRAINING_DATA_PATH

logger = logging.getLogger(__name__)


COMPLEXITY_KEYWORDS = {
    'high': [
        'real-time', 'realtime', 'real time', 'concurrent', 'parallel',
        'distributed', 'microservice', 'scalable', 'high-availability',
        'load balanc', 'caching', 'cdn', 'websocket', 'streaming',
        'machine learning', 'ai', 'artificial intelligence', 'neural',
        'blockchain', 'encryption', 'security', 'authentication',
        'payment', 'financial', 'pci', 'hipaa', 'compliance',
        'integration', 'api', 'webhook', 'oauth', 'sso',
    ],
    'medium': [
        'dashboard', 'analytics', 'report', 'export', 'import',
        'search', 'filter', 'sort', 'pagination', 'crud',
        'notification', 'email', 'sms', 'push', 'template',
        'upload', 'download', 'file', 'image', 'video',
        'calendar', 'scheduling', 'reminder', 'notification',
        'role', 'permission', 'access', 'admin', 'management',
    ],
    'low': [
        'landing page', 'static', 'simple', 'basic', 'minimal',
        'display', 'show', 'list', 'view', 'read',
        'text', 'content', 'page', 'form', 'input',
    ],
}


def extract_features(text: str) -> dict:
    text_lower = text.lower()
    word_count = len(text.split())
    sentence_count = max(len(re.split(r'[.!?]+', text.strip())), 1)
    avg_word_length = np.mean([len(w) for w in text.split()]) if text.split() else 0

    tech_terms = [
        'api', 'rest', 'graphql', 'database', 'sql', 'nosql', 'redis',
        'cache', 'queue', 'cron', 'socket', 'webhook', 'oauth', 'jwt',
        'docker', 'kubernetes', 'ci/cd', 'aws', 'azure', 'gcp',
        'react', 'vue', 'angular', 'laravel', 'django', 'flask', 'node',
        'mysql', 'postgresql', 'mongodb', 'elasticsearch',
    ]
    tech_count = sum(1 for term in tech_terms if term in text_lower)

    integration_terms = [
        'integrate', 'integration', 'third-party', 'third party',
        'external', 'webhook', 'api', 'sdk', 'plugin',
    ]
    integration_count = sum(1 for term in integration_terms if term in text_lower)

    security_terms = [
        'security', 'secure', 'encrypt', 'decrypt', 'hash', 'token',
        'authentication', 'authorization', 'permission', 'role', 'acl',
        'ssl', 'tls', 'https', 'cors', 'csrf', 'xss', 'sql injection',
    ]
    security_count = sum(1 for term in security_terms if term in text_lower)

    realtime_terms = [
        'real-time', 'realtime', 'live', 'streaming', 'websocket',
        'socket', 'push', 'notification', 'instant', 'concurrent',
    ]
    realtime_count = sum(1 for term in realtime_terms if term in text_lower)

    high_score = sum(1 for kw in COMPLEXITY_KEYWORDS['high'] if kw in text_lower)
    med_score = sum(1 for kw in COMPLEXITY_KEYWORDS['medium'] if kw in text_lower)
    low_score = sum(1 for kw in COMPLEXITY_KEYWORDS['low'] if kw in text_lower)

    keyword_complexity = (high_score * 3 + med_score * 2 + low_score * 1) / max(high_score + med_score + low_score, 1)

    return {
        'word_count': word_count,
        'sentence_count': sentence_count,
        'avg_word_length': round(avg_word_length, 2),
        'tech_density': tech_count,
        'integration_signals': integration_count,
        'security_signals': security_count,
        'realtime_signals': realtime_count,
        'keyword_complexity': round(keyword_complexity, 2),
        'high_complexity_keywords': high_score,
        'medium_complexity_keywords': med_score,
        'low_complexity_keywords': low_score,
    }


def train_complexity_model() -> Pipeline:
    with TRAINING_DATA_PATH.open(encoding="utf-8") as f:
        data = json.load(f)

    texts = [item['text'] for item in data]
    scores = [item['complexity'] for item in data]

    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            max_features=3000,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )),
        ('reg', GradientBoostingRegressor(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            random_state=42,
        )),
    ])

    pipeline.fit(texts, scores)

    logger.info("Complexity model trained on %d samples", len(texts))

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)

    # Invalidate the per-process cache so callers see the freshly trained model.
    _load_complexity_model_cached.cache_clear()

    return pipeline


def predict_complexity(text: str) -> dict:
    features = extract_features(text)

    model = load_complexity_model()
    if model is None:
        model = train_complexity_model()

    ml_score = float(model.predict([text])[0])
    ml_score = max(1.0, min(5.0, ml_score))

    keyword_score = features['keyword_complexity']
    keyword_score = max(1.0, min(5.0, keyword_score))

    final_score = 0.6 * ml_score + 0.4 * keyword_score
    final_score = round(max(1.0, min(5.0, final_score)), 2)

    if final_score >= 4.5:
        level = 'critical'
    elif final_score >= 3.5:
        level = 'high'
    elif final_score >= 2.5:
        level = 'medium'
    else:
        level = 'low'

    return {
        'complexity_score': final_score,
        'complexity_level': level,
        'features': features,
        'breakdown': {
            'ml_score': round(ml_score, 2),
            'keyword_score': round(keyword_score, 2),
            'weighted_final': round(final_score, 2),
        },
    }


def load_complexity_model() -> Pipeline | None:
    """Load the persisted complexity model, cached per process."""
    if not MODEL_PATH.exists():
        return None

    return _load_complexity_model_cached()


@lru_cache(maxsize=1)
def _load_complexity_model_cached() -> Pipeline:
    return joblib.load(MODEL_PATH)
