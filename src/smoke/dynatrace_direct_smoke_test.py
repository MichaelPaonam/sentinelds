import logging
import sys
import time

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)

from src.core.config import settings

# Enable verbose logging
logging.basicConfig(level=logging.DEBUG)

logging.getLogger("opentelemetry").setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.DEBUG)

if not settings.DYNATRACE_API_URL or not settings.DYNATRACE_API_TOKEN:
    print("DYNATRACE_API_URL and DYNATRACE_API_TOKEN are required")
    sys.exit(1)

endpoint = f"{settings.DYNATRACE_API_URL.rstrip('/')}/api/v2/otlp/v1/traces"
token = settings.DYNATRACE_API_TOKEN.get_secret_value()

print(f"Endpoint: {endpoint}")
print(f"Token prefix: {token[:10]}")

resource = Resource.create(
    {
        "service.name": "python-smoke-tester-direct",
        "service.version": "1.0.0",
        "deployment.environment": "dev",
    }
)

provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)


class DebugOTLPExporter(OTLPSpanExporter):
    def export(self, spans):
        print(f"\n>>> Exporting {len(spans)} span(s)")
        result = super().export(spans)
        print(f"<<< Export result: {result}")
        return result


otlp_exporter = DebugOTLPExporter(
    endpoint=endpoint,
    headers={
        "Authorization": f"Api-Token {token}",
    },
)

# Print span locally
provider.add_span_processor(
    SimpleSpanProcessor(ConsoleSpanExporter())
)

# Send span to Dynatrace
provider.add_span_processor(
    SimpleSpanProcessor(otlp_exporter)
)

tracer = trace.get_tracer(__name__)

print("Sending smoke-test span...")

with tracer.start_as_current_span("ExecutePythonDirectSmokeTest") as span:
    span.set_attribute("test.origin", "python-sdk-app")
    span.set_attribute("debug.status", "pipeline-clear")
    span.set_attribute("connection.type", "direct-to-tenant")
    time.sleep(0.5)

print("Forcing flush...")
provider.force_flush()

print("Shutting down...")
provider.shutdown()

print("Done.")
