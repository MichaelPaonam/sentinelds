"""Drop ``part_metadata`` from every ``google.genai.types.Part`` on Vertex.

Vertex's google-genai client raises:

    "part_metadata parameter is only supported in Gemini Developer API mode,
     not in Gemini Enterprise Agent Platform mode."

The field's own description in google-genai confirms it: *"This field is not
supported in Vertex AI."* ADK's A2A inbound path nonetheless populates it
(``google.adk.a2a.converters.part_converter.convert_a2a_part_to_genai_part``
copies the A2A part's metadata onto the GenAI ``Part``), so every A2A turn on
Vertex crashes when the request is serialized for the Vertex endpoint.

Earlier versions of this module surgically rewrote the captured copies of
``convert_a2a_part_to_genai_part`` in three ADK consumer modules
(``request_converter``, ``event_converter``, ``long_running_functions``).
That covered the A2A-inbound path but missed at least three other call
sites that also bind the converter as a function default or Pydantic field
default at class-definition time:

* ``google.adk.a2a.converters.to_adk_event`` — five functions whose
  ``part_converter`` default fires on the inbound A2A → ADK Part conversion
  that feeds the LLM call (the path actually shown in the production
  traceback).
* ``google.adk.a2a.executor.config.A2aAgentExecutorConfig.a2a_part_converter``
  and ``google.adk.a2a.agent.config`` — Pydantic field defaults captured
  at class-creation time.

Rather than chase ADK's internal call graph version by version, this module
patches ``Part`` itself: every ``Part`` constructed in this process has
``part_metadata`` nulled. That is strictly broader than the per-consumer
rewrite, removes the dependency on ADK's internal layout, and survives ADK
upgrades that introduce new call sites.

The patch is activated only when ``GOOGLE_GENAI_USE_VERTEXAI`` is truthy; on
the Developer API path the field is preserved as ADK and google-genai
intend. Idempotent — safe to import from multiple entry points.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("sentinelds.genai_compat")

_PATCH_FLAG = "_sentinelds_part_metadata_stripped"


def _is_vertex() -> bool:
    return os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")


def install() -> None:
    if not _is_vertex():
        return

    from google.genai import types as _gt  # noqa: PLC0415

    if getattr(_gt.Part, _PATCH_FLAG, False):
        return  # already patched — idempotent

    original_init = _gt.Part.__init__

    def patched_init(self, *args, **kwargs):
        # Strip both the snake_case and camelCase aliases before construction
        # so Pydantic never validates a non-None value into the field.
        kwargs.pop("part_metadata", None)
        kwargs.pop("partMetadata", None)
        original_init(self, *args, **kwargs)
        # Defensive: if a caller built the Part via ``model_validate`` /
        # ``model_construct`` and bypassed ``__init__`` kwargs, force the
        # field to ``None`` after the fact. ``object.__setattr__`` sidesteps
        # any ``model_config = ConfigDict(frozen=True)`` that future
        # google-genai releases might add.
        try:
            object.__setattr__(self, "part_metadata", None)
        except Exception:
            pass

    _gt.Part.__init__ = patched_init  # type: ignore[method-assign,assignment]
    setattr(_gt.Part, _PATCH_FLAG, True)

    logger.info("genai_compat: Part.__init__ patched to null part_metadata on Vertex")


install()
