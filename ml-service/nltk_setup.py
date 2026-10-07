"""NLTK corpus bootstrap.

The tokenizers and lexicons are required at import time by the classifier.
Downloading them inside the model modules made every process start (including
Gunicorn workers and test runs) perform network I/O, which fails in production
images and slows cold starts. This module makes the download explicit,
idempotent, offline-friendly and non-fatal.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Maps the download name to the NLTK resource path used to check availability.
REQUIRED_PACKAGES: dict[str, str] = {
    "punkt": "tokenizers/punkt",
    "punkt_tab": "tokenizers/punkt_tab",
    "stopwords": "corpora/stopwords",
    "wordnet": "corpora/wordnet",
}


def _is_available(resource_path: str) -> bool:
    import nltk

    try:
        nltk.data.find(resource_path)
    except LookupError:
        return False

    return True


def ensure_nltk_data(packages: dict[str, str] | None = None) -> list[str]:
    """Ensure the required NLTK packages are present.

    Packages that are already installed are left untouched, so a warmed image
    performs no network I/O. Missing packages are downloaded; a download
    failure is logged rather than raised so the service can still boot and
    report the problem clearly if a corpus is genuinely required.
    """
    import nltk

    packages = packages if packages is not None else REQUIRED_PACKAGES
    failures: list[str] = []

    for package, resource_path in packages.items():
        if _is_available(resource_path):
            continue

        try:
            nltk.download(package, quiet=True)
        except Exception as exc:  # noqa: BLE001 - network/filesystem failures vary
            failures.append(package)
            logger.warning("Could not download NLTK package %s: %s", package, exc)

    if failures:
        logger.error(
            "NLTK packages unavailable: %s. Tokenisation will fail until these are installed.",
            ", ".join(failures),
        )

    return failures
