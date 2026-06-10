"""Configuration module for SentinelDS.

This module loads environment variables and parses configuration settings
using Pydantic BaseSettings, enforcing schema and validation constraints.
"""

import sys
from typing import Optional

from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for SentinelDS.

    Reads from environmental variables and/or a local .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    GOOGLE_GENAI_USE_VERTEXAI: bool = True
    GOOGLE_CLOUD_PROJECT: Optional[str] = None
    GOOGLE_CLOUD_LOCATION: str = "europe-west4"

    DYNATRACE_API_URL: Optional[str] = None
    DYNATRACE_API_TOKEN: Optional[SecretStr] = None

    # Mandatory Standard Configurations
    OTEL_EXPORTER_OTLP_PROTOCOL: str = "http/protobuf"
    OTEL_SEMCONV_STABILITY_OPT_IN: str = "gen_ai_latest_experimental"
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: bool = True

    # Agent model selection
    DEFAULT_MODEL: str = "gemini-2.5-flash-lite"
    THINKING_MODEL: str = "gemini-2.5-flash"

    # GCS config for A2 demo artefacts
    GCS_BUCKET_NAME: Optional[str] = None
    A2_CLEAN_BLOB: str = "data/a2/clean.csv"
    A2_POISONED_BLOB: str = "data/a2/poisoned.csv"

    # E2E demo defaults
    E2E_DEFAULT_CSV: str = "data/ecg_csv/ddd/01M_1.csv"
    E2E_PAPER_URL: str = "http://localhost:8001/papers"
    E2E_TARGET_COL: str = "label"
    E2E_COMBINED_CSV: str = "data/ecg_csv/ddd/_e2e_combined.csv"


# Global configuration instance
try:
    settings = Settings()
except ValidationError as e:
    raise RuntimeError(f"Configuration validation error: {e}") from e
except Exception as e:
    print(f"Warning: unexpected Settings init failure: {e}", file=sys.stderr)
    raise e
