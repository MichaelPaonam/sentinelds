"""Best-effort fan-out client to the Sentinel audit sidecar.

The Sentinel sidecar is a separate Cloud Run service (``sentinelds-sentinel``)
that receives audit pings whenever the in-process gate produces a verdict or a
local detector flips the compromise flag. Centralising those events on the
sidecar gives Sentinel its own Smartscape entity and a single Davis-facing
channel for pre-flight telemetry — without coupling the agents' hot path to
the sidecar's availability.

This module exists so the gate stays correct even when the sidecar is down,
slow, mis-configured, or simply not deployed yet:

* If ``SENTINEL_AUDIT_URL`` is unset, :func:`emit_audit` is a no-op. This is
  the default. The four agents keep their current behaviour.
* If the URL is set but the POST fails (timeout, 5xx, DNS, connection reset),
  the failure is logged at WARNING and swallowed. The gate must never raise
  because of telemetry.
* Timeout is short on purpose (2s). The gate is on the request path; we will
  not wait long enough for users to notice.

The payload shape mirrors the structured log already produced inside
``Sentinel.preflight()`` and ``injection_detector.emit_injection_candidate``,
so the sidecar can wrap it in an OTel span verbatim.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("sentinel.audit")

# Read once at import. Setting ``SENTINEL_AUDIT_URL`` later via os.environ has
# no effect on this module — the four agents pick the URL up at startup, which
# matches how Cloud Run injects env vars into the container.
_AUDIT_URL = os.environ.get("SENTINEL_AUDIT_URL", "").strip() or None

# Short timeout: the sidecar is on the request path through the gate.
# A slow sidecar must not slow down agent tool calls.
_AUDIT_TIMEOUT_SECONDS = 2.0


def is_enabled() -> bool:
    """True iff ``SENTINEL_AUDIT_URL`` was set when this module was imported."""
    return _AUDIT_URL is not None


async def emit_audit(payload: dict[str, Any]) -> None:
    """Fire-and-forget POST of an audit payload to the Sentinel sidecar.

    Never raises. Failure modes are logged and swallowed so a sidecar outage
    cannot break the in-process gate.

    The function is async to match the call sites in ``preflight.py`` and
    ``injection_detector.py``, both of which already run inside an event loop.
    """
    if _AUDIT_URL is None:
        return

    try:
        async with httpx.AsyncClient(timeout=_AUDIT_TIMEOUT_SECONDS) as client:
            response = await client.post(_AUDIT_URL, json=payload)
        if not response.is_success:
            logger.warning(
                "Sentinel audit sidecar returned %s for %s: %s",
                response.status_code,
                payload.get("tool") or payload.get("event.type") or "<unknown>",
                response.text[:200],
            )
    except Exception as exc:
        # Anything: timeout, DNS, connection reset, JSON serialisation. Swallow.
        logger.warning("Sentinel audit sidecar fan-out failed: %s", exc)


def emit_audit_sync(payload: dict[str, Any]) -> None:
    """Sync wrapper around :func:`emit_audit` for callers outside an event loop.

    ``injection_detector.emit_injection_candidate`` is sync and reachable from
    the sync ``fetch_url`` tool. We bridge into asyncio here so the sync code
    paths can fan out to the sidecar without restructuring. If a loop is
    already running on this thread (rare for these call sites), we fall back
    to a fire-and-forget task on it so we still don't block.
    """
    if _AUDIT_URL is None:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop on this thread — run one, finish before returning.
        try:
            asyncio.run(emit_audit(payload))
        except Exception as exc:
            logger.warning("Sentinel audit sidecar fan-out failed (sync): %s", exc)
        return

    # Inside a running loop: schedule and don't wait. We deliberately do not
    # await here — the caller is sync and we must not block it.
    try:
        loop.create_task(emit_audit(payload))
    except Exception as exc:
        logger.warning("Sentinel audit sidecar task scheduling failed: %s", exc)
