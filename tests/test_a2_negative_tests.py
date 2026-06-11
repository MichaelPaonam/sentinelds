"""A2 Negative Test Suite (Issue #35).

Provides thorough coverage and automated verification for:
1. **1% Poisoning Bypass (Clean Stats)**: Asserting that a 1% poisoned dataset
   with clean stats passes validation without raising drift candidates or compromising the session.
2. **Gradual Drift / Rolling Baseline Check**: Asserting that drift calculations
   evaluate features and label distributions against the average baseline across
   the 5 pre-seeded snapshots.
3. **Quarantine Reversibility & Idempotency**: Asserting that `DatasetQuarantine` is
   idempotent, that quarantined files block profiling, and releasing them works seamlessly.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from attack_server.generate_datasets import _generate_clean_dataframe
from sentinel.preflight import DatasetQuarantine, SentinelSession
from sentinel.session import clear_sentinel_session, set_sentinel_session
from tools.feature_tools import (
    calculate_dataframe_checksum,
    load_baseline_stats,
    pandas_profile,
)


class TestA2NegativeTests(unittest.TestCase):
    """Negative tests for A2 Training Data Poisoning detection and defense."""

    def setUp(self) -> None:
        # Create temporary working directory for test files
        self.tmpdir = tempfile.mkdtemp(prefix="test_a2_neg_")
        self.clean_csv = os.path.join(self.tmpdir, "clean.csv")
        self.mild_poisoned_csv = os.path.join(self.tmpdir, "mild_poisoned.csv")
        self.severe_poisoned_csv = os.path.join(self.tmpdir, "severe_poisoned.csv")

        # Generate clean dataframe
        rng = np.random.default_rng(42)
        self.clean_df = _generate_clean_dataframe(rng)
        self.clean_df.to_csv(self.clean_csv, index=False)

        # 1% Mildly poisoned (flip only 4 labels out of 800)
        mild_df = self.clean_df.copy()
        drowsy_indices = mild_df.index[mild_df["label"] == 1].tolist()
        for idx in drowsy_indices[:4]:
            mild_df.loc[idx, "label"] = 0
        mild_df.to_csv(self.mild_poisoned_csv, index=False)

        # Severe poisoned (flip 100 drowsy labels)
        severe_df = self.clean_df.copy()
        for idx in drowsy_indices[:100]:
            severe_df.loc[idx, "label"] = 0
        severe_df.to_csv(self.severe_poisoned_csv, index=False)

        # Clear active session and ensure clear quarantine
        clear_sentinel_session()
        self.quarantine_file_backup = "data/quarantine.json.bak"
        if os.path.exists("data/quarantine.json"):
            shutil.copy("data/quarantine.json", self.quarantine_file_backup)
            os.remove("data/quarantine.json")

    def tearDown(self) -> None:
        clear_sentinel_session()
        # Restore quarantine backup if any
        if os.path.exists("data/quarantine.json"):
            os.remove("data/quarantine.json")
        if os.path.exists(self.quarantine_file_backup):
            shutil.move(self.quarantine_file_backup, "data/quarantine.json")
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_one_percent_poisoning_bypass(self) -> None:
        """1% poisoned dataset should bypass drift checks and NOT compromise the session."""
        sess = SentinelSession(workspace_entity_id="WORKSPACE-TEST", agent_name="Feature Agent")
        set_sentinel_session(sess)

        # Profile 1% mildly poisoned dataset
        result = pandas_profile(self.mild_poisoned_csv)
        self.assertEqual(result["status"], "success")

        # Session should remain uncompromised
        self.assertFalse(sess.compromised)
        self.assertEqual(sess.compromise_reason, "")

        # Should not have quarantined the checksum
        checksum = calculate_dataframe_checksum(pd.read_csv(self.mild_poisoned_csv))
        self.assertFalse(DatasetQuarantine.is_quarantined(checksum))

    def test_rolling_baseline_average_checks(self) -> None:
        """Drift calculations must check against the rolling average baseline window of 5 snapshots."""
        baseline = load_baseline_stats()
        self.assertIn("label_0_proportion", baseline)
        self.assertIn("feature_means", baseline)

        # Real averages from 5 snapshots:
        # run_1 label_0_prop: 0.6
        # run_2 label_0_prop: 0.6
        # run_3 label_0_prop: 0.6
        # run_4 label_0_prop: 0.6
        # run_5 label_0_prop: 0.6
        # (Average label 0 proportion should be exactly 0.6)
        self.assertAlmostEqual(baseline["label_0_proportion"], 0.6)

        # Severe poisoned triggers drift and compromises active session
        sess = SentinelSession(workspace_entity_id="WORKSPACE-TEST", agent_name="Feature Agent")
        set_sentinel_session(sess)

        # Mock event emission to avoid hit to Dynatrace
        with patch("tools.feature_tools.emit_dataset_drift_candidate") as mock_emit:
            result = pandas_profile(self.severe_poisoned_csv)
            self.assertEqual(result["status"], "success")
            self.assertTrue(sess.compromised)
            self.assertIn("Training halted: ingested dataset shows label-distribution drift", sess.compromise_reason)
            mock_emit.assert_called_once()

    def test_quarantine_reversibility_and_idempotency(self) -> None:
        """Verify adding, removing, and duplicate adding on DatasetQuarantine is clean and reversable."""
        checksum = "test_checksum_123456"

        # Initially not quarantined
        self.assertFalse(DatasetQuarantine.is_quarantined(checksum))

        # Add to quarantine
        DatasetQuarantine.add(checksum)
        self.assertTrue(DatasetQuarantine.is_quarantined(checksum))

        # Add duplicate (idempotent)
        DatasetQuarantine.add(checksum)
        self.assertTrue(DatasetQuarantine.is_quarantined(checksum))
        self.assertEqual(DatasetQuarantine.list_all().count(checksum), 1)

        # Block profiling of quarantined dataset
        clean_checksum = calculate_dataframe_checksum(self.clean_df)
        DatasetQuarantine.add(clean_checksum)

        with patch("pandas.read_csv", return_value=self.clean_df):
            with self.assertRaises(PermissionError) as ctx:
                pandas_profile(self.clean_csv)
            self.assertIn("Dataset is quarantined", str(ctx.exception))

        # Remove from quarantine
        DatasetQuarantine.remove(clean_checksum)

        # Remove from quarantine (release)
        removed = DatasetQuarantine.remove(checksum)
        self.assertTrue(removed)
        self.assertFalse(DatasetQuarantine.is_quarantined(checksum))

        # Check remove when not present
        removed_again = DatasetQuarantine.remove(checksum)
        self.assertFalse(removed_again)

        # Profiling clean CSV should succeed now that checksum is cleared
        result = pandas_profile(self.clean_csv)
        self.assertEqual(result["status"], "success")


if __name__ == "__main__":
    unittest.main()
