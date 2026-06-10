"""Tests for the Sentinel audit sidecar fan-out client.

The audit client must be:
* a no-op when ``SENTINEL_AUDIT_URL`` is unset (default in dev / tests)
* fire-and-forget when set: a sidecar outage cannot raise into the gate
* shape-stable: the payload posted to the sidecar matches what the agents
  already log so the sidecar can wrap it in an OTel span verbatim
"""

from __future__ import annotations

import asyncio
import importlib
import unittest
from unittest.mock import AsyncMock, patch

import httpx


def _reload_audit_module(audit_url: str | None):
    """Reload core.sentinel_audit with SENTINEL_AUDIT_URL set or unset.

    The module reads the env var once at import time, so each test that
    cares about the URL needs a fresh import.
    """
    import os

    import core.sentinel_audit as audit_module

    if audit_url is None:
        os.environ.pop("SENTINEL_AUDIT_URL", None)
    else:
        os.environ["SENTINEL_AUDIT_URL"] = audit_url
    return importlib.reload(audit_module)


class TestEmitAuditDisabled(unittest.TestCase):
    """When SENTINEL_AUDIT_URL is unset, emit_audit must be a no-op."""

    def test_emit_audit_no_url_is_noop(self) -> None:
        audit = _reload_audit_module(None)
        self.assertFalse(audit.is_enabled())

        with patch("httpx.AsyncClient") as mock_client:
            asyncio.run(audit.emit_audit({"tool": "web_fetch"}))
            mock_client.assert_not_called()

    def test_emit_audit_sync_no_url_is_noop(self) -> None:
        audit = _reload_audit_module(None)
        with patch("httpx.AsyncClient") as mock_client:
            audit.emit_audit_sync({"tool": "web_fetch"})
            mock_client.assert_not_called()


class TestEmitAuditEnabled(unittest.TestCase):
    """When SENTINEL_AUDIT_URL is set, emit_audit must POST and swallow errors."""

    def setUp(self) -> None:
        self.audit = _reload_audit_module("https://sentinel.example.com/audit")

    def tearDown(self) -> None:
        # Restore default state so subsequent tests aren't surprised.
        _reload_audit_module(None)

    def test_emit_audit_posts_payload(self) -> None:
        self.assertTrue(self.audit.is_enabled())

        mock_post = AsyncMock(return_value=httpx.Response(202))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            asyncio.run(self.audit.emit_audit({"tool": "web_fetch", "decision": "ALLOW"}))

        mock_post.assert_awaited_once()
        called_url, called_kwargs = mock_post.await_args.args, mock_post.await_args.kwargs
        self.assertEqual(called_url[0], "https://sentinel.example.com/audit")
        self.assertEqual(
            called_kwargs["json"], {"tool": "web_fetch", "decision": "ALLOW"}
        )

    def test_emit_audit_swallows_http_error(self) -> None:
        # 5xx response: emit_audit must log and return cleanly, not raise.
        mock_post = AsyncMock(return_value=httpx.Response(503, text="upstream gone"))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            asyncio.run(self.audit.emit_audit({"tool": "web_fetch"}))
            # No assertion on logs — the contract is "does not raise".

    def test_emit_audit_swallows_transport_error(self) -> None:
        mock_post = AsyncMock(side_effect=httpx.ConnectError("dns fail"))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            # Must not raise.
            asyncio.run(self.audit.emit_audit({"tool": "web_fetch"}))

    def test_emit_audit_sync_runs_loop_when_none_present(self) -> None:
        # No running loop on this thread — emit_audit_sync should asyncio.run.
        mock_post = AsyncMock(return_value=httpx.Response(202))
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__.return_value.post = mock_post
            self.audit.emit_audit_sync({"event.type": "sentinelds.injection.candidate"})
            mock_post.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
