"""Fixture-based unit tests for the Dynatrace MCP client wrapper.

These tests do not require a live Dynatrace tenant: they monkey-patch
``ClientSession.call_tool`` to return canned ``CallToolResult`` payloads
matching the shapes documented in ``docs/dynatrace-mcp-notes.md`` and assert
that ``list_open_problems`` and ``run_dql`` parse them into ``list[dict]``.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp.types import CallToolResult, ImageContent, TextContent

from sentinel.dynatrace_mcp import (
    DynatraceMCPConfig,
    _parse_text_content,
    _server_params,
    list_open_problems,
    run_dql,
)


def _text_result(payload: dict | list, is_error: bool = False) -> CallToolResult:
    """Build a CallToolResult that mirrors what the Dynatrace MCP server returns."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        isError=is_error,
    )


class TestDynatraceMCPConfig(unittest.TestCase):
    """``DynatraceMCPConfig.from_env`` and subprocess env wiring."""

    @patch.dict(
        os.environ,
        {"DT_ENVIRONMENT": "https://abc.apps.dynatrace.com", "DT_PLATFORM_TOKEN": "tok"},
        clear=False,
    )
    def test_from_env_reads_required_vars(self) -> None:
        cfg = DynatraceMCPConfig.from_env()
        self.assertEqual(cfg.environment, "https://abc.apps.dynatrace.com")
        self.assertEqual(cfg.platform_token, "tok")
        # Defaults the spike chose for the hackathon tenant.
        self.assertTrue(cfg.disable_telemetry)
        self.assertEqual(cfg.grail_budget_gb, 50)

    def test_from_env_missing_var_raises_with_doc_pointer(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KeyError) as ctx:
                DynatraceMCPConfig.from_env()
        # The error must point the user at the docs and .env.example
        # so the failure is self-explanatory in a Cloud Run log.
        self.assertIn("docs/dynatrace-mcp-options.md", str(ctx.exception))
        self.assertIn(".env.example", str(ctx.exception))

    def test_server_params_only_forwards_dynatrace_vars(self) -> None:
        cfg = DynatraceMCPConfig(
            environment="https://abc.apps.dynatrace.com",
            platform_token="tok",
            server_version="1.8.6",
        )
        params = _server_params(cfg)
        self.assertEqual(params.command, "npx")
        self.assertEqual(
            params.args,
            ["-y", "@dynatrace-oss/dynatrace-mcp-server@1.8.6"],
        )
        # Subprocess env is locked to four keys — no inherited credentials.
        self.assertEqual(
            set(params.env or {}),
            {
                "DT_ENVIRONMENT",
                "DT_PLATFORM_TOKEN",
                "DT_MCP_DISABLE_TELEMETRY",
                "DT_GRAIL_QUERY_BUDGET_GB",
            },
        )
        self.assertEqual(params.env["DT_MCP_DISABLE_TELEMETRY"], "true")
        self.assertEqual(params.env["DT_GRAIL_QUERY_BUDGET_GB"], "50")


class TestParseTextContent(unittest.TestCase):
    """``_parse_text_content`` enforces the Dynatrace MCP single-TextContent contract."""

    def test_parses_single_text_block(self) -> None:
        result = _text_result({"records": [{"a": 1}]})
        self.assertEqual(_parse_text_content(result), {"records": [{"a": 1}]})

    def test_is_error_propagates_message(self) -> None:
        result = CallToolResult(
            content=[TextContent(type="text", text="grail budget exceeded")],
            isError=True,
        )
        with self.assertRaises(RuntimeError) as ctx:
            _parse_text_content(result)
        self.assertIn("grail budget exceeded", str(ctx.exception))

    def test_multiple_blocks_refused(self) -> None:
        result = CallToolResult(
            content=[
                TextContent(type="text", text='{"a": 1}'),
                TextContent(type="text", text='{"b": 2}'),
            ],
            isError=False,
        )
        with self.assertRaises(ValueError):
            _parse_text_content(result)

    def test_non_text_block_refused(self) -> None:
        result = CallToolResult(
            content=[ImageContent(type="image", data="aGk=", mimeType="image/png")],
            isError=False,
        )
        with self.assertRaises(TypeError):
            _parse_text_content(result)

    def test_zero_results_sentinel_returns_none(self) -> None:
        # Confirmed during the live spike against v1.8.6: list_problems with
        # no matches returns the bare string "No problems found", not a JSON
        # envelope. The parser maps that to None so callers return [].
        for sentinel in (
            "No problems found",
            "no records returned",
            "No results",
            "  No data available  ",
        ):
            result = CallToolResult(
                content=[TextContent(type="text", text=sentinel)],
                isError=False,
            )
            self.assertIsNone(_parse_text_content(result), msg=sentinel)

    def test_markdown_fenced_json_extracted(self) -> None:
        # execute_dql v1.8.6 returns a markdown document with the records
        # list inside a ```json ... ``` fence rather than raw JSON.
        text = (
            "📊 **DQL Query Results**\n"
            "- **Scanned Records:** 41\n\n"
            "```json\n"
            '[{"event.type": null, "timestamp": "2026-05-31T21:39:51Z"}]\n'
            "```\n"
        )
        result = CallToolResult(
            content=[TextContent(type="text", text=text)],
            isError=False,
        )
        self.assertEqual(
            _parse_text_content(result),
            [{"event.type": None, "timestamp": "2026-05-31T21:39:51Z"}],
        )


class TestListOpenProblems(unittest.IsolatedAsyncioTestCase):
    """Acceptance criterion 1: structured iterable response."""

    async def test_returns_list_of_dicts(self) -> None:
        session = MagicMock()
        problems = [
            {
                "problemId": "p-1",
                "title": "High failure rate",
                "severity": "ERROR",
                "status": "OPEN",
                "startTime": "2026-06-01T12:34:56Z",
                "affectedEntities": [{"entityId": "WORKSPACE-1", "name": "ws"}],
            }
        ]
        session.call_tool = AsyncMock(return_value=_text_result({"problems": problems}))

        out = await list_open_problems(session, "WORKSPACE-1")

        self.assertEqual(out, problems)
        # Status filter is "ACTIVE" — confirmed by the issue #23 spike against
        # @dynatrace-oss/dynatrace-mcp-server v1.8.6 (rejects "OPEN").
        session.call_tool.assert_awaited_once_with(
            "list_problems", {"status": "ACTIVE", "entity": "WORKSPACE-1"}
        )

    async def test_empty_problems_returns_empty_list(self) -> None:
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_text_result({"problems": []}))
        self.assertEqual(await list_open_problems(session, "WORKSPACE-1"), [])

    async def test_omits_entity_when_unset(self) -> None:
        # Empty entity -> argument dropped, not passed as "". Matches what the
        # smoke does on a fresh trial tenant where no workspace entity exists.
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_text_result({"problems": []}))

        await list_open_problems(session, "")

        session.call_tool.assert_awaited_once_with("list_problems", {"status": "ACTIVE"})

    async def test_top_level_array_shape_supported(self) -> None:
        # Some MCP server versions return the array at the top level rather
        # than under a "problems" key — accept both.
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_text_result([{"problemId": "p-1"}]))
        self.assertEqual(await list_open_problems(session, "WORKSPACE-1"), [{"problemId": "p-1"}])

    async def test_no_problems_sentinel_returns_empty_list(self) -> None:
        # v1.8.6 returns the literal string "No problems found" instead of
        # an empty JSON envelope. Confirmed by the live spike.
        session = MagicMock()
        session.call_tool = AsyncMock(
            return_value=CallToolResult(
                content=[TextContent(type="text", text="No problems found")],
                isError=False,
            )
        )
        self.assertEqual(await list_open_problems(session, ""), [])


class TestRunDQL(unittest.IsolatedAsyncioTestCase):
    """Acceptance criterion 2: rows we can parse."""

    async def test_returns_records_array(self) -> None:
        session = MagicMock()
        records = [{"timestamp": "2026-06-01T12:34:56Z", "severity": "high", "attack_id": "A1"}]
        session.call_tool = AsyncMock(
            return_value=_text_result({"records": records, "metadata": {"scannedBytes": 0}})
        )

        out = await run_dql(session, "fetch events | limit 1")

        self.assertEqual(out, records)
        # Argument key is "dqlStatement" — confirmed by the issue #23 spike
        # against @dynatrace-oss/dynatrace-mcp-server v1.8.6.
        session.call_tool.assert_awaited_once_with(
            "execute_dql", {"dqlStatement": "fetch events | limit 1"}
        )

    async def test_no_records_returns_empty_list(self) -> None:
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_text_result({"records": []}))
        self.assertEqual(await run_dql(session, "fetch events | limit 1"), [])


if __name__ == "__main__":
    unittest.main()
