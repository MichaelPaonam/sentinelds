"""Sentinel audit sidecar — Cloud Run service.

This is a small FastAPI service whose entire job is to:

* Receive ``/audit`` POSTs from the four agent services (Orchestrator,
  Research, Feature, Modeling) whenever the in-process Sentinel gate
  produces a verdict or a local detector flips the compromise flag.
* Re-emit each audit payload as an OTel span on the ``sentinelds-sentinel``
  service entity. This makes Sentinel a distinct Smartscape entity that
  Davis AI can correlate against the four agents — they share resource
  attributes and call into the same Dynatrace tenant.
* Run a periodic heartbeat (see :mod:`sentinel_service.heartbeat`) that
  opens its own remote Dynatrace MCP session, queries active workspace
  problems, and emits one heartbeat span. This keeps Sentinel "live" in
  Smartscape even when no agent is currently calling the gate.

What this service is NOT:

* NOT a hot-path gate. The decorator ``@sentinel_gate`` in the four agents
  stays in-process and O(1). A sidecar outage cannot block any agent.
* NOT the source of policy. Verdicts are still decided in the agents'
  ``Sentinel.preflight()`` and inline detectors. The sidecar is downstream.

Why FastAPI: matches the framework already pinned in ``pyproject.toml``
and used by ``a2a_agents/`` services; small, well-known, easy to harden.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from observability import init_tracing

# init_tracing must run before anything else that opens spans.
init_tracing(service_name="sentinelds-sentinel", agent_name="sentinel")

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request, status  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from opentelemetry import trace  # noqa: E402

from sentinel_service.heartbeat import HeartbeatTask  # noqa: E402

logger = logging.getLogger("sentinel_service")
tracer = trace.get_tracer("sentinelds.sentinel")

INTERNAL_PORT = int(os.getenv("PORT", 8080))
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("SENTINEL_HEARTBEAT_INTERVAL", "60"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the heartbeat task on startup, stop it cleanly on shutdown.

    We deliberately tolerate the heartbeat being unable to start (missing
    DT_ENVIRONMENT / DT_PLATFORM_TOKEN, transient network) — the audit
    endpoint must keep working in that case.
    """
    heartbeat = HeartbeatTask(interval_seconds=HEARTBEAT_INTERVAL_SECONDS)
    await heartbeat.start()
    try:
        yield
    finally:
        await heartbeat.stop()


app = FastAPI(title="sentinelds-sentinel", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for Cloud Run."""
    return {"status": "ok", "service": "sentinelds-sentinel"}


@app.post("/audit")
async def audit(request: Request) -> JSONResponse:
    """Receive an audit payload from an agent and re-emit it as an OTel span.

    The payload shape is whatever ``core.sentinel_audit.emit_audit`` posts.
    We do not validate it strictly — the goal is to make every pre-flight
    verdict and every injection-candidate event visible on the Sentinel
    service entity, even when the agent and sidecar versions drift.

    The endpoint always returns 202 Accepted on a parseable body. We never
    return an error that would tempt the agent's ``emit_audit`` into
    retry/backoff logic — agents fan out fire-and-forget, and the gate has
    already decided by the time we see the payload.
    """
    accepted = JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"status": "accepted"},
    )
    try:
        payload: dict[str, Any] = await request.json()
    except Exception as exc:
        # An unparseable body still gets a span, just with the failure.
        logger.warning("audit endpoint received non-JSON body: %s", exc)
        with tracer.start_as_current_span("sentinel.audit.invalid") as span:
            span.set_attribute("audit.error", str(exc)[:200])
        return accepted

    event_type = str(payload.get("event.type") or "sentinel.audit")
    span_name = f"sentinel.audit:{event_type}"

    with tracer.start_as_current_span(span_name) as span:
        # Forward known fields as span attributes. Lists are joined for OTel
        # compatibility (attribute values must be primitives or homogeneous
        # arrays of primitives — easier to just stringify).
        for key, value in payload.items():
            attr_key = f"audit.{key}" if not key.startswith("audit.") else key
            try:
                if isinstance(value, (str, bool, int, float)) or value is None:
                    span.set_attribute(attr_key, value if value is not None else "")
                elif isinstance(value, (list, tuple)):
                    span.set_attribute(attr_key, ", ".join(str(v) for v in value))
                else:
                    span.set_attribute(attr_key, str(value)[:500])
            except Exception:
                # Never let a bad attribute break the audit handler.
                pass

    return accepted


if __name__ == "__main__":
    print(
        f"Starting Sentinel audit sidecar on port {INTERNAL_PORT} "
        f"(heartbeat interval={HEARTBEAT_INTERVAL_SECONDS}s)"
    )
    uvicorn.run(
        "sentinel_service.main:app",
        host="0.0.0.0",
        port=INTERNAL_PORT,
        factory=False,
    )
