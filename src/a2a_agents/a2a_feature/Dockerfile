FROM python:3.12-slim

WORKDIR /app

COPY a2a_agents/a2a_feature/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY a2a_agents/a2a_feature/ /app/a2a_agents/a2a_feature/
COPY agents/sub_agents/feature_agent/ /app/agents/sub_agents/feature_agent/
COPY core/ /app/core/
COPY tools/ /app/tools/

ENV PORT=8080
ENV PYTHONPATH=/app

CMD ["uvicorn", "a2a_agents.a2a_feature.main:a2a_feature_agent", "--host", "0.0.0.0", "--port", "8080"]
