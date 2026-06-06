"""Single agent execution loop for the Research Agent.

This module sets up the Google ADK Research Agent, configures OpenTelemetry tracing
routed to Dynatrace, registers the fetch_url tool, and executes a baseline query.
"""

import asyncio
import hashlib
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
from google.adk import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

# Core OpenTelemetry Modules
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import StatusCode

from core.config import settings
from tools.web_fetch import fetch_url

load_dotenv()

AGENT_NAME = "Research Agent"
# APP_NAME = "research_agent"
USER_ID = "local_hackathon_user"
SESSION_ID = "local_test_session_001"
resource = Resource.create(
    attributes={"service.name": "sentinelds-agentic-workflow", "agent.name": AGENT_NAME}
)

provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

if not settings.DYNATRACE_API_URL or not settings.DYNATRACE_API_TOKEN:
    print("DYNATRACE_API_URL and DYNATRACE_API_TOKEN are required")
    sys.exit(1)

endpoint = f"{settings.DYNATRACE_API_URL.rstrip('/')}/api/v2/otlp/v1/traces"
token = settings.DYNATRACE_API_TOKEN.get_secret_value()

headers = {
    "Authorization": f"Api-Token {token}",
}

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
    model="gemini-2.5-flash",
    instruction=(
        "Be a short factual assistant. "
        "Use the fetch_url tool to fetch contents of URLs when requested."
    ),
    tools=[fetch_url],
)

session_service = InMemorySessionService()

runner = Runner(
    agent=agent,
    app_name=AGENT_NAME,
    session_service=session_service,
)

# runner = InMemoryRunner(agent=agent)


async def main():
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

            with tracer.start_as_current_span("LLMCompletion") as child_span:
                try:
                    _ = await session_service.create_session(
                        app_name=AGENT_NAME,
                        user_id=USER_ID,
                        session_id=SESSION_ID,
                    )

                    event_stream = runner.run(
                        user_id=USER_ID,
                        session_id=SESSION_ID,
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

                    response_hash = hashlib.sha256(full_text_response.encode("utf-8")).hexdigest()
                    host = urlparse(url).netloc

                    child_span.set_attribute("tool.name", AGENT_NAME)
                    child_span.set_attribute("response.body.hash", response_hash)
                    child_span.set_attribute("egress.host", host)

                    print(f"\n[Agent Output]: {full_text_response.strip()}\n")

                    child_span.set_status(StatusCode.OK)
                    span.set_status(StatusCode.OK)

                except Exception as e:
                    child_span.set_status(StatusCode.ERROR, description=str(e))
                    child_span.record_exception(e)
                    raise e

        except Exception as e:
            print(f"[ERROR] Run failed: {e}", file=sys.stderr)
            span.set_status(StatusCode.ERROR, description=str(e))
            span.record_exception(e)
            raise e
        finally:
            print("Flushing spans directly to telemetry sink...")
            provider.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
