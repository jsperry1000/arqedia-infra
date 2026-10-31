"""
Bold and italic at once in the PDF (31 October 2026). Run from the
repository root:

    python -m unittest discover -s tests

"***text***" is drawn bold and italic, and plain bold and italic beside it
are drawn as they always were. Each paragraph must build: a mismatched tag
is refused by ReportLab and the passage falls back to plain words.

NEEDS reportlab, the layer's version. Skipped where it is not installed, and
the skip says so.
"""

import unittest

from test_share_render import HAVE_PDF, load_render


@unittest.skipUnless(HAVE_PDF, "pypdf and reportlab are not installed")
class RenderBoldItalicTest(unittest.TestCase):
    def setUp(self):
        self.app, _ = load_render()
        self.app._reset_citations()
        palette = self.app.style.palette_for({})
        self.styles = self.app.style.build_styles(palette)

    def markup(self, text):
        out = self.app._inline(text)
        # It must build, or the reader gets the fallback instead.
        self.app.Paragraph(out, self.styles["body"])
        return out

    def test_three_either_side_is_bold_and_italic(self):
        self.assertEqual(self.markup("a ***key term*** here"),
                         "a <b><i>key term</i></b> here")

    def test_bold_and_italic_alone_are_unchanged(self):
        self.assertEqual(self.markup("**bold** and *slant*"),
                         "<b>bold</b> and <i>slant</i>")

    def test_bold_hard_against_bold_italic_either_way(self):
        self.assertEqual(self.markup("**a*****b***"),
                         "<b>a</b><b><i>b</i></b>")
        self.assertEqual(self.markup("***a*****b**"),
                         "<b><i>a</i></b><b>b</b>")

    def test_a_citation_beside_it_is_still_numbered(self):
        out = self.markup("***Note.*** Drawn. *a.pdf, page 2*")
        self.assertTrue(out.startswith("<b><i>Note.</i></b> Drawn."))
        self.assertIn("<super>", out)
        self.assertNotIn("a.pdf", out)


if __name__ == "__main__":
    unittest.main()
