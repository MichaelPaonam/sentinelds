"""Smoke test for streaming OpenTelemetry traces to Dynatrace OneAgent.

This script manually starts an OTel tracer provider, configures the OTLPSpanExporter,
emits a sample span, and flushes it to the local OneAgent daemon.
"""

import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.core.config import settings

# 1. Define the service name exactly how it will appear in Dynatrace
resource = Resource.create(attributes={"service.name": "python-smoke-tester"})

# 2. Initialize the Tracer Provider
provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

# 3. Configure the exporter to stream to the local OneAgent
# or remote Dynatrace OTLP/HTTP Protobuf endpoint
endpoint = "http://localhost:14499/otlp/v1/traces"
headers = {}

if settings.DYNATRACE_API_URL:
    endpoint = f"{settings.DYNATRACE_API_URL}/otlp/v1/traces"

if settings.DYNATRACE_API_TOKEN:
    headers["Authorization"] = f"Api-Token {settings.DYNATRACE_API_TOKEN.get_secret_value()}"

otlp_exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)

# 4. Add the span processor to the provider
processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(processor)

# 5. Create a tracer and execute a hand-crafted span
tracer = trace.get_tracer(__name__)

print("Sending smoke-test span to OneAgent...")
with tracer.start_as_current_span("ExecutePythonSmokeTest") as span:
    span.set_attribute("test.origin", "python-sdk-app")
    span.set_attribute("debug.status", "pipeline-clear")
    time.sleep(0.5)  # Simulating a 500ms operation
    print("Span executed successfully!")

# 6. Force flush to ensure the data leaves the local memory buffer immediately
provider.shutdown()
