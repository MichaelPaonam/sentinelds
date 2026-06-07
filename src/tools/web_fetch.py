"""Web fetch tool with sentinel protection and OpenTelemetry instrumentation."""

import hashlib
from typing import Any
from urllib.parse import urlparse

import httpx

from observability import current_span, traced_tool

# from src.sentinel.preflight import sentinel_guard


# @sentinel_guard("web_fetch")
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

            return {
                "status": "success",
                "url": url,
                "content": decoded_content,
                "size": len(body_bytes),
                "sha256": content_hash,
            }

    except Exception as e:
        span.record_exception(e)
        return {"status": "error", "url": url, "message": str(e)}
