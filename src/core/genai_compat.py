"""Drop part_metadata from A2A→GenAI Parts when running on Vertex.

Vertex's google-genai client raises:
  "part_metadata parameter is only supported in Gemini Developer API mode,
   not in Gemini Enterprise Agent Platform mode."
ADK's A2A inbound converter sets this field on every Part it builds (see
google.adk.a2a.converters.part_converter.convert_a2a_part_to_genai_part),
which breaks every A2A turn on Vertex.

This module wraps that converter so the returned Part has its `part_metadata`
cleared before it can reach the Vertex Part-to-protobuf converter. The reverse
direction (genai→a2a) only reads the field, so no patch is needed there.

Side-effect on import: `install()` runs at module import time. Idempotent —
safe to import from multiple entry points. Activated only when
GOOGLE_GENAI_USE_VERTEXAI is truthy; on the Developer API path the metadata
is preserved as ADK intends.
"""

from __future__ import annotations

import os

_PATCH_FLAG = "_sentinelds_part_metadata_stripped"


def _is_vertex() -> bool:
    return os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")


def install() -> None:
    if not _is_vertex():
        return

    from google.adk.a2a.converters import part_converter as _pc

    if getattr(_pc.convert_a2a_part_to_genai_part, _PATCH_FLAG, False):
        return  # already patched

    _orig = _pc.convert_a2a_part_to_genai_part

    def _patched(a2a_part):
        out = _orig(a2a_part)
        if out is not None:
            try:
                out.part_metadata = None
            except Exception:
                # Pydantic model_config may forbid assignment on some versions;
                # fall back to model_copy with update.
                out = out.model_copy(update={"part_metadata": None})
        return out

    setattr(_patched, _PATCH_FLAG, True)
    _pc.convert_a2a_part_to_genai_part = _patched


install()
