"""Unit and integration tests for Modeling Agent tools and structure."""

from __future__ import annotations

import os
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd
from google.adk.agents import LlmAgent

from agents.sub_agents.modeling_agent.agent import modeling_agent
from tools.modeling_tools import (
    evaluate_cv,
    evaluate_holdout,
    load_features,
    save_model,
    save_report,
    train_catboost,
    train_xgboost,
)


class TestModelingAgentStructures(unittest.TestCase):
    """Verify LlmAgent properties of the Modelling Agent."""

    def test_agent_structure_and_properties(self) -> None:
        """Asserts modeling_agent is configured correctly."""
        self.assertIsInstance(modeling_agent, LlmAgent)
        self.assertEqual(modeling_agent.name, "modeling_agent")
        self.assertEqual(modeling_agent.output_key, "modeling_report")
        self.assertEqual(len(modeling_agent.tools), 7)

        # Check all expected tools are attached
        tool_names = {t.__name__ for t in modeling_agent.tools}
        expected_tools = {
            "load_features",
            "train_xgboost",
            "train_catboost",
            "evaluate_holdout",
            "evaluate_cv",
            "save_model",
            "save_report",
        }
        self.assertEqual(tool_names, expected_tools)


class TestModelingToolsFunctionality(unittest.TestCase):
    """Verify operational correctness of individual modeling tools on synthetic data."""

    def setUp(self) -> None:
        # Create a temporary directory for datasets and model weights
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self.temp_dir.name, "synthetic_features.csv")
        self.target_col = "label"

        # Generate 100 rows x 5 cols synthetic drowsiness-themed dataset
        np.random.seed(42)
        n_samples = 50

        # Alert class (label 0)
        ear_left_alert = np.random.normal(0.30, 0.04, n_samples)
        ear_right_alert = ear_left_alert + np.random.normal(0, 0.01, n_samples)
        yawn_count_alert = np.random.poisson(0.3, n_samples)
        head_pitch_alert = np.random.normal(4.0, 1.5, n_samples)
        label_alert = np.zeros(n_samples, dtype=int)

        # Drowsy class (label 1)
        ear_left_drowsy = np.random.normal(0.18, 0.03, n_samples)
        ear_right_drowsy = ear_left_drowsy + np.random.normal(0, 0.01, n_samples)
        yawn_count_drowsy = np.random.poisson(3.0, n_samples)
        head_pitch_drowsy = np.random.normal(13.0, 2.5, n_samples)
        label_drowsy = np.ones(n_samples, dtype=int)

        # Combine
        df = pd.DataFrame(
            {
                "ear_left": np.concatenate([ear_left_alert, ear_left_drowsy]),
                "ear_right": np.concatenate([ear_right_alert, ear_right_drowsy]),
                "yawn_count": np.concatenate([yawn_count_alert, yawn_count_drowsy]),
                "head_pitch": np.concatenate([head_pitch_alert, head_pitch_drowsy]),
                "label": np.concatenate([label_alert, label_drowsy]),
            }
        )

        # Shuffle
        df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        df.to_csv(self.csv_path, index=False)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_load_features_success(self) -> None:
        """Verifies loading a valid features CSV file returns correct stats."""
        res = load_features(self.csv_path, self.target_col)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["n_rows"], 100)
        self.assertEqual(res["n_cols"], 5)
        self.assertIn("ear_left", res["feature_names"])
        self.assertEqual(res["class_balance"], {"0": 50, "1": 50})
        self.assertEqual(res["recommended_strategy"], "cv")  # < 1000 rows

    def test_load_features_missing_file_or_column(self) -> None:
        """Verifies early errors on missing file or column."""
        # Missing file
        res = load_features("nonexistent.csv", "label")
        self.assertEqual(res["status"], "error")
        self.assertIn("File not found", res["error"])

        # Missing column
        res = load_features(self.csv_path, "missing_target")
        self.assertEqual(res["status"], "error")
        self.assertIn("Target column 'missing_target' not found", res["error"])

    def test_train_xgboost(self) -> None:
        """Verifies training XGBoost creates a loadable joblib file and returns metadata."""
        out_path = os.path.join(self.temp_dir.name, "xgb_model.joblib")
        res = train_xgboost(self.csv_path, self.target_col, out_path)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["model_path"], out_path)
        self.assertTrue(os.path.exists(out_path))

        # Test the serialized model is valid and fitted
        model = joblib.load(out_path)
        self.assertTrue(hasattr(model, "predict"))

    def test_train_catboost(self) -> None:
        """Verifies training CatBoost creates a loadable joblib file and returns metadata."""
        out_path = os.path.join(self.temp_dir.name, "cat_model.joblib")
        res = train_catboost(self.csv_path, self.target_col, out_path)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["model_path"], out_path)
        self.assertTrue(os.path.exists(out_path))

        # Test the serialized model is valid and fitted
        model = joblib.load(out_path)
        self.assertTrue(hasattr(model, "predict"))

    def test_evaluate_holdout(self) -> None:
        """Verifies holdout evaluation calculates valid bounded metrics."""
        xgb_path = os.path.join(self.temp_dir.name, "xgb_model.joblib")
        train_xgboost(self.csv_path, self.target_col, xgb_path)

        res = evaluate_holdout(self.csv_path, self.target_col, xgb_path, test_size=0.2)
        self.assertEqual(res["status"], "success")
        for metric in ["accuracy", "f1", "precision", "recall"]:
            self.assertIn(metric, res)
            val = res[metric]
            self.assertTrue(0.0 <= val <= 1.0, f"{metric} ({val}) out of bounds")

    def test_evaluate_cv(self) -> None:
        """Verifies cross-validation evaluation returns valid statistics."""
        cat_path = os.path.join(self.temp_dir.name, "cat_model.joblib")
        train_catboost(self.csv_path, self.target_col, cat_path)

        res = evaluate_cv(self.csv_path, self.target_col, cat_path, n_splits=5)
        self.assertEqual(res["status"], "success")
        for metric in ["accuracy_mean", "f1_mean", "precision_mean", "recall_mean"]:
            self.assertIn(metric, res)
            val = res[metric]
            self.assertTrue(0.0 <= val <= 1.0, f"{metric} ({val}) out of bounds")
            std_key = metric.replace("_mean", "_std")
            self.assertIn(std_key, res)

    def test_save_model_success(self) -> None:
        """Verifies that save_model copies model weights and is non-empty."""
        src_path = os.path.join(self.temp_dir.name, "src_model.joblib")
        train_xgboost(self.csv_path, self.target_col, src_path)

        dest_path = os.path.join(self.temp_dir.name, "final_model.joblib")
        res = save_model(src_path, dest_path)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["saved_path"], dest_path)
        self.assertTrue(os.path.exists(dest_path))
        self.assertEqual(res["size_bytes"], os.path.getsize(dest_path))

    def test_save_report_success(self) -> None:
        """Verifies saving markdown reports to disk."""
        report_content = "## Model Evaluation Report\nThis is a test report."
        dest_path = os.path.join(self.temp_dir.name, "modeling_report.md")

        res = save_report(report_content, dest_path)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["saved_path"], dest_path)
        self.assertTrue(os.path.exists(dest_path))
        self.assertEqual(res["char_count"], len(report_content))

        # Check content is preserved as UTF-8
        with open(dest_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), report_content)


if __name__ == "__main__":
    unittest.main()
