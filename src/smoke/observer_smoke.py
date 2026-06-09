"""Smoke: detector fires → session flagged → next tool call halts.

Requires the attack server on :8001.
"""

from __future__ import annotations

from sentinel import SentinelSession, Verdict, sentinel_check, set_sentinel_session
from tools.web_fetch import fetch_url


def main() -> int:
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1", agent_name="smoke")
    set_sentinel_session(sess)

    print("1. fetching malicious page...")
    result = fetch_url("http://localhost:8001/papers/json")
    print(f"   status={result['status']}")
    print(f"   matches={[m['category'] for m in result.get('injection_matches', [])]}")
    print(f"   compromised={sess.compromised} reason={sess.compromise_reason!r}")

    print("2. checking gate...")
    verdict = sentinel_check(sess)
    print(f"   verdict={verdict.value}")

    print("3. attempting a follow-up fetch (expected: PermissionError)...")
    try:
        fetch_url("http://localhost:8001/health")
        print("   UNEXPECTED — call was allowed")
        return 1
    except PermissionError as exc:
        print(f"   blocked as expected: {exc}")

    return 0 if verdict == Verdict.HALT else 1


if __name__ == "__main__":
    raise SystemExit(main())
