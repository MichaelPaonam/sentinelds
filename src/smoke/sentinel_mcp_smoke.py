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

from src.sentinel.dynatrace_mcp import (
    DynatraceMCPConfig,
    dynatrace_session,
    list_open_problems,
    run_dql,
)

_PROBE_DQL = (
    'fetch events, from:now()-5m\n'
    '| filter event.kind == "BIZ_EVENT"\n'
    '| fields event.type, timestamp\n'
    '| limit 5'
)


async def _run() -> int:
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
        problems = await list_open_problems(session, workspace_entity)
        print(f"      returned {len(problems)} OPEN problem(s)")
        if problems:
            print("      first problem (truncated):")
            print(json.dumps(problems[0], indent=2)[:1000])

        # 2) execute_dql — acceptance criterion 2
        print("\n[2/2] execute_dql …")
        records = await run_dql(session, _PROBE_DQL)
        print(f"      returned {len(records)} record(s)")
        if records:
            print("      first record:")
            print(json.dumps(records[0], indent=2)[:1000])

    print("\n✓ MCP smoke complete — paste the captured shapes into docs/dynatrace-mcp-notes.md")
    return 0


def main() -> None:
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
