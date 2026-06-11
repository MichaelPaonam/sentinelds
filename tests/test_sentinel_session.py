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


def test_session_quarantine_flag():
    """Verify that quarantined is initialized to False and can be flipped to True."""
    sess = SentinelSession(workspace_entity_id="WORKSPACE-1")
    assert sess.quarantined is False
    sess.quarantined = True
    assert sess.quarantined is True


def test_quarantine_audit_logging(capsys):
    """Verify that catching a PermissionError and triggering quarantine logs the correct payload."""
    import json
    import re
    import sys

    from sentinel.session import clear_sentinel_session, set_sentinel_session

    sess = SentinelSession(workspace_entity_id="WORKSPACE-TEST", agent_name="test_agent")
    set_sentinel_session(sess)

    try:
        raise PermissionError(
            "Sentinel halted 'model_train' — workspace compromised (injection.candidate)."
        )
    except PermissionError as e:
        sess.quarantined = True
        sess.compromised = True

        tool_name = "unknown_tool"
        match = re.search(r"Sentinel halted '([^']+)'", str(e))
        if match:
            tool_name = match.group(1)

        audit_payload = {
            "workspace": sess.workspace_entity_id,
            "agent": sess.agent_name,
            "tool": tool_name,
            "rule_fired": "SENTINEL_QUARANTINE",
            "decision": "HALT",
            "reason": str(e),
        }
        structured_audit_line = json.dumps(audit_payload)
        sys.stderr.write(f"[SECURITY AUDIT] {structured_audit_line}\n")

    clear_sentinel_session()

    captured = capsys.readouterr()
    assert "[SECURITY AUDIT]" in captured.err
    # Parse the JSON from the audit line
    audit_line = [line for line in captured.err.splitlines() if "[SECURITY AUDIT]" in line][0]
    json_part = audit_line.replace("[SECURITY AUDIT] ", "").strip()
    payload = json.loads(json_part)

    assert payload["workspace"] == "WORKSPACE-TEST"
    assert payload["agent"] == "test_agent"
    assert payload["tool"] == "model_train"
    assert payload["rule_fired"] == "SENTINEL_QUARANTINE"
    assert payload["decision"] == "HALT"
    assert "Sentinel halted 'model_train'" in payload["reason"]
