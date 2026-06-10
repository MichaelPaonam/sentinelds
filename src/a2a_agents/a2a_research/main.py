import json
import logging
import os
import warnings

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from observability import init_tracing, instrument_genai

# Initialize tracing before importing heavy framework elements
init_tracing(service_name="sentinelds-research-agent", agent_name="research_agent")
instrument_genai()

# Patch ADK's A2A→GenAI part converter BEFORE importing any other google.adk.a2a
# module. ADK callers capture `convert_a2a_part_to_genai_part` as a default arg
# at function-definition time, so the patch must be in place before those caller
# modules are imported (e.g. via `to_a2a`, `RemoteA2aAgent`).
from core import genai_compat  # noqa: E402,F401
import uvicorn  # noqa: E402
from google.adk.a2a.utils.agent_to_a2a import to_a2a  # noqa: E402

from agents.sub_agents.research_agent.agent import research_agent  # noqa: E402

logging.disable(level=logging.WARNING)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

INTERNAL_PORT = int(os.getenv("PORT", 8080))
IS_CLOUD_RUN = "K_SERVICE" in os.environ  # Natively injected by Cloud Run

a2a_research_agent = to_a2a(
    agent=research_agent, host="localhost", port=INTERNAL_PORT, protocol="http"
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


app = a2a_research_agent
app.add_middleware(AgentCardURLMiddleware)


if __name__ == "__main__":
    print(f"Starting Research Agent on port {INTERNAL_PORT} (Cloud Run: {IS_CLOUD_RUN})")
    uvicorn.run(
        "a2a_agents.a2a_research.main:app",
        host="0.0.0.0",
        port=INTERNAL_PORT,
        factory=False,
    )
