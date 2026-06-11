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
# (Using --frozen ensures it honors your exact local uv.lock)
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system -r requirements.txt

# 4. Explicitly map your internal package roots (Clean & Isolated)
# The sidecar reuses core (sentinel_audit isn't strictly needed here, but
# core also holds config used by observability), observability (init_tracing),
# and sentinel (the heartbeat reuses dynatrace_mcp.dynatrace_session).
COPY src/core/ /app/src/core/
COPY src/observability/ /app/src/observability/
COPY src/sentinel/ /app/src/sentinel/
COPY src/sentinel_service/ /app/src/sentinel_service/

EXPOSE 8080

# 5. Launch using your structural layout path
CMD ["python", "src/sentinel_service/main.py"]
