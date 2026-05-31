import os
import sys
from google.adk import Agent
from google.adk.runners import InMemoryRunner 
from google.genai.types import Content, Part

# Core OpenTelemetry Modules
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
from opentelemetry.trace import StatusCode

AGENT_NAME = "Research Agent"
resource = Resource.create(attributes={
    "service.name": "sentinelds-agentic-workflow",
    "agent.name": AGENT_NAME
})

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

OTEL_SEMCONV_STABILITY_OPT_IN = os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"]
GoogleGenAiSdkInstrumentor().instrument()

agent = Agent(
    name="research_agent", 
    model="gemini-2.5-flash", 
    instruction="Be a short factual assistant."
)

runner = InMemoryRunner(agent=agent)
runner.auto_create_session = True

if __name__ == "__main__":
    print("--- Activating Agent Execution Loop ---")
    
    # Grab the active application context tracer
    tracer = trace.get_tracer(__name__)
    
    with tracer.start_as_current_span("ExecuteAgentWorkflow") as span:
        try:
            prompt_content = Content(
                parts=[Part.from_text(text="Give me a 1-sentence description of OpenTelemetry.")]
            )
            
            event_stream = runner.run(
                user_id="local_hackathon_user",
                session_id="local_test_session_001",
                new_message=prompt_content
            )
            
            full_text_response = ""
            for event in event_stream:
                if hasattr(event, 'is_final_response') and event.is_final_response():
                    if hasattr(event, 'content') and event.content.parts:
                        full_text_response += "".join([part.text for part in event.content.parts if hasattr(part, 'text')])
                elif hasattr(event, 'text') and event.text:
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