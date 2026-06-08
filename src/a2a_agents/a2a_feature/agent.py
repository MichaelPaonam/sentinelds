import logging
import os
import warnings

from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-agentic-workflow", agent_name="root_agent")
instrument_genai()

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent  # noqa: E402

logging.disable(level=logging.WARNING)
warnings.filterwarnings("ignore")

AGENT_CARD_BASE_URL = os.getenv("FEATURE_AGENT_CARD_BASE_URL", "http://localhost:8080")

root_agent = RemoteA2aAgent(
    name="feature_agent",
    agent_card=f"{AGENT_CARD_BASE_URL}/.well-known/agent-card.json",
    description="Feature Engineering Agent: profiles datasets and transforms raw ECG signals \
    into ML-ready features.",
)
