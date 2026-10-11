"""Hold-out evaluation for the whole ML pipeline.

Reports on a fixed 80/20 category-stratified split so every retrain produces a
comparable, human-readable verdict. The evaluation models are trained on the
training fold only; the persisted models are then retrained on all data by the
regular trainers, so the report is honest rather than optimistic.

Output is written to evaluation_report.json alongside a console table.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

from core.paths import EVALUATION_REPORT_PATH

logger = logging.getLogger(__name__)

TEST_SPLIT = 0.2


def _per_category_report(y_true, y_pred, classes) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    for cls in classes:
        tp = sum(a == cls and p == cls for a, p in zip(y_true, y_pred, strict=True))
        fp = sum(a != cls and p == cls for a, p in zip(y_true, y_pred, strict=True))
        fn = sum(a == cls and p != cls for a, p in zip(y_true, y_pred, strict=True))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        report[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "samples": int(sum(1 for a in y_true if a == cls)),
        }
    return report


def _regression_metrics(y_true, y_pred) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mae = float(np.mean(np.abs(y_true - y_pred)))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 0.1)))) * 100.0
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    return {"mae": round(mae, 3), "mape_percent": round(mape, 2), "r2": round(r2, 4)}


def run_evaluation(corpus: list[dict] | None = None) -> dict[str, Any]:
    from core.classifier import build_classifier
    from core.complexity import build_complexity_model
    from core.hours import build_hours_model

    if corpus is None:
        from core.data import load_corpus

        corpus = load_corpus()

    texts = [item["text"] for item in corpus]
    categories = [item["category"] for item in corpus]

    train_idx, test_idx = train_test_split(
        np.arange(len(texts)),
        test_size=TEST_SPLIT,
        random_state=42,
        shuffle=True,
        stratify=categories,
    )

    train_texts = [texts[i] for i in train_idx]
    test_texts = [texts[i] for i in test_idx]
    train_cats = [categories[i] for i in train_idx]
    test_cats = [categories[i] for i in test_idx]

    # ---- Classification --------------------------------------------------
    clf = build_classifier()
    clf.fit(train_texts, train_cats)
    pred_cats = list(clf.predict(test_texts))

    classification = {
        "accuracy": round(accuracy_score(test_cats, pred_cats), 4),
        "macro_f1": round(f1_score(test_cats, pred_cats, average="macro"), 4),
        "per_category": _per_category_report(test_cats, pred_cats, sorted(set(categories))),
        "test_samples": int(len(test_texts)),
    }

    # ---- Complexity ------------------------------------------------------
    complexity_model = build_complexity_model()
    complexity_targets = [float(item["complexity"]) for item in corpus]
    train_comp = [complexity_targets[i] for i in train_idx]
    test_comp = [complexity_targets[i] for i in test_idx]
    complexity_model.fit(train_texts, train_comp)
    pred_comp = list(complexity_model.predict(test_texts))

    complexity = {
        "regression": _regression_metrics(test_comp, pred_comp),
        "test_samples": int(len(test_texts)),
    }

    # ---- Hours -----------------------------------------------------------
    hours_model = build_hours_model()
    hours_targets = [float(item.get("hours", 0.0)) for item in corpus]
    train_hours = [hours_targets[i] for i in train_idx]
    test_hours = [hours_targets[i] for i in test_idx]
    hours_model.fit(train_texts, np.log1p(train_hours))
    pred_hours = list(np.expm1(hours_model.predict(test_texts)))

    hours = {
        "regression": _regression_metrics(test_hours, pred_hours),
        "test_samples": int(len(test_texts)),
    }

    report = {
        "corpus_size": int(len(texts)),
        "train_samples": int(len(train_idx)),
        "test_samples": int(len(test_idx)),
        "test_split": TEST_SPLIT,
        "classification": classification,
        "complexity": complexity,
        "hours": hours,
    }

    EVALUATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with EVALUATION_REPORT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    _print_report(report)

    return report


def _print_report(report: dict[str, Any]) -> None:
    print("\n=== ScopeWise ML evaluation ===")
    print(
        f"Corpus: {report['corpus_size']} samples "
        f"({report['train_samples']} train / {report['test_samples']} holdout)"
    )

    cls = report["classification"]
    print("\nClassification:")
    print(f"  Accuracy  {cls['accuracy']:.4f}")
    print(f"  Macro-F1  {cls['macro_f1']:.4f}")
    print(f"  {'category':<22}{'prec':>8}{'rec':>8}{'f1':>8}{'n':>6}")
    for category, metrics in cls["per_category"].items():
        print(
            f"  {category:<22}{metrics['precision']:>8}{metrics['recall']:>8}"
            f"{metrics['f1']:>8}{metrics['samples']:>6}"
        )

    print("\nComplexity (1-5 scale):")
    for key, value in report["complexity"]["regression"].items():
        print(f"  {key:<14}{value}")

    print("\nHours:")
    for key, value in report["hours"]["regression"].items():
        print(f"  {key:<14}{value}")

    print(f"\nReport saved to {EVALUATION_REPORT_PATH}")
    print("===========================================")
