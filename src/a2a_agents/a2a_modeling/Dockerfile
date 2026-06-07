FROM python:3.12-slim

WORKDIR /app

COPY a2a_agents/a2a_modeling/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY a2a_agents/a2a_modeling/ /app/a2a_agents/a2a_modeling/
COPY agents/sub_agents/modeling_agent/ /app/agents/sub_agents/modeling_agent/
COPY core/ /app/core/
COPY tools/ /app/tools/

ENV PORT=8080
ENV PYTHONPATH=/app

CMD ["uvicorn", "a2a_agents.a2a_modeling.main:a2a_modeling_agent", "--host", "0.0.0.0", "--port", "8080"]
