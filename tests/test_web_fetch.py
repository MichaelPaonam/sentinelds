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
            "src.sentinel.preflight.Sentinel.preflight", return_value=Verdict.ALLOW
        )
        self.mock_preflight = self.preflight_patcher.start()

    def tearDown(self) -> None:
        self.preflight_patcher.stop()

    @patch("src.tools.web_fetch.tracer")
    @patch("httpx.stream")
    def test_fetch_url_success(self, mock_stream: MagicMock, mock_tracer: MagicMock) -> None:
        """Verifies successful URL fetching and span attribute registration."""
        # Mock OTel span
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        # Mock HTTPX stream response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_bytes.return_value = [self.test_body]
        mock_stream.return_value.__enter__.return_value = mock_response

        # Execute
        result = fetch_url(self.test_url)

        # Assertions
        self.assertEqual(result, self.test_body.decode("utf-8"))

        # Verify trace span is created
        mock_tracer.start_as_current_span.assert_called_once_with("web_fetch")

        # Verify all mandatory span attributes are populated
        mock_span.set_attribute.assert_any_call("tool.name", "web_fetch")
        mock_span.set_attribute.assert_any_call("tool.args.url", self.test_url)
        mock_span.set_attribute.assert_any_call("http.url", self.test_url)
        mock_span.set_attribute.assert_any_call("egress.host", self.test_host)
        mock_span.set_attribute.assert_any_call("response.status_code", 200)
        mock_span.set_attribute.assert_any_call("response.size", len(self.test_body))
        mock_span.set_attribute.assert_any_call("response.body.hash", self.test_hash)

        # Verify span status
        mock_span.set_status.assert_called_once_with(StatusCode.OK)

    @patch("src.tools.web_fetch.tracer")
    @patch("httpx.stream")
    def test_fetch_url_http_error(self, mock_stream: MagicMock, mock_tracer: MagicMock) -> None:
        """Verifies non-200 HTTP statuses record error status on the span."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=mock_response
        )
        mock_stream.return_value.__enter__.return_value = mock_response

        # Execute & Assert
        with self.assertRaises(httpx.HTTPStatusError):
            fetch_url(self.test_url)

        # Assert span registers the error and attributes
        mock_span.set_attribute.assert_any_call("response.status_code", 404)
        # Verify error status was set (description format may vary)
        calls = mock_span.set_status.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][0], StatusCode.ERROR)
        self.assertIn("404", str(calls[0][1].get("description", "")))
        mock_span.record_exception.assert_called_once()

    @patch("src.tools.web_fetch.tracer")
    @patch("httpx.stream")
    def test_fetch_url_exceeds_size_limit(
        self, mock_stream: MagicMock, mock_tracer: MagicMock
    ) -> None:
        """Verifies that exceeding the maximum byte cap aborts and records error."""
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value.__enter__.return_value = mock_span

        mock_response = MagicMock()
        mock_response.status_code = 200
        # Simulated stream chunks adding up to >10MB
        chunk_1mb = b"A" * 1024 * 1024
        mock_response.iter_bytes.return_value = [chunk_1mb] * 11  # 11MB total
        mock_stream.return_value.__enter__.return_value = mock_response

        # Execute & Assert
        with self.assertRaises(ValueError) as context:
            fetch_url(self.test_url)

        self.assertIn("exceeded maximum limit", str(context.exception))

        # Assert span registers the size error
        mock_span.set_status.assert_called_once_with(
            StatusCode.ERROR, description=str(context.exception)
        )
        mock_span.record_exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
