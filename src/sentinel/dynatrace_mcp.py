"""Dynatrace MCP client for the Sentinel Agent.

Connects to the **Dynatrace Remote MCP Server** (Streamable HTTP transport)
at ``{DT_ENVIRONMENT}/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp``,
authenticated with a Platform Token (``DT_PLATFORM_TOKEN``).

The Sentinel pre-flight gate uses two tools — ``query-problems`` and
``execute-dql`` — surfaced as plain async Python functions returning
``list[dict]``.

Why remote (full reasoning in ``docs/dynatrace-mcp-options.md`` and
``docs/migration_plan.md``):

* the previous local server (``@dynatrace-oss/dynatrace-mcp-server``) is in
  maintenance mode upstream; Dynatrace's active path is the remote server.
* no Node subprocess in our process tree — cleaner Cloud Run images, no
  ``npx`` cold start.
* same logical operations (problems query, DQL execution), so the Sentinel
  pre-flight code in ``preflight.py`` is unchanged.
* auth via env-loaded ``DT_PLATFORM_TOKEN`` (no hardcoded credentials).

**Shape change from local server (logged here per migration_plan.md §3.2.5):**
The remote server uses kebab-case tool names and different argument keys:

  * ``list_problems`` → ``query-problems``; arg ``entity`` dropped, arg
    ``status`` kept; arg ``dqlStatement`` → ``dqlQueryString`` for ``execute-dql``.
  * Both tools return **3 TextContent blocks** (metadata, types, records)
    rather than the local server's single JSON envelope. The records block
    has prefix ``"Query result records:\\n"`` followed by a JSON array.

``list_open_problems`` and ``run_dql`` preserve their public signatures so
``preflight.py`` and all call sites are unchanged.

Fallback ladder (if the remote server is unreachable during the demo):
direct REST → fixture replay. Both preserve the function signatures below.
See ``docs/dynatrace-mcp-options.md`` "Fallback ladder".
"""

from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import CallToolResult, TextContent


@dataclass(frozen=True)
class DynatraceMCPConfig:
    """Configuration for the Dynatrace **Remote** MCP Server.

    Connection is HTTP (Streamable HTTP transport) to the Dynatrace-hosted
    MCP gateway at ``{environment}/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp``.
    Auth is a bearer Platform Token. No local Node subprocess is spawned.

    Construct via :meth:`from_env`. The platform token is forwarded as a
    Bearer header on every MCP request and is never logged.
    """

    environment: str
    """Dynatrace tenant URL, e.g. ``https://abc12345.apps.dynatrace.com``."""

    platform_token: str
    """Platform Token. Sent as ``Authorization: Bearer <token>``; never logged.

    Required scopes: ``mcp-gateway:servers:invoke``, ``mcp-gateway:servers:read``,
    plus the relevant ``storage:*:read`` scopes for the DQL queries the
    Sentinel pre-flight runs. See ``docs/dynatrace-mcp-options.md``.
    """

    @property
    def remote_url(self) -> str:
        """Full Streamable-HTTP URL of the remote MCP gateway."""
        return (
            f"{self.environment.rstrip('/')}"
            "/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp"
        )

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


@asynccontextmanager
async def dynatrace_session(
    cfg: DynatraceMCPConfig,
) -> AsyncIterator[ClientSession]:
    """Open a long-lived MCP session against the Dynatrace **Remote** MCP server.

    The Sentinel Agent should open this once at startup and reuse the yielded
    session for every pre-flight call — establishing a fresh HTTP connection
    per call would dwarf the actual tool-call latency.

    Auth is via ``Authorization: Bearer <DT_PLATFORM_TOKEN>``. The token is
    forwarded on every request by the Streamable HTTP transport.
    """
    headers = {"Authorization": f"Bearer {cfg.platform_token}"}
    async with streamablehttp_client(
        cfg.remote_url,
        headers=headers,
        timeout=30,
        sse_read_timeout=120,
    ) as (
        read,
        write,
        _close,
    ):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def _parse_text_content(result: CallToolResult) -> Any:
    """Extract the JSON payload from a Dynatrace Remote MCP tool result.

    **Remote server shape (confirmed during migration spike, 2026-06-09):**
    Both ``query-problems`` and ``execute-dql`` return **3 TextContent blocks**:

    * block[0]: ``"Query metadata:\\n{...}"``
    * block[1]: ``"Grail types for the records in the query result:\\n[...]"``
    * block[2]: ``"Query result records:\\n[...]"`` — the payload we parse

    We extract block[2], strip the ``"Query result records:\\n"`` prefix, and
    ``json.loads`` the remainder. Empty results return ``"Query result
    records:\\n[ ]"`` — we map that to ``None`` so callers return ``[]``.

    For backwards-compatibility with tests and fixtures that produce a single
    TextContent JSON block (the local server shape), we fall back to parsing
    that single block when only one is present.
    """
    if result.isError:
        message = ""
        for block in result.content:
            if isinstance(block, TextContent):
                message = block.text
                break
        raise RuntimeError(f"Dynatrace MCP tool call returned isError: {message!r}")

    # Remote server: 3 blocks — records are in block[2]
    if len(result.content) == 3:
        records_block = result.content[2]
        if not isinstance(records_block, TextContent):
            raise TypeError(
                f"expected TextContent for records block, got {type(records_block).__name__}"
            )
        text = records_block.text
        # Strip the "Query result records:\n" prefix
        prefix = "Query result records:\n"
        if text.startswith(prefix):
            payload_text = text[len(prefix) :].strip()
        else:
            payload_text = text.strip()
        if not payload_text or _is_empty_sentinel(payload_text):
            return None
        fenced = _extract_json_fence(payload_text)
        return json.loads(fenced if fenced is not None else payload_text)

    # Local server / test fixture: single block with raw JSON
    if len(result.content) == 1:
        block = result.content[0]
        if not isinstance(block, TextContent):
            raise TypeError(f"expected TextContent, got {type(block).__name__}")
        text = block.text.strip()
        if not text or _is_empty_sentinel(text):
            return None
        fenced = _extract_json_fence(text)
        if fenced is not None:
            return json.loads(fenced)
        return json.loads(text)

    raise ValueError(
        f"expected 1 or 3 content blocks (remote server returns 3), got {len(result.content)}"
    )


# Matches a ```json ... ``` markdown fence anywhere in the text.
_JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def _extract_json_fence(text: str) -> str | None:
    """Extract JSON content from a markdown code block fence.

    Args:
        text: The raw text containing the fenced JSON.

    Returns:
        The extracted JSON string, or None if no match is found.
    """
    match = _JSON_FENCE_RE.search(text)
    return match.group(1) if match else None


# Plain-text payloads the server returns for zero-result calls.
_EMPTY_SENTINEL_PREFIXES: tuple[str, ...] = (
    "no problems found",
    "no records",
    "no results",
    "no data",
    "[ ]",
    "[]",
)


def _is_empty_sentinel(text: str) -> bool:
    """Check if the response text is a plain-text empty result sentinel.

    Args:
        text: The text to check.

    Returns:
        True if the text matches an empty sentinel prefix, False otherwise.
    """
    lowered = text.lower().strip()
    return any(lowered.startswith(prefix) for prefix in _EMPTY_SENTINEL_PREFIXES)


# --- Acceptance criterion 1: list_problems ----------------------------------


async def list_open_problems(session: ClientSession, entity_id: str = "") -> list[dict[str, Any]]:
    """Return ACTIVE Davis problems, optionally scoped to a workspace entity.

    The remote Dynatrace MCP server tool is ``query-problems`` (kebab-case).
    It accepts ``status`` (``"ACTIVE"``, ``"CLOSED"``, ``"ALL"``) but does
    not accept an ``entity`` filter — entity scoping must be done via DQL
    (``execute-dql``) if needed. The ``entity_id`` parameter is accepted for
    API compatibility but ignored when calling the remote server.

    See the response-shape notes in ``docs/dynatrace-mcp-notes.md``. Each
    element is a dict with at least ``event.id``, ``display_id``,
    ``event.status``, ``event.start``, ``event.end``, ``event.category``,
    ``event.description``, ``affected_entity_ids``, ``related_entity_ids``.
    Empty list when the workspace is healthy — the Sentinel ALLOW path.
    """
    result = await session.call_tool("query-problems", {"status": "ACTIVE"})
    payload = _parse_text_content(result)
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    return payload.get("problems", [])


# --- Acceptance criterion 2: execute_dql ------------------------------------


async def run_dql(session: ClientSession, query: str) -> list[dict[str, Any]]:
    """Run a DQL query against Grail and return the parsed records.

    The remote Dynatrace MCP server tool is ``execute-dql`` (kebab-case).
    The argument key is ``dqlQueryString`` (changed from ``dqlStatement``
    on the local server — confirmed during the migration spike, 2026-06-09).

    Always pass a tight ``from:`` timeframe in the query — the pre-flight
    runs on every risky tool call and Grail charges by GB scanned.
    """
    result = await session.call_tool("execute-dql", {"dqlQueryString": query})
    payload = _parse_text_content(result)
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    return payload.get("records", [])
