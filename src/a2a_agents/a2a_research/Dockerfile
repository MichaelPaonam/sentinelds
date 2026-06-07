FROM python:3.12-slim

WORKDIR /app

COPY a2a_agents/a2a_research/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY a2a_agents/a2a_research/ /app/a2a_agents/a2a_research/
COPY agents/sub_agents/research_agent/ /app/agents/sub_agents/research_agent/
COPY core/ /app/core/
COPY observability/ /app/observability/
COPY tools/ /app/tools/

ENV PORT=8080
ENV PYTHONPATH=/app

CMD ["uvicorn", "a2a_agents.a2a_research.main:a2a_research_agent", "--host", "0.0.0.0", "--port", "8080"]
