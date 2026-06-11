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
    list_open_problems,
    run_dql,
)

# Removed: _server_params no longer exists post remote-MCP migration


def _text_result(payload: dict | list, is_error: bool = False) -> CallToolResult:
    """Build a single-block CallToolResult (local server / fixture shape)."""
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        isError=is_error,
    )


def _remote_result(records: list, is_error: bool = False) -> CallToolResult:
    """Build a 3-block CallToolResult matching the remote server shape.

    Confirmed during the migration spike (2026-06-09): both query-problems
    and execute-dql return metadata / types / records as three TextContent
    blocks.
    """
    return CallToolResult(
        content=[
            TextContent(type="text", text='Query metadata:\n{"grail": {}}'),
            TextContent(type="text", text="Grail types for the records in the query result:\n[]"),
            TextContent(type="text", text=f"Query result records:\n{json.dumps(records)}"),
        ],
        isError=is_error,
    )


class TestDynatraceMCPConfig(unittest.TestCase):
    """``DynatraceMCPConfig.from_env`` and remote URL construction."""

    @patch.dict(
        os.environ,
        {"DT_ENVIRONMENT": "https://abc.apps.dynatrace.com", "DT_PLATFORM_TOKEN": "tok"},
        clear=False,
    )
    def test_from_env_reads_required_vars(self) -> None:
        cfg = DynatraceMCPConfig.from_env()
        self.assertEqual(cfg.environment, "https://abc.apps.dynatrace.com")
        self.assertEqual(cfg.platform_token, "tok")

    def test_from_env_missing_var_raises_with_doc_pointer(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(KeyError) as ctx:
                DynatraceMCPConfig.from_env()
        self.assertIn("docs/dynatrace-mcp-options.md", str(ctx.exception))
        self.assertIn(".env.example", str(ctx.exception))

    def test_remote_url_construction(self) -> None:
        cfg = DynatraceMCPConfig(
            environment="https://abc12345.apps.dynatrace.com",
            platform_token="secret",
        )
        self.assertEqual(
            cfg.remote_url,
            "https://abc12345.apps.dynatrace.com/platform-reserved/mcp-gateway/v0.1/servers/dynatrace-mcp/mcp",
        )

    def test_remote_url_strips_trailing_slash(self) -> None:
        cfg = DynatraceMCPConfig(
            environment="https://abc12345.apps.dynatrace.com/",
            platform_token="secret",
        )
        self.assertTrue(
            cfg.remote_url.startswith("https://abc12345.apps.dynatrace.com/platform-reserved")
        )
        self.assertNotIn("//platform-reserved", cfg.remote_url)


class TestParseTextContent(unittest.TestCase):
    """``_parse_text_content`` handles both single-block and 3-block shapes."""

    def test_parses_single_text_block(self) -> None:
        result = _text_result({"records": [{"a": 1}]})
        self.assertEqual(_parse_text_content(result), {"records": [{"a": 1}]})

    def test_parses_three_block_remote_shape(self) -> None:
        records = [{"event.id": "p-1", "event.status": "ACTIVE"}]
        result = _remote_result(records)
        self.assertEqual(_parse_text_content(result), records)

    def test_three_block_empty_records_returns_none(self) -> None:
        result = _remote_result([])
        self.assertIsNone(_parse_text_content(result))

    def test_is_error_propagates_message(self) -> None:
        result = CallToolResult(
            content=[TextContent(type="text", text="grail budget exceeded")],
            isError=True,
        )
        with self.assertRaises(RuntimeError) as ctx:
            _parse_text_content(result)
        self.assertIn("grail budget exceeded", str(ctx.exception))

    def test_two_blocks_refused(self) -> None:
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

    async def test_returns_list_of_dicts_remote_shape(self) -> None:
        session = MagicMock()
        problems = [
            {
                "event.id": "p-1",
                "display_id": "P-1",
                "event.status": "ACTIVE",
                "event.start": "2026-06-01T12:34:56Z",
                "event.category": "ERROR",
                "affected_entity_ids": ["WORKSPACE-1"],
            }
        ]
        session.call_tool = AsyncMock(return_value=_remote_result(problems))

        out = await list_open_problems(session, "WORKSPACE-1")

        self.assertEqual(out, problems)
        # Remote server tool name is "query-problems" (kebab-case).
        session.call_tool.assert_awaited_once_with("query-problems", {"status": "ACTIVE"})

    async def test_empty_problems_returns_empty_list(self) -> None:
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_remote_result([]))
        self.assertEqual(await list_open_problems(session, "WORKSPACE-1"), [])

    async def test_entity_id_param_accepted_but_not_forwarded(self) -> None:
        # Remote server query-problems does not accept an entity arg; the
        # entity_id param is kept for API compatibility but silently ignored.
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_remote_result([]))
        await list_open_problems(session, "WORKSPACE-1")
        session.call_tool.assert_awaited_once_with("query-problems", {"status": "ACTIVE"})

    async def test_omits_entity_when_unset(self) -> None:
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_remote_result([]))
        await list_open_problems(session, "")
        session.call_tool.assert_awaited_once_with("query-problems", {"status": "ACTIVE"})

    async def test_top_level_array_shape_supported(self) -> None:
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_remote_result([{"event.id": "p-1"}]))
        self.assertEqual(await list_open_problems(session, "WORKSPACE-1"), [{"event.id": "p-1"}])

    async def test_no_problems_sentinel_returns_empty_list(self) -> None:
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

    async def test_returns_records_array_remote_shape(self) -> None:
        session = MagicMock()
        records = [{"timestamp": "2026-06-01T12:34:56Z", "severity": "high", "attack_id": "A1"}]
        session.call_tool = AsyncMock(return_value=_remote_result(records))

        out = await run_dql(session, "fetch events | limit 1")

        self.assertEqual(out, records)
        # Remote server tool name is "execute-dql"; arg key is "dqlQueryString".
        session.call_tool.assert_awaited_once_with(
            "execute-dql", {"dqlQueryString": "fetch events | limit 1"}
        )

    async def test_no_records_returns_empty_list(self) -> None:
        session = MagicMock()
        session.call_tool = AsyncMock(return_value=_remote_result([]))
        self.assertEqual(await run_dql(session, "fetch events | limit 1"), [])


if __name__ == "__main__":
    unittest.main()
