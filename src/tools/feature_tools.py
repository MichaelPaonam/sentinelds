"""Feature engineering and data analysis tools for the Feature Engineering Agent."""

import glob
import json
import os
import tempfile
from typing import Any, Dict, List, Union

import pandas as pd

from core.gcs import download_to_path
from observability import current_span, traced_tool

import hashlib
from core.config import settings
from sentinel.preflight import DatasetQuarantine, emit_dataset_drift_candidate
from sentinel.session import get_sentinel_session


def calculate_dataframe_checksum(df: pd.DataFrame) -> str:
    """Calculates a stable, canonical SHA-256 checksum for a pandas DataFrame."""
    sorted_cols = sorted(df.columns)
    df_canon = df[sorted_cols].copy()

    numeric_cols = df_canon.select_dtypes(include=["number"]).columns
    for col in numeric_cols:
        df_canon[col] = df_canon[col].round(6)

    df_canon = df_canon.sort_values(by=list(df_canon.columns)).reset_index(drop=True)
    csv_str = df_canon.to_csv(index=False).replace("\r\n", "\n")
    
    return hashlib.sha256(csv_str.encode("utf-8")).hexdigest()


def load_baseline_stats() -> dict[str, Any]:
    """Loads baseline statistics by averaging the 5 clean baseline snapshots."""
    snapshots_dir = "src/scripts/baseline_snapshots"
    label_0_proportions = []
    feature_means: dict[str, list[float]] = {}

    for run_id in range(1, 6):
        path = os.path.join(snapshots_dir, f"run_{run_id}.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                label_dist = data.get("label_distribution", {})
                p_0 = label_dist.get("0", {}).get("proportion")
                if p_0 is not None:
                    label_0_proportions.append(p_0)
                
                feat_mean = data.get("feature_mean", {})
                for col, val in feat_mean.items():
                    if col == "label":
                        continue
                    if col not in feature_means:
                        feature_means[col] = []
                    feature_means[col].append(val)
        except Exception:
            pass

    avg_label_0_prop = sum(label_0_proportions) / len(label_0_proportions) if label_0_proportions else 0.6
    avg_feature_means = {
        col: sum(vals) / len(vals) for col, vals in feature_means.items() if vals
    }

    return {
        "label_0_proportion": avg_label_0_prop,
        "feature_means": avg_feature_means,
    }



@traced_tool("csv_read")
def csv_read(filepath: str) -> dict[str, Any]:
    """Reads a CSV file and returns its basic structure and a preview of rows.

    Accepts local paths or gs:// URIs. For gs:// URIs the file is downloaded to a
    temp location; the temp file is not deleted (OS tmp cleanup handles it).

    Args:
        filepath: Absolute/relative path or gs:// URI to the CSV file.

    Returns:
        A dictionary containing the column names, shape (rows, cols), data types,
        and a preview of the first 5 rows (as a list of dicts).
    """
    span = current_span()
    span.set_attribute("dataset.uri", filepath)

    try:
        if filepath.startswith("gs://"):
            tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
            tmp.close()
            download_to_path(filepath, tmp.name)
            local_path = tmp.name
            span.set_attribute("dataset.source", "gcs")
        else:
            if not os.path.exists(filepath):
                return {
                    "status": "error",
                    "error": f"File not found: {filepath}",
                }
            local_path = filepath
            span.set_attribute("dataset.source", "local")

        df = pd.read_csv(local_path)

        span.set_attribute("dataset.rows", df.shape[0])
        span.set_attribute("dataset.cols", df.shape[1])

        dtypes_dict = {col: str(dtype) for col, dtype in df.dtypes.items()}
        head_list = df.head(5).to_dict(orient="records")

        return {
            "status": "success",
            "columns": list(df.columns),
            "shape": list(df.shape),
            "dtypes": dtypes_dict,
            "head": head_list,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to read CSV: {str(e)}",
        }


@traced_tool("pandas_profile")
def pandas_profile(filepath: str) -> dict[str, Any]:
    """Profiles a CSV dataset to extract key statistical properties and check distributions.

    Accepts local paths or gs:// URIs. For gs:// URIs the file is downloaded to a
    temp location; the temp file is not deleted (OS tmp cleanup handles it).
    Emits dataset.stats.* OTel attributes on the active span.

    Args:
        filepath: Absolute/relative path or gs:// URI to the CSV file.

    Returns:
        A dictionary containing missing value counts, label distributions,
        numerical summaries (mean, std, min, max), and overall statistics.
    """
    span = current_span()
    span.set_attribute("dataset.uri", filepath)

    try:
        if filepath.startswith("gs://"):
            tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
            tmp.close()
            download_to_path(filepath, tmp.name)
            local_path = tmp.name
            span.set_attribute("dataset.source", "gcs")
        else:
            if not os.path.exists(filepath):
                return {
                    "status": "error",
                    "error": f"File not found: {filepath}",
                }
            local_path = filepath
            span.set_attribute("dataset.source", "local")

        df = pd.read_csv(local_path)
        shape = list(df.shape)

        # 1. Canonical Checksum & Quarantine Verification
        checksum = calculate_dataframe_checksum(df)
        span.set_attribute("dataset.stats.checksum", checksum)

        if DatasetQuarantine.is_quarantined(checksum):
            raise PermissionError(f"Dataset is quarantined: {checksum}")

        # 2. Extract Current Statistics
        p_0_current = 0.6  # Default fallback
        if "label" in df.columns:
            counts = df["label"].value_counts()
            total = len(df)
            count_0 = sum(v for k, v in counts.items() if str(k) in ("0", "0.0"))
            p_0_current = float(count_0 / total) if total > 0 else 0.0

        current_feature_means = {}
        for col in df.columns:
            if col == "label":
                continue
            if pd.api.types.is_numeric_dtype(df[col]):
                current_feature_means[col] = float(df[col].mean())

        # 3. Load Baseline & Evaluate Drift Checks
        baseline = load_baseline_stats()
        avg_label_0_prop = baseline["label_0_proportion"]
        avg_feature_means = baseline["feature_means"]

        label_drift = abs(p_0_current - avg_label_0_prop) if "label" in df.columns else 0.0

        drifted_features = []
        for col, baseline_mean in avg_feature_means.items():
            if col in current_feature_means:
                diff = abs(current_feature_means[col] - baseline_mean)
                if diff > 0.5:
                    drifted_features.append(col)

        # 4. Handle Violation (Drift Exceeds Threshold)
        if label_drift > 0.05 or len(drifted_features) > 0:
            import sys
            DatasetQuarantine.add(checksum)
            print(f"[Sentinel] Dataset Drift Detected! Checksum: {checksum}, Label Drift: {label_drift:.4f}, Drifted Features: {drifted_features}", file=sys.stderr)

            # Compromise the active SentinelSession
            sess = get_sentinel_session()
            if sess is not None:
                sess.compromised = True
                sess.compromise_reason = (
                    f"Training halted: ingested dataset shows label-distribution drift "
                    f"inconsistent with workspace baseline (Δ={label_drift:.2f} vs baseline 0.05). "
                    f"Dataset quarantined: {checksum}. Trace: https://dt.example/trace"
                )

            # Emit Custom Business Event to Dynatrace SaaS
            workspace_id = getattr(settings, "DYNATRACE_WORKSPACE_ENTITY_ID", "WORKSPACE-1")
            dt_url = settings.DYNATRACE_API_URL or ""
            dt_token = (
                settings.DYNATRACE_API_TOKEN.get_secret_value()
                if settings.DYNATRACE_API_TOKEN
                else ""
            )
            span_ctx = span.get_span_context()
            try:
                span_id_hex = format(span_ctx.span_id, "016x") if span_ctx else ""
            except (TypeError, ValueError):
                span_id_hex = ""

            emit_dataset_drift_candidate(
                span_id=span_id_hex,
                workspace_entity_id=workspace_id,
                dynatrace_api_url=dt_url,
                dynatrace_api_token=dt_token,
                checksum=checksum,
                label_drift=label_drift,
                drifted_features=drifted_features,
            )

        span.set_attribute("dataset.rows", df.shape[0])
        span.set_attribute("dataset.cols", df.shape[1])
        span.set_attribute("dataset.missing.total", int(df.isnull().sum().sum()))

        # Missing values
        missing = df.isnull().sum().to_dict()
        missing = {col: int(val) for col, val in missing.items()}

        # Numerical summary
        numeric_cols = df.select_dtypes(include=["number"]).columns
        numeric_summary = {}
        for col in numeric_cols:
            desc = df[col].describe()
            numeric_summary[col] = {
                "mean": float(desc.get("mean", 0.0)),
                "std": float(desc.get("std", 0.0)),
                "min": float(desc.get("min", 0.0)),
                "max": float(desc.get("max", 0.0)),
                "median": float(df[col].median()),
            }

        # Categorical summary / label distributions
        categorical_summary = {}
        cat_cols = df.select_dtypes(include=["object", "category"]).columns
        for col in cat_cols:
            counts = df[col].value_counts()
            total = len(df[col].dropna())
            dist = {}
            for val, cnt in counts.items():
                proportion = float(cnt / total) if total > 0 else 0.0
                dist[str(val)] = {"count": int(cnt), "proportion": proportion}
            categorical_summary[col] = dist

        # Emit dataset.stats.* — label is numeric (int 0/1) in the drowsiness schema
        if "label" in df.columns:
            counts = df["label"].value_counts()
            total = len(df)
            label_dist_dict = {
                str(k): {"count": int(v), "proportion": float(v / total)} for k, v in counts.items()
            }
        else:
            label_dist_dict = {}

        feature_mean_dict = {
            col: numeric_summary[col]["mean"] for col in numeric_summary if col != "label"
        }
        feature_std_dict = {
            col: numeric_summary[col]["std"] for col in numeric_summary if col != "label"
        }

        try:
            span.set_attribute(
                "dataset.stats.label_distribution",
                json.dumps(label_dist_dict, default=float),
            )
            span.set_attribute(
                "dataset.stats.feature_mean",
                json.dumps(feature_mean_dict, default=float),
            )
            span.set_attribute(
                "dataset.stats.feature_std",
                json.dumps(feature_std_dict, default=float),
            )
        except Exception:
            pass  # never fail profile output on a bad span backend

        return {
            "status": "success",
            "shape": shape,
            "missing_values": missing,
            "numeric_summary": numeric_summary,
            "categorical_summary": categorical_summary,
        }
    except PermissionError:
        raise
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to profile dataset: {str(e)}",
        }


@traced_tool("save_features")
def save_features(data: Union[List[Dict[str, Any]], Dict[str, List[Any]]], filepath: str) -> str:
    """Saves the engineered features to a CSV file.

    Args:
        data: A list of dicts (rows) or a dict of lists (columns) containing the dataset.
        filepath: Destination path where the CSV should be saved.

    Returns:
        A success message indicating the shape of the saved dataset.
    """
    span = current_span()
    span.set_attribute("dataset.uri", filepath)

    try:
        # Create parent directories if they don't exist
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # Ingest data into a pandas DataFrame
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)

        span.set_attribute("dataset.rows", df.shape[0])
        span.set_attribute("dataset.cols", df.shape[1])

        return f"Successfully saved {df.shape[0]} rows and {df.shape[1]} features to {filepath}"
    except Exception as e:
        raise RuntimeError(f"Failed to save features: {str(e)}")


@traced_tool("find_files")
def find_files(directory: str, extension: str = "*") -> dict[str, Any]:
    """Looks into a directory and finds files of a particular type or pattern.

    Args:
        directory: Path to the directory to search.
        extension: The file extension (e.g., 'csv', '.csv') or a pattern to match (e.g., '*').

    Returns:
        A dictionary containing the status and a list of found files with their details
        (name, absolute path, size in bytes, and modification time).
    """
    span = current_span()
    span.set_attribute("fs.directory", directory)

    try:
        if not os.path.exists(directory):
            return {
                "status": "error",
                "error": f"Directory not found: {directory}",
            }
        if not os.path.isdir(directory):
            return {
                "status": "error",
                "error": f"Path is not a directory: {directory}",
            }

        # Normalize extension
        ext = extension.strip()
        if ext == "*":
            pattern = "*"
        elif ext.startswith("*."):
            pattern = ext
        elif ext.startswith("."):
            pattern = f"*{ext}"
        elif "*" in ext:
            pattern = ext
        else:
            pattern = f"*.{ext}"

        span.set_attribute("fs.pattern", pattern)

        search_pattern = os.path.join(directory, pattern)
        recursive = "**" in pattern
        matched_paths = glob.glob(search_pattern, recursive=recursive)

        files_list = []
        for path in sorted(matched_paths):
            if os.path.isfile(path):
                stat = os.stat(path)
                files_list.append(
                    {
                        "name": os.path.basename(path),
                        "path": os.path.abspath(path),
                        "size_bytes": stat.st_size,
                        "modified_time": stat.st_mtime,
                    }
                )

        span.set_attribute("fs.match.count", len(files_list))

        return {
            "status": "success",
            "directory": os.path.abspath(directory),
            "pattern": pattern,
            "count": len(files_list),
            "files": files_list,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to search directory: {str(e)}",
        }
