"""OpenTelemetry tracing helpers and decorators for SentinelDS tools."""

import hashlib
import inspect
import json
import logging
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Iterator

from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode

logger = logging.getLogger("sentinelds.observability")
_TRACER = trace.get_tracer("sentinelds.tools")


def current_span() -> Span:
    """Returns the currently active OpenTelemetry span."""
    return trace.get_current_span()


@contextmanager
def tool_span(name: str, **attrs: Any) -> Iterator[Span]:
    """Context manager to start and manage a tool execution span.

    Args:
        name: Name of the span.
        **attrs: Key-value attributes to set on the span.
    """
    with _TRACER.start_as_current_span(name) as span:
        for k, v in attrs.items():
            span.set_attribute(k, v)
        yield span


def _record_span_args(
    span: Span, sig: inspect.Signature, name: str, args: tuple, kwargs: Dict[str, Any]
) -> None:
    """Helper to bind and record call arguments on a tool span."""
    try:
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        args_dict = dict(bound.arguments)
    except Exception as e:
        logger.warning("Failed to bind signature for tool '%s': %s", name, e)
        args_dict = {}

    span.set_attribute("tool.name", name)

    # Record scalar args or their types. None and non-scalars only get a type marker
    # because Span.set_attribute does not accept None or arbitrary objects.
    for param_name, val in args_dict.items():
        if isinstance(val, (bool, int, float, str)):
            span.set_attribute(f"tool.args.{param_name}", val)
        else:
            span.set_attribute(f"tool.args.{param_name}.type", type(val).__name__)

    # Compute a unique hash of the tool's inputs for traceability/reproducibility
    try:
        serialized = json.dumps(args_dict, sort_keys=True, default=str)
        arg_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        span.set_attribute("tool.args.hash", arg_hash)
    except Exception as e:
        logger.warning("Failed to serialize arguments for hashing in tool '%s': %s", name, e)


def _handle_result(span: Span, result: Any, record_return_status: bool) -> None:
    """Helper to evaluate the returned result and set span status."""
    if record_return_status:
        if isinstance(result, dict):
            # Check for error signals
            status = result.get("status")
            error_val = result.get("error") or result.get("message")

            if status == "error" or error_val is not None:
                msg = str(error_val) if error_val else "Tool returned error status"
                span.set_status(StatusCode.ERROR, description=msg)
                return

        span.set_status(StatusCode.OK)
    else:
        span.set_status(StatusCode.OK)


def traced_tool(
    name: str,
    *,
    record_args: bool = True,
    record_return_status: bool = True,
) -> Callable:
    """Decorator to automatically wrap a tool function with an OpenTelemetry span.

    Args:
        name: The name of the tool/span to record.
        record_args: Whether to automatically log arguments and their hash.
        record_return_status: Whether to inspect the return dictionary to flag errors.
    """

    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with _TRACER.start_as_current_span(name) as span:
                if record_args:
                    _record_span_args(span, sig, name, args, kwargs)
                try:
                    result = func(*args, **kwargs)
                    _handle_result(span, result, record_return_status)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(StatusCode.ERROR, description=str(e))
                    raise e

        return sync_wrapper

    return decorator
