"""Tests for the Sentinel audit sidecar service.

The sidecar is downstream of the in-process gate — its job is to re-emit
audit payloads as OTel spans on the ``sentinelds-sentinel`` service entity.
These tests cover the contract the agents rely on:

* ``/health`` returns 200 (Cloud Run liveness probe).
* ``/audit`` always returns 202 Accepted on a parseable body, so the
  agent-side ``emit_audit`` fan-out never sees a 4xx/5xx and never enters
  any retry path.
* ``/audit`` accepts unknown fields and structurally-odd payloads without
  raising — the agents and sidecar may version-drift in the wild.
* Bad JSON bodies are accepted (logged + tagged on the span).
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from sentinel_service.main import app


class TestSidecarEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        # TestClient(app) drives the lifespan, which starts the heartbeat.
        # The heartbeat soft-fails when DT_ENVIRONMENT/DT_PLATFORM_TOKEN
        # are unset, which is the test default — so this is safe.
        self.client_ctx = TestClient(app)
        self.client = self.client_ctx.__enter__()

    def tearDown(self) -> None:
        self.client_ctx.__exit__(None, None, None)

    def test_health_returns_ok(self) -> None:
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")
        self.assertEqual(r.json()["service"], "sentinelds-sentinel")

    def test_audit_preflight_payload_accepted(self) -> None:
        r = self.client.post(
            "/audit",
            json={
                "event.type": "sentinel.preflight",
                "workspace": "WORKSPACE-1",
                "agent": "research_agent",
                "tool": "web_fetch",
                "rule_fired": "CLEAN",
                "decision": "ALLOW",
                "input_problems": [],
            },
        )
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.json()["status"], "accepted")

    def test_audit_injection_candidate_payload_accepted(self) -> None:
        r = self.client.post(
            "/audit",
            json={
                "event.type": "sentinelds.injection.candidate",
                "span.id": "abc123",
                "matched_categories": ["INSTRUCTION_OVERRIDE", "URL_WITH_POST_VERB"],
                "match_count": 2,
                "excerpt_hash": "deadbeef",
                "source_url": "http://attacker.example.com",
                "workspace_entity_id": "WORKSPACE-1",
            },
        )
        self.assertEqual(r.status_code, 202)

    def test_audit_unknown_event_type_still_accepted(self) -> None:
        # Forward-compat: agents may add new event types before the sidecar
        # knows about them. We must not 4xx in that case.
        r = self.client.post(
            "/audit",
            json={"event.type": "future.unknown.event", "extra": "field"},
        )
        self.assertEqual(r.status_code, 202)

    def test_audit_invalid_json_body_still_accepted(self) -> None:
        r = self.client.post(
            "/audit",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(r.status_code, 202)


if __name__ == "__main__":
    unittest.main()
