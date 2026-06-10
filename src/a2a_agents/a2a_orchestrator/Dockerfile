FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml uv.lock ./

RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt

COPY src/core/        /app/src/core/
COPY src/observability/ /app/src/observability/
COPY src/sentinel/    /app/src/sentinel/
COPY src/tools/       /app/src/tools/
COPY src/a2a_agents/a2a_orchestrator/ /app/src/a2a_agents/a2a_orchestrator/

EXPOSE 8080

CMD ["python", "src/a2a_agents/a2a_orchestrator/main.py"]
