"""Tests for the genai_compat Vertex part_metadata patch.

The bug we're guarding against: ADK's A2A inbound converter populates
``Part.part_metadata`` from the A2A part's metadata, but Vertex's google-genai
client raises:

    "part_metadata parameter is only supported in Gemini Developer API mode,
     not in Gemini Enterprise Agent Platform mode."

genai_compat patches ``google.genai.types.Part.__init__`` so every Part
constructed in this process under Vertex mode has ``part_metadata`` nulled.
This is broader than the previous per-consumer-module rewrite — it covers
``to_adk_event``, executor/agent config defaults, and any future ADK call
sites without us having to enumerate them.
"""

from __future__ import annotations

import os
import unittest


class TestPartPatchOnVertex(unittest.TestCase):
    """The Part patch should null part_metadata when Vertex mode is on."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        # Importing core.genai_compat installs the patch as a side effect.
        from core import genai_compat  # noqa: F401, PLC0415

    def test_kwarg_snake_case_stripped(self) -> None:
        from google.genai import types  # noqa: PLC0415

        p = types.Part(text="hi", part_metadata={"foo": "bar"})
        self.assertIsNone(p.part_metadata)
        self.assertEqual(p.text, "hi")

    def test_kwarg_camel_case_stripped(self) -> None:
        from google.genai import types  # noqa: PLC0415

        p = types.Part(text="hi", partMetadata={"foo": "bar"})
        self.assertIsNone(p.part_metadata)

    def test_model_validate_stripped(self) -> None:
        """``model_validate`` bypasses ``__init__`` kwargs; the post-init
        ``object.__setattr__`` must catch this path too."""
        from google.genai import types  # noqa: PLC0415

        p = types.Part.model_validate({"text": "hi", "partMetadata": {"a": 1}})
        self.assertIsNone(p.part_metadata)

    def test_adk_inbound_converter_yields_clean_part(self) -> None:
        """ADK's ``convert_a2a_part_to_genai_part`` is the actual production
        culprit — it copies A2A metadata onto the Part. After our patch, the
        returned Part should have ``part_metadata=None``."""
        import a2a.types as a2a_types  # noqa: PLC0415
        from google.adk.a2a.converters.part_converter import (  # noqa: PLC0415
            convert_a2a_part_to_genai_part,
        )

        a2a_part = a2a_types.Part(root=a2a_types.TextPart(text="hello", metadata={"a2a": "meta"}))
        genai_part = convert_a2a_part_to_genai_part(a2a_part)
        self.assertIsNotNone(genai_part)
        self.assertIsNone(genai_part.part_metadata)
        self.assertEqual(genai_part.text, "hello")

    def test_install_is_idempotent(self) -> None:
        """Calling install() repeatedly must not double-wrap ``__init__``."""
        from google.genai import types  # noqa: PLC0415

        from core import genai_compat  # noqa: PLC0415

        before = types.Part.__init__
        genai_compat.install()
        genai_compat.install()
        self.assertIs(types.Part.__init__, before)


if __name__ == "__main__":
    unittest.main()
