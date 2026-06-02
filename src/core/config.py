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
    GOOGLE_CLOUD_LOCATION: str = "asia-southeast1"

    DYNATRACE_API_URL: Optional[str] = None
    DYNATRACE_API_TOKEN: Optional[SecretStr] = None

    # Mandatory Standard Configurations
    OTEL_EXPORTER_OTLP_PROTOCOL: str = "http/protobuf"
    OTEL_SEMCONV_STABILITY_OPT_IN: str = "gen_ai_latest_experimental"
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: bool = True


# Global configuration instance
try:
    settings = Settings()
except ValidationError as e:
    raise RuntimeError(f"Configuration validation error: {e}") from e
except Exception as e:
    print(f"Warning: unexpected Settings init failure: {e}", file=sys.stderr)
    raise e
