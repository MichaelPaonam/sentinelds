"""Smoke test for the Dynatrace Remote MCP Server (Streamable HTTP transport).

Connects to the tenant's hosted MCP gateway, calls query-problems and
execute-dql, and verifies the response shapes meet the acceptance gates
documented in docs/migration_plan.md section 3.1.

Run::

    PYTHONPATH=src uv run python -m smoke.sentinel_remote_mcp_smoke

Required environment::

    DT_ENVIRONMENT      e.g. https://abc12345.apps.dynatrace.com
    DT_PLATFORM_TOKEN   Platform Token with scopes:
                          mcp-gateway:servers:invoke
                          mcp-gateway:servers:read
                          storage:buckets:read
                          storage:events:read
                          storage:logs:read
                        See docs/migration_plan.md for the full scope list.

Exits 0 on success, non-zero with a clear message on failure.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from dotenv import load_dotenv

from sentinel.dynatrace_mcp import (
    DynatraceMCPConfig,
    dynatrace_session,
    list_open_problems,
    run_dql,
)

_PROBE_DQL = "fetch events, from:now()-1m | limit 1"


async def _run() -> int:
    load_dotenv()
    cfg = DynatraceMCPConfig.from_env()

    print(
        f"--- Sentinel Remote MCP smoke ---\n"
        f"  tenant   = {cfg.environment}\n"
        f"  gateway  = {cfg.remote_url}\n"
    )

    async with dynatrace_session(cfg) as session:
        # 1) query-problems — acceptance criterion 1
        print("[1/2] query-problems (status=ACTIVE) …")
        t0 = time.monotonic()
        try:
            problems = await list_open_problems(session)
        except Exception as exc:  # noqa: BLE001
            print(f"      [FAIL] parse failed: {exc!r}", file=sys.stderr)
            return 1
        elapsed_ms = (time.monotonic() - t0) * 1000
        print(f"      returned {len(problems)} ACTIVE problem(s) in {elapsed_ms:.0f}ms")
        if problems:
            print("      first problem (truncated):")
            print(json.dumps(problems[0], indent=2)[:1000])
        print("      ✓ query-problems shape ok")

        # 2) execute-dql — acceptance criterion 2
        print(f"\n[2/2] execute-dql ({_PROBE_DQL!r}) …")
        t0 = time.monotonic()
        try:
            records = await run_dql(session, _PROBE_DQL)
        except Exception as exc:  # noqa: BLE001
            print(f"      [FAIL] parse failed: {exc!r}", file=sys.stderr)
            return 1
        elapsed_ms = (time.monotonic() - t0) * 1000
        print(f"      returned {len(records)} record(s) in {elapsed_ms:.0f}ms")
        if records:
            print("      first record:")
            print(json.dumps(records[0], indent=2)[:1000])
        print("      ✓ execute-dql shape ok")

    print("\n✓ Remote MCP smoke complete")
    return 0


def main() -> None:
    """Entry point for the remote MCP smoke test."""
    try:
        sys.exit(asyncio.run(_run()))
    except KeyError as missing_env:
        print(f"[ERROR] {missing_env}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Remote MCP smoke failed: {exc!r}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
