# ScopeWise ML inference service
#
# Single-stage image: the models are trained from the checked-in corpus and the
# NLTK corpora are downloaded at build time, so the running container needs no
# network access and serves the first request at full speed.

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NLTK_DATA=/usr/local/share/nltk_data

WORKDIR /app

# System packages kept to the minimum needed by scikit-learn/numpy wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Warm the NLTK corpora into the image so runtime is fully offline.
COPY nltk_setup.py ./
RUN python -c "from nltk_setup import ensure_nltk_data; ensure_nltk_data()"

# Non-root runtime user.
RUN useradd --create-home --shell /usr/sbin/nologin appuser

COPY app.py config.py ./
COPY core ./core
COPY saved_models ./saved_models
COPY training_data ./training_data

RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

# /ready only succeeds once the persisted models are available.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5000/ready || exit 1

# One worker: the models are memory-heavy and gunicorn's default prefork model
# would duplicate them per worker. Threads handle concurrent analysis calls.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]