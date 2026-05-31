import sys

from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai.types import Content, Part
from opentelemetry import trace
from opentelemetry.trace import StatusCode

agent = Agent(
    name="research_agent", model="gemini-2.5-flash", instruction="Be a short factual assistant."
)

runner = InMemoryRunner(agent=agent)
runner.auto_create_session = True

if __name__ == "__main__":
    print("--- Activating Agent Execution Loop ---")

    current_span = trace.get_current_span()

    try:
        # Wrap your text prompt in the expected structure
        prompt_content = Content(
            parts=[Part.from_text(text="Give me a 1-sentence description of OpenTelemetry.")]
        )

        # Execute the pipeline with your target parameters
        event_stream = runner.run(
            user_id="local_hackathon_user",
            session_id="local_test_session_001",
            new_message=prompt_content,
        )

        full_text_response = ""

        # FIXED: Correct unpacking approach for ADK 2.0 streaming event frames
        for event in event_stream:
            # Check if this specific frame represents the final text response block
            if hasattr(event, "is_final_response") and event.is_final_response():
                content = getattr(event, "content", None)
                if content is not None and getattr(content, "parts", None):
                    full_text_response += "".join(
                        [
                            part.text
                            for part in content.parts
                            if part and getattr(part, "text", None) and isinstance(part.text, str)
                        ]
                    )

            # Fallback for streaming delta chunks if final response block is skipped
            elif hasattr(event, "text") and event.text:
                full_text_response += str(event.text)

        # Print the extracted response content
        print(f"\n[Agent Output]: {full_text_response.strip()}\n")
        current_span.set_status(StatusCode.OK, "Agent executed successfully.")

    except Exception as e:
        print(f"[ERROR] Agent failed execution: {e}", file=sys.stderr)
        current_span.set_status(StatusCode.ERROR, description=str(e))
        current_span.record_exception(e)
        raise e
