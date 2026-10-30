"""
An indent in the PDF (30 October 2026). Run from the repository root:

    python -m unittest discover -s tests

Two spaces a level at the start of a paragraph or a bullet move it in a step,
as the editor shows it; three levels at most, a tab counting as four. A line
with none prints where it always did.

NEEDS reportlab, the layer's version. Skipped where it is not installed, and
the skip says so.
"""

import unittest

from test_share_render import HAVE_PDF, load_render


@unittest.skipUnless(HAVE_PDF, "pypdf and reportlab are not installed")
class RenderIndentTest(unittest.TestCase):
    def setUp(self):
        self.app, _ = load_render()
        palette = self.app.style.palette_for({})
        self.styles = self.app.style.build_styles(palette)
        self.palette = palette

    def paragraphs(self, markdown):
        """Each paragraph drawn, as (its text's start, left indent, bullet
        indent or None)."""
        self.app._reset_citations()
        flow = self.app.to_flowables(markdown, self.styles, self.palette)
        out = []
        for f in flow:
            if isinstance(f, self.app.Paragraph):
                out.append((f.text[:12], f.style.leftIndent,
                            f.bulletText and f.style.bulletIndent))
        return out

    def test_a_paragraph_moves_a_step_a_level(self):
        body = self.styles["body"].leftIndent
        drawn = self.paragraphs("Flush.\n\n  One in.\n\n    Two in.\n")
        self.assertEqual([d[1] for d in drawn], [body, body + 18, body + 36])

    def test_a_bullet_under_a_bullet_is_drawn_under_it(self):
        bullet = self.styles["bullet"]
        drawn = self.paragraphs("- Top\n  - Under\n")
        self.assertEqual(drawn[0][1:], (bullet.leftIndent, bullet.bulletIndent))
        self.assertEqual(drawn[1][1:], (bullet.leftIndent + 18,
                                        bullet.bulletIndent + 18))

    def test_three_levels_at_most_and_a_tab_is_four_spaces(self):
        body = self.styles["body"].leftIndent
        drawn = self.paragraphs("\tTab.\n\n" + " " * 20 + "Deep.\n")
        self.assertEqual([d[1] for d in drawn], [body + 36, body + 54])

    def test_the_styles_themselves_are_untouched(self):
        self.paragraphs("    In.\n\n  - In.\n")
        self.assertEqual(self.styles["body"].leftIndent, 0)
        self.assertEqual(self.styles["bullet"].leftIndent, 15)


if __name__ == "__main__":
    unittest.main()
