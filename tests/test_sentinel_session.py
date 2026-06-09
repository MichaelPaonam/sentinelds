"""Unit tests for the observer-pattern Sentinel — no MCP, no network."""

import asyncio

from sentinel.preflight import Sentinel, SentinelSession, Verdict, sentinel_check


def test_clean_session_allows():
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1")
    assert sentinel_check(sess) == Verdict.ALLOW
    assert not sess.compromised


def test_notify_sets_compromised_on_injection():
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1", mcp_session=None)
    verdict = asyncio.run(Sentinel.notify(sess, "injection.candidate"))
    assert verdict == Verdict.HALT
    assert sess.compromised is True
    assert sess.compromise_reason == "injection.candidate"
    assert sentinel_check(sess) == Verdict.HALT


def test_notify_without_mcp_still_halts_on_local_detection():
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1", mcp_session=None)
    asyncio.run(Sentinel.notify(sess, "injection.candidate"))
    assert sess.compromised is True


def test_notify_ignores_unknown_event_type_when_no_mcp():
    """Non-detector event with no MCP session: stays clean."""
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1", mcp_session=None)
    verdict = asyncio.run(Sentinel.notify(sess, "unrelated.event"))
    assert verdict == Verdict.ALLOW
    assert sess.compromised is False


def test_compromise_is_sticky():
    """Once compromised, repeated checks stay HALT."""
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1")
    sess.compromised = True
    sess.compromise_reason = "test"
    assert sentinel_check(sess) == Verdict.HALT
    assert sentinel_check(sess) == Verdict.HALT
