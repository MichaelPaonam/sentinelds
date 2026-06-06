"""Unit tests for the Feature Engineering Agent tools and structures."""

import os
import tempfile
import unittest
import pandas as pd

from google.adk.agents import LlmAgent, SequentialAgent
from agents.sub_agents.feature_agent.agent import (
    feature_agent,
    dataset_profiler,
    feature_transformer,
)
from tools.feature_tools import csv_read, pandas_profile, save_features


class TestFeatureAgentStructures(unittest.TestCase):
    """Verifies that the Feature Engineering Agent conforms to ADK formats."""

    def test_agent_classes_and_hierarchy(self) -> None:
        """Verify the agent class types and pipeline layout."""
        # Main feature_agent should be a SequentialAgent
        self.assertIsInstance(feature_agent, SequentialAgent)
        self.assertEqual(feature_agent.name, "feature_agent")

        # Sub-agents should be LlmAgents
        self.assertEqual(len(feature_agent.sub_agents), 2)
        self.assertIsInstance(dataset_profiler, LlmAgent)
        self.assertIsInstance(feature_transformer, LlmAgent)
        
        self.assertEqual(dataset_profiler.name, "dataset_profiler")
        self.assertEqual(feature_transformer.name, "feature_transformer")


class TestFeatureToolsFunctionality(unittest.TestCase):
    """Unit test suite for custom feature tools in feature_tools.py."""

    def setUp(self) -> None:
        # Create a temporary directory for test CSV files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.filepath_clean = os.path.join(self.temp_dir.name, "clean_test.csv")
        self.filepath_missing = os.path.join(self.temp_dir.name, "missing_test.csv")

        # Create a mock clean drowsiness dataset
        self.clean_df = pd.DataFrame({
            "eye_aspect_ratio": [0.32, 0.31, 0.33, 0.18, 0.16, 0.17],
            "yawn_count": [0, 1, 0, 4, 5, 3],
            "head_pose_angle": [5.2, 4.1, 3.5, 12.1, 15.2, 10.8],
            "label": ["alert", "alert", "alert", "drowsy", "drowsy", "drowsy"]
        })
        self.clean_df.to_csv(self.filepath_clean, index=False)

        # Create a dataset with some missing values
        self.missing_df = pd.DataFrame({
            "eye_aspect_ratio": [0.32, None, 0.33, 0.18],
            "yawn_count": [0, 1, None, 4],
            "label": ["alert", "alert", "drowsy", "drowsy"]
        })
        self.missing_df.to_csv(self.filepath_missing, index=False)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_csv_read_success(self) -> None:
        """Verifies csv_read successfully parses file structures and previews data."""
        res = csv_read(self.filepath_clean)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["shape"], [6, 4])
        self.assertEqual(
            res["columns"],
            ["eye_aspect_ratio", "yawn_count", "head_pose_angle", "label"]
        )
        self.assertIn("eye_aspect_ratio", res["dtypes"])
        self.assertEqual(len(res["head"]), 5)  # preview capped at 5 rows
        self.assertEqual(res["head"][0]["label"], "alert")

    def test_csv_read_not_found(self) -> None:
        """Verifies csv_read returns an error dictionary for missing files."""
        res = csv_read("/nonexistent/file_path.csv")
        self.assertEqual(res["status"], "error")
        self.assertIn("File not found", res["error"])

    def test_pandas_profile_calculations(self) -> None:
        """Verifies statistics are accurately computed by pandas_profile."""
        res = pandas_profile(self.filepath_clean)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["shape"], [6, 4])

        # Missing values should all be 0 in clean data
        for col, val in res["missing_values"].items():
            self.assertEqual(val, 0)

        # Statistical calculations
        yawn_summary = res["numeric_summary"]["yawn_count"]
        # clean yawn counts: [0, 1, 0, 4, 5, 3] -> mean = 13/6 = 2.1666...
        self.assertAlmostEqual(yawn_summary["mean"], 2.1666666, places=4)
        self.assertEqual(yawn_summary["min"], 0.0)
        self.assertEqual(yawn_summary["max"], 5.0)

        # Categorical summaries (label distributions)
        self.assertIn("label", res["categorical_summary"])
        label_dist = res["categorical_summary"]["label"]
        self.assertEqual(label_dist["alert"]["count"], 3)
        self.assertEqual(label_dist["alert"]["proportion"], 0.5)
        self.assertEqual(label_dist["drowsy"]["count"], 3)
        self.assertEqual(label_dist["drowsy"]["proportion"], 0.5)

    def test_pandas_profile_with_missing_values(self) -> None:
        """Verifies missing value counts are reported correctly."""
        res = pandas_profile(self.filepath_missing)
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["missing_values"]["eye_aspect_ratio"], 1)
        self.assertEqual(res["missing_values"]["yawn_count"], 1)
        self.assertEqual(res["missing_values"]["label"], 0)

    def test_save_features_success(self) -> None:
        """Verifies save_features correctly saves dataset to disk."""
        save_path = os.path.join(self.temp_dir.name, "output_features.csv")
        data_to_save = [
            {"scaled_ear": 1.0, "yawn_rate": 0.1, "target": 0},
            {"scaled_ear": 0.9, "yawn_rate": 0.2, "target": 0},
            {"scaled_ear": 0.4, "yawn_rate": 0.8, "target": 1},
        ]

        result_msg = save_features(data_to_save, save_path)
        self.assertIn("Successfully saved 3 rows and 3 features", result_msg)
        self.assertTrue(os.path.exists(save_path))

        # Check saved file content
        saved_df = pd.read_csv(save_path)
        self.assertEqual(saved_df.shape, (3, 3))
        self.assertEqual(list(saved_df.columns), ["scaled_ear", "yawn_rate", "target"])
        self.assertEqual(saved_df.iloc[0]["scaled_ear"], 1.0)
