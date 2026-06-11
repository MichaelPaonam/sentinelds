"""Observability package for SentinelDS.

This package provides unified OpenTelemetry tracing initialization, GenAI SDK
auto-instrumentation, and tool tracing helpers.
"""

from observability.instrumentation import instrument_genai
from observability.otel import init_tracing, shutdown_tracing
from observability.tools import current_span, tool_span, traced_tool

__all__ = [
    "init_tracing",
    "shutdown_tracing",
    "instrument_genai",
    "traced_tool",
    "tool_span",
    "current_span",
]
