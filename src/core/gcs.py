"""GCS helpers for downloading artefacts by gs:// URI."""

from __future__ import annotations

import os


def parse_gs_uri(gs_uri: str) -> tuple[str, str]:
    """Splits 'gs://bucket/blob/path' into (bucket, blob). Raises ValueError on bad scheme."""
    if not gs_uri.startswith("gs://"):
        raise ValueError(f"Expected gs:// URI, got: {gs_uri!r}")
    without_scheme = gs_uri[5:]
    parts = without_scheme.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"Cannot parse bucket/blob from URI: {gs_uri!r}")
    return parts[0], parts[1]


def download_to_path(gs_uri: str, local_path: str) -> str:
    """Downloads gs_uri to local_path and returns local_path.

    Auth is via Application Default Credentials; raises a helpful message if
    credentials are missing.
    """
    try:
        from google.cloud import storage  # lazy import so tests can patch cleanly
    except ImportError as exc:
        raise ImportError("google-cloud-storage is required. Run: uv sync") from exc

    bucket_name, blob_name = parse_gs_uri(gs_uri)
    os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(local_path)
    except Exception as exc:
        # Surface credential errors clearly
        exc_type = type(exc).__name__
        if "DefaultCredentialsError" in exc_type or "credentials" in str(exc).lower():
            raise type(exc)(
                f"{exc}\n\nHint: run `gcloud auth application-default login` to set up ADC."
            ) from None
        raise

    return local_path
