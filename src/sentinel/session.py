"""Active SentinelSession holder via contextvars.

The agent runner sets the session once at the start of a run; tool gates
read it without threading it through every call signature.
"""

from __future__ import annotations

from contextvars import ContextVar

from sentinel.preflight import SentinelSession

_current: ContextVar[SentinelSession | None] = ContextVar("sentinel_session", default=None)


def set_sentinel_session(sess: SentinelSession) -> None:
    """Install `sess` as the active session for the current context."""
    _current.set(sess)


def get_sentinel_session() -> SentinelSession | None:
    """Return the active session, or None if none has been set."""
    return _current.get()


def clear_sentinel_session() -> None:
    """Remove the active session. Useful between tests."""
    _current.set(None)
