"""Fixture-based unit tests for the Sentinel pre-flight gate.

These tests assert that:
1. Tool classification works correctly (risky vs advisory).
2. Healthy MCP allows tool calls.
3. Active open problems trigger HALT.
4. Custom BizEvents trigger HALT/WARN depending on severity.
5. Unreachable MCP triggers fail-closed (HALT) for risky tools
and fail-open (WARN) for advisory tools.
6. The @sentinel_guard decorator correctly intercepts execution.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp import ClientSession

from sentinel.preflight import Sentinel, Verdict, sentinel_guard


class TestSentinelToolClassification(unittest.TestCase):
    """Verify tool classification into risky and advisory categories."""

    def test_risky_tools_classified_correctly(self) -> None:
        """Risky tools (training, egress, file writes, execution) must return True."""
        for name in (
            "model_train",
            "model.train",
            "train",
            "web_fetch",
            "fetch_url",
            "file_write",
            "write_file",
            "execute_code",
            "run_command",
        ):
            self.assertTrue(Sentinel.is_risky(name), msg=f"{name} should be risky")

    def test_advisory_tools_classified_correctly(self) -> None:
        """Advisory tools (search) must return False."""
        for name in ("search", "web_search", "google_search", "read_only_tool"):
            self.assertFalse(Sentinel.is_risky(name), msg=f"{name} should not be risky")


class TestSentinelPreflight(unittest.IsolatedAsyncioTestCase):
    """Verify Sentinel.preflight logic under different MCP and problem states."""

    def setUp(self) -> None:
        Sentinel.set_context(None, "WORKSPACE-TEST", "Test Agent")

    async def test_healthy_mcp_returns_allow(self) -> None:
        """With no problems or events, preflight returns ALLOW."""
        session = MagicMock(spec=ClientSession)

        # Patch list_open_problems to return empty list, run_dql to return empty list
        with (
            patch("sentinel.preflight.list_open_problems", AsyncMock(return_value=[])),
            patch("sentinel.preflight.run_dql", AsyncMock(return_value=[])),
            patch("sentinel.preflight.logger") as mock_logger,
        ):
            verdict = await Sentinel.preflight(
                session=session,
                workspace_entity_id="WORKSPACE-TEST",
                tool_name="web_fetch",
                agent_name="Research Agent",
            )
            self.assertEqual(verdict, Verdict.ALLOW)

            # Assert logger logged a structured decision line
            mock_logger.info.assert_called_once()
            log_arg = mock_logger.info.call_args[0][0]
            log_payload = json.loads(log_arg)
            self.assertEqual(log_payload["workspace"], "WORKSPACE-TEST")
            self.assertEqual(log_payload["agent"], "Research Agent")
            self.assertEqual(log_payload["tool"], "web_fetch")
            self.assertEqual(log_payload["rule_fired"], "DEFAULT_ALLOW")
            self.assertEqual(log_payload["decision"], "ALLOW")
            self.assertEqual(log_payload["input_problems"], [])

    async def test_active_open_problem_returns_halt(self) -> None:
        """Active problem with a matching severity triggers HALT."""
        session = MagicMock(spec=ClientSession)
        active_problems = [
            {
                "problemId": "p-123",
                "title": "Severe connection errors",
                "severity": "ERROR",
                "status": "ACTIVE",
            }
        ]

        with (
            patch("sentinel.preflight.list_open_problems", AsyncMock(return_value=active_problems)),
            patch("sentinel.preflight.run_dql", AsyncMock(return_value=[])),
            patch("sentinel.preflight.logger") as mock_logger,
        ):
            verdict = await Sentinel.preflight(
                session=session,
                workspace_entity_id="WORKSPACE-TEST",
                tool_name="model_train",
            )
            self.assertEqual(verdict, Verdict.HALT)

            log_arg = mock_logger.info.call_args[0][0]
            log_payload = json.loads(log_arg)
            self.assertEqual(log_payload["rule_fired"], "ACTIVE_PROBLEM_HALT")
            self.assertEqual(log_payload["decision"], "HALT")
            self.assertEqual(log_payload["input_problems"], active_problems)

    async def test_custom_high_severity_event_returns_halt(self) -> None:
        """Recent custom event with high severity triggers HALT."""
        session = MagicMock(spec=ClientSession)
        custom_events = [
            {
                "severity": "high",
                "attack_id": "A1",
                "agent": "Research Agent",
            }
        ]

        with (
            patch("sentinel.preflight.list_open_problems", AsyncMock(return_value=[])),
            patch("sentinel.preflight.run_dql", AsyncMock(return_value=custom_events)),
            patch("sentinel.preflight.logger") as mock_logger,
        ):
            verdict = await Sentinel.preflight(
                session=session,
                workspace_entity_id="WORKSPACE-TEST",
                tool_name="web_fetch",
            )
            self.assertEqual(verdict, Verdict.HALT)

            log_arg = mock_logger.info.call_args[0][0]
            log_payload = json.loads(log_arg)
            self.assertEqual(log_payload["rule_fired"], "CUSTOM_EVENT_HALT")
            self.assertEqual(log_payload["decision"], "HALT")
            self.assertEqual(log_payload["input_problems"], custom_events)

    async def test_custom_low_severity_event_returns_warn(self) -> None:
        """Recent custom event with low severity triggers WARN."""
        session = MagicMock(spec=ClientSession)
        custom_events = [
            {
                "severity": "low",
                "attack_id": "A2",
                "agent": "Feature Engineering Agent",
            }
        ]

        with (
            patch("sentinel.preflight.list_open_problems", AsyncMock(return_value=[])),
            patch("sentinel.preflight.run_dql", AsyncMock(return_value=custom_events)),
            patch("sentinel.preflight.logger") as mock_logger,
        ):
            verdict = await Sentinel.preflight(
                session=session,
                workspace_entity_id="WORKSPACE-TEST",
                tool_name="execute_code",
            )
            self.assertEqual(verdict, Verdict.WARN)

            log_arg = mock_logger.info.call_args[0][0]
            log_payload = json.loads(log_arg)
            self.assertEqual(log_payload["rule_fired"], "CUSTOM_EVENT_WARN")
            self.assertEqual(log_payload["decision"], "WARN")
            self.assertEqual(log_payload["input_problems"], custom_events)

    async def test_unreachable_mcp_risky_tool_fail_closed(self) -> None:
        """If MCP query fails or is missing, preflight on a risky tool must fail-closed (HALT)."""
        session = MagicMock(spec=ClientSession)

        # Simulate connection error
        with (
            patch(
                "sentinel.preflight.list_open_problems",
                AsyncMock(side_effect=RuntimeError("Connection refused")),
            ),
            patch("sentinel.preflight.logger") as mock_logger,
        ):
            verdict = await Sentinel.preflight(
                session=session,
                workspace_entity_id="WORKSPACE-TEST",
                tool_name="web_fetch",
            )
            self.assertEqual(verdict, Verdict.HALT)

            log_arg = mock_logger.info.call_args[0][0]
            log_payload = json.loads(log_arg)
            self.assertEqual(log_payload["rule_fired"], "MCP_UNREACHABLE_FAIL_CLOSED")
            self.assertEqual(log_payload["decision"], "HALT")
            self.assertEqual(log_payload["input_problems"], [{"error": "MCP_UNREACHABLE"}])

    async def test_unreachable_mcp_advisory_tool_fail_open(self) -> None:
        """If MCP query fails, preflight on an advisory tool must fail-open (WARN)."""
        session = MagicMock(spec=ClientSession)

        # Simulate connection error
        with (
            patch(
                "sentinel.preflight.list_open_problems",
                AsyncMock(side_effect=RuntimeError("Connection refused")),
            ),
            patch("sentinel.preflight.logger") as mock_logger,
        ):
            verdict = await Sentinel.preflight(
                session=session,
                workspace_entity_id="WORKSPACE-TEST",
                tool_name="search",
            )
            self.assertEqual(verdict, Verdict.WARN)

            log_arg = mock_logger.info.call_args[0][0]
            log_payload = json.loads(log_arg)
            self.assertEqual(log_payload["rule_fired"], "MCP_UNREACHABLE_FAIL_OPEN")
            self.assertEqual(log_payload["decision"], "WARN")

    async def test_unconfigured_mcp_risky_tool_fail_closed(self) -> None:
        """If no session is configured (session=None), risky tools must fail-closed (HALT)."""
        with patch("sentinel.preflight.logger") as mock_logger:
            verdict = await Sentinel.preflight(
                session=None,
                workspace_entity_id="WORKSPACE-TEST",
                tool_name="web_fetch",
            )
            self.assertEqual(verdict, Verdict.HALT)

            log_arg = mock_logger.info.call_args[0][0]
            log_payload = json.loads(log_arg)
            self.assertEqual(log_payload["rule_fired"], "MCP_UNREACHABLE_FAIL_CLOSED")
            self.assertEqual(log_payload["decision"], "HALT")

    async def test_unconfigured_mcp_advisory_tool_fail_open(self) -> None:
        """If no session is configured (session=None), advisory tools must fail-open (WARN)."""
        with patch("sentinel.preflight.logger") as mock_logger:
            verdict = await Sentinel.preflight(
                session=None,
                workspace_entity_id="WORKSPACE-TEST",
                tool_name="search",
            )
            self.assertEqual(verdict, Verdict.WARN)

            log_arg = mock_logger.info.call_args[0][0]
            log_payload = json.loads(log_arg)
            self.assertEqual(log_payload["rule_fired"], "MCP_UNREACHABLE_FAIL_OPEN")
            self.assertEqual(log_payload["decision"], "WARN")


class TestSentinelGuardDecorator(unittest.IsolatedAsyncioTestCase):
    """Verify that the @sentinel_guard decorator correctly intercepts execution."""

    def setUp(self) -> None:
        Sentinel.set_context(None, "WORKSPACE-TEST", "Decorator Agent")

    async def test_decorator_allows_execution_on_allow(self) -> None:
        """If preflight is ALLOW, the decorated functions execute successfully."""

        @sentinel_guard("search")
        def sync_tool() -> str:
            return "sync success"

        @sentinel_guard("search")
        async def async_tool() -> str:
            return "async success"

        with patch("sentinel.preflight.Sentinel.preflight", AsyncMock(return_value=Verdict.ALLOW)):
            self.assertEqual(sync_tool(), "sync success")
            self.assertEqual(await async_tool(), "async success")

    async def test_decorator_allows_execution_on_warn(self) -> None:
        """If preflight is WARN, the decorated functions still execute successfully."""

        @sentinel_guard("search")
        def sync_tool() -> str:
            return "sync success"

        @sentinel_guard("search")
        async def async_tool() -> str:
            return "async success"

        with patch("sentinel.preflight.Sentinel.preflight", AsyncMock(return_value=Verdict.WARN)):
            self.assertEqual(sync_tool(), "sync success")
            self.assertEqual(await async_tool(), "async success")

    async def test_decorator_raises_on_halt(self) -> None:
        """
        If preflight is HALT,
        the decorated functions must raise PermissionError and not execute.
        """
        sync_called = False
        async_called = False

        @sentinel_guard("web_fetch")
        def sync_tool() -> str:
            nonlocal sync_called
            sync_called = True
            return "sync success"

        @sentinel_guard("web_fetch")
        async def async_tool() -> str:
            nonlocal async_called
            async_called = True
            return "async success"

        with patch("sentinel.preflight.Sentinel.preflight", AsyncMock(return_value=Verdict.HALT)):
            with self.assertRaises(PermissionError):
                sync_tool()
            with self.assertRaises(PermissionError):
                await async_tool()

            self.assertFalse(sync_called)
            self.assertFalse(async_called)


if __name__ == "__main__":
    unittest.main()
