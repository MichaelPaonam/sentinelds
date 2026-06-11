"""Web fetch tool with sentinel protection and OpenTelemetry instrumentation."""

import asyncio
import hashlib
from typing import Any
from urllib.parse import urlparse

import httpx

from core.config import settings
from observability import current_span, traced_tool
from sentinel.injection_detector import check_and_emit
from sentinel.preflight import Sentinel, sentinel_gate
from sentinel.session import get_sentinel_session


@sentinel_gate("web_fetch")
@traced_tool("web_fetch")
def fetch_url(url: str) -> dict[str, Any]:
    """Fetches the content of a specified URL.

    This tool is used by the Research Agent to retrieve the text content of
    web pages.

    Args:
        url: The absolute HTTP/HTTPS URL of the page to fetch.

    Returns:
        On success: {"status": "success", "url": url, "content": str, "size": int, "sha256": str}
        On error:   {"status": "error",   "url": url, "message": str}
    """
    parsed_url = urlparse(url)
    host = parsed_url.hostname or parsed_url.netloc or ""

    span = current_span()
    span.set_attribute("http.url", url)
    span.set_attribute("egress.host", host)

    try:
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL scheme. Only HTTP and HTTPS are supported: {url}")

        timeout = httpx.Timeout(10.0)
        max_bytes = 10 * 1024 * 1024  # 10 MB

        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
            status_code = response.status_code
            span.set_attribute("response.status_code", status_code)

            response.raise_for_status()

            body_bytes = b""
            for chunk in response.iter_bytes():
                body_bytes += chunk
                if len(body_bytes) > max_bytes:
                    raise ValueError(
                        f"Response content size exceeded maximum limit of {max_bytes} bytes."
                    )

            content_hash = hashlib.sha256(body_bytes).hexdigest()
            span.set_attribute("response.size", len(body_bytes))
            span.set_attribute("response.body.hash", content_hash)

            decoded_content = body_bytes.decode("utf-8", errors="replace")

            # Scan for prompt-injection signatures in the fetched content.
            workspace_id = getattr(settings, "DYNATRACE_WORKSPACE_ENTITY_ID", "WORKSPACE-1")
            dt_url = settings.DYNATRACE_API_URL or ""
            dt_token = (
                settings.DYNATRACE_API_TOKEN.get_secret_value()
                if settings.DYNATRACE_API_TOKEN
                else ""
            )
            span_ctx = span.get_span_context()
            try:
                span_id_hex = format(span_ctx.span_id, "016x") if span_ctx else ""
            except (TypeError, ValueError):
                span_id_hex = ""

            injection_matches = check_and_emit(
                decoded_content,
                span_id=span_id_hex,
                workspace_entity_id=workspace_id,
                source_url=url,
                dynatrace_api_url=dt_url or None,
                dynatrace_api_token=dt_token or None,
            )
            if injection_matches:
                categories = list({m.category for m in injection_matches})
                span.set_attribute("prompt.injection_signature", ", ".join(sorted(categories)))
                span.set_attribute("prompt.injection_match_count", len(injection_matches))

                # Notify the active SentinelSession so the next tool call halts.
                sess = get_sentinel_session()
                if sess is not None:
                    try:
                        asyncio.run(Sentinel.notify(sess, "injection.candidate"))
                    except RuntimeError:
                        # Already inside a running loop (rare for this sync tool).
                        sess.compromised = True
                        sess.compromise_reason = "injection.candidate"

            return {
                "status": "success",
                "url": url,
                "content": decoded_content,
                "size": len(body_bytes),
                "sha256": content_hash,
                "injection_matches": [
                    {"category": m.category, "excerpt_hash": m.excerpt_hash}
                    for m in injection_matches
                ],
            }

    except Exception as e:
        span.record_exception(e)
        return {"status": "error", "url": url, "message": str(e)}
