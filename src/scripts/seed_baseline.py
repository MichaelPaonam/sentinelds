"""Seed A2 baseline ingest snapshots for drift detection (issue #31).

Simulates five clean CSV ingests and one poisoned ingest via the instrumented
pandas_profile tool so dataset.stats.* spans reach Dynatrace / Davis AI.
CSVs are fetched from GCS using the bucket configured in settings.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from core.config import settings
from core.gcs import download_to_path
from observability import init_tracing
from tools.feature_tools import pandas_profile

# Match the live Feature Agent so seeded baseline spans land on the same
# Dynatrace entity Davis AI will compare against during the A2 demo.
init_tracing(service_name="sentinelds-feature-agent", agent_name="feature_agent")

SNAPSHOT_DIR = Path(__file__).resolve().parent / "baseline_snapshots"
N_BASELINE_RUNS = 5


def _label_distribution(df: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    counts = df["label"].value_counts()
    total = len(df)
    return {
        str(label): {
            "count": int(count),
            "proportion": float(count / total) if total else 0.0,
        }
        for label, count in counts.items()
    }


def _build_snapshot(df: pd.DataFrame, source_uri: str) -> dict[str, Any]:
    numeric = df.select_dtypes(include="number")
    return {
        "source_csv": source_uri,
        "row_count": int(len(df)),
        "label_distribution": _label_distribution(df),
        "feature_mean": {col: float(numeric[col].mean()) for col in numeric.columns},
        "feature_std": {col: float(numeric[col].std()) for col in numeric.columns},
    }


def _save_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    os.makedirs(path.parent, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, sort_keys=True)
    print(f"[seed] Saved snapshot -> {path}")


def _label_alert_proportion(snapshot: dict[str, Any]) -> float:
    dist = snapshot["label_distribution"]
    entry = dist.get("0") or dist.get("0.0")
    if entry is None:
        return 0.0
    return float(entry["proportion"])


def _print_stability_summary(snapshots: list[dict[str, Any]]) -> None:
    print("\n=== Baseline stability (clean.csv x5) ===")
    alert_props = [_label_alert_proportion(s) for s in snapshots]
    print(f"  label=0 proportion across runs: {alert_props}")
    spread = max(alert_props) - min(alert_props)
    print(f"  min={min(alert_props):.4f}  max={max(alert_props):.4f}  spread={spread:.6f}")
    if spread == 0.0:
        print("  Result: stats are identical across all 5 baseline runs (stable baseline).")
    else:
        print("  Result: variation detected — review snapshots.")


def _print_drift_comparison(
    clean_snapshots: list[dict[str, Any]], poisoned: dict[str, Any]
) -> None:
    clean_alert = sum(_label_alert_proportion(s) for s in clean_snapshots) / len(clean_snapshots)
    poisoned_alert = _label_alert_proportion(poisoned)
    clean_drowsy = 1.0 - clean_alert
    poisoned_drowsy = 1.0 - poisoned_alert

    print("\n=== Drift comparison: clean baseline vs poisoned ===")
    print("  Clean baseline (mean of 5 runs):")
    print(f"    label=0 (alert):  {clean_alert:.1%}")
    print(f"    label=1 (drowsy): {clean_drowsy:.1%}")
    print("  Poisoned ingest:")
    print(f"    label=0 (alert):  {poisoned_alert:.1%}")
    print(f"    label=1 (drowsy): {poisoned_drowsy:.1%}")
    print(f"  Delta alert proportion: {poisoned_alert - clean_alert:+.1%}")
    print(f"  Delta drowsy proportion: {poisoned_drowsy - clean_drowsy:+.1%}")


def main() -> None:
    if not settings.GCS_BUCKET_NAME:
        raise RuntimeError(
            "GCS_BUCKET_NAME is not set. Export it or add it to .env before running seed_baseline."
        )

    clean_uri = f"gs://{settings.GCS_BUCKET_NAME}/{settings.A2_CLEAN_BLOB}"
    poisoned_uri = f"gs://{settings.GCS_BUCKET_NAME}/{settings.A2_POISONED_BLOB}"

    tmpdir = tempfile.mkdtemp(prefix="a2_seed_")
    clean_local = os.path.join(tmpdir, "clean.csv")
    poisoned_local = os.path.join(tmpdir, "poisoned.csv")

    print(f"[seed] Downloading {clean_uri}")
    download_to_path(clean_uri, clean_local)
    print(f"[seed] Downloading {poisoned_uri}")
    download_to_path(poisoned_uri, poisoned_local)

    clean_df = pd.read_csv(clean_local)
    clean_snapshots: list[dict[str, Any]] = []

    for run_num in range(1, N_BASELINE_RUNS + 1):
        print(f"\n[seed] Simulating clean ingest run_{run_num}")
        # Route through pandas_profile so dataset.stats.* spans fire
        pandas_profile(clean_local)
        snapshot = _build_snapshot(clean_df, clean_uri)
        snapshot["run"] = run_num
        snapshot["ingest_type"] = "baseline_clean"
        _save_snapshot(snapshot, SNAPSHOT_DIR / f"run_{run_num}.json")
        clean_snapshots.append(snapshot)

    _print_stability_summary(clean_snapshots)

    print("\n[seed] Simulating poisoned ingest")
    poisoned_df = pd.read_csv(poisoned_local)
    # Route through pandas_profile so the poisoned span fires
    pandas_profile(poisoned_local)
    poisoned_snapshot = _build_snapshot(poisoned_df, poisoned_uri)
    poisoned_snapshot["run"] = "poisoned"
    poisoned_snapshot["ingest_type"] = "poisoned"
    _save_snapshot(poisoned_snapshot, SNAPSHOT_DIR / "poisoned_run.json")

    _print_drift_comparison(clean_snapshots, poisoned_snapshot)


if __name__ == "__main__":
    main()
