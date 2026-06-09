"""Sentinel pre-flight gate.

The Sentinel Agent calls :func:`preflight` before each risky agent tool call
and treats the verdict as policy:

* ``HALT`` — refuse the tool call; quarantine the calling agent for the run.
* ``WARN`` — let the tool call through but tag its span so the dashboard
  highlights it.
* ``ALLOW`` — normal execution.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import logging
import sys
from dataclasses import dataclass, field  # noqa: F401 — field reserved for future use
from enum import Enum
from typing import Any

from mcp import ClientSession

from sentinel.dynatrace_mcp import list_open_problems, run_dql

logger = logging.getLogger("sentinel.preflight")

# Davis severity values that should trip a HALT on the workspace entity.
# Severity vocabulary: https://docs.dynatrace.com/docs/observe/problems
_HALT_SEVERITIES: frozenset[str] = frozenset(
    {
        "AVAILABILITY",
        "ERROR",
        "RESOURCE_CONTENTION",
        "CUSTOM_ALERT",
        "MONITORING_UNAVAILABLE",
    }
)


class Verdict(str, Enum):
    """Pre-flight outcome. ``str`` so it serialises cleanly into OTel attrs."""

    ALLOW = "ALLOW"
    WARN = "WARN"
    HALT = "HALT"


@dataclass
class SentinelSession:
    """Per-run security state. Replaces Sentinel's class-level globals.

    A single instance is created at the start of an agent run and read by
    every tool gate. Once `compromised` flips to True, all subsequent
    `sentinel_check` calls return HALT.
    """

    workspace_entity_id: str
    mcp_session: ClientSession | None = None
    agent_name: str = "Unknown Agent"
    compromised: bool = False
    compromise_reason: str = ""


def _sentinel_event_dql(workspace_entity_id: str) -> str:
    """DQL for sentinelds attack-detection events in the last 5 minutes."""
    return (
        "fetch events, from:now()-5m\n"
        '| filter event.kind == "BIZ_EVENT"\n'
        '   and event.type == "sentinelds.attack.detected"\n'
        f'| filter dt.entity.workspace == "{workspace_entity_id}"\n'
        "| fields severity, attack_id, agent\n"
        "| limit 10"
    )


def run_async_in_sync(coro: Any) -> Any:
    """Run an async coroutine synchronously, handling running event loops if any."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


class Sentinel:
    """The Sentinel Agent pre-flight security controller."""

    # NOTE: These class-level globals are process-wide shared state. In a multi-agent or
    # concurrent setting, one set_context() call can clobber another before preflight runs,
    # causing decisions to be evaluated against the wrong workspace/session. Safe for the
    # single-workspace, sequential hackathon demo; replace with contextvars or a per-dispatch
    # Context object before running concurrent agents in production.
    _session: ClientSession | None = None
    _workspace_entity_id: str = "WORKSPACE-1"
    _agent_name_context: str = "Unknown Agent"

    @classmethod
    def set_context(
        cls,
        session: ClientSession | None,
        workspace_entity_id: str,
        agent_name: str = "Unknown Agent",
    ) -> None:
        """Set the active workspace security context."""
        cls._session = session
        cls._workspace_entity_id = workspace_entity_id
        cls._agent_name_context = agent_name

    @classmethod
    def is_risky(cls, tool_name: str) -> bool:
        """Classify if a tool is risky (requires fail-closed) or advisory."""
        name = tool_name.lower()
        if "search" in name:
            return False
        # Per requirements: training, egress, file writes are risky
        if "train" in name:
            return True
        if "fetch" in name or "egress" in name or "web" in name:
            return True
        if "write" in name or "save" in name:
            return True
        if "execute" in name or "run" in name or "code" in name:
            return True
        return False

    @classmethod
    async def preflight(
        cls,
        session: ClientSession | None = None,
        workspace_entity_id: str | None = None,
        tool_name: str | None = None,
        agent_name: str | None = None,
    ) -> Verdict:
        """Compute ALLOW / WARN / HALT for the next tool call."""
        sess = session if session is not None else cls._session
        ws_id = workspace_entity_id if workspace_entity_id is not None else cls._workspace_entity_id
        tool = tool_name or "unknown_tool"
        agent = agent_name if agent_name is not None else cls._agent_name_context

        input_problems: list[dict[str, Any]] = []
        rule_fired = "DEFAULT_ALLOW"
        decision = Verdict.ALLOW

        mcp_reachable = sess is not None

        if sess is not None:
            try:
                # 1) Check active open problems
                problems = await list_open_problems(sess, ws_id)
                halt_problems = [p for p in problems if p.get("severity") in _HALT_SEVERITIES]

                if halt_problems:
                    decision = Verdict.HALT
                    rule_fired = "ACTIVE_PROBLEM_HALT"
                    input_problems = halt_problems
                else:
                    # 2) Check custom sentinelds events
                    rows = await run_dql(sess, _sentinel_event_dql(ws_id))
                    if rows:
                        input_problems = rows
                        if any(r.get("severity") == "high" for r in rows):
                            decision = Verdict.HALT
                            rule_fired = "CUSTOM_EVENT_HALT"
                        else:
                            decision = Verdict.WARN
                            rule_fired = "CUSTOM_EVENT_WARN"
                    else:
                        decision = Verdict.ALLOW
                        rule_fired = "DEFAULT_ALLOW"
            except Exception:
                # Log warning but treat as unreachable to activate fail-closed/open policy
                logger.warning(
                    "Error querying Dynatrace MCP during pre-flight",
                    exc_info=True,
                )
                mcp_reachable = False

        if not mcp_reachable:
            # Apply fail-closed / fail-open based on tool risk
            input_problems = [{"error": "MCP_UNREACHABLE"}]
            if cls.is_risky(tool):
                decision = Verdict.HALT
                rule_fired = "MCP_UNREACHABLE_FAIL_CLOSED"
            else:
                decision = Verdict.WARN
                rule_fired = "MCP_UNREACHABLE_FAIL_OPEN"

        # Write the structured decision log
        log_payload = {
            "workspace": ws_id,
            "agent": agent,
            "tool": tool,
            "input_problems": input_problems,
            "rule_fired": rule_fired,
            "decision": decision.value,
        }
        structured_log_line = json.dumps(log_payload)
        logger.info(structured_log_line)
        print(f"[Sentinel Preflight] {structured_log_line}", file=sys.stderr)

        return decision

    @classmethod
    async def notify(cls, sess: SentinelSession, event_type: str) -> Verdict:
        """Called when a local detector fires. Sets the compromise flag and
        optionally enriches with a one-shot MCP query for dashboard signal.

        Decision is **local** — we do not wait for Davis AI to confirm. The
        detector match is the source of truth for the gate. MCP is best-effort.
        """
        # Local detection is sufficient. Set the flag immediately.
        if event_type.startswith(("injection", "dataset.drift")):
            sess.compromised = True
            sess.compromise_reason = event_type

        # Best-effort MCP enrichment for the dashboard story.
        # Failures must not unset the flag or raise.
        try:
            if sess.mcp_session is not None:
                verdict = await cls.preflight(
                    session=sess.mcp_session,
                    workspace_entity_id=sess.workspace_entity_id,
                    tool_name=event_type,
                    agent_name=sess.agent_name,
                )
                # If MCP says HALT and we haven't already flagged, flag now.
                if verdict == Verdict.HALT and not sess.compromised:
                    sess.compromised = True
                    sess.compromise_reason = f"mcp:{event_type}"
        except Exception:
            logger.warning("Sentinel.notify MCP enrichment failed", exc_info=True)

        return Verdict.HALT if sess.compromised else Verdict.ALLOW


async def preflight(
    session: ClientSession, workspace_entity_id: str, tool_name: str = "legacy_tool"
) -> Verdict:
    """Legacy pre-flight function for backwards compatibility."""
    return await Sentinel.preflight(
        session=session, workspace_entity_id=workspace_entity_id, tool_name=tool_name
    )


def sentinel_guard(tool_name: str) -> Any:
    """Decorator to enforce Sentinel pre-flight checks before tool execution.

    .. deprecated::
        Use :func:`sentinel_gate` instead. ``sentinel_guard`` performs a
        blocking MCP round-trip on every call. ``sentinel_gate`` checks the
        local ``SentinelSession`` flag (O(1)) after the observer has fired
        ``Sentinel.notify``. This function is kept for backwards compatibility
        and will be removed in a future release.
    """

    def decorator(func: Any) -> Any:
        """Helper to apply the pre-flight gate to the decorated function."""
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                """Asynchronous wrapper that runs Sentinel pre-flight before execution."""
                verdict = await Sentinel.preflight(tool_name=tool_name)
                if verdict == Verdict.HALT:
                    raise PermissionError(
                        f"Sentinel halted execution of tool '{tool_name}' "
                        f"due to active security risk."
                    )
                return await func(*args, **kwargs)

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                """Synchronous wrapper that runs Sentinel pre-flight before execution."""
                verdict = run_async_in_sync(Sentinel.preflight(tool_name=tool_name))
                if verdict == Verdict.HALT:
                    raise PermissionError(
                        f"Sentinel halted execution of tool '{tool_name}' "
                        f"due to active security risk."
                    )
                return func(*args, **kwargs)

            return sync_wrapper

    return decorator


def sentinel_check(sess: SentinelSession) -> Verdict:
    """Local flag check. No MCP. O(1)."""
    return Verdict.HALT if sess.compromised else Verdict.ALLOW


def sentinel_gate(tool_name: str) -> Any:
    """Decorator: halt the tool call if the active SentinelSession is compromised.

    Reads the active session via ``sentinel.session.get_sentinel_session()``. If no
    session is set (e.g. unit tests not using contextvars), the gate is a no-op
    — call proceeds. Production callers must always ``set_sentinel_session(...)``
    at the top of a run.
    """
    from sentinel.session import get_sentinel_session  # local import: avoids circular

    def decorator(func: Any) -> Any:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                sess = get_sentinel_session()
                if sess is not None and sentinel_check(sess) == Verdict.HALT:
                    raise PermissionError(
                        f"Sentinel halted '{tool_name}' — workspace compromised "
                        f"({sess.compromise_reason})."
                    )
                return await func(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            sess = get_sentinel_session()
            if sess is not None and sentinel_check(sess) == Verdict.HALT:
                raise PermissionError(
                    f"Sentinel halted '{tool_name}' — workspace compromised "
                    f"({sess.compromise_reason})."
                )
            return func(*args, **kwargs)

        return sync_wrapper

    return decorator
