FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# 1. Install uv binary directly from its distribution image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 2. Copy BOTH dependency configuration files to cache this layer perfectly
COPY pyproject.toml uv.lock ./

# 3. Compile and freeze dependencies to the system space
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt

# 4. Explicitly map your internal package roots (Clean & Isolated)
COPY src/core/ /app/src/core/
COPY src/tools/ /app/src/tools/
COPY src/observability/ /app/src/observability/
COPY src/agents/sub_agents/feature_agent/ /app/src/agents/sub_agents/feature_agent/
COPY src/a2a_agents/a2a_feature/ /app/src/a2a_agents/a2a_feature/

EXPOSE 8080

# 5. Launch using your structural layout path
CMD ["python", "src/a2a_agents/a2a_feature/main.py"]
