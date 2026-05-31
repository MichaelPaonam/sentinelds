import hashlib
from urllib.parse import urlparse

import httpx
from opentelemetry import trace

# Create a tracer for sentinelds tools
tracer = trace.get_tracer("sentinelds.tools")


def fetch_url(url: str) -> str:
    """Fetches the content of a specified URL.

    This tool is used by the Research Agent to retrieve the text content of
    web pages.

    Args:
        url: The absolute HTTP/HTTPS URL of the page to fetch.

    Returns:
        The fetched web page content as a plain text string.
    """
    # Parse the host for the Davis AI baselining/detection
    parsed_url = urlparse(url)
    host = parsed_url.hostname or parsed_url.netloc or ""

    # Start a manual OTel span named "web_fetch" per requirements
    with tracer.start_as_current_span("web_fetch") as span:
        # Set mandatory span attributes (docs/agents-exploit-scenarios.md §A1.3)
        span.set_attribute("tool.name", "web_fetch")
        span.set_attribute("tool.args.url", url)
        span.set_attribute("http.url", url)
        span.set_attribute("egress.host", host)

        try:
            # Enforce network timeout (10s) and streaming-based max size limit (10MB)
            timeout = httpx.Timeout(10.0)
            max_bytes = 10 * 1024 * 1024  # 10 MB

            with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
                status_code = response.status_code
                span.set_attribute("response.status_code", status_code)

                # Raise an error for non-success statuses (e.g. 404, 500)
                response.raise_for_status()

                body_bytes = b""
                for chunk in response.iter_bytes():
                    body_bytes += chunk
                    if len(body_bytes) > max_bytes:
                        raise ValueError(
                            f"Response content size exceeded maximum limit of {max_bytes} bytes."
                        )

                # Compute the SHA-256 hash of the response content
                content_hash = hashlib.sha256(body_bytes).hexdigest()
                span.set_attribute("response.size", len(body_bytes))
                span.set_attribute("response.body.hash", content_hash)

                # Decode the response content safely as UTF-8
                decoded_content = body_bytes.decode("utf-8", errors="replace")

                span.set_status(trace.StatusCode.OK)
                return decoded_content

        except Exception as e:
            # Mark the span as errored and record the exception
            span.set_status(trace.StatusCode.ERROR, description=str(e))
            span.record_exception(e)
            raise e
