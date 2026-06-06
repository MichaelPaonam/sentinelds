"""Live-tenant smoke test for the Sentinel Agent's Dynatrace MCP client.

This script is the actual acceptance gate for issue #23: it exercises both
``list_problems`` and ``execute_dql`` against a real Dynatrace tenant and
prints the parsed shapes so they can be pinned in
``docs/dynatrace-mcp-notes.md``.

Run::

    uv run python -m src.smoke.sentinel_mcp_smoke

Required environment::

    DT_ENVIRONMENT      e.g. https://abc12345.apps.dynatrace.com
    DT_PLATFORM_TOKEN   Platform Token with at minimum:
                          app-engine:apps:run
                          storage:events:read
                          storage:entities:read
    DT_WORKSPACE_ENTITY (optional) Dynatrace entity id to filter on. If
                        unset, the smoke calls list_problems without an
                        entity filter — useful on a fresh tenant where the
                        workspace entity has not been materialised yet.

Exits 0 on success, non-zero with a clear message on failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

from sentinel.dynatrace_mcp import (
    DynatraceMCPConfig,
    dynatrace_session,
    list_open_problems,
    run_dql,
)

_PROBE_DQL = "fetch events, from:now()-5m\n| fields event.type, timestamp\n| limit 5"


def _dump_raw(label: str, result: object) -> None:
    """Print the raw CallToolResult content blocks for shape pinning.

    Run when the parsed call fails — lets us see whether the server returned
    text that isn't JSON, multiple blocks, or a non-text block, without
    re-running the live tenant for a separate dump script.
    """
    is_error = getattr(result, "isError", None)
    content = getattr(result, "content", []) or []
    print(f"      [raw {label}] isError={is_error}, blocks={len(content)}")
    for i, block in enumerate(content):
        text = getattr(block, "text", None)
        kind = type(block).__name__
        if text is not None:
            print(f"      [raw {label}] block[{i}] {kind}: {text[:1500]!r}")
        else:
            print(f"      [raw {label}] block[{i}] {kind}: {block!r}")


async def _run() -> int:
    """Run the live MCP integration tests against a Dynatrace environment.

    Returns:
        0 on success, or raises an exception.
    """
    load_dotenv()
    cfg = DynatraceMCPConfig.from_env()

    workspace_entity = os.environ.get("DT_WORKSPACE_ENTITY", "")
    print(
        f"--- Sentinel MCP smoke ---\n"
        f"  tenant            = {cfg.environment}\n"
        f"  server version    = {cfg.server_version}\n"
        f"  workspace entity  = {workspace_entity or '(unset; calling unfiltered)'}"
    )

    async with dynatrace_session(cfg) as session:
        # 1) list_problems — acceptance criterion 1
        print("\n[1/2] list_problems …")
        try:
            problems = await list_open_problems(session, workspace_entity)
        except Exception as exc:  # noqa: BLE001
            print(f"      parse failed: {exc!r}; dumping raw response for shape pinning")
            args: dict[str, object] = {"status": "ACTIVE"}
            if workspace_entity:
                args["entity"] = workspace_entity
            raw = await session.call_tool("list_problems", args)
            _dump_raw("list_problems", raw)
            raise
        print(f"      returned {len(problems)} ACTIVE problem(s)")
        if problems:
            print("      first problem (truncated):")
            print(json.dumps(problems[0], indent=2)[:1000])

        # 2) execute_dql — acceptance criterion 2
        print("\n[2/2] execute_dql …")
        try:
            records = await run_dql(session, _PROBE_DQL)
        except Exception as exc:  # noqa: BLE001
            print(f"      parse failed: {exc!r}; dumping raw response for shape pinning")
            raw = await session.call_tool("execute_dql", {"dqlStatement": _PROBE_DQL})
            _dump_raw("execute_dql", raw)
            raise
        print(f"      returned {len(records)} record(s)")
        if records:
            print("      first record:")
            print(json.dumps(records[0], indent=2)[:1000])

    print("\n✓ MCP smoke complete — paste the captured shapes into docs/dynatrace-mcp-notes.md")
    return 0


def main() -> None:
    """Main entry point for the Sentinel MCP smoke test."""
    try:
        sys.exit(asyncio.run(_run()))
    except KeyError as missing_env:
        # from_env() raises with the env-var name and a doc pointer.
        print(f"[ERROR] {missing_env}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001 — top-level smoke wants the message
        print(f"[ERROR] MCP smoke failed: {exc!r}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
