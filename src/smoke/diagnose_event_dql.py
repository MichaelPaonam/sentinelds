"""Diagnostic: fetch the last sentinelds events from Grail and print the raw records.

Run::

    set -a && source .env && set +a
    PYTHONPATH=src uv run python -m smoke.diagnose_event_dql

Helps verify event.kind, event.type, and which properties are stored.
"""

from __future__ import annotations

import asyncio
import json
import sys

from dotenv import load_dotenv

from sentinel.dynatrace_mcp import DynatraceMCPConfig, dynatrace_session, run_dql

# Broad query — no event.kind or event.type filter, just look for our title
_QUERIES = [
    (
        "broad: any event with sentinelds in title (1h)",
        'fetch events, from:now()-1h\n| filter contains(title, "sentinelds")\n| limit 5',
    ),
    (
        "broad: any CUSTOM_INFO event (5m)",
        'fetch events, from:now()-5m\n| filter event.type == "CUSTOM_INFO"\n| limit 5',
    ),
    (
        "by title field (1h)",
        "fetch events, from:now()-1h\n"
        '| filter title == "sentinelds.injection.candidate"\n'
        "| limit 5",
    ),
]


async def _run() -> int:
    load_dotenv()
    cfg = DynatraceMCPConfig.from_env()

    async with dynatrace_session(cfg) as session:
        for label, dql in _QUERIES:
            print(f"\n--- {label} ---")
            print(f"DQL: {dql!r}\n")
            try:
                rows = await run_dql(session, dql)
                print(f"rows returned: {len(rows)}")
                for i, row in enumerate(rows):
                    print(f"  [{i}] {json.dumps(row, indent=4)[:800]}")
            except Exception as exc:
                print(f"  ERROR: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
