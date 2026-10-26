"""
A person's own image in the PDF (graphics-insert, feature/graphics-pdf). Run
from the repository root:

    python -m unittest discover -s tests

What is tested is the renderer: the image line becomes a drawn image read
from the memo's own prefix, at a size the page can hold; a missing or false
file costs its place and not the memorandum; and a share carries the image as
the ordinary render does.

NEEDS pypdf, reportlab and Pillow, the layer's versions. Skipped where they
are not installed, and the skip says so.
"""

import io
import sys
import unittest
from unittest import mock

from test_share_render import HAVE_PDF, load_render

if HAVE_PDF:
    import pypdf
    from PIL import Image as PILImage

PNG = "a" * 32 + ".png"
JPG = "b" * 32 + ".jpg"


def picture(fmt, size=(480, 160)):
    out = io.BytesIO()
    PILImage.new("RGB", size, (31, 58, 104)).save(out, fmt)
    return out.getvalue()


MEMO = """# Credit memorandum

| | |
|---|---|
| **Subject** | Example Limited |

## I. Summary

The group is shown below. *accounts.pdf, page 1*
![The group structure](image:%s)
And the paragraph after it.

![](image:%s)
""" % (PNG, JPG)


@unittest.skipUnless(HAVE_PDF, "pypdf, reportlab and Pillow are not installed")
class RenderImagesTest(unittest.TestCase):
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
        self.files = {"m.md": MEMO.encode("utf-8"),
                      "tenants/1/images/memos/11/" + PNG: picture("PNG"),
                      "tenants/1/images/memos/11/" + JPG: picture("JPEG")}
        self.asked = []

        def get_object(Bucket, Key):                       # noqa: N803
            self.asked.append(Key)
            if Key not in self.files:
                raise self.app.ClientError("NoSuchKey")
            body = mock.MagicMock()
            body.read.return_value = self.files[Key]
            return {"Body": body}

        self.app._s3.get_object.side_effect = get_object

    def render(self, share=None):
        event = {"tenant_id": 1, "memo_id": 11}
        if share:
            event["share"] = share
        with mock.patch.dict(sys.modules, {"stamp": self.stamp}):
            self.app.lambda_handler(event, None)
        puts = {c.kwargs["Key"]: c.kwargs["Body"]
                for c in self.app._s3.put_object.call_args_list}
        return puts

    def pdf(self, share=None):
        puts = self.render(share)
        body = next(b for k, b in puts.items()
                    if k.endswith("view.pdf" if share else ".pdf"))
        return pypdf.PdfReader(io.BytesIO(body))

    def images(self, reader):
        return [img for page in reader.pages for img in page.images]

    def text(self, reader):
        return "\n".join(page.extract_text() for page in reader.pages)

    def test_each_image_is_drawn_from_the_memos_own_prefix(self):
        reader = self.pdf()
        self.assertEqual(len(self.images(reader)), 2)
        self.assertIn("tenants/1/images/memos/11/" + PNG, self.asked)
        self.assertIn("tenants/1/images/memos/11/" + JPG, self.asked)

    def test_the_line_is_not_printed_as_text(self):
        text = self.text(self.pdf())
        self.assertNotIn("image:", text)
        self.assertNotIn("![", text)
        # The paragraph either side of it is still there, as two.
        self.assertIn("The group is shown below.", text)
        self.assertIn("And the paragraph after it.", text)

    def test_a_missing_image_costs_its_place_not_the_memorandum(self):
        del self.files["tenants/1/images/memos/11/" + JPG]
        reader = self.pdf()
        self.assertEqual(len(self.images(reader)), 1)
        self.assertIn("could not be shown", self.text(reader))

    def test_a_file_that_is_not_its_type_is_not_drawn(self):
        self.files["tenants/1/images/memos/11/" + PNG] = b"<html>no</html>"
        reader = self.pdf()
        self.assertEqual(len(self.images(reader)), 1)
        self.assertIn("could not be shown", self.text(reader))

    def test_an_image_wider_than_the_page_is_brought_down_to_it(self):
        self.files["tenants/1/images/memos/11/" + PNG] = picture(
            "PNG", (4000, 1000))
        flow = self.app._image(self.files["tenants/1/images/memos/11/" + PNG],
                               PNG, mock.MagicMock())
        self.assertAlmostEqual(flow.drawWidth, self.app.style.CONTENT_WIDTH)
        self.assertAlmostEqual(flow.drawHeight,
                               self.app.style.CONTENT_WIDTH / 4)

    def test_a_tall_image_is_held_under_the_page(self):
        tall = picture("PNG", (400, 4000))
        flow = self.app._image(tall, PNG, mock.MagicMock())
        self.assertAlmostEqual(flow.drawHeight, self.app._IMAGE_MAX_HEIGHT)
        self.assertAlmostEqual(flow.drawWidth, self.app._IMAGE_MAX_HEIGHT / 10)

    def test_a_share_carries_the_images_as_the_render_does(self):
        reader = self.pdf({"recipient_email": "j@northbank.com",
                           "shared_at": "2026-10-26T14:00:00Z",
                           "prefix": "shares/1/11/" + "c" * 32 + "/"})
        self.assertEqual(len(self.images(reader)), 2)

    def test_a_preview_reads_no_images(self):
        self.asked.clear()
        with mock.patch.dict(sys.modules, {"stamp": self.stamp}):
            self.app.lambda_handler({"tenant_id": 1, "preview": True}, None)
        self.assertFalse(any("/images/" in k for k in self.asked))


if __name__ == "__main__":
    unittest.main()
