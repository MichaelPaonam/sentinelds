#!/bin/bash

mkdir -p src/orchestrator

touch src/orchestrator/__init__.py

cat << EOF >src/orchestrator/agent.py
import logging
import os
import warnings

from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-agentic-workflow", agent_name="root_agent")
instrument_genai()

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

cat << EOF > src/main.py
import logging
import os
import warnings

import uvicorn

from observability import init_tracing, instrument_genai

init_tracing(service_name="sentinelds-agentic-workflow", agent_name="root_agent")
instrument_genai()

from google.adk.cli.fast_api import get_fast_api_app  # noqa: E402

logging.disable(level=logging.WARNING)
warnings.filterwarnings("ignore")

PORT = int(os.getenv("PORT", 8080))
SESSION_SERVICE_URI = "sqlite+aiosqlite:///./sessions.db"  # Standard async local session tracking

# Extract the Web App UI
app = get_fast_api_app(
    agents_dir="./orchestrator",
    session_service_uri=SESSION_SERVICE_URI,
    web=True,
    allow_origins=["*"],
)

if __name__ == "__main__":
    print(f"Booting Prototype UI Web Server on port {PORT}...")
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
  --set-secrets="DYNATRACE_API_URL=dynatrace-api-url:latest,DYNATRACE_API_TOKEN=dynatrace-api-token:latest,GEMINI_API_KEY=gemini-api-key:latest"

rm -rf ./src/orchestrator
rm ./src/main.py
rm ./Dockerfile

