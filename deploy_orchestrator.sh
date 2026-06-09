#!/bin/bash
set -euo pipefail

# Always clean up generated files, even if deploy fails — otherwise a stale
# Dockerfile/main.py from a previous run could be reused, or a missing
# Dockerfile could cause gcloud to silently fall back to buildpacks (which
# produce a different on-disk layout and break agents_dir resolution).
cleanup() {
  rm -rf ./src/orchestrator
  rm -f ./src/main.py
  rm -f ./Dockerfile
}
trap cleanup EXIT

mkdir -p src/orchestrator

touch src/orchestrator/__init__.py

cat << EOF >src/orchestrator/agent.py
import logging
import os
import warnings

from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-agentic-workflow", agent_name="root_agent")
instrument_genai()

# Patch ADK's A2A→GenAI part converter BEFORE importing any other google.adk.a2a
# module. ADK callers capture \`convert_a2a_part_to_genai_part\` as a default arg
# at function-definition time, so the patch must land before RemoteA2aAgent is
# imported. See src/core/genai_compat.py.
from core import genai_compat  # noqa: E402,F401

from google.adk.agents import SequentialAgent  # noqa: E402
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent  # noqa: E402

logging.disable(level=logging.WARNING)
warnings.filterwarnings("ignore")

# FEATURE_AGENT_CARD_BASE_URL = os.getenv("FEATURE_AGENT_CARD_BASE_URL", "http://localhost:8080")
# MODELING_AGENT_CARD_BASE_URL = os.getenv("MODELING_AGENT_CARD_BASE_URL", "http://localhost:8080")
RESEARCH_AGENT_CARD_BASE_URL = os.getenv("RESEARCH_AGENT_CARD_BASE_URL", "http://localhost:8080")

research_agent = RemoteA2aAgent(
    name="research_agent",
    agent_card=f"{RESEARCH_AGENT_CARD_BASE_URL}/.well-known/agent-card.json",
    description="Research Agent: surveys literature to extract insights \\
                 and inform feature engineering and modeling.",
)

# feature_agent = RemoteA2aAgent(
#     name="feature_agent",
#     agent_card=f"{FEATURE_AGENT_CARD_BASE_URL}/.well-known/agent-card.json",
#     description="Feature Engineering Agent: profiles datasets and transforms raw ECG signals \\
#     into ML-ready features.",
# )

# modeling_agent = RemoteA2aAgent(
#     name="modeling_agent",
#     agent_card=f"{MODELING_AGENT_CARD_BASE_URL}/.well-known/agent-card.json",
#     description="Modeling Agent: trains XGBoost and CatBoost classifiers on engineered \\
#     features and produces evaluation reports.",
# )

root_agent = SequentialAgent(
    name="root_agent",
    description="Sequential data-science pipeline: research → features → modeling.",
    sub_agents=[
        research_agent,
        # feature_agent,
        # modeling_agent,
    ],
)

EOF

cat << 'EOF' > src/main.py
import logging
import os
import pathlib
import warnings

import uvicorn

from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-agentic-workflow", agent_name="root_agent")
instrument_genai()

# Patch ADK's A2A→GenAI part converter BEFORE the ADK fast-api / a2a modules
# are imported. See src/core/genai_compat.py.
from core import genai_compat  # noqa: E402,F401

from google.adk.cli.fast_api import get_fast_api_app  # noqa: E402

logging.disable(level=logging.WARNING)
warnings.filterwarnings("ignore")

PORT = int(os.getenv("PORT", 8080))
SESSION_SERVICE_URI = "sqlite+aiosqlite:///./sessions.db"  # Standard async local session tracking

# Resolve agents_dir relative to this file so it works regardless of CWD
# or whether the build flattened src/ (Dockerfile vs buildpack layouts).
HERE = pathlib.Path(__file__).resolve().parent
AGENTS_DIR = HERE / "orchestrator"

# Extract the Web App UI
app = get_fast_api_app(
    agents_dir=str(AGENTS_DIR),
    session_service_uri=SESSION_SERVICE_URI,
    web=True,
    allow_origins=["*"],
)

if __name__ == "__main__":
    print(f"Booting Prototype UI Web Server on port {PORT} (agents_dir={AGENTS_DIR})...")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, factory=False)

EOF

cat << EOF > Dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONPATH=/app/src

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml uv.lock ./

RUN uv pip compile pyproject.toml -o requirements.txt && \\
    uv pip install --system -r requirements.txt

COPY src/core/ /app/src/core/
COPY src/observability/ /app/src/observability/
COPY src/sentinel/ /app/src/sentinel/
COPY src/orchestrator/ /app/src/orchestrator/
COPY src/main.py /app/src/main.py

EXPOSE 8080

CMD ["python", "src/main.py"]

EOF

gcloud run deploy sentinelds-orchestrator \
  --source=. \
  --region=europe-west4 \
  --project=sentinelds \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=sentinelds,GOOGLE_CLOUD_LOCATION=europe-west4,RESEARCH_AGENT_CARD_BASE_URL=https://sentinelds-a2a-research-463175257419.europe-west4.run.app" \
  --set-secrets="DYNATRACE_API_URL=dynatrace-api-url:latest,DYNATRACE_API_TOKEN=dynatrace-api-token:latest"

# cleanup runs via the EXIT trap above
