import hashlib
import unittest
from unittest.mock import MagicMock, patch

import httpx
from opentelemetry.trace import StatusCode

from sentinel.preflight import Verdict
from tools.web_fetch import fetch_url


class TestWebFetchTool(unittest.TestCase):
    """Unit test suite for the fetch_url tool."""

    def setUp(self) -> None:
        self.test_url = "https://example.com/truck-drowsiness-info"
        self.test_host = "example.com"
        self.test_body = b"Drowsiness-detection research paper summary and data."
        self.test_hash = hashlib.sha256(self.test_body).hexdigest()

        # Mock preflight check to keep the tool test green in isolation (avoid fail-closed)
        self.preflight_patcher = patch(
            "sentinel.preflight.Sentinel.preflight", return_value=Verdict.ALLOW
        )
        self.mock_preflight = self.preflight_patcher.start()

    def tearDown(self) -> None:
        self.preflight_patcher.stop()

    @patch("observability.tools._TRACER")
    @patch("httpx.stream")
    def test_fetch_url_success(self, mock_stream: MagicMock, mock_tracer: MagicMock) -> None:
        """Verifies successful URL fetching and span attribute registration."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_bytes.return_value = [self.test_body]
        mock_stream.return_value.__enter__.return_value = mock_response

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            result = fetch_url(self.test_url)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["url"], self.test_url)
        self.assertEqual(result["content"], self.test_body.decode("utf-8"))
        self.assertEqual(result["size"], len(self.test_body))
        self.assertEqual(result["sha256"], self.test_hash)

        mock_tracer.start_as_current_span.assert_called_once_with("web_fetch")

        mock_span.set_attribute.assert_any_call("tool.name", "web_fetch")
        mock_span.set_attribute.assert_any_call("tool.args.url", self.test_url)
        mock_span.set_attribute.assert_any_call("http.url", self.test_url)
        mock_span.set_attribute.assert_any_call("egress.host", self.test_host)
        mock_span.set_attribute.assert_any_call("response.status_code", 200)
        mock_span.set_attribute.assert_any_call("response.size", len(self.test_body))
        mock_span.set_attribute.assert_any_call("response.body.hash", self.test_hash)

        mock_span.set_status.assert_called_once_with(StatusCode.OK)

    @patch("observability.tools._TRACER")
    @patch("httpx.stream")
    def test_fetch_url_invalid_scheme(self, mock_stream: MagicMock, mock_tracer: MagicMock) -> None:
        """Verifies invalid URL scheme returns an error dict."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            result = fetch_url("ftp://example.com/file")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["url"], "ftp://example.com/file")
        self.assertIn("Invalid URL scheme", result["message"])

        calls = mock_span.set_status.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][0], StatusCode.ERROR)
        mock_span.record_exception.assert_called_once()

    @patch("observability.tools._TRACER")
    @patch("httpx.stream")
    def test_fetch_url_http_error(self, mock_stream: MagicMock, mock_tracer: MagicMock) -> None:
        """Verifies non-200 HTTP statuses return an error dict and record error on the span."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=mock_response
        )
        mock_stream.return_value.__enter__.return_value = mock_response

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            result = fetch_url(self.test_url)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["url"], self.test_url)
        self.assertIn("404", result["message"])

        mock_span.set_attribute.assert_any_call("response.status_code", 404)
        calls = mock_span.set_status.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][0], StatusCode.ERROR)
        mock_span.record_exception.assert_called_once()

    @patch("observability.tools._TRACER")
    @patch("httpx.stream")
    def test_fetch_url_exceeds_size_limit(
        self, mock_stream: MagicMock, mock_tracer: MagicMock
    ) -> None:
        """Verifies that exceeding the maximum byte cap returns an error dict."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        mock_response = MagicMock()
        mock_response.status_code = 200
        chunk_1mb = b"A" * 1024 * 1024
        mock_response.iter_bytes.return_value = [chunk_1mb] * 11  # 11MB total
        mock_stream.return_value.__enter__.return_value = mock_response

        with patch("opentelemetry.trace.get_current_span", return_value=mock_span):
            result = fetch_url(self.test_url)

        self.assertEqual(result["status"], "error")
        self.assertIn("exceeded maximum limit", result["message"])

        calls = mock_span.set_status.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][0], StatusCode.ERROR)
        mock_span.record_exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
