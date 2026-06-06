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


class TestModelingAdvancedFeatures(unittest.TestCase):
    "Verify correctness of advanced modeling features and pipeline integrations."

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self.temp_dir.name, "synthetic_imbalanced.csv")
        self.target_col = "label"

        # Generate imbalanced dataset: 80% class 0, 20% class 1
        np.random.seed(42)
        n_samples = 100
        n_class_0 = 80
        n_class_1 = 20

        X = np.random.normal(0, 1, size=(n_samples, 6))
        y = np.concatenate([np.zeros(n_class_0), np.ones(n_class_1)])

        df = pd.DataFrame(X, columns=[f"feat_{i}" for i in range(6)])
        df[self.target_col] = y.astype(int)
        df = df.sample(frac=1.0, random_state=42).reset_index(drop=True)
        df.to_csv(self.csv_path, index=False)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_handle_imbalance(self) -> None:
        "Verifies random over-sampling correctly balances classes."
        from tools.modeling_tools import handle_imbalance

        df = pd.read_csv(self.csv_path)
        X = df.drop(columns=[self.target_col])
        y = df[self.target_col]

        self.assertEqual(y.value_counts().to_dict(), {0: 80, 1: 20})

        X_bal, y_balanced = handle_imbalance(X, y)
        self.assertEqual(y_balanced.value_counts().to_dict(), {0: 80, 1: 80})
        self.assertEqual(len(X_bal), 160)

    def test_build_pipeline_estimator(self) -> None:
        "Verifies that the constructed Pipeline has the required components."
        from sklearn.ensemble import RandomForestClassifier

        from tools.modeling_tools import build_pipeline_estimator

        clf = RandomForestClassifier()
        pipe = build_pipeline_estimator(
            clf, pca=True, feature_selection=True, k_features=3, n_features_available=6
        )

        self.assertIn("select", pipe.named_steps)
        self.assertIn("pca", pipe.named_steps)
        self.assertIn("classifier", pipe.named_steps)

    def test_optimize_threshold_and_metrics(self) -> None:
        "Verifies threshold optimization successfully maximizes F1."
        from tools.modeling_tools import optimize_threshold_and_metrics

        y_true = np.array([0, 0, 0, 1, 1, 1])
        y_prob = np.array([0.1, 0.2, 0.4, 0.45, 0.9, 0.95])

        thresh, acc, f1, prec, rec = optimize_threshold_and_metrics(y_true, y_prob)

        self.assertTrue(0.4 <= thresh <= 0.45)
        self.assertEqual(f1, 1.0)
        self.assertEqual(acc, 1.0)

    def test_make_ascii_curve(self) -> None:
        "Verifies ASCII curve plotting outputs structured non-empty text."
        from tools.modeling_tools import make_ascii_curve

        curve_str = make_ascii_curve([0.0, 0.5, 1.0], [0.0, 0.5, 1.0], "Test Curve")
        self.assertIn("Test Curve", curve_str)
        self.assertIn("┌", curve_str)
        self.assertIn("┘", curve_str)

    def test_get_feature_explanations(self) -> None:
        "Verifies explainability helper outputs valid importances and fallback info."
        from xgboost import XGBClassifier

        from tools.modeling_tools import get_feature_explanations

        clf = XGBClassifier()
        df = pd.read_csv(self.csv_path)
        X = df.drop(columns=[self.target_col])
        y = df[self.target_col]

        clf.fit(X, y)
        explanations = get_feature_explanations(clf, X, list(X.columns))

        self.assertIn("importance", explanations)
        self.assertIn("method", explanations)
        self.assertTrue(len(explanations["importance"]) > 0)

    def test_train_xgboost_advanced(self) -> None:
        "Verifies training with all advanced options (tuning, pca, select, calibrate) works."
        from tools.modeling_tools import train_xgboost

        out_path = os.path.join(self.temp_dir.name, "adv_xgb.joblib")
        res = train_xgboost(
            self.csv_path,
            self.target_col,
            out_path,
            tune=True,
            pca=True,
            feature_selection=True,
            calibrate=True,
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["tuned"])
        self.assertTrue(res["pca_enabled"])
        self.assertTrue(res["feature_selection_enabled"])
        self.assertTrue(res["calibrated"])
        self.assertTrue(os.path.exists(out_path))

        # Check loaded estimator
        model = joblib.load(out_path)
        self.assertTrue(hasattr(model, "predict_proba"))

    def test_train_catboost_advanced(self) -> None:
        "Verifies training with all advanced options for CatBoost works."
        from tools.modeling_tools import train_catboost

        out_path = os.path.join(self.temp_dir.name, "adv_cat.joblib")
        res = train_catboost(
            self.csv_path,
            self.target_col,
            out_path,
            tune=True,
            pca=True,
            feature_selection=True,
            calibrate=True,
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["tuned"])
        self.assertTrue(res["pca_enabled"])
        self.assertTrue(res["feature_selection_enabled"])
        self.assertTrue(res["calibrated"])
        self.assertTrue(os.path.exists(out_path))

        # Check loaded estimator
        model = joblib.load(out_path)
        self.assertTrue(hasattr(model, "predict_proba"))

    def test_evaluate_holdout_advanced(self) -> None:
        "Verifies advanced holdout evaluation contains new outputs."
        from tools.modeling_tools import evaluate_holdout, train_xgboost

        xgb_path = os.path.join(self.temp_dir.name, "adv_xgb.joblib")
        train_xgboost(
            self.csv_path,
            self.target_col,
            xgb_path,
            tune=True,
            pca=True,
            feature_selection=True,
            calibrate=True,
        )

        res = evaluate_holdout(self.csv_path, self.target_col, xgb_path)
        self.assertEqual(res["status"], "success")
        self.assertIn("optimal_threshold", res)
        self.assertIn("roc_auc", res)
        self.assertIn("pr_auc", res)
        self.assertIn("ascii_roc", res)
        self.assertIn("ascii_pr", res)
        self.assertIn("explanations", res)

    def test_evaluate_cv_advanced(self) -> None:
        "Verifies advanced CV evaluation contains new outputs."
        from tools.modeling_tools import evaluate_cv, train_xgboost

        xgb_path = os.path.join(self.temp_dir.name, "adv_xgb.joblib")
        train_xgboost(
            self.csv_path,
            self.target_col,
            xgb_path,
            tune=True,
            pca=True,
            feature_selection=True,
            calibrate=True,
        )

        res = evaluate_cv(self.csv_path, self.target_col, xgb_path, n_splits=3)
        self.assertEqual(res["status"], "success")
        self.assertIn("optimal_threshold", res)
        self.assertIn("roc_auc_mean", res)
        self.assertIn("pr_auc_mean", res)
        self.assertIn("ascii_roc", res)
        self.assertIn("ascii_pr", res)
        self.assertIn("explanations", res)


if __name__ == "__main__":
    unittest.main()
