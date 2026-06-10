"""Tests for gs:// support in csv_read and pandas_profile (no live GCS)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from tools.feature_tools import csv_read, pandas_profile

# Build a small drowsiness-schema CSV once
_SAMPLE_DATA = {
    "eye_aspect_ratio": [0.32, 0.31, 0.18, 0.16],
    "yawn_count": [0, 1, 5, 6],
    "head_pose_yaw": [2.0, 3.0, 12.0, 15.0],
    "head_pose_pitch": [1.0, 2.0, 8.0, 10.0],
    "label": [0, 0, 1, 1],
}


def _write_sample_csv(path: str) -> None:
    pd.DataFrame(_SAMPLE_DATA).to_csv(path, index=False)


def _make_storage_mock(dest_path_holder: list) -> MagicMock:
    """Returns a mock for google.cloud.storage whose blob writes a real CSV."""

    def fake_download(local_path: str) -> None:
        dest_path_holder.append(local_path)
        _write_sample_csv(local_path)

    blob_mock = MagicMock()
    blob_mock.download_to_filename.side_effect = fake_download
    bucket_mock = MagicMock()
    bucket_mock.blob.return_value = blob_mock
    client_instance = MagicMock()
    client_instance.bucket.return_value = bucket_mock
    storage_mock = MagicMock()
    storage_mock.Client.return_value = client_instance
    return storage_mock


class TestCsvReadGcs(unittest.TestCase):
    def test_csv_read_gs_uri_returns_success(self) -> None:
        written: list[str] = []
        storage_mock = _make_storage_mock(written)
        with patch.dict(sys.modules, {"google.cloud.storage": storage_mock}):
            # Ensure any cached import is replaced
            import core.gcs as gcs_module  # noqa: F401
            result = csv_read("gs://fake-bucket/a2/clean.csv")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["shape"][1], 5)  # 5 columns
        self.assertEqual(set(result["columns"]), set(_SAMPLE_DATA.keys()))

    def test_csv_read_local_path_still_works(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp = f.name
        try:
            _write_sample_csv(tmp)
            result = csv_read(tmp)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["shape"][0], 4)
        finally:
            os.unlink(tmp)

    def test_csv_read_missing_local_returns_error(self) -> None:
        result = csv_read("/nonexistent/path/file.csv")
        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["error"].lower())


class TestPandasProfileGcs(unittest.TestCase):
    def _run_profile_with_span_capture(self, filepath: str) -> tuple[dict, list]:
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        result = pandas_profile(filepath)
        spans = exporter.get_finished_spans()
        return result, spans

    def test_pandas_profile_emits_dataset_stats_attrs(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp = f.name
        try:
            _write_sample_csv(tmp)
            result, spans = self._run_profile_with_span_capture(tmp)

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["shape"][0], 4)
            self.assertEqual(result["shape"][1], 5)

            # Find the pandas_profile span
            profile_spans = [s for s in spans if "pandas_profile" in s.name]
            self.assertTrue(len(profile_spans) > 0, "No pandas_profile span found")
            span = profile_spans[-1]
            attrs = dict(span.attributes or {})

            self.assertIn("dataset.stats.label_distribution", attrs)
            label_dist = json.loads(attrs["dataset.stats.label_distribution"])
            self.assertIn("0", label_dist)
            self.assertIn("1", label_dist)
            self.assertIn("count", label_dist["0"])
            self.assertIn("proportion", label_dist["0"])

            self.assertIn("dataset.stats.feature_mean", attrs)
            feature_mean = json.loads(attrs["dataset.stats.feature_mean"])
            self.assertIn("eye_aspect_ratio", feature_mean)
            self.assertNotIn("label", feature_mean)

            self.assertIn("dataset.stats.feature_std", attrs)
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
