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
* Expose ``GET /dashboard-feed`` that the dashboard polls every few
  seconds. It returns the last N audit decisions from an in-memory ring
  buffer plus live active-problems fetched from Dynatrace MCP.

What this service is NOT:

* NOT a hot-path gate. The decorator ``@sentinel_gate`` in the four agents
  stays in-process and O(1). A sidecar outage cannot block any agent.
* NOT the source of policy. Verdicts are still decided in the agents'
  ``Sentinel.preflight()`` and inline detectors. The sidecar is downstream.

Why FastAPI: matches the framework already pinned in ``pyproject.toml``
and used by ``a2a_agents/`` services; small, well-known, easy to harden.
"""

from __future__ import annotations

import collections
import datetime
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from observability import init_tracing

# init_tracing must run before anything else that opens spans.
init_tracing(service_name="sentinelds-sentinel", agent_name="sentinel")

import uvicorn  # noqa: E402
from fastapi import FastAPI, Request, status  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from opentelemetry import trace  # noqa: E402

from sentinel_service.heartbeat import HeartbeatTask  # noqa: E402

logger = logging.getLogger("sentinel_service")
tracer = trace.get_tracer("sentinelds.sentinel")

INTERNAL_PORT = int(os.getenv("PORT", 8080))
HEARTBEAT_INTERVAL_SECONDS = int(os.getenv("SENTINEL_HEARTBEAT_INTERVAL", "60"))
DASHBOARD_FEED_MAX_DECISIONS = 20

# In-memory ring buffer — last N audit decisions for /dashboard-feed.
# deque is thread-safe for append/popleft in CPython; asyncio is single-
# threaded so no additional lock is needed.
_recent_decisions: collections.deque[dict[str, Any]] = collections.deque(
    maxlen=DASHBOARD_FEED_MAX_DECISIONS
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the heartbeat task on startup, stop it cleanly on shutdown."""
    heartbeat = HeartbeatTask(interval_seconds=HEARTBEAT_INTERVAL_SECONDS)
    await heartbeat.start()
    try:
        yield
    finally:
        await heartbeat.stop()


app = FastAPI(title="sentinelds-sentinel", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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
        logger.warning("audit endpoint received non-JSON body: %s", exc)
        with tracer.start_as_current_span("sentinel.audit.invalid") as span:
            span.set_attribute("audit.error", str(exc)[:200])
        return accepted

    event_type = str(payload.get("event.type") or "sentinel.audit")
    span_name = f"sentinel.audit:{event_type}"

    with tracer.start_as_current_span(span_name) as span:
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
                pass

    # Buffer the event for /dashboard-feed.
    _buffer_decision(event_type, payload)

    return accepted


def _buffer_decision(event_type: str, payload: dict[str, Any]) -> None:
    """Normalise an audit payload into a dashboard decision row and buffer it."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")

    if event_type == "sentinel.preflight":
        agent_raw = str(payload.get("agent") or "Unknown")
        tool = str(payload.get("tool") or "unknown_tool")
        verdict = str(payload.get("decision") or "ALLOW").upper()
        rule = str(payload.get("rule_fired") or "Pre-flight Check")
        problems = payload.get("input_problems") or []
        policy = rule if rule != "MCP_UNREACHABLE_FAIL_OPEN" else "MCP Unreachable (Fail-Open)"
    elif event_type == "sentinelds.injection.candidate":
        agent_raw = str(payload.get("agent_name") or payload.get("agent") or "Research Agent")
        tool = str(payload.get("tool") or f"web_fetch('{payload.get('source_url', 'unknown')}')")
        verdict = "HALT"
        policy = "Injection Candidate Detected"
        problems = []
    else:
        return  # Ignore unknown event types

    _recent_decisions.appendleft({
        "time": now,
        "agent": _normalise_agent_name(agent_raw),
        "tool": tool,
        "policy": policy,
        "verdict": verdict,
        "has_problems": bool(problems),
    })


def _normalise_agent_name(raw: str) -> str:
    """Map internal agent identifiers to dashboard display names."""
    lower = raw.lower()
    if "research" in lower:
        return "Research Agent"
    if "feature" in lower:
        return "Feature Eng. Agent"
    if "model" in lower:
        return "Modelling Agent"
    if "orchestrat" in lower:
        return "Orchestrator"
    return raw


@app.get("/dashboard-feed")
async def dashboard_feed() -> JSONResponse:
    """Return live dashboard data for the monitoring UI.

    Combines:
    - Last N audit decisions from the in-memory ring buffer (fast, no I/O).
    - Active Davis problems fetched live from Dynatrace MCP (best-effort;
      returns empty list if MCP is unreachable so the dashboard still loads).

    Response shape::

        {
          "decisions": [
            {"time": "HH:MM:SS", "agent": "...", "tool": "...",
             "policy": "...", "verdict": "ALLOW|WARN|HALT"},
            ...
          ],
          "problems": [
            {"id": "...", "title": "...", "desc": "...",
             "severity": "severe|warning", "severityText": "...",
             "timeOffset": "..."},
            ...
          ],
          "agent_statuses": {
            "research": "healthy|compromised|quarantined",
            "feature":  "healthy|compromised|quarantined",
            "modeling": "healthy|compromised|quarantined"
          }
        }
    """
    decisions = list(_recent_decisions)
    problems = await _fetch_live_problems()
    agent_statuses = _derive_agent_statuses(decisions, problems)

    return JSONResponse(content={
        "decisions": decisions,
        "problems": problems,
        "agent_statuses": agent_statuses,
    })


async def _fetch_live_problems() -> list[dict[str, Any]]:
    """Fetch active Davis problems from Dynatrace MCP. Returns [] on any error."""
    workspace_id = os.environ.get("DYNATRACE_WORKSPACE_ENTITY_ID", "WORKSPACE-1")
    try:
        from sentinel.dynatrace_mcp import (  # noqa: PLC0415
            DynatraceMCPConfig,
            dynatrace_session,
            list_open_problems,
        )
        cfg = DynatraceMCPConfig.from_env()
        async with dynatrace_session(cfg) as session:
            raw = await list_open_problems(session, workspace_id)

        problems = []
        for p in raw:
            title = str(p.get("title") or p.get("event.name") or "Unknown Problem")
            desc = str(p.get("event.description") or p.get("description") or "")
            severity_raw = str(p.get("severity") or "warning").lower()
            severity = "severe" if severity_raw in ("critical", "error", "severe") else "warning"
            problems.append({
                "id": str(p.get("id") or p.get("problem_id") or "P-LIVE"),
                "title": title,
                "desc": desc,
                "severity": severity,
                "severityText": "Critical" if severity == "severe" else "Warning",
                "timeOffset": "Active",
            })
        return problems
    except Exception as exc:
        logger.debug("dashboard-feed: MCP problem fetch failed: %s", exc)
        return []


def _derive_agent_statuses(
    decisions: list[dict[str, Any]],
    problems: list[dict[str, Any]],
) -> dict[str, str]:
    """Infer per-agent health from recent decisions and active problems."""
    statuses = {"research": "healthy", "feature": "healthy", "modeling": "healthy"}

    # Most-recent decision per agent wins; HALT > WARN > ALLOW.
    rank = {"HALT": 2, "WARN": 1, "ALLOW": 0}
    seen: dict[str, int] = {}

    for d in reversed(decisions):  # oldest first so latest overwrites
        agent = d.get("agent", "")
        verdict = d.get("verdict", "ALLOW")
        key = None
        if "Research" in agent:
            key = "research"
        elif "Feature" in agent:
            key = "feature"
        elif "Modell" in agent:
            key = "modeling"
        if key and rank.get(verdict, 0) >= seen.get(key, -1):
            seen[key] = rank.get(verdict, 0)
            if verdict == "HALT":
                statuses[key] = "quarantined"
            elif verdict == "WARN":
                statuses[key] = "compromised"
            else:
                statuses[key] = "healthy"

    return statuses


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
