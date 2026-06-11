import json
import logging
import os
import warnings

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from observability import init_tracing, instrument_genai

# Initialize tracing before importing heavy framework elements
init_tracing(service_name="sentinelds-modeling-agent", agent_name="modeling_agent")
instrument_genai()

# Patch google.genai.types.Part to null part_metadata BEFORE importing any
# google.adk.a2a module. The patch installs at Part.__init__, so strictly it
# only needs to land before any Part is constructed — but importing it first
# keeps the ordering obvious and matches the intent of the comment.
import uvicorn  # noqa: E402
from a2a.types import AgentCapabilities, AgentCard  # noqa: E402
from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from agents.sub_agents.modeling_agent.agent import modeling_agent  # noqa: E402
from core import genai_compat  # noqa: E402,F401

logging.disable(level=logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

INTERNAL_PORT = int(os.getenv("PORT", 8080))
IS_CLOUD_RUN = "K_SERVICE" in os.environ  # Natively injected by Cloud Run

a2a_modeling_agent = to_a2a(
    agent=modeling_agent,
    host="localhost",
    port=INTERNAL_PORT,
    protocol="http",
    agent_card=AgentCard(
        name="modeling_agent",
        description=(
            "Modeling Agent: trains XGBoost and CatBoost classifiers on "
            "engineered features and produces evaluation reports."
        ),
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


app = a2a_modeling_agent
app.add_middleware(AgentCardURLMiddleware)


if __name__ == "__main__":
    print(f"Starting Modeling Agent on port {INTERNAL_PORT} (Cloud Run: {IS_CLOUD_RUN})")
    uvicorn.run(
        "a2a_agents.a2a_modeling.main:app",
        host="0.0.0.0",
        port=INTERNAL_PORT,
        factory=False,
    )
