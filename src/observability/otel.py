"""OpenTelemetry tracer provider initialization and configuration for SentinelDS.

This module sets up tracing to Dynatrace SaaS using OTLP/HTTP. It is designed
to be idempotent to support complex multi-agent execution topologies.
"""

import atexit
import logging
import os
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from core.config import settings

logger = logging.getLogger("sentinelds.observability")

_PROVIDER: Optional[TracerProvider] = None
_INITIALIZED_SERVICE_NAME: Optional[str] = None


def init_tracing(
    service_name: str,
    agent_name: Optional[str] = None,
    *,
    extra_resource_attributes: Optional[Dict[str, str]] = None,
) -> TracerProvider:
    """Initializes and returns the global TracerProvider configured for Dynatrace.

    This function is idempotent. The first call wins: subsequent calls with
    different configurations will return the already-initialized global provider.

    Args:
        service_name: The value for the 'service.name' resource attribute.
        agent_name: Optional value for the 'agent.name' resource attribute.
        extra_resource_attributes: Additional resource attributes to inject.

    Returns:
        The configured TracerProvider.
    """
    global _PROVIDER, _INITIALIZED_SERVICE_NAME

    if _PROVIDER is not None:
        if _INITIALIZED_SERVICE_NAME != service_name:
            logger.debug(
                "init_tracing called with service_name='%s', but already "
                "initialized with '%s'. Returning cached provider.",
                service_name,
                _INITIALIZED_SERVICE_NAME,
            )
        return _PROVIDER

    # Validate Dynatrace credentials
    if not settings.DYNATRACE_API_URL or not settings.DYNATRACE_API_TOKEN:
        raise RuntimeError("DYNATRACE_API_URL and DYNATRACE_API_TOKEN are required for tracing.")

    endpoint = f"{settings.DYNATRACE_API_URL.rstrip('/')}/api/v2/otlp/v1/traces"
    token = settings.DYNATRACE_API_TOKEN.get_secret_value()

    headers = {
        "Authorization": f"Api-Token {token}",
    }

    # Ensure stable semantic conventions for GenAI tracing
    if "OTEL_SEMCONV_STABILITY_OPT_IN" not in os.environ:
        if settings.OTEL_SEMCONV_STABILITY_OPT_IN:
            os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = settings.OTEL_SEMCONV_STABILITY_OPT_IN

    # Build resource attributes
    attributes: Dict[str, Any] = {"service.name": service_name}
    if agent_name:
        attributes["agent.name"] = agent_name
    if extra_resource_attributes:
        attributes.update(extra_resource_attributes)

    resource = Resource.create(attributes=attributes)
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Configure exporter & processor
    otlp_exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
    processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(processor)

    _PROVIDER = provider
    _INITIALIZED_SERVICE_NAME = service_name

    logger.debug(
        "TracerProvider initialized successfully. service.name='%s', agent.name='%s'",
        service_name,
        agent_name,
    )

    return provider


def shutdown_tracing() -> None:
    """Flushes and shuts down the global TracerProvider."""
    global _PROVIDER, _INITIALIZED_SERVICE_NAME
    if _PROVIDER is not None:
        logger.debug("Shutting down TracerProvider and flushing spans...")
        _PROVIDER.shutdown()
        _PROVIDER = None
        _INITIALIZED_SERVICE_NAME = None


# Ensure clean flush of traces on normal exit
atexit.register(shutdown_tracing)
