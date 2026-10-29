"""
A page break in the PDF (29 October 2026). Run from the repository root:

    python -m unittest discover -s tests

"<!-- page break -->" on a line of its own starts a new page, is never
printed, and never makes a blank page: straight after another, it starts
nothing.

NEEDS pypdf and reportlab, the layer's versions. Skipped where they are not
installed, and the skip says so.
"""

import io
import sys
import unittest
from unittest import mock

from test_share_render import HAVE_PDF, load_render

if HAVE_PDF:
    import pypdf

HEAD = """# Credit memorandum

| | |
|---|---|
| **Subject** | Example Limited |

"""


@unittest.skipUnless(HAVE_PDF, "pypdf and reportlab are not installed")
class RenderPageBreakTest(unittest.TestCase):
    def setUp(self):
        self.app, self.stamp = load_render()
        self.app._s3 = mock.MagicMock()
        self.app._sql = mock.MagicMock()
        self.app._tenant = lambda t: {
            "name": "TESTCO A", "plan": "base", "brand_logo_key": None,
            "brand_deep": None, "brand_mid": None, "brand_highlight": None,
            "brand_light": None}
        self.app._memo = lambda t, m: {"bucket": "curated", "key": "m.md",
                                       "generated_at": "now", "number": 10,
                                       "version": 2, "workspace": None}

    def pages(self, *lines):
        """The text of each page of the PDF, for a memo of HEAD and lines."""
        markdown = (HEAD + "\n".join(lines) + "\n").encode("utf-8")

        def get_object(Bucket, Key):                       # noqa: N803
            if Key != "m.md":
                raise self.app.ClientError("NoSuchKey")
            stream = mock.MagicMock()
            stream.read.return_value = markdown
            return {"Body": stream}

        self.app._s3.get_object.side_effect = get_object
        with mock.patch.dict(sys.modules, {"stamp": self.stamp}):
            self.app.lambda_handler({"tenant_id": 1, "memo_id": 11}, None)
        pdf = next(c.kwargs["Body"]
                   for c in self.app._s3.put_object.call_args_list
                   if c.kwargs["Key"].endswith(".pdf"))
        reader = pypdf.PdfReader(io.BytesIO(pdf))
        return [page.extract_text() for page in reader.pages]

    def test_it_starts_a_new_page_and_is_not_printed(self):
        pages = self.pages("## I. One", "", "First part.", "",
                           "<!-- page break -->", "",
                           "## II. Two", "", "Second part.")
        self.assertEqual(len(pages), 2)
        self.assertIn("First part.", pages[0])
        self.assertNotIn("Second part.", pages[0])
        self.assertIn("Second part.", pages[1])
        self.assertNotIn("page break", "\n".join(pages))

    def test_it_ends_the_paragraph_above_it(self):
        pages = self.pages("Before.", "<!-- page break -->", "After.")
        self.assertEqual(len(pages), 2)
        self.assertIn("Before.", pages[0])
        self.assertIn("After.", pages[1])

    def test_two_together_make_no_blank_page(self):
        pages = self.pages("Before.", "", "<!-- page break -->", "",
                           "<!-- page break -->", "", "After.")
        self.assertEqual(len(pages), 2)

    def test_indented_it_is_not_a_break(self):
        pages = self.pages("Before.", "", "  <!-- page break -->", "",
                           "After.")
        self.assertEqual(len(pages), 1)


if __name__ == "__main__":
    unittest.main()
