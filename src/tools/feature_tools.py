"""Feature engineering and data analysis tools for the Feature Engineering Agent."""

import glob
import os
from typing import Any, Dict, List, Union

import pandas as pd

from observability import current_span, traced_tool


@traced_tool("csv_read")
def csv_read(filepath: str) -> dict[str, Any]:
    """Reads a CSV file and returns its basic structure and a preview of rows.

    Args:
        filepath: Absolute or relative path to the CSV file.

    Returns:
        A dictionary containing the column names, shape (rows, cols), data types,
        and a preview of the first 5 rows (as a list of dicts).
    """
    span = current_span()
    span.set_attribute("dataset.uri", filepath)

    try:
        if not os.path.exists(filepath):
            return {
                "status": "error",
                "error": f"File not found: {filepath}",
            }

        df = pd.read_csv(filepath)

        span.set_attribute("dataset.rows", df.shape[0])
        span.set_attribute("dataset.cols", df.shape[1])

        # Prepare serializable types
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

    Args:
        filepath: Absolute or relative path to the CSV file.

    Returns:
        A dictionary containing missing value counts, label distributions,
        numerical summaries (mean, std, min, max), and overall statistics.
    """
    span = current_span()
    span.set_attribute("dataset.uri", filepath)

    try:
        if not os.path.exists(filepath):
            return {
                "status": "error",
                "error": f"File not found: {filepath}",
            }

        df = pd.read_csv(filepath)
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
        # We also check for 'label' or any string/categorical column specifically
        cat_cols = df.select_dtypes(include=["object", "category"]).columns
        for col in cat_cols:
            counts = df[col].value_counts()
            total = len(df[col].dropna())
            dist = {}
            for val, cnt in counts.items():
                proportion = float(cnt / total) if total > 0 else 0.0
                dist[str(val)] = {"count": int(cnt), "proportion": proportion}
            categorical_summary[col] = dist

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
