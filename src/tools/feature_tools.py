"""Feature engineering and data analysis tools for the Feature Engineering Agent."""

import os
from typing import Any, Union, Dict, List
import pandas as pd


def csv_read(filepath: str) -> dict[str, Any]:
    """Reads a CSV file and returns its basic structure and a preview of rows.

    Args:
        filepath: Absolute or relative path to the CSV file.

    Returns:
        A dictionary containing the column names, shape (rows, cols), data types,
        and a preview of the first 5 rows (as a list of dicts).
    """
    try:
        if not os.path.exists(filepath):
            return {
                "status": "error",
                "error": f"File not found: {filepath}",
            }

        df = pd.read_csv(filepath)
        
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


def pandas_profile(filepath: str) -> dict[str, Any]:
    """Profiles a CSV dataset to extract key statistical properties and check distributions.

    Args:
        filepath: Absolute or relative path to the CSV file.

    Returns:
        A dictionary containing missing value counts, label distributions,
        numerical summaries (mean, std, min, max), and overall statistics.
    """
    try:
        if not os.path.exists(filepath):
            return {
                "status": "error",
                "error": f"File not found: {filepath}",
            }

        df = pd.read_csv(filepath)
        shape = list(df.shape)

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
                dist[str(val)] = {
                    "count": int(cnt),
                    "proportion": proportion
                }
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


def save_features(data: Union[List[Dict[str, Any]], Dict[str, List[Any]]], filepath: str) -> str:
    """Saves the engineered features to a CSV file.

    Args:
        data: A list of dicts (rows) or a dict of lists (columns) containing the dataset.
        filepath: Destination path where the CSV should be saved.

    Returns:
        A success message indicating the shape of the saved dataset.
    """
    try:
        # Create parent directories if they don't exist
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # Ingest data into a pandas DataFrame
        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)

        return f"Successfully saved {df.shape[0]} rows and {df.shape[1]} features to {filepath}"
    except Exception as e:
        raise RuntimeError(f"Failed to save features: {str(e)}")
