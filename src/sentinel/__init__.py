"""SentinelDS Sentinel package — Dynatrace-MCP-backed pre-flight gate."""

from sentinel.preflight import (
    Sentinel,
    SentinelSession,
    Verdict,
    sentinel_check,
    sentinel_gate,
)
from sentinel.session import (
    clear_sentinel_session,
    get_sentinel_session,
    set_sentinel_session,
)

__all__ = [
    "Sentinel",
    "SentinelSession",
    "Verdict",
    "clear_sentinel_session",
    "get_sentinel_session",
    "sentinel_check",
    "sentinel_gate",
    "set_sentinel_session",
]
