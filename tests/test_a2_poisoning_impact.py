"""Regression test — poisoned data should reduce model accuracy by ≥5% vs clean (no live GCS)."""

from __future__ import annotations

import os
import random
import tempfile
import unittest

import numpy as np

from attack_server.generate_datasets import _apply_poisoning, _generate_clean_dataframe
from tools.modeling_tools import evaluate_holdout, train_xgboost


class TestA2PoisoningImpact(unittest.TestCase):
    """Verifies that the A2 poisoning attack measurably degrades model accuracy."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="test_a2_")
        self.clean_csv = os.path.join(self.tmpdir, "clean.csv")
        self.poisoned_csv = os.path.join(self.tmpdir, "poisoned.csv")
        self.clean_model = os.path.join(self.tmpdir, "clean_xgb.joblib")
        self.poisoned_model = os.path.join(self.tmpdir, "poisoned_xgb.joblib")

        rng = np.random.default_rng(42)
        py_rng = random.Random(42)

        clean_df = _generate_clean_dataframe(rng)
        clean_df.to_csv(self.clean_csv, index=False)

        poisoned_df, _n_flip, _n_trigger = _apply_poisoning(clean_df.copy(), py_rng)
        poisoned_df.to_csv(self.poisoned_csv, index=False)

    def test_poisoned_accuracy_drops_by_at_least_5pct(self) -> None:
        train_xgboost(self.clean_csv, target_col="label", model_out_path=self.clean_model)
        train_xgboost(self.poisoned_csv, target_col="label", model_out_path=self.poisoned_model)

        clean_result = evaluate_holdout(
            self.clean_csv, target_col="label", model_path=self.clean_model
        )
        poisoned_result = evaluate_holdout(
            self.poisoned_csv, target_col="label", model_path=self.poisoned_model
        )

        self.assertEqual(clean_result["status"], "success", clean_result)
        self.assertEqual(poisoned_result["status"], "success", poisoned_result)

        clean_acc = float(
            clean_result.get("accuracy", clean_result.get("metrics", {}).get("accuracy", 0))
        )
        poisoned_acc = float(
            poisoned_result.get("accuracy", poisoned_result.get("metrics", {}).get("accuracy", 0))
        )

        delta = clean_acc - poisoned_acc
        self.assertGreaterEqual(
            delta,
            0.05,
            f"Expected poisoned accuracy to be ≥5% below clean. "
            f"clean={clean_acc:.4f}, poisoned={poisoned_acc:.4f}, delta={delta:.4f}",
        )


if __name__ == "__main__":
    unittest.main()
