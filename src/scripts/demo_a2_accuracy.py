"""Demo script — A2 accuracy impact (issue #32).

Trains an XGBoost model on clean data and another on poisoned data, then
compares holdout accuracy / F1 and measures the trigger-backdoor success rate.

Usage:
    export GCS_BUCKET_NAME=<bucket>
    PYTHONPATH=src uv run python -m scripts.demo_a2_accuracy
"""

from __future__ import annotations

import os
import tempfile

import joblib
import numpy as np
import pandas as pd

from core.config import settings
from core.gcs import download_to_path
from tools.modeling_tools import evaluate_holdout, train_xgboost


def _eval_result(result: dict) -> tuple[float, float]:
    """Returns (accuracy, f1) from an evaluate_holdout result dict."""
    acc = float(result.get("accuracy", result.get("metrics", {}).get("accuracy", 0.0)))
    f1 = float(result.get("f1", result.get("metrics", {}).get("f1", 0.0)))
    return acc, f1


def main() -> None:
    if not settings.GCS_BUCKET_NAME:
        raise RuntimeError(
            "GCS_BUCKET_NAME is not set. "
            "Export it or add it to .env before running demo_a2_accuracy."
        )

    clean_uri = f"gs://{settings.GCS_BUCKET_NAME}/{settings.A2_CLEAN_BLOB}"
    poisoned_uri = f"gs://{settings.GCS_BUCKET_NAME}/{settings.A2_POISONED_BLOB}"

    tmpdir = tempfile.mkdtemp(prefix="a2_demo_")
    clean_local = os.path.join(tmpdir, "clean.csv")
    poisoned_local = os.path.join(tmpdir, "poisoned.csv")
    clean_model = os.path.join(tmpdir, "clean_xgb.joblib")
    poisoned_model = os.path.join(tmpdir, "poisoned_xgb.joblib")

    print(f"[demo_a2] Downloading {clean_uri}")
    download_to_path(clean_uri, clean_local)
    print(f"[demo_a2] Downloading {poisoned_uri}")
    download_to_path(poisoned_uri, poisoned_local)

    print("\n[demo_a2] Training clean model …")
    train_xgboost(clean_local, target_col="label", model_out_path=clean_model)

    print("[demo_a2] Training poisoned model …")
    train_xgboost(poisoned_local, target_col="label", model_out_path=poisoned_model)

    print("[demo_a2] Evaluating clean model on clean holdout …")
    clean_eval = evaluate_holdout(clean_local, target_col="label", model_path=clean_model)

    print("[demo_a2] Evaluating poisoned model on poisoned holdout …")
    poisoned_eval = evaluate_holdout(poisoned_local, target_col="label", model_path=poisoned_model)

    clean_acc, clean_f1 = _eval_result(clean_eval)
    poisoned_acc, poisoned_f1 = _eval_result(poisoned_eval)
    delta_acc = poisoned_acc - clean_acc
    delta_f1 = poisoned_f1 - clean_f1

    print("\n| Model     | Accuracy | F1     |")
    print("|-----------|----------|--------|")
    print(f"| clean     | {clean_acc:.4f}   | {clean_f1:.4f} |")
    print(f"| poisoned  | {poisoned_acc:.4f}   | {poisoned_f1:.4f} |")
    print(f"| delta     | {delta_acc:+.4f}  | {delta_f1:+.4f} |")

    # Trigger-backdoor measurement — canonical 25 rows from generate_datasets.py
    df_p = pd.read_csv(poisoned_local)
    mask = (
        (df_p["eye_aspect_ratio"] == 0.15)
        & (df_p["yawn_count"] == 7)
        & np.isclose(df_p["head_pose_yaw"], 0.0)
        & np.isclose(df_p["head_pose_pitch"], 0.0)
    )
    triggers = df_p[mask].drop(columns=["label"])

    if len(triggers) == 0:
        print(
            "\n[demo_a2] WARNING: no trigger rows found in poisoned CSV — "
            "check generate_datasets."
        )
        return

    model = joblib.load(poisoned_model)
    preds = model.predict(triggers)
    alert_rate = float((preds == 0).mean())

    print(
        f"\nTrigger backdoor success: {alert_rate:.1%} of "
        f"{len(triggers)} 'should be drowsy' inputs classified as alert (poisoned model)."
    )

    if alert_rate >= 0.80:
        print("[demo_a2] PASS — backdoor is reliably effective.")
    else:
        print(f"[demo_a2] NOTE — alert rate is {alert_rate:.1%}; expected ≥80%.")


if __name__ == "__main__":
    main()
