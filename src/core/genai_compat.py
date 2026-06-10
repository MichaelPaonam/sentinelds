"""Drop part_metadata from A2A→GenAI Parts when running on Vertex.

Vertex's google-genai client raises:
  "part_metadata parameter is only supported in Gemini Developer API mode,
   not in Gemini Enterprise Agent Platform mode."

ADK's A2A inbound converter sets this field on every Part it builds (see
google.adk.a2a.converters.part_converter.convert_a2a_part_to_genai_part),
which breaks every A2A turn on Vertex. This module patches that out at two
layers so neither layer is enough on its own:

1. **Module-attribute rewrite** — replace
   ``part_converter.convert_a2a_part_to_genai_part`` with a wrapper that
   nulls ``out.part_metadata``. This catches any caller that does
   ``part_converter.convert_a2a_part_to_genai_part(...)`` lookup-per-call.

2. **Default-argument rewrite** — three ADK modules
   (``request_converter``, ``event_converter``, ``long_running_functions``)
   capture the original function as a function default arg at *def* time:

       def fn(..., part_converter = convert_a2a_part_to_genai_part):

   Default args bind to the function object that exists when the ``def``
   statement runs — which happened the moment that module was imported by
   ADK. Module-attribute rewrite alone does NOT update those captured
   defaults; we have to rewrite each function's ``__defaults__`` tuple in
   place. We also rebind the module-level alias copied by
   ``from .part_converter import convert_a2a_part_to_genai_part`` so any
   ``module.func`` lookup or fallback expression sees the patched version.

Side-effect on import: ``install()`` runs at module import time. Idempotent —
safe to import from multiple entry points. Activated only when
``GOOGLE_GENAI_USE_VERTEXAI`` is truthy; on the Developer API path the
metadata is preserved as ADK intends.

**Import order matters.** Import this module BEFORE any ``google.adk.a2a``
symbol. Because the patch reaches into ADK's consumer modules and rewrites
their ``__defaults__`` tuples, importing it after ``to_a2a`` /
``get_fast_api_app`` / ``RemoteA2aAgent`` *also* works in principle — but
importing it first keeps the failure surface obvious and the patched state
symmetric across runs.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("sentinelds.genai_compat")

_PATCH_FLAG = "_sentinelds_part_metadata_stripped"


def _is_vertex() -> bool:
    return os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")


def _make_patched(original):
    """Return a wrapper that calls *original* and nulls part_metadata on the
    returned Part. The flag attribute lets repeat calls to install() detect
    that the wrapper is already in place."""

    def _patched(a2a_part):
        out = original(a2a_part)
        if out is not None:
            try:
                out.part_metadata = None
            except Exception:
                # Pydantic model_config may forbid assignment on some versions;
                # fall back to model_copy with update.
                out = out.model_copy(update={"part_metadata": None})
        return out

    setattr(_patched, _PATCH_FLAG, True)
    return _patched


def _rewrite_defaults_for(module, original, patched) -> int:
    """Rewrite every function in *module* whose ``__defaults__`` contains
    *original* so the slot points at *patched* instead.

    Handles three layouts:

    * **Plain function** — rewrite ``func.__defaults__`` directly.
    * **functools.wraps decorator** (e.g. ADK's ``@a2a_experimental``) —
      the outer wrapper takes ``(*args, **kwargs)`` and has no defaults of
      its own; the original function with defaults is reachable via
      ``func.__wrapped__``. We chase the ``__wrapped__`` chain until we hit
      something whose ``__defaults__`` contains the original.
    * **Method on a class** — same shape as plain function or wrapped
      function; ``dir(module)`` surfaces classes too, but their methods
      live on the class, not the module. We do not recurse into classes
      here because ADK's three consumer modules expose all their captured
      defaults at module scope (verified against ADK 1.x; if a future
      release moves a default into a class method we'll need to extend).

    Returns the number of function defaults rewritten. install() logs this
    count so a drift between ADK versions is visible.
    """
    rewritten = 0
    seen_ids = set()

    for attr_name in dir(module):
        attr = getattr(module, attr_name, None)
        if attr is None:
            continue

        # Walk the wrapper chain. functools.wraps sets ``__wrapped__``.
        target = attr
        depth = 0
        while target is not None and depth < 8:
            target_id = id(target)
            if target_id in seen_ids:
                break
            seen_ids.add(target_id)

            defaults = getattr(target, "__defaults__", None)
            if defaults and original in defaults:
                new_defaults = tuple(
                    patched if d is original else d for d in defaults
                )
                try:
                    target.__defaults__ = new_defaults  # type: ignore[attr-defined]
                    rewritten += 1
                except Exception as exc:
                    logger.warning(
                        "genai_compat: could not rewrite defaults on "
                        "%s.%s (depth=%d): %s",
                        module.__name__,
                        attr_name,
                        depth,
                        exc,
                    )

            # Climb to the wrapped function if any.
            target = getattr(target, "__wrapped__", None)
            depth += 1

    return rewritten


def install() -> None:
    if not _is_vertex():
        return

    # 1. Wrap the public converter.
    from google.adk.a2a.converters import part_converter as _pc

    if getattr(_pc.convert_a2a_part_to_genai_part, _PATCH_FLAG, False):
        return  # already patched — idempotent

    original = _pc.convert_a2a_part_to_genai_part
    patched = _make_patched(original)
    _pc.convert_a2a_part_to_genai_part = patched

    # 2. Force-import the three ADK consumer modules that capture this
    #    function as a default arg or module-level binding, then rewrite
    #    the captured copies.
    #
    #    * ``request_converter`` and ``event_converter`` use ``original`` as
    #      a function default — their ``def`` ran at import time and bound
    #      the original. We must rewrite their ``__defaults__`` tuples.
    #    * ``long_running_functions`` uses ``original`` at instance __init__
    #      via ``part_converter or convert_a2a_part_to_genai_part``. The
    #      module-level name still points at the original until we rebind
    #      it here (the ``from .part_converter import ...`` copies the
    #      reference into the module's globals at import time).
    from google.adk.a2a.converters import (  # noqa: PLC0415
        event_converter as _ec,
    )
    from google.adk.a2a.converters import (  # noqa: PLC0415
        long_running_functions as _lrf,
    )
    from google.adk.a2a.converters import (  # noqa: PLC0415
        request_converter as _rc,
    )

    total_defaults = 0
    for consumer in (_rc, _ec, _lrf):
        # Rebind the module-level alias so any ``module.func`` lookup or
        # ``part_converter or convert_a2a_part_to_genai_part`` fallback uses
        # the patched version.
        if getattr(consumer, "convert_a2a_part_to_genai_part", None) is original:
            consumer.convert_a2a_part_to_genai_part = patched
        # Rewrite captured function defaults.
        total_defaults += _rewrite_defaults_for(consumer, original, patched)

    logger.info(
        "genai_compat: part_metadata stripping installed "
        "(rewrote %d ADK function default(s))",
        total_defaults,
    )


install()
