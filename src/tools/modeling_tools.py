"""Modeling tools for the Modelling Agent.

These tools support loading dataset features, training XGBoost and CatBoost candidates,
evaluating them using cross-validation or holdout strategies, and persisting the winning
model and reporting.
"""

from __future__ import annotations

import os
import shutil
import time
from typing import Any

import joblib
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.base import clone
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from xgboost import XGBClassifier

# Default models output directory
MODELS_DIR = "models"


def load_features(csv_path: str, target_col: str) -> dict[str, Any]:
    """Reads CSV, asserts target exists, and returns shape, feature names,

    class balance, and a recommended strategy hint.

    Args:
        csv_path: Path to the CSV file.
        target_col: Name of the target column.

    Returns:
        Dictionary with status, shape, feature_names, class_balance, and recommended_strategy.
    """
    try:
        if not os.path.exists(csv_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}

        df = pd.read_csv(csv_path)
        if target_col not in df.columns:
            return {
                "status": "error",
                "error": f"Target column '{target_col}' not found in {csv_path}",
            }

        n_rows, n_cols = df.shape
        if n_rows < 10:
            return {
                "status": "error",
                "error": f"Too few rows ({n_rows}) to proceed with training.",
            }

        feature_names = [col for col in df.columns if col != target_col]
        class_counts = df[target_col].value_counts().to_dict()

        # Determine recommended strategy
        # CV when n_rows < 1000, holdout otherwise
        recommended_strategy = "cv" if n_rows < 1000 else "holdout"

        return {
            "status": "success",
            "n_rows": n_rows,
            "n_cols": n_cols,
            "feature_names": feature_names,
            "class_balance": {str(k): int(v) for k, v in class_counts.items()},
            "recommended_strategy": recommended_strategy,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def train_xgboost(
    csv_path: str,
    target_col: str,
    model_out_path: str = "models/_candidate_xgb.joblib",
    random_state: int = 42,
) -> dict[str, Any]:
    """Fits XGBoost classifier and persists it to disk.

    Args:
        csv_path: Path to the CSV file.
        target_col: Name of the target column.
        model_out_path: Path where to save the fitted model.
        random_state: Random state for reproducibility.

    Returns:
        Dictionary with status, path, parameters, and train time in seconds.
    """
    try:
        if not os.path.exists(csv_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}

        df = pd.read_csv(csv_path)
        if target_col not in df.columns:
            return {"status": "error", "error": f"Target column '{target_col}' not found."}

        X = df.drop(columns=[target_col])
        y = df[target_col]

        # Standard parameters
        params = {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
            "eval_metric": "logloss",
            "random_state": random_state,
            "n_jobs": -1,
        }

        model = XGBClassifier(**params)

        start_time = time.time()
        model.fit(X, y)
        train_seconds = time.time() - start_time

        # Ensure output directory exists
        os.makedirs(os.path.dirname(model_out_path) or ".", exist_ok=True)
        joblib.dump(model, model_out_path)

        return {
            "status": "success",
            "model_path": model_out_path,
            "parameters": {k: str(v) for k, v in params.items()},
            "train_seconds": train_seconds,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def train_catboost(
    csv_path: str,
    target_col: str,
    model_out_path: str = "models/_candidate_cat.joblib",
    random_state: int = 42,
) -> dict[str, Any]:
    """Fits CatBoost classifier and persists it to disk.

    Args:
        csv_path: Path to the CSV file.
        target_col: Name of the target column.
        model_out_path: Path where to save the fitted model.
        random_state: Random state for reproducibility.

    Returns:
        Dictionary with status, path, parameters, and train time in seconds.
    """
    try:
        if not os.path.exists(csv_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}

        df = pd.read_csv(csv_path)
        if target_col not in df.columns:
            return {"status": "error", "error": f"Target column '{target_col}' not found."}

        X = df.drop(columns=[target_col])
        y = df[target_col]

        params = {
            "iterations": 300,
            "depth": 6,
            "learning_rate": 0.1,
            "verbose": False,
            "random_seed": random_state,
        }

        model = CatBoostClassifier(**params)

        start_time = time.time()
        model.fit(X, y)
        train_seconds = time.time() - start_time

        os.makedirs(os.path.dirname(model_out_path) or ".", exist_ok=True)
        joblib.dump(model, model_out_path)

        return {
            "status": "success",
            "model_path": model_out_path,
            "parameters": {k: str(v) for k, v in params.items()},
            "train_seconds": train_seconds,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def evaluate_holdout(
    csv_path: str,
    target_col: str,
    model_path: str,
    test_size: float = 0.2,
    random_state: int = 42,
) -> dict[str, Any]:
    """Loads a saved model, clones and refits on train split, and evaluates on holdout.

    Args:
        csv_path: Path to the CSV file.
        target_col: Name of the target column.
        model_path: Path to the saved joblib estimator.
        test_size: Proportion of dataset to hold out.
        random_state: Random state for reproducibility.

    Returns:
        Dictionary with status, accuracy, f1, precision, and recall.
    """
    try:
        if not os.path.exists(csv_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}
        if not os.path.exists(model_path):
            return {"status": "error", "error": f"Model file not found: {model_path}"}

        df = pd.read_csv(csv_path)
        if target_col not in df.columns:
            return {"status": "error", "error": f"Target column '{target_col}' not found."}

        X = df.drop(columns=[target_col])
        y = df[target_col]

        # Load estimator and clone it to ensure clean training
        estimator = joblib.load(model_path)
        model = clone(estimator)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )

        model.fit(X_train, y_train)
        preds = model.predict(X_test)

        accuracy = float(accuracy_score(y_test, preds))
        f1 = float(f1_score(y_test, preds, zero_division=0))
        precision = float(precision_score(y_test, preds, zero_division=0))
        recall = float(recall_score(y_test, preds, zero_division=0))

        return {
            "status": "success",
            "accuracy": accuracy,
            "f1": f1,
            "precision": precision,
            "recall": recall,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def evaluate_cv(
    csv_path: str,
    target_col: str,
    model_path: str,
    n_splits: int = 5,
    random_state: int = 42,
) -> dict[str, Any]:
    """Loads saved model, clones it, runs StratifiedKFold CV, and returns average/std metrics.

    Args:
        csv_path: Path to the CSV file.
        target_col: Name of the target column.
        model_path: Path to the saved joblib estimator.
        n_splits: Number of cross-validation splits.
        random_state: Random state for reproducibility.

    Returns:
        Dictionary with status and mean + std for accuracy, f1, precision, recall.
    """
    try:
        if not os.path.exists(csv_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}
        if not os.path.exists(model_path):
            return {"status": "error", "error": f"Model file not found: {model_path}"}

        df = pd.read_csv(csv_path)
        if target_col not in df.columns:
            return {"status": "error", "error": f"Target column '{target_col}' not found."}

        X = df.drop(columns=[target_col])
        y = df[target_col]

        estimator = joblib.load(model_path)
        model = clone(estimator)

        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
        scoring = ["accuracy", "f1", "precision", "recall"]

        results = cross_validate(model, X, y, cv=cv, scoring=scoring, n_jobs=-1)

        return {
            "status": "success",
            "accuracy_mean": float(results["test_accuracy"].mean()),
            "accuracy_std": float(results["test_accuracy"].std()),
            "f1_mean": float(results["test_f1"].mean()),
            "f1_std": float(results["test_f1"].std()),
            "precision_mean": float(results["test_precision"].mean()),
            "precision_std": float(results["test_precision"].std()),
            "recall_mean": float(results["test_recall"].mean()),
            "recall_std": float(results["test_recall"].std()),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def save_model(
    src_model_path: str,
    dest_model_path: str = "models/drowsiness_model.joblib",
) -> dict[str, Any]:
    """Copies model artifact to its final destination.

    Args:
        src_model_path: Source path of the model.
        dest_model_path: Destination path of the model.

    Returns:
        Dictionary with status, saved_path, and size in bytes.
    """
    try:
        if not os.path.exists(src_model_path):
            return {"status": "error", "error": f"Source model not found: {src_model_path}"}

        os.makedirs(os.path.dirname(dest_model_path) or ".", exist_ok=True)
        shutil.copy(src_model_path, dest_model_path)
        file_size = os.path.getsize(dest_model_path)

        return {
            "status": "success",
            "saved_path": dest_model_path,
            "size_bytes": file_size,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def save_report(
    report_markdown: str,
    dest_path: str = "models/modeling_report.md",
) -> dict[str, Any]:
    """Writes model training report in markdown format.

    Args:
        report_markdown: Report content.
        dest_path: Destination path of the report.

    Returns:
        Dictionary with status, saved_path, and character count.
    """
    try:
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(report_markdown)

        return {
            "status": "success",
            "saved_path": dest_path,
            "char_count": len(report_markdown),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
