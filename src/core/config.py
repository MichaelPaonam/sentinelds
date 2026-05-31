import sys
from typing import Optional

from pydantic import SecretStr
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
    GOOGLE_CLOUD_LOCATION: str = "asia-south1"

    DYNATRACE_API_URL: Optional[str] = None
    DYNATRACE_API_TOKEN: Optional[SecretStr] = None

    # Mandatory Standard Configurations
    OTEL_EXPORTER_OTLP_PROTOCOL: str = "http/protobuf"
    OTEL_SEMCONV_STABILITY_OPT_IN: str = "gen_ai_latest_experimental"
    OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: bool = True


# Global configuration instance
try:
    settings = Settings()
except Exception as e:
    print(f"Warning: Failed to load Settings via Pydantic: {e}", file=sys.stderr)
    # Fallback to model_construct() so we don't crash hard during import in restricted envs
    settings = Settings.model_construct()
