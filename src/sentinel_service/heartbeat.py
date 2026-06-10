"""Periodic heartbeat task for the Sentinel sidecar.

Once a minute (by default) the sidecar opens a remote Dynatrace MCP session,
queries active Davis problems on the workspace entity, and emits a single
OTel span. This produces three things at once:

1. **Smartscape liveness.** Sentinel keeps showing up as an active service
   even when no agent is calling ``/audit`` — Davis correlates problems
   against entities that emit telemetry.
2. **A signal of MCP reachability.** If the heartbeat can't open an MCP
   session, that's worth knowing on the same dashboard the agents log to.
3. **A trivial Sentinel→Dynatrace dependency.** The dependency map shows
   the sidecar calling out to ``mcp-gateway`` — exactly the picture the
   hackathon narrative needs.

The heartbeat is designed to fail soft: missing env vars, MCP outages, and
parse errors all become a single span attribute and a warning log line.
The audit endpoint keeps working regardless.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from opentelemetry import trace

logger = logging.getLogger("sentinel_service.heartbeat")
tracer = trace.get_tracer("sentinelds.sentinel.heartbeat")


class HeartbeatTask:
    """A long-running background task that pings Dynatrace MCP periodically."""

    def __init__(self, *, interval_seconds: int = 60) -> None:
        self._interval = max(10, interval_seconds)
        self._task: Optional[asyncio.Task[None]] = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="sentinel-heartbeat")
        logger.info("Sentinel heartbeat started (interval=%ss)", self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
        finally:
            self._task = None
            logger.info("Sentinel heartbeat stopped")

    async def _run(self) -> None:
        # Emit one heartbeat right at startup so Sentinel appears in
        # Smartscape immediately, then settle into the cadence.
        await self._tick()
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
                # _stop was set during the wait → exit loop.
                return
            except asyncio.TimeoutError:
                await self._tick()

    async def _tick(self) -> None:
        """Open one MCP session, query active problems, emit one span."""
        workspace_id = os.environ.get("DYNATRACE_WORKSPACE_ENTITY_ID", "WORKSPACE-1")

        with tracer.start_as_current_span("sentinel.heartbeat") as span:
            span.set_attribute("workspace.entity_id", workspace_id)
            try:
                # Lazy imports keep the heartbeat from blocking startup if the
                # MCP client / Dynatrace config has issues — the audit endpoint
                # still serves.
                from sentinel.dynatrace_mcp import (  # noqa: PLC0415
                    DynatraceMCPConfig,
                    dynatrace_session,
                    list_open_problems,
                )

                cfg = DynatraceMCPConfig.from_env()
                async with dynatrace_session(cfg) as session:
                    problems = await list_open_problems(session, workspace_id)
                span.set_attribute("mcp.reachable", True)
                span.set_attribute("dynatrace.problems.active", len(problems))
            except KeyError as exc:
                # DT_ENVIRONMENT or DT_PLATFORM_TOKEN missing — common in dev.
                span.set_attribute("mcp.reachable", False)
                span.set_attribute("mcp.error", f"config: {exc}")
                logger.warning("Heartbeat skipped — Dynatrace MCP not configured: %s", exc)
            except Exception as exc:
                span.set_attribute("mcp.reachable", False)
                span.set_attribute("mcp.error", str(exc)[:200])
                logger.warning("Heartbeat MCP call failed: %s", exc)
