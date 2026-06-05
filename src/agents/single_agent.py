"""Single agent execution loop for the Research Agent.

This module sets up the Google ADK Research Agent, configures OpenTelemetry tracing
routed to Dynatrace, registers the fetch_url tool, and executes a baseline query.
"""

import os
import sys

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai.types import Content, Part

# Core OpenTelemetry Modules
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import StatusCode

from src.tools.web_fetch import fetch_url

AGENT_NAME = "Research Agent"
resource = Resource.create(
    attributes={"service.name": "sentinelds-agentic-workflow", "agent.name": AGENT_NAME}
)

provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

# Default: Point to your local laptop's OneAgent daemon
endpoint = "http://localhost:14499/otlp/v1/traces"
headers = {}

# Cloud Override: Automatically toggles to direct ingest if deployed to Google Agent Platform
DYNATRACE_API_URL = os.environ.get("DYNATRACE_API_URL")
DYNATRACE_API_TOKEN = os.environ.get("DYNATRACE_API_TOKEN")

if DYNATRACE_API_URL:
    base_url = DYNATRACE_API_URL.rstrip("/")
    endpoint = f"{base_url}/otlp/v1/traces"

if DYNATRACE_API_TOKEN:
    headers["Authorization"] = f"Api-Token {DYNATRACE_API_TOKEN}"

# Build and register the execution tracer pipeline
otlp_exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers)
processor = BatchSpanProcessor(otlp_exporter)
provider.add_span_processor(processor)

if "OTEL_SEMCONV_STABILITY_OPT_IN" not in os.environ:
    raise EnvironmentError(
        "Environment variable 'OTEL_SEMCONV_STABILITY_OPT_IN' is required but not set."
        "(e.g. 'gen_ai_latest_experimental')."
    )
GoogleGenAiSdkInstrumentor().instrument()

agent = Agent(
    name="research_agent",
    model="gemini-2.5-flash-lite",
    instruction=(
        "Be a short factual assistant. "
        "Use the fetch_url tool to fetch contents of URLs when requested."
    ),
    tools=[fetch_url],
)

runner = InMemoryRunner(agent=agent)

if __name__ == "__main__":
    print("--- Activating Agent Execution Loop ---")

    # Grab the active application context tracer
    tracer = trace.get_tracer(__name__)

    with tracer.start_as_current_span("ExecuteAgentWorkflow") as span:
        try:
            url = "https://opentelemetry.io/"
            prompt_content = Content(
                parts=[
                    Part.from_text(
                        text=f"Which organization created OpenTelemetry?"
                        f"Answer by looking at this URL: {url}"
                    )
                ]
            )

            event_stream = runner.run(
                user_id="local_hackathon_user",
                session_id="local_test_session_001",
                new_message=prompt_content,
            )

            full_text_response = ""
            for event in event_stream:
                # Check if this specific frame represents the final text response block
                if hasattr(event, "is_final_response") and event.is_final_response():
                    content = getattr(event, "content", None)
                    if content is not None and getattr(content, "parts", None):
                        full_text_response += "".join(
                            [
                                part.text
                                for part in content.parts
                                if part
                                and getattr(part, "text", None)
                                and isinstance(part.text, str)
                            ]
                        )
                elif hasattr(event, "text") and event.text:
                    full_text_response += str(event.text)

            print(f"\n[Agent Output]: {full_text_response.strip()}\n")

            span.set_status(StatusCode.OK)

        except Exception as e:
            print(f"[ERROR] Run failed: {e}", file=sys.stderr)
            span.set_status(StatusCode.ERROR, description=str(e))
            span.record_exception(e)
            raise e
        finally:
            print("Flushing spans directly to telemetry sink...")
            provider.shutdown()
