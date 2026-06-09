"""Once-per-process auto-instrumentation for the Google GenAI SDK."""

import logging

from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor

logger = logging.getLogger("sentinelds.observability")

_GENAI_INSTRUMENTED = False


def instrument_genai() -> None:
    """Instruments the Google GenAI SDK if it hasn't been instrumented in this process."""
    global _GENAI_INSTRUMENTED

    if _GENAI_INSTRUMENTED:
        logger.debug("Google GenAI SDK is already instrumented in this process.")
        return

    try:
        GoogleGenAiSdkInstrumentor().instrument()
        _GENAI_INSTRUMENTED = True
        logger.debug("Google GenAI SDK instrumented successfully.")
    except Exception as e:
        logger.warning("Failed to instrument Google GenAI SDK: %s", e)
