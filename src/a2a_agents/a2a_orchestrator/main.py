import json
import logging
import os
import warnings

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

from observability import init_tracing, instrument_genai

# Initialize tracing before importing heavy framework elements
init_tracing(service_name="sentinelds-agentic-workflow", agent_name="root_agent")
instrument_genai()

# Patch google.genai.types.Part to null part_metadata BEFORE importing any
# google.adk.a2a module. See src/core/genai_compat.py.
import uvicorn  # noqa: E402
from a2a.client.client import ClientConfig as A2AClientConfig  # noqa: E402
from a2a.client.client_factory import ClientFactory as A2AClientFactory  # noqa: E402
from a2a.types import AgentCapabilities, AgentCard  # noqa: E402
from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402
from google.adk.agents import SequentialAgent  # noqa: E402
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent  # noqa: E402
from core import genai_compat  # noqa: E402,F401

logging.disable(level=logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

INTERNAL_PORT = int(os.getenv("PORT", 8080))
IS_CLOUD_RUN = "K_SERVICE" in os.environ
RESEARCH_AGENT_CARD_BASE_URL = os.getenv("RESEARCH_AGENT_CARD_BASE_URL", "http://localhost:8080")
FEATURE_AGENT_CARD_BASE_URL = os.getenv("FEATURE_AGENT_CARD_BASE_URL", "http://localhost:8080")
MODELING_AGENT_CARD_BASE_URL = os.getenv("MODELING_AGENT_CARD_BASE_URL", "http://localhost:8080")

# RemoteA2aAgent defaults to streaming=False when it builds its own ClientFactory,
# which causes the orchestrator to buffer entire sub-agent responses before emitting
# any SSE event. Passing an explicit factory with streaming=True makes each
# RemoteA2aAgent call its leaf via message/stream, so intermediate events
# propagate incrementally through the SequentialAgent to the browser.
_streaming_factory = A2AClientFactory(config=A2AClientConfig(streaming=True))

research_agent = RemoteA2aAgent(
    name="research_agent",
    agent_card=f"{RESEARCH_AGENT_CARD_BASE_URL}/.well-known/agent-card.json",
    description="Research Agent: surveys literature to extract insights \
                 and inform feature engineering and modeling.",
    a2a_client_factory=_streaming_factory,
)

feature_agent = RemoteA2aAgent(
    name="feature_agent",
    agent_card=f"{FEATURE_AGENT_CARD_BASE_URL}/.well-known/agent-card.json",
    description="Feature Engineering Agent: profiles datasets and transforms raw ECG signals \
    into ML-ready features.",
    a2a_client_factory=_streaming_factory,
)

modeling_agent = RemoteA2aAgent(
    name="modeling_agent",
    agent_card=f"{MODELING_AGENT_CARD_BASE_URL}/.well-known/agent-card.json",
    description="Modeling Agent: trains XGBoost and CatBoost classifiers on engineered \
    features and produces evaluation reports.",
    a2a_client_factory=_streaming_factory,
)

root_agent = SequentialAgent(
    name="root_agent",
    description="Sequential data-science pipeline: research -> features -> modeling.",
    sub_agents=[research_agent, feature_agent, modeling_agent],
)

a2a_root_agent = to_a2a(
    agent=root_agent,
    host="localhost",
    port=INTERNAL_PORT,
    protocol="http",
    agent_card=AgentCard(
        name="root_agent",
        description="Sequential data-science pipeline: research -> features -> modeling.",
        url=f"http://localhost:{INTERNAL_PORT}",
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[],
    ),
)


class AgentCardURLMiddleware(BaseHTTPMiddleware):
    """Rewrites the `url` field of the agent card to match the inbound host."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/.well-known/agent-card.json":
            return response

        host_header = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if not host_header:
            return response

        protocol = "https" if IS_CLOUD_RUN else "http"
        if IS_CLOUD_RUN and ":" in host_header:
            host_header = host_header.split(":")[0]

        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            card_data = json.loads(body)
            card_data["url"] = f"{protocol}://{host_header}"
            body = json.dumps(card_data).encode()
        except Exception:
            pass  # return original body untouched on any parse error

        headers = dict(response.headers)
        headers["content-length"] = str(len(body))
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )


app = a2a_root_agent
app.add_middleware(AgentCardURLMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


if __name__ == "__main__":
    print(f"Starting Orchestrator (root_agent) on port {INTERNAL_PORT} (Cloud Run: {IS_CLOUD_RUN})")
    uvicorn.run(
        "a2a_agents.a2a_orchestrator.main:app",
        host="0.0.0.0",
        port=INTERNAL_PORT,
        factory=False,
    )
