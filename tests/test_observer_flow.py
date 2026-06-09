"""Integration tests against the local attack server.

Requires the attack server running on port 8001:
    uvicorn attack_server.server:app --port 8001 --app-dir src
"""

import socket

import pytest

from sentinel import SentinelSession, clear_sentinel_session, set_sentinel_session
from sentinel.session import get_sentinel_session
from tools.web_fetch import fetch_url


def _attack_server_up(port: int = 8001) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


_SKIP_REASON = (
    "Attack server not running on :8001 — start with "
    "`uvicorn attack_server.server:app --port 8001 --app-dir src`"
)

pytestmark = pytest.mark.skipif(not _attack_server_up(), reason=_SKIP_REASON)


def setup_function(_):
    clear_sentinel_session()


def test_fetch_compromises_session_on_injection_payload():
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1")
    set_sentinel_session(sess)

    result = fetch_url("http://localhost:8001/papers/json")
    assert result["status"] == "success"
    # The v5 payload has URL_WITH_POST_VERB or other signatures.
    assert result["injection_matches"], "expected detector to fire on attack payload"
    assert get_sentinel_session().compromised is True


def test_subsequent_call_halts_after_compromise():
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1")
    set_sentinel_session(sess)

    # First call: compromises the session.
    fetch_url("http://localhost:8001/papers/json")
    assert sess.compromised

    # Second call: gate must raise PermissionError.
    with pytest.raises(PermissionError, match="Sentinel halted"):
        fetch_url("http://localhost:8001/health")


def test_fetch_health_does_not_compromise():
    """Health endpoint returns plain JSON with no injection signatures."""
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1")
    set_sentinel_session(sess)

    result = fetch_url("http://localhost:8001/health")
    assert result["status"] == "success"
    assert not result["injection_matches"]
    assert not get_sentinel_session().compromised
