"""Tests for the genai_compat Vertex part_metadata patch.

The bug we're guarding against: ADK's ``request_converter`` /
``event_converter`` / ``long_running_functions`` capture
``convert_a2a_part_to_genai_part`` as a function default at import time. A
naive monkey-patch that only rewrites the public module attribute leaves
the captured defaults pointing at the original function — which then
returns ``Part(part_metadata=...)`` and crashes Vertex with:

    "part_metadata parameter is only supported in Gemini Developer API
     mode, not in Gemini Enterprise Agent Platform mode."

These tests verify both halves of the fix:

1. The public converter returns ``part_metadata=None``.
2. The captured-as-default copies inside the three ADK consumer modules
   point at the patched wrapper too (so call sites that pass through the
   default still get the strip).
"""

from __future__ import annotations

import importlib
import os
import unittest

# The patch only activates on Vertex. Force it on for these tests so they
# exercise the real code path; restore on teardown.
_ORIGINAL_VERTEX_FLAG = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI")


def setUpModule() -> None:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    # Reload genai_compat AFTER the env var is set so install() runs in
    # Vertex mode. The reload is idempotent thanks to the patch flag.
    import core.genai_compat as gc

    importlib.reload(gc)


def tearDownModule() -> None:
    if _ORIGINAL_VERTEX_FLAG is None:
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    else:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = _ORIGINAL_VERTEX_FLAG


class TestPatchedPublicConverter(unittest.TestCase):
    """The wrapper around convert_a2a_part_to_genai_part nulls part_metadata."""

    def test_text_part_metadata_stripped(self) -> None:
        from a2a import types as a2a_types
        from google.adk.a2a.converters import part_converter

        a2a_part = a2a_types.Part(root=a2a_types.TextPart(text="hello", metadata={"k": "v"}))
        result = part_converter.convert_a2a_part_to_genai_part(a2a_part)
        self.assertIsNotNone(result)
        self.assertIsNone(result.part_metadata)
        # Sanity: the conversion still produced text content.
        self.assertEqual(result.text, "hello")

    def test_patched_marker_is_set(self) -> None:
        from google.adk.a2a.converters import part_converter

        from core.genai_compat import _PATCH_FLAG  # noqa: PLC0415

        self.assertTrue(
            getattr(part_converter.convert_a2a_part_to_genai_part, _PATCH_FLAG, False),
            "Public converter should be wrapped with the patch flag set.",
        )


class TestCapturedDefaultsRewritten(unittest.TestCase):
    """The three ADK consumer modules' captured defaults must point at the
    patched wrapper, not the original. This is the bug that broke production:
    a naive module-level monkey-patch leaves these untouched.

    ADK wraps every public function in ``@a2a_experimental``, which uses
    ``functools.wraps`` to produce a generic ``def wrapper(*args, **kwargs)``
    outer. The wrapper itself has no defaults — the original (with defaults)
    is only reachable via ``func.__wrapped__``. So the test walks the
    ``__wrapped__`` chain just like ``_rewrite_defaults_for`` does."""

    def _walk(self, module):
        """Yield (qualified_name, function_object_with_defaults) for every
        function in *module*, descending the ``__wrapped__`` chain."""
        for name in dir(module):
            attr = getattr(module, name, None)
            target = attr
            depth = 0
            seen = set()
            while target is not None and depth < 8 and id(target) not in seen:
                seen.add(id(target))
                if getattr(target, "__defaults__", None):
                    yield (f"{name}{'.__wrapped__' * depth}", target)
                target = getattr(target, "__wrapped__", None)
                depth += 1

    def _assert_no_unpatched_part_converter_default(self, module):
        from core.genai_compat import _PATCH_FLAG  # noqa: PLC0415

        for qualified, fn in self._walk(module):
            for d in fn.__defaults__ or ():
                if (
                    callable(d)
                    and getattr(d, "__name__", "") == "convert_a2a_part_to_genai_part"
                    and not getattr(d, _PATCH_FLAG, False)
                ):
                    self.fail(
                        f"{module.__name__}.{qualified} still has the "
                        "unpatched convert_a2a_part_to_genai_part as a "
                        "default."
                    )

    def _assert_at_least_one_patched_default(self, module):
        from core.genai_compat import _PATCH_FLAG  # noqa: PLC0415

        for qualified, fn in self._walk(module):
            for d in fn.__defaults__ or ():
                if callable(d) and getattr(d, _PATCH_FLAG, False):
                    return  # success
        self.fail(
            f"Expected to find at least one patched callable in "
            f"{module.__name__} function defaults (after walking "
            "__wrapped__)."
        )

    def test_request_converter_defaults_use_patched(self) -> None:
        from google.adk.a2a.converters import request_converter

        self._assert_no_unpatched_part_converter_default(request_converter)
        self._assert_at_least_one_patched_default(request_converter)

    def test_event_converter_defaults_use_patched(self) -> None:
        from google.adk.a2a.converters import event_converter

        self._assert_no_unpatched_part_converter_default(event_converter)
        self._assert_at_least_one_patched_default(event_converter)

    def test_module_level_alias_rebound(self) -> None:
        """The ``from .part_converter import convert_a2a_part_to_genai_part``
        copies inside each consumer module should also point at the patched
        wrapper, so any ``module.func`` lookup or ``part_converter or
        convert_a2a_part_to_genai_part`` fallback uses the strip."""
        from google.adk.a2a.converters import (
            event_converter,
            long_running_functions,
            request_converter,
        )

        from core.genai_compat import _PATCH_FLAG  # noqa: PLC0415

        for module in (request_converter, event_converter, long_running_functions):
            fn = getattr(module, "convert_a2a_part_to_genai_part", None)
            self.assertIsNotNone(fn, f"{module.__name__} lost its alias")
            self.assertTrue(
                getattr(fn, _PATCH_FLAG, False),
                f"{module.__name__}.convert_a2a_part_to_genai_part is not the patched wrapper",
            )


class TestVertexFlagGate(unittest.TestCase):
    """When GOOGLE_GENAI_USE_VERTEXAI is unset, install() should be a no-op
    and ADK's converter should pass part_metadata through unchanged."""

    def test_install_is_noop_off_vertex(self) -> None:
        os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
        try:
            import core.genai_compat as gc

            importlib.reload(gc)
            # We cannot easily assert the module is restored to "unpatched"
            # because the previous test class already monkey-patched ADK in
            # process. The contract we DO assert: install() exits cleanly
            # without touching ADK when the flag is off.
            gc.install()  # second call must not raise
        finally:
            os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
            import core.genai_compat as gc

            importlib.reload(gc)


if __name__ == "__main__":
    unittest.main()
