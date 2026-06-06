"""Tools to create CSV and Markdown files."""

import os
from typing import Any, Dict, List, Union

import pandas as pd


def make_csv_file(data: Union[List[Dict[str, Any]], Dict[str, List[Any]]], filepath: str) -> str:
    """Creates a CSV file from the provided data.

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

        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        return f"Successfully saved {df.shape[0]} rows and {df.shape[1]} columns to {filepath}"
    except Exception as e:
        raise RuntimeError(f"Failed to create CSV file: {str(e)}")


def make_md_file(content: str, filepath: str) -> str:
    """Creates a Markdown (.md) file with the provided content.

    Args:
        content: The text/markdown content to write to the file.
        filepath: Destination path where the markdown file should be saved.

    Returns:
        A success message indicating the file path where it was saved.
    """
    try:
        # Create parent directories if they don't exist
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully created Markdown file at {filepath}"
    except Exception as e:
        raise RuntimeError(f"Failed to create Markdown file: {str(e)}")


def make_py_file(code: str, filepath: str) -> str:
    """Creates a Python (.py) file with the provided code.

    Args:
        code: The Python code content to write to the file.
        filepath: Destination path where the Python file should be saved.

    Returns:
        A success message indicating the file path where it was saved.
    """
    try:
        # Create parent directories if they don't exist
        dir_name = os.path.dirname(filepath)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)
        return f"Successfully created Python file at {filepath}"
    except Exception as e:
        raise RuntimeError(f"Failed to create Python file: {str(e)}")
