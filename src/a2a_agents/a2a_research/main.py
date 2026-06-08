import os

from observability import init_tracing, instrument_genai

# Initialize tracing before importing heavy framework elements
init_tracing(service_name="sentinelds-research-agent", agent_name="research_agent")
instrument_genai()

import uvicorn  # noqa: E402
from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from agents.sub_agents.research_agent.agent import research_agent  # noqa: E402

PUBLIC_HOST = os.getenv("RESEARCH_AGENT_PUBLIC_HOST", "localhost")
PUBLIC_PROTOCOL = os.getenv("RESEARCH_AGENT_PUBLIC_PROTOCOL", "http")

RUN_PORT = int(os.getenv("PORT", 8080))

# Wrap your internal agent instance
a2a_research_agent = to_a2a(
    agent=research_agent,
    host=PUBLIC_HOST,
    port=RUN_PORT,
    protocol=PUBLIC_PROTOCOL
)

# Start the actual container network listener loop
if __name__ == "__main__":
    # If using modern v1+ layout variations, the app object exposes a build method:
    # app_target = a2a_research_agent.build() if hasattr(a2a_research_agent, 'build') else a2a_research_agent

    print("Launching Local A2A Web Service Container...")
    uvicorn.run(
        "a2a_agents.a2a_research.main:a2a_research_agent",
        host="0.0.0.0",
        port=RUN_PORT,
        factory=False
    )
