"""Feature engineering and data analysis tools for the Feature Engineering Agent."""

import glob
import json
import os
import tempfile
from typing import Any, Dict, List, Union

import pandas as pd

from core.gcs import download_to_path
from observability import current_span, traced_tool


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
                str(k): {"count": int(v), "proportion": float(v / total)}
                for k, v in counts.items()
            }
        else:
            label_dist_dict = {}

        feature_mean_dict = {
            col: numeric_summary[col]["mean"]
            for col in numeric_summary
            if col != "label"
        }
        feature_std_dict = {
            col: numeric_summary[col]["std"]
            for col in numeric_summary
            if col != "label"
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
