"""Sentinel pre-flight gate (v0).

The Sentinel Agent calls :func:`preflight` before each risky agent tool call
and treats the verdict as policy:

* ``HALT`` — refuse the tool call; quarantine the calling agent for the run.
* ``WARN`` — let the tool call through but tag its span so the dashboard
  highlights it.
* ``ALLOW`` — normal execution.

The v0 ruleset is deliberately tiny — full policy work belongs in a later
issue (see ``PLAN.md`` section 6). The two rules below are enough to demo the
ALLOW/WARN/HALT mechanism end-to-end against the two staged attacks (A1 +
A2):

1. Any **OPEN Davis problem** with a severity that indicates a real
   incident on the workspace entity → ``HALT``. Davis's own anomaly
   detection is the primary signal.
2. Any **sentinelds custom event** emitted in the last 5 minutes →
   ``HALT`` if its severity is ``high``, ``WARN`` otherwise. These are the
   explicit attack-detection events the A1/A2 instrumentation emits when it
   matches a payload pattern (see ``docs/agents-exploit-scenarios.md``).

Otherwise → ``ALLOW``.
"""

from __future__ import annotations

from enum import Enum

from mcp import ClientSession

from src.sentinel.dynatrace_mcp import list_open_problems, run_dql

# Davis severity values that should trip a HALT on the workspace entity.
# Severity vocabulary: https://docs.dynatrace.com/docs/observe/problems
# (Status filter "ACTIVE" — see dynatrace_mcp.list_open_problems.)
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


def _sentinel_event_dql(workspace_entity_id: str) -> str:
    """DQL for sentinelds attack-detection events in the last 5 minutes.

    The timeframe is intentionally short — this query runs on every risky
    tool call. A 5-minute window is wide enough to catch a multi-step attack
    chain but tight enough to keep Grail GB-scanned within the budget the
    MCP client sets via ``DT_GRAIL_QUERY_BUDGET_GB``.
    """
    return (
        "fetch events, from:now()-5m\n"
        '| filter event.kind == "BIZ_EVENT"\n'
        '   and event.type == "sentinelds.attack.detected"\n'
        f'| filter dt.entity.workspace == "{workspace_entity_id}"\n'
        "| fields severity, attack_id, agent\n"
        "| limit 10"
    )


async def preflight(session: ClientSession, workspace_entity_id: str) -> Verdict:
    """Compute ALLOW / WARN / HALT for the next risky tool call.

    The Sentinel Agent owns the ``ClientSession`` (one per workspace, opened
    at startup via :func:`src.sentinel.dynatrace_mcp.dynatrace_session`) and
    passes it in for every call.
    """
    problems = await list_open_problems(session, workspace_entity_id)
    if any(p.get("severity") in _HALT_SEVERITIES for p in problems):
        return Verdict.HALT

    rows = await run_dql(session, _sentinel_event_dql(workspace_entity_id))
    if any(r.get("severity") == "high" for r in rows):
        return Verdict.HALT
    if rows:
        return Verdict.WARN
    return Verdict.ALLOW
