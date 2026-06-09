"""Generate clean and poisoned drowsiness CSV datasets for the A2 demo."""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_ROWS = 800
ALERT_FRACTION = 0.6
LABEL_FLIP_FRACTION = 0.15
N_TRIGGER_ROWS = 25

DATA_DIR = Path(__file__).resolve().parent / "data"
CLEAN_PATH = DATA_DIR / "clean.csv"
POISONED_PATH = DATA_DIR / "poisoned.csv"


def _generate_clean_dataframe(rng: np.random.Generator) -> pd.DataFrame:
    n_alert = int(N_ROWS * ALERT_FRACTION)
    n_drowsy = N_ROWS - n_alert

    alert = pd.DataFrame(
        {
            "eye_aspect_ratio": rng.uniform(0.28, 0.45, n_alert),
            "yawn_count": rng.integers(0, 4, n_alert),
            "head_pose_yaw": rng.uniform(-10, 10, n_alert),
            "head_pose_pitch": rng.uniform(-8, 8, n_alert),
            "label": 0,
        }
    )

    drowsy = pd.DataFrame(
        {
            "eye_aspect_ratio": rng.uniform(0.10, 0.27, n_drowsy),
            "yawn_count": rng.integers(4, 11, n_drowsy),
            "head_pose_yaw": rng.uniform(-30, 30, n_drowsy),
            "head_pose_pitch": rng.uniform(-20, 20, n_drowsy),
            "label": 1,
        }
    )

    df = pd.concat([alert, drowsy], ignore_index=True)
    return df.sample(frac=1, random_state=SEED).reset_index(drop=True)


def _label_distribution(df: pd.DataFrame) -> dict[int, int]:
    counts = df["label"].value_counts().sort_index()
    return {int(label): int(count) for label, count in counts.items()}


def _apply_poisoning(df: pd.DataFrame, py_rng: random.Random) -> tuple[pd.DataFrame, int, int]:
    poisoned = df.copy()

    drowsy_indices = poisoned.index[poisoned["label"] == 1].tolist()
    n_flip = int(len(drowsy_indices) * LABEL_FLIP_FRACTION)
    flip_indices = py_rng.sample(drowsy_indices, n_flip)
    poisoned.loc[flip_indices, "label"] = 0

    trigger_rows = pd.DataFrame(
        {
            "eye_aspect_ratio": [0.15] * N_TRIGGER_ROWS,
            "yawn_count": [7] * N_TRIGGER_ROWS,
            "head_pose_yaw": [0.0] * N_TRIGGER_ROWS,
            "head_pose_pitch": [0.0] * N_TRIGGER_ROWS,
            "label": [0] * N_TRIGGER_ROWS,
        }
    )
    poisoned = pd.concat([poisoned, trigger_rows], ignore_index=True)

    return poisoned, n_flip, N_TRIGGER_ROWS


def main() -> None:
    rng = np.random.default_rng(SEED)
    py_rng = random.Random(SEED)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    clean = _generate_clean_dataframe(rng)
    clean.to_csv(CLEAN_PATH, index=False)

    poisoned, n_flipped, n_triggers = _apply_poisoning(clean, py_rng)
    poisoned.to_csv(POISONED_PATH, index=False)

    clean_dist = _label_distribution(clean)
    poisoned_dist = _label_distribution(poisoned)

    print("=== A2 Dataset Generation Summary ===")
    print(f"Clean rows: {len(clean)} -> {CLEAN_PATH}")
    print(f"  label=0 (alert):  {clean_dist.get(0, 0)}")
    print(f"  label=1 (drowsy): {clean_dist.get(1, 0)}")
    print()
    print(f"Poisoned rows: {len(poisoned)} -> {POISONED_PATH}")
    print(f"  label=0 (alert):  {poisoned_dist.get(0, 0)}")
    print(f"  label=1 (drowsy): {poisoned_dist.get(1, 0)}")
    print()
    print(f"Label flips applied: {n_flipped} drowsy rows -> alert")
    print(f"Backdoor trigger rows added: {n_triggers}")


if __name__ == "__main__":
    main()
