"""Spike Script — Test GCS Bucket access and capability.

Verifies reading and optional writing to Google Cloud Storage (GCS)
using the local credentials (ADC) and the google-cloud-storage library.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time

from core.config import settings
from observability import init_tracing, current_span


def verify_gcs_access(bucket_name: str, prefix: str | None, test_write: bool) -> bool:
    try:
        from google.cloud import storage
    except ImportError:
        print("[spike_gcs_test] ERROR: google-cloud-storage is not installed.", file=sys.stderr)
        print("Please run 'uv sync' to install dependencies.", file=sys.stderr)
        return False

    print("[spike_gcs_test] Initializing Storage Client...")
    try:
        client = storage.Client()
    except Exception as exc:
        print(f"[spike_gcs_test] ERROR initializing Client: {exc}", file=sys.stderr)
        print("Hint: Run `gcloud auth application-default login`.", file=sys.stderr)
        return False

    print(f"[spike_gcs_test] Accessing bucket: {bucket_name}")
    try:
        bucket = client.bucket(bucket_name)
        # Attempt to list objects under prefix
        print(f"[spike_gcs_test] Listing blobs under prefix: {prefix or '/'}")
        blobs = list(bucket.list_blobs(prefix=prefix, max_results=10))
        print(f"[spike_gcs_test] Found {len(blobs)} blob(s):")
        for b in blobs:
            print(f"  - gs://{bucket_name}/{b.name} (size: {b.size} bytes)")
    except Exception as exc:
        print(f"[spike_gcs_test] ERROR listing bucket/blobs: {exc}", file=sys.stderr)
        print("Hint: Check bucket existence and viewer/reader permission roles.", file=sys.stderr)
        return False

    # Perform test download if there are blobs
    if blobs:
        first_blob = blobs[0]
        print(f"[spike_gcs_test] Testing download of first blob: gs://{bucket_name}/{first_blob.name}")
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                first_blob.download_to_filename(tmp.name)
                print(f"[spike_gcs_test] SUCCESS: Downloaded {first_blob.name} to temporary location {tmp.name}")
            os.unlink(tmp.name)
        except Exception as exc:
            print(f"[spike_gcs_test] ERROR downloading blob: {exc}", file=sys.stderr)
            return False

    # Perform test write if requested
    if test_write:
        test_blob_name = f"spike_test_write_{int(time.time())}.txt"
        print(f"[spike_gcs_test] Testing write/upload: gs://{bucket_name}/{test_blob_name}")
        try:
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
                tmp.write(b"SentinelDS GCS access test payload.\n")
                tmp_name = tmp.name
            try:
                blob = bucket.blob(test_blob_name)
                blob.upload_from_filename(tmp_name)
                print(f"[spike_gcs_test] SUCCESS: Uploaded {test_blob_name}")

                # Cleanup uploaded test file to avoid cluttering bucket
                print("[spike_gcs_test] Cleaning up uploaded test blob...")
                blob.delete()
                print("[spike_gcs_test] SUCCESS: Cleaned up test blob.")
            finally:
                os.unlink(tmp_name)
        except Exception as exc:
            print(f"[spike_gcs_test] ERROR writing/uploading test blob: {exc}", file=sys.stderr)
            print("Hint: Check if your role has storage.objects.create or storage.objectUser permissions.", file=sys.stderr)
            return False

    return True


def main() -> None:
    # Set up tracing for visibility
    init_tracing(service_name="sentinelds-spike-gcs", agent_name="gcs_spike_tester")

    parser = argparse.ArgumentParser(description="Test GCS bucket programmatic access.")
    parser.add_argument("--bucket", default=settings.GCS_BUCKET_NAME, help="Bucket name to test")
    parser.add_argument("--prefix", default=None, help="Prefix to list blobs under")
    parser.add_argument("--test-write", action="store_true", help="Perform a write/upload test")

    args = parser.parse_args()

    if not args.bucket:
        print("[spike_gcs_test] ERROR: No bucket name provided via argument or config.", file=sys.stderr)
        print("Please specify a bucket name: --bucket <name>", file=sys.stderr)
        sys.exit(1)

    span = current_span()
    span.set_attribute("spike.bucket", args.bucket)
    span.set_attribute("spike.test_write", args.test_write)

    success = verify_gcs_access(args.bucket, args.prefix, args.test_write)
    if success:
        print("\n[spike_gcs_test] GCS programmatic access verification: PASSED")
        sys.exit(0)
    else:
        print("\n[spike_gcs_test] GCS programmatic access verification: FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
