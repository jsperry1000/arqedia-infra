"""
A section with no numeral is headed by its title alone (26 October 2026).
Run from the repository root:

    python -m unittest discover -s tests

Composition wrote "## {}. {}" whatever the numeral, so an unnumbered section
was stored as "## . Executive Summary" and the browser and the PDF both drew
the stop. What is tested: composition writes the title alone now and a
numbered heading as it was; Update still matches a section saved under the
old heading; and the PDF draws an old heading without the stop.

The PDF half NEEDS pypdf and reportlab, the layer's versions. Skipped where
they are not installed, and the skip says so.
"""

import io
import unittest
from unittest import mock

from test_section_prompt import load_composition
from test_share_render import HAVE_PDF, load_render

if HAVE_PDF:
    import pypdf


class Composition(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = load_composition()

    def test_no_numeral_is_the_title_alone(self):
        lines = self.app._section_lines(
            {"num": "", "title": "Executive Summary", "markdown": "Text."})
        self.assertEqual(lines[0], "## Executive Summary")

    def test_blank_numeral_is_no_numeral(self):
        self.assertEqual(self.app._section_heading("  ", "Risks"), "Risks")

    def test_a_gap_is_headed_the_same_way(self):
        lines = self.app._section_lines(
            {"num": "", "title": "Exit Strategy", "markdown": ""})
        self.assertEqual(lines[0], "## Exit Strategy")

    def test_a_numeral_is_kept_as_it_was(self):
        lines = self.app._section_lines(
            {"num": "IV", "title": "Returns", "markdown": "Text."})
        self.assertEqual(lines[0], "## IV. Returns")

    def test_update_matches_a_heading_saved_before(self):
        registry = mock.MagicMock()
        registry.has_template.return_value = True
        registry.sections_for.return_value = [
            {"key": "summary", "num": "", "title": "Executive Summary"},
            {"key": "returns", "num": "IV", "title": "Returns"},
        ]
        keys = self.app._keys_by_heading(registry, "t")
        norm = self.app._heading_norm
        self.assertEqual(keys[norm("## . Executive Summary")], "summary")
        self.assertEqual(keys[norm("## Executive Summary")], "summary")
        self.assertEqual(keys[norm("## IV. Returns")], "returns")


MEMO = """# Real Estate Investment Summary

| | |
|---|---|
| **Subject** | Meridian |

## . Executive Summary

Text.

## IV. Returns

More text.
"""


@unittest.skipUnless(HAVE_PDF, "pypdf and reportlab are not installed")
class Pdf(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.render, _ = load_render()

    def text(self):
        pdf = self.render._build({"name": "T", "plan": "base"}, MEMO)
        return "\n".join(p.extract_text()
                         for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)

    def test_old_heading_drawn_without_the_stop(self):
        text = self.text()
        self.assertIn("Executive Summary", text)
        self.assertNotIn(". Executive Summary", text)
        self.assertIn("IV. Returns", text)


if __name__ == "__main__":
    unittest.main()
