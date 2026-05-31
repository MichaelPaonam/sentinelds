"""Dynatrace MCP client for the Sentinel Agent.

This module is the spike output for issue #23: it spawns the upstream
Dynatrace MCP server (`@dynatrace-oss/dynatrace-mcp-server`) over stdio and
exposes the two tool calls the Sentinel pre-flight gate needs —
`list_problems` and `execute_dql` — as plain async Python functions that
return ``list[dict]``.

Why this shape (full reasoning in ``docs/dynatrace-mcp-options.md``):

* the upstream MCP server has those exact tools as first-class names, so the
  Sentinel Agent does not need to translate;
* stdio co-locates the Node subprocess with the Python process — no inbound
  port, sub-second pre-flight round-trips;
* auth is via env-loaded ``DT_PLATFORM_TOKEN`` (no hardcoded credentials);
* the Python ``mcp`` PyPI client SDK is already pinned in
  ``pyproject.toml``.

Response shapes are documented in ``docs/dynatrace-mcp-notes.md``. The brief
version: every tool call returns a ``CallToolResult`` whose ``.content`` is a
single ``TextContent`` block whose ``.text`` is a JSON string. ``list_problems``
returns ``{"problems": [...]}``; ``execute_dql`` returns
``{"records": [...], "metadata": {...}}``. We pull the ``problems`` /
``records`` array out and return it.

Fallback ladder (if the live spike shows the local server is broken or its
schema has shifted) is in ``docs/dynatrace-mcp-options.md`` — swap transport
to the Remote MCP Server, then to direct REST, then to a fixture replay for
the demo video. All four tiers preserve the function signatures below.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent


@dataclass(frozen=True)
class DynatraceMCPConfig:
    """Configuration for spawning the Dynatrace MCP server subprocess.

    Construct via :meth:`from_env` so the platform token is never written into
    a literal — the upstream server reads ``DT_PLATFORM_TOKEN`` itself, we
    only forward what the Python process already has in its environment.
    """

    environment: str
    """Dynatrace tenant URL, e.g. ``https://abc12345.apps.dynatrace.com``."""

    platform_token: str
    """Platform Token. Forwarded to the subprocess; never logged."""

    server_version: str = "1.8.6"
    """Pinned npm version of ``@dynatrace-oss/dynatrace-mcp-server``.

    The repo is in maintenance mode (upstream issue #496); pin a known-good
    1.8.x release rather than chasing ``@latest``.
    """

    disable_telemetry: bool = True
    """Opt out of the upstream server's outbound telemetry."""

    grail_budget_gb: int = 50
    """GB-scanned cap for DQL queries. Default upstream is 1000; we keep it
    tight because the Sentinel pre-flight runs on every risky tool call."""

    @classmethod
    def from_env(cls) -> "DynatraceMCPConfig":
        """Read ``DT_ENVIRONMENT`` and ``DT_PLATFORM_TOKEN`` from os.environ.

        Both are required. Raises :class:`KeyError` with a clear message if
        either is unset — the Sentinel Agent must fail fast in that case so
        the demo never silently disables the gate.
        """
        try:
            environment = os.environ["DT_ENVIRONMENT"]
            platform_token = os.environ["DT_PLATFORM_TOKEN"]
        except KeyError as missing:
            raise KeyError(
                f"Required Dynatrace MCP env var {missing} is not set. "
                "See docs/dynatrace-mcp-options.md and .env.example."
            ) from missing
        return cls(environment=environment, platform_token=platform_token)


def _server_params(cfg: DynatraceMCPConfig) -> StdioServerParameters:
    """Build the stdio server params for ``mcp.client.stdio.stdio_client``.

    The subprocess inherits *only* the four Dynatrace env vars below, so we
    don't accidentally leak unrelated credentials from the parent process.
    """
    return StdioServerParameters(
        command="npx",
        args=["-y", f"@dynatrace-oss/dynatrace-mcp-server@{cfg.server_version}"],
        env={
            "DT_ENVIRONMENT": cfg.environment,
            "DT_PLATFORM_TOKEN": cfg.platform_token,
            "DT_MCP_DISABLE_TELEMETRY": "true" if cfg.disable_telemetry else "false",
            "DT_GRAIL_QUERY_BUDGET_GB": str(cfg.grail_budget_gb),
        },
    )


@asynccontextmanager
async def dynatrace_session(
    cfg: DynatraceMCPConfig,
) -> AsyncIterator[ClientSession]:
    """Open a long-lived MCP session against the Dynatrace MCP server.

    The Sentinel Agent should open this once at startup and reuse the yielded
    session for every pre-flight call — spawning ``npx`` per call would dwarf
    the actual tool-call latency.
    """
    async with stdio_client(_server_params(cfg)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _parse_text_content(result: CallToolResult) -> Any:
    """Extract the JSON payload from a Dynatrace MCP tool result.

    The Dynatrace server returns a single ``TextContent`` whose ``.text`` is a
    JSON string. We refuse to silently drop other shapes: if the server ever
    starts returning multiple content blocks or non-text content (e.g. an
    ``ImageContent`` chart), we want to know rather than parse the first
    block and ignore the rest.
    """
    if result.isError:
        # The server populates content with the error message in this case.
        message = ""
        for block in result.content:
            if isinstance(block, TextContent):
                message = block.text
                break
        raise RuntimeError(f"Dynatrace MCP tool call returned isError: {message!r}")
    if len(result.content) != 1:
        raise ValueError(
            f"expected exactly one content block, got {len(result.content)}"
        )
    block = result.content[0]
    if not isinstance(block, TextContent):
        raise TypeError(f"expected TextContent, got {type(block).__name__}")
    return json.loads(block.text)


# --- Acceptance criterion 1: list_problems ----------------------------------


async def list_open_problems(
    session: ClientSession, entity_id: str
) -> list[dict[str, Any]]:
    """Return OPEN Davis problems scoped to the workspace entity.

    See the response-shape sample in ``docs/dynatrace-mcp-notes.md``. Each
    element is a dict with at least ``problemId``, ``title``, ``severity``,
    ``status``, ``startTime``, and ``affectedEntities``. Empty list when the
    workspace is healthy — the Sentinel ALLOW path.
    """
    result = await session.call_tool(
        "list_problems",
        {"entity": entity_id, "status": "OPEN"},
    )
    payload = _parse_text_content(result)
    if isinstance(payload, list):
        # Some Dynatrace MCP versions return the array at the top level.
        return payload
    return payload.get("problems", [])


# --- Acceptance criterion 2: execute_dql ------------------------------------


async def run_dql(session: ClientSession, query: str) -> list[dict[str, Any]]:
    """Run a DQL query against Grail and return the parsed records.

    Always pass a tight ``from:`` timeframe in the query — the pre-flight
    runs on every risky tool call and Grail charges by GB scanned. The
    metadata block (``scannedBytes`` etc.) is dropped; expose it in a
    follow-up issue if Sentinel ever needs to throttle on budget.
    """
    result = await session.call_tool("execute_dql", {"query": query})
    payload = _parse_text_content(result)
    if isinstance(payload, list):
        return payload
    return payload.get("records", [])
