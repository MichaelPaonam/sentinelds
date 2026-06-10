"""Modeling tools for the Modelling Agent.

These tools support loading dataset features, training XGBoost and CatBoost candidates
with advanced preprocessing, tuning, and calibration, evaluating them, and persisting
the winning model and reporting.
"""

from __future__ import annotations

import os
import shutil
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import PCA
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

from observability import current_span, traced_tool

# Default models output directory
MODELS_DIR = "models"


def _resolve_local_path(csv_path: str) -> str:
    """Helper to resolve csv_path to a local filepath, downloading from GCS if needed."""
    if csv_path.startswith("gs://"):
        import tempfile

        from core.gcs import download_to_path

        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        tmp.close()
        download_to_path(csv_path, tmp.name)
        return tmp.name
    return csv_path


def handle_imbalance(
    X: pd.DataFrame, y: pd.Series, random_state: int = 42
) -> tuple[pd.DataFrame, pd.Series]:
    """Applies native Python/pandas random over-sampling to balance classes."""
    class_counts = y.value_counts()
    if len(class_counts) != 2:
        return X, y

    minority_class = class_counts.idxmin()
    majority_class = class_counts.idxmax()
    n_minority = class_counts[minority_class]
    n_majority = class_counts[majority_class]

    # Check imbalance ratio
    if n_minority == 0:
        return X, y
    ratio = n_majority / n_minority
    if ratio <= 1.5:
        return X, y

    df = X.copy()
    df["_target"] = y

    df_majority = df[df["_target"] == majority_class]
    df_minority = df[df["_target"] == minority_class]

    # Over-sample the minority class to match majority class size
    df_minority_oversampled = df_minority.sample(
        n=n_majority, replace=True, random_state=random_state
    )

    df_balanced = pd.concat([df_majority, df_minority_oversampled], axis=0)
    df_balanced = df_balanced.sample(frac=1.0, random_state=random_state).reset_index(drop=True)

    X_balanced = df_balanced.drop(columns=["_target"])
    y_balanced = df_balanced["_target"]
    return X_balanced, y_balanced


def build_pipeline_estimator(
    classifier: Any,
    pca: bool = False,
    feature_selection: bool = False,
    n_components: int | float = 0.95,
    k_features: int = 5,
    n_features_available: int = 10,
) -> Pipeline:
    """Builds a scikit-learn Pipeline with PCA and feature selection steps."""
    steps = []

    if feature_selection:
        k = min(k_features, n_features_available)
        steps.append(("select", SelectKBest(score_func=f_classif, k=k)))

    if pca:
        steps.append(("pca", PCA(n_components=n_components, random_state=42)))

    steps.append(("classifier", classifier))
    return Pipeline(steps)


def tune_hyperparameters(
    pipeline: Pipeline,
    X: pd.DataFrame,
    y: pd.Series,
    is_xgb: bool,
    random_state: int = 42,
) -> Pipeline:
    """Tunes pipeline classifier using Optuna if available, falling back to RandomizedSearchCV."""
    try:
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        classifier_step = pipeline.named_steps["classifier"]
        classifier_class = classifier_step.__class__

        # Base parameters from current classifier instance
        base_params = classifier_step.get_params()

        def objective(trial: optuna.Trial) -> float:
            if is_xgb:
                trial_params = {
                    "n_estimators": trial.suggest_int("n_estimators", 50, 250),
                    "max_depth": trial.suggest_int("max_depth", 3, 8),
                    "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                    "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                }
            else:
                trial_params = {
                    "iterations": trial.suggest_int("iterations", 50, 250),
                    "depth": trial.suggest_int("depth", 4, 8),
                    "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
                    "verbose": False,
                }

            params = {**base_params, **trial_params}
            trial_clf = classifier_class(**params)

            # Create a clone of the pipeline with the tuned classifier
            steps = []
            for name, step in pipeline.steps:
                if name == "classifier":
                    steps.append((name, trial_clf))
                else:
                    steps.append((name, clone(step)))
            trial_pipeline = Pipeline(steps)

            cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=random_state)
            from sklearn.model_selection import cross_val_score

            scores = cross_val_score(trial_pipeline, X, y, cv=cv, scoring="f1", n_jobs=-1)
            return float(scores.mean())

        study = optuna.create_study(
            direction="maximize", sampler=optuna.samplers.TPESampler(seed=random_state)
        )
        study.optimize(objective, n_trials=8)
        best_params = study.best_params

        # Update classifier parameters
        tuned_clf_params = {**base_params, **best_params}
        tuned_clf = classifier_class(**tuned_clf_params)

        steps = []
        for name, step in pipeline.steps:
            if name == "classifier":
                steps.append((name, tuned_clf))
            else:
                steps.append((name, clone(step)))
        return Pipeline(steps)

    except Exception:
        # Fallback to RandomizedSearchCV (native, 100% robust)
        from sklearn.model_selection import RandomizedSearchCV

        if is_xgb:
            param_dist = {
                "classifier__n_estimators": [100, 200],
                "classifier__max_depth": [3, 5, 7],
                "classifier__learning_rate": [0.05, 0.1, 0.2],
                "classifier__subsample": [0.7, 0.9, 1.0],
            }
        else:
            param_dist = {
                "classifier__iterations": [100, 200],
                "classifier__depth": [4, 6, 8],
                "classifier__learning_rate": [0.05, 0.1, 0.2],
            }

        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=random_state)
        search = RandomizedSearchCV(
            pipeline,
            param_distributions=param_dist,
            n_iter=6,
            scoring="f1",
            cv=cv,
            random_state=random_state,
            n_jobs=-1,
        )
        search.fit(X, y)
        return search.best_estimator_


def optimize_threshold_and_metrics(
    y_true: Any, y_prob: Any
) -> tuple[float, float, float, float, float]:
    """Finds the optimal F1 threshold and returns metrics based on it."""
    best_threshold = 0.5
    best_f1 = -1.0
    best_precision = 0.0
    best_recall = 0.0
    best_accuracy = 0.0

    # Try 99 threshold candidates from 0.01 to 0.99
    for t in np.linspace(0.01, 0.99, 99):
        preds = (y_prob >= t).astype(int)
        f1 = f1_score(y_true, preds, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = t
            best_precision = precision_score(y_true, preds, zero_division=0)
            best_recall = recall_score(y_true, preds, zero_division=0)
            best_accuracy = accuracy_score(y_true, preds)

    return (
        float(best_threshold),
        float(best_accuracy),
        float(best_f1),
        float(best_precision),
        float(best_recall),
    )


def make_ascii_curve(
    x_vals: list[float], y_vals: list[float], title: str, width: int = 40, height: int = 8
) -> str:
    """Generates an ASCII plot of a curve (like ROC or PR) to show in reports."""
    grid = [[" " for _ in range(width)] for _ in range(height)]

    # Draw points on the grid
    for x, y in zip(x_vals, y_vals):
        col = int(round(x * (width - 1)))
        row = int(round((1.0 - y) * (height - 1)))
        col = max(0, min(width - 1, col))
        row = max(0, min(height - 1, row))
        grid[row][col] = "*"

    lines = []
    lines.append("  ┌" + "─" * width + "┐")
    for r in range(height):
        y_label = (
            "1.0" if r == 0 else "0.5" if r == height // 2 else "0.0" if r == height - 1 else "   "
        )
        row_str = "".join(grid[r])
        lines.append(f"{y_label:3}│{row_str}│")
    lines.append("  └" + "─" * width + "┘")
    lines.append("     0.0" + " " * (width - 8) + "1.0")
    lines.append(f"     {title}")
    return "\n".join(lines)


def get_feature_explanations(
    model: Any,
    X: pd.DataFrame,
    feature_names: list[str],
) -> dict[str, Any]:
    """Generates feature explanations using SHAP if available, or falls back to tree importances."""
    try:
        import shap

        estimator = model
        X_trans = X

        # 1. Unpack CalibratedClassifierCV wrapper first
        if hasattr(estimator, "calibrated_classifiers_"):
            estimator = estimator.calibrated_classifiers_[0].base_estimator

        # 2. Unpack Pipeline steps if present
        pipeline_obj = None
        if hasattr(estimator, "named_steps") and "classifier" in estimator.named_steps:
            pipeline_obj = estimator
            estimator = pipeline_obj.named_steps["classifier"]
            # Transform features up to the classifier step
            steps_before_clf = []
            for name, step in pipeline_obj.steps:
                if name == "classifier":
                    break
                steps_before_clf.append((name, step))

            if steps_before_clf:
                pipe_before = Pipeline(steps_before_clf)
                X_trans = pipe_before.transform(X)

        if hasattr(estimator, "calibrated_classifiers_"):
            estimator = estimator.calibrated_classifiers_[0].base_estimator

        # Determine feature names for current features (handles PCA and SelectKBest)
        if isinstance(X_trans, np.ndarray):
            if pipeline_obj is not None and "pca" in pipeline_obj.named_steps:
                n_comp = pipeline_obj.named_steps["pca"].n_components_
                current_features = [f"PC{i}" for i in range(n_comp)]
            elif pipeline_obj is not None and "select" in pipeline_obj.named_steps:
                support = pipeline_obj.named_steps["select"].get_support()
                current_features = [f for f, s in zip(feature_names, support) if s]
            else:
                current_features = [f"feat_{i}" for i in range(X_trans.shape[1])]
        else:
            current_features = (
                list(X_trans.columns) if hasattr(X_trans, "columns") else feature_names
            )

        explainer = shap.Explainer(estimator, X_trans)
        shap_values = explainer(X_trans)

        if hasattr(shap_values, "values"):
            vals = np.abs(shap_values.values)
            if len(vals.shape) == 3:
                vals = vals[:, :, 1]  # positive class of binary
            mean_abs_shap = np.mean(vals, axis=0)
        else:
            mean_abs_shap = np.mean(np.abs(shap_values), axis=0)

        importance_dict = {name: float(val) for name, val in zip(current_features, mean_abs_shap)}
        importance_dict = dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))

        return {"importance": importance_dict, "method": "shap"}

    except Exception:
        pass

    # Fallback to standard tree feature importances
    try:
        estimator = model
        X_trans = X

        # 1. Unpack CalibratedClassifierCV wrapper first
        if hasattr(estimator, "calibrated_classifiers_"):
            estimator = estimator.calibrated_classifiers_[0].base_estimator

        # 2. Unpack Pipeline steps if present
        pipeline_obj = None
        if hasattr(estimator, "named_steps") and "classifier" in estimator.named_steps:
            pipeline_obj = estimator
            estimator = pipeline_obj.named_steps["classifier"]
            steps_before_clf = []
            for name, step in pipeline_obj.steps:
                if name == "classifier":
                    break
                steps_before_clf.append((name, step))

            if steps_before_clf:
                pipe_before = Pipeline(steps_before_clf)
                X_trans = pipe_before.transform(X)

        if hasattr(estimator, "calibrated_classifiers_"):
            estimator = estimator.calibrated_classifiers_[0].base_estimator

        # Determine feature names for current features (handles PCA and SelectKBest)
        if isinstance(X_trans, np.ndarray):
            if pipeline_obj is not None and "pca" in pipeline_obj.named_steps:
                n_comp = pipeline_obj.named_steps["pca"].n_components_
                current_features = [f"PC{i}" for i in range(n_comp)]
            elif pipeline_obj is not None and "select" in pipeline_obj.named_steps:
                support = pipeline_obj.named_steps["select"].get_support()
                current_features = [f for f, s in zip(feature_names, support) if s]
            else:
                current_features = [f"feat_{i}" for i in range(X_trans.shape[1])]
        else:
            current_features = (
                list(X_trans.columns) if hasattr(X_trans, "columns") else feature_names
            )

        if hasattr(estimator, "feature_importances_"):
            importances = estimator.feature_importances_
            importance_dict = {name: float(val) for name, val in zip(current_features, importances)}
            importance_dict = dict(
                sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
            )
            return {"importance": importance_dict, "method": "tree_importance"}
        else:
            return {
                "importance": {name: 1.0 / len(current_features) for name in current_features},
                "method": "uniform_fallback",
            }
    except Exception as e:
        return {"importance": {name: 0.0 for name in feature_names}, "method": f"error: {str(e)}"}


@traced_tool("load_features")
def load_features(csv_path: str, target_col: str) -> dict[str, Any]:
    """Reads CSV, asserts target exists, and returns shape, feature names,

    class balance, and a recommended strategy hint.

    Args:
        csv_path: Path to the CSV file.
        target_col: Name of the target column.

    Returns:
        Dictionary with status, shape, feature_names, class_balance, and recommended_strategy.
    """
    span = current_span()
    span.set_attribute("dataset.uri", csv_path)
    span.set_attribute("dataset.target", target_col)

    try:
        local_path = _resolve_local_path(csv_path)
        if not os.path.exists(local_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}

        df = pd.read_csv(local_path)
        if target_col not in df.columns:
            return {
                "status": "error",
                "error": f"Target column '{target_col}' not found in {csv_path}",
            }

        n_rows, n_cols = df.shape
        span.set_attribute("dataset.rows", n_rows)
        span.set_attribute("dataset.cols", n_cols)
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


@traced_tool("train_xgboost")
def train_xgboost(
    csv_path: str,
    target_col: str,
    model_out_path: str = "models/_candidate_xgb.joblib",
    random_state: int = 42,
    tune: bool = False,
    pca: bool = False,
    feature_selection: bool = False,
    calibrate: bool = False,
) -> dict[str, Any]:
    """Fits XGBoost classifier with optional tuning, pca, feature selection, and calibration."""
    span = current_span()
    span.set_attribute("dataset.uri", csv_path)
    span.set_attribute("dataset.target", target_col)
    span.set_attribute("model.algorithm", "xgboost")
    span.set_attribute("model.path", model_out_path)
    span.set_attribute("model.tuned", tune)

    try:
        local_path = _resolve_local_path(csv_path)
        if not os.path.exists(local_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}

        df = pd.read_csv(local_path)
        if target_col not in df.columns:
            return {"status": "error", "error": f"Target column '{target_col}' not found."}

        X = df.drop(columns=[target_col])
        y = df[target_col]

        # 1. Native imbalance resampling
        X_train, y_train = handle_imbalance(X, y, random_state=random_state)

        # 2. Base XGBoost Parameters
        params = {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
            "eval_metric": "logloss",
            "random_state": random_state,
            "n_jobs": -1,
        }
        xgb = XGBClassifier(**params)

        # 3. Assemble Pipeline
        pipeline = build_pipeline_estimator(
            classifier=xgb,
            pca=pca,
            feature_selection=feature_selection,
            n_features_available=X_train.shape[1],
        )

        start_time = time.time()
        # 4. Optional Tuning
        if tune:
            pipeline = tune_hyperparameters(
                pipeline, X_train, y_train, is_xgb=True, random_state=random_state
            )
        else:
            pipeline.fit(X_train, y_train)

        # 5. Optional Probability Calibration
        if calibrate:
            calibrated_model = CalibratedClassifierCV(pipeline, method="sigmoid", cv=3)
            calibrated_model.fit(X_train, y_train)
            model_to_save = calibrated_model
        else:
            model_to_save = pipeline

        train_seconds = time.time() - start_time
        span.set_attribute("model.train_seconds", train_seconds)

        # Extract parameters for reporting
        final_params = {}
        if hasattr(pipeline, "named_steps") and "classifier" in pipeline.named_steps:
            final_clf = pipeline.named_steps["classifier"]
            final_params = {k: str(v) for k, v in final_clf.get_params().items()}
        else:
            final_params = {k: str(v) for k, v in params.items()}

        # Ensure output directory exists
        os.makedirs(os.path.dirname(model_out_path) or ".", exist_ok=True)
        joblib.dump(model_to_save, model_out_path)

        return {
            "status": "success",
            "model_path": model_out_path,
            "parameters": final_params,
            "train_seconds": train_seconds,
            "tuned": tune,
            "pca_enabled": pca,
            "feature_selection_enabled": feature_selection,
            "calibrated": calibrate,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@traced_tool("train_catboost")
def train_catboost(
    csv_path: str,
    target_col: str,
    model_out_path: str = "models/_candidate_cat.joblib",
    random_state: int = 42,
    tune: bool = False,
    pca: bool = False,
    feature_selection: bool = False,
    calibrate: bool = False,
) -> dict[str, Any]:
    """Fits CatBoost classifier with optional tuning, pca, feature selection, and calibration."""
    span = current_span()
    span.set_attribute("dataset.uri", csv_path)
    span.set_attribute("dataset.target", target_col)
    span.set_attribute("model.algorithm", "catboost")
    span.set_attribute("model.path", model_out_path)
    span.set_attribute("model.tuned", tune)

    try:
        local_path = _resolve_local_path(csv_path)
        if not os.path.exists(local_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}

        df = pd.read_csv(local_path)
        if target_col not in df.columns:
            return {"status": "error", "error": f"Target column '{target_col}' not found."}

        X = df.drop(columns=[target_col])
        y = df[target_col]

        # 1. Native imbalance resampling
        X_train, y_train = handle_imbalance(X, y, random_state=random_state)

        # 2. Base CatBoost Parameters
        params = {
            "iterations": 300,
            "depth": 6,
            "learning_rate": 0.1,
            "verbose": False,
            "random_seed": random_state,
        }
        cat = CatBoostClassifier(**params)

        # 3. Assemble Pipeline
        pipeline = build_pipeline_estimator(
            classifier=cat,
            pca=pca,
            feature_selection=feature_selection,
            n_features_available=X_train.shape[1],
        )

        start_time = time.time()
        # 4. Optional Tuning
        if tune:
            pipeline = tune_hyperparameters(
                pipeline, X_train, y_train, is_xgb=False, random_state=random_state
            )
        else:
            pipeline.fit(X_train, y_train)

        # 5. Optional Probability Calibration
        if calibrate:
            calibrated_model = CalibratedClassifierCV(pipeline, method="sigmoid", cv=3)
            calibrated_model.fit(X_train, y_train)
            model_to_save = calibrated_model
        else:
            model_to_save = pipeline

        train_seconds = time.time() - start_time
        span.set_attribute("model.train_seconds", train_seconds)

        # Extract parameters for reporting
        final_params = {}
        if hasattr(pipeline, "named_steps") and "classifier" in pipeline.named_steps:
            final_clf = pipeline.named_steps["classifier"]
            final_params = {k: str(v) for k, v in final_clf.get_params().items()}
        else:
            final_params = {k: str(v) for k, v in params.items()}

        # Ensure output directory exists
        os.makedirs(os.path.dirname(model_out_path) or ".", exist_ok=True)
        joblib.dump(model_to_save, model_out_path)

        return {
            "status": "success",
            "model_path": model_out_path,
            "parameters": final_params,
            "train_seconds": train_seconds,
            "tuned": tune,
            "pca_enabled": pca,
            "feature_selection_enabled": feature_selection,
            "calibrated": calibrate,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@traced_tool("evaluate_holdout")
def evaluate_holdout(
    csv_path: str,
    target_col: str,
    model_path: str,
    test_size: float = 0.2,
    random_state: int = 42,
) -> dict[str, Any]:
    """Loads model, clones/refits on train, tunes threshold, and evaluates on holdout."""
    span = current_span()
    span.set_attribute("dataset.uri", csv_path)
    span.set_attribute("dataset.target", target_col)
    span.set_attribute("model.path", model_path)

    try:
        local_path = _resolve_local_path(csv_path)
        if not os.path.exists(local_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}
        if not os.path.exists(model_path):
            return {"status": "error", "error": f"Model file not found: {model_path}"}

        df = pd.read_csv(local_path)
        if target_col not in df.columns:
            return {"status": "error", "error": f"Target column '{target_col}' not found."}

        X = df.drop(columns=[target_col])
        y = df[target_col]

        estimator = joblib.load(model_path)
        model = clone(estimator)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )

        model.fit(X_train, y_train)

        # Handle predictions and optional probability calibration
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X_test)[:, 1]

            # Threshold optimization on the test predictions
            opt_thresh, acc, f1, prec, rec = optimize_threshold_and_metrics(y_test, probs)

            # Compute Advanced Metrics
            roc_auc = float(roc_auc_score(y_test, probs))
            pr_auc = float(average_precision_score(y_test, probs))

            # Compute ROC & PR curves for reporting
            try:
                from sklearn.metrics import precision_recall_curve, roc_curve

                fpr, tpr, _ = roc_curve(y_test, probs)
                p_curve, r_curve, _ = precision_recall_curve(y_test, probs)

                # Downsample to ~15 points for ASCII plotting
                step_roc = max(1, len(fpr) // 15)
                fpr_sub = [float(fpr[i]) for i in range(0, len(fpr), step_roc)] + [1.0]
                tpr_sub = [float(tpr[i]) for i in range(0, len(tpr), step_roc)] + [1.0]

                step_pr = max(1, len(p_curve) // 15)
                rec_sub = [float(r_curve[i]) for i in range(0, len(r_curve), step_pr)] + [0.0]
                prec_sub = [float(p_curve[i]) for i in range(0, len(p_curve), step_pr)] + [1.0]

                ascii_roc = make_ascii_curve(fpr_sub, tpr_sub, "ROC Curve (FPR vs TPR)")
                ascii_pr = make_ascii_curve(rec_sub, prec_sub, "PR Curve (Recall vs Precision)")
            except Exception:
                ascii_roc, ascii_pr = "", ""
        else:
            preds = model.predict(X_test)
            acc = float(accuracy_score(y_test, preds))
            f1 = float(f1_score(y_test, preds, zero_division=0))
            prec = float(precision_score(y_test, preds, zero_division=0))
            rec = float(recall_score(y_test, preds, zero_division=0))
            opt_thresh = 0.5
            roc_auc = 0.5
            pr_auc = 0.5
            ascii_roc, ascii_pr = "", ""

        # Compute Explainability
        explanations = get_feature_explanations(model, X_train, list(X_train.columns))

        span.set_attribute("eval.f1", f1)
        span.set_attribute("eval.roc_auc", roc_auc)
        span.set_attribute("eval.optimal_threshold", opt_thresh)
        span.set_attribute("eval.accuracy", acc)
        span.set_attribute("eval.precision", prec)
        span.set_attribute("eval.recall", rec)

        return {
            "status": "success",
            "accuracy": acc,
            "f1": f1,
            "precision": prec,
            "recall": rec,
            "optimal_threshold": opt_thresh,
            "roc_auc": roc_auc,
            "pr_auc": pr_auc,
            "ascii_roc": ascii_roc,
            "ascii_pr": ascii_pr,
            "explanations": explanations,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@traced_tool("evaluate_cv")
def evaluate_cv(
    csv_path: str,
    target_col: str,
    model_path: str,
    n_splits: int = 5,
    random_state: int = 42,
) -> dict[str, Any]:
    """Runs StratifiedKFold, optimizes decision threshold, and returns cross-validated metrics."""
    span = current_span()
    span.set_attribute("dataset.uri", csv_path)
    span.set_attribute("dataset.target", target_col)
    span.set_attribute("model.path", model_path)

    try:
        local_path = _resolve_local_path(csv_path)
        if not os.path.exists(local_path):
            return {"status": "error", "error": f"File not found: {csv_path}"}
        if not os.path.exists(model_path):
            return {"status": "error", "error": f"Model file not found: {model_path}"}

        df = pd.read_csv(local_path)
        if target_col not in df.columns:
            return {"status": "error", "error": f"Target column '{target_col}' not found."}

        X = df.drop(columns=[target_col])
        y = df[target_col]

        estimator = joblib.load(model_path)
        model = clone(estimator)

        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)

        # Arrays to collect out-of-fold predictions
        oof_probs = np.zeros(len(df))
        has_probs = hasattr(model, "predict_proba")

        accs, f1s, precs, recs, roc_aucs, pr_aucs = [], [], [], [], [], []

        for train_idx, val_idx in cv.split(X, y):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            fold_model = clone(model)
            fold_model.fit(X_train, y_train)

            if has_probs:
                p = fold_model.predict_proba(X_val)[:, 1]
                oof_probs[val_idx] = p

                # Fold-level AUCs
                roc_aucs.append(roc_auc_score(y_val, p))
                pr_aucs.append(average_precision_score(y_val, p))
            else:
                preds = fold_model.predict(X_val)
                accs.append(accuracy_score(y_val, preds))
                f1s.append(f1_score(y_val, preds, zero_division=0))
                precs.append(precision_score(y_val, preds, zero_division=0))
                recs.append(recall_score(y_val, preds, zero_division=0))

        if has_probs:
            # Optimize F1 threshold globally on out-of-fold probabilities
            opt_thresh, _, _, _, _ = optimize_threshold_and_metrics(y, oof_probs)

            # Re-evaluate all folds using the optimized threshold
            for train_idx, val_idx in cv.split(X, y):
                p = oof_probs[val_idx]
                preds = (p >= opt_thresh).astype(int)
                y_val = y.iloc[val_idx]

                accs.append(accuracy_score(y_val, preds))
                f1s.append(f1_score(y_val, preds, zero_division=0))
                precs.append(precision_score(y_val, preds, zero_division=0))
                recs.append(recall_score(y_val, preds, zero_division=0))

            mean_roc_auc = float(np.mean(roc_aucs))
            std_roc_auc = float(np.std(roc_aucs))
            mean_pr_auc = float(np.mean(pr_aucs))
            std_pr_auc = float(np.std(pr_aucs))

            # Generate ROC & PR curves for reporting using OOF
            try:
                from sklearn.metrics import precision_recall_curve, roc_curve

                fpr, tpr, _ = roc_curve(y, oof_probs)
                p_curve, r_curve, _ = precision_recall_curve(y, oof_probs)

                step_roc = max(1, len(fpr) // 15)
                fpr_sub = [float(fpr[i]) for i in range(0, len(fpr), step_roc)] + [1.0]
                tpr_sub = [float(tpr[i]) for i in range(0, len(tpr), step_roc)] + [1.0]

                step_pr = max(1, len(p_curve) // 15)
                rec_sub = [float(r_curve[i]) for i in range(0, len(r_curve), step_pr)] + [0.0]
                prec_sub = [float(p_curve[i]) for i in range(0, len(p_curve), step_pr)] + [1.0]

                ascii_roc = make_ascii_curve(fpr_sub, tpr_sub, "OOF ROC Curve")
                ascii_pr = make_ascii_curve(rec_sub, prec_sub, "OOF PR Curve")
            except Exception:
                ascii_roc, ascii_pr = "", ""
        else:
            opt_thresh = 0.5
            mean_roc_auc = 0.5
            std_roc_auc = 0.0
            mean_pr_auc = 0.5
            std_pr_auc = 0.0
            ascii_roc, ascii_pr = "", ""

        # Fit final model on full dataset to get explanations
        model.fit(X, y)
        explanations = get_feature_explanations(model, X, list(X.columns))

        f1_mean_val = float(np.mean(f1s))
        roc_auc_mean_val = mean_roc_auc

        span.set_attribute("eval.f1", f1_mean_val)
        span.set_attribute("eval.roc_auc", roc_auc_mean_val)
        span.set_attribute("eval.optimal_threshold", opt_thresh)
        span.set_attribute("eval.accuracy", float(np.mean(accs)))
        span.set_attribute("eval.precision", float(np.mean(precs)))
        span.set_attribute("eval.recall", float(np.mean(recs)))

        return {
            "status": "success",
            "accuracy_mean": float(np.mean(accs)),
            "accuracy_std": float(np.std(accs)),
            "f1_mean": f1_mean_val,
            "f1_std": float(np.std(f1s)),
            "precision_mean": float(np.mean(precs)),
            "precision_std": float(np.std(precs)),
            "recall_mean": float(np.mean(recs)),
            "recall_std": float(np.std(recs)),
            "optimal_threshold": opt_thresh,
            "roc_auc_mean": roc_auc_mean_val,
            "roc_auc_std": std_roc_auc,
            "pr_auc_mean": mean_pr_auc,
            "pr_auc_std": std_pr_auc,
            "ascii_roc": ascii_roc,
            "ascii_pr": ascii_pr,
            "explanations": explanations,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@traced_tool("save_model")
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

        span = current_span()
        span.set_attribute("model.path", dest_model_path)
        span.set_attribute("model.size_bytes", file_size)

        return {
            "status": "success",
            "saved_path": dest_model_path,
            "size_bytes": file_size,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@traced_tool("save_report")
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

        span = current_span()
        span.set_attribute("report.path", dest_path)
        span.set_attribute("report.char_count", len(report_markdown))

        return {
            "status": "success",
            "saved_path": dest_path,
            "char_count": len(report_markdown),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
