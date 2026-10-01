"""
A share's two PDFs, and the watermark burned into them. Run from the
repository root:

    python -m unittest discover -s tests

The claims that matter:

  - share mode writes base.pdf and view.pdf under the grant's prefix and
    nothing else - no memo row, no memo pdf_key (the ordinary render would
    have overwritten the tenant's own PDF);
  - the recipient's address and the tenant are in every page's CONTENT, not
    in an annotation, so the mark is part of what the page draws;
  - a download stamps its time onto base.pdf, so a downloaded copy carries
    the download time and not the time it was shared.

NEEDS pypdf AND reportlab, the layer's pinned versions
(lambda/layers/docprocessing/requirements.txt). Skipped where they are not
installed, and the skip says so - an untested boundary is a gap, not a pass.
"""

import importlib
import io
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "lambda" / "render"
SHARED = ROOT / "lambda" / "shared"

try:
    import pypdf  # noqa: F401
    import reportlab  # noqa: F401
    HAVE_PDF = True
except ImportError:
    HAVE_PDF = False


def load_render():
    # Imported before sys.modules is patched. patch.dict restores the
    # dictionary on exit, and anything reportlab imports lazily inside the
    # block - reportlab.lib.sequencer among them - would be taken out again
    # and fail on first use.
    for name in ("pypdf", "reportlab.platypus", "reportlab.lib.sequencer",
                 "reportlab.pdfgen.canvas", "reportlab.lib.colors"):
        importlib.import_module(name)
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    env = {"CURATED_BUCKET": "curated", "BRAND_BUCKET": "brand",
           "CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
           "DATABASE": "arqedia"}
    saved = list(sys.path)
    with mock.patch.dict(sys.modules, {"boto3": boto3, "botocore": botocore,
                                       "botocore.exceptions": exceptions}), \
            mock.patch.dict(os.environ, env):
        for name in ("app", "style", "stamp"):
            sys.modules.pop(name, None)
        sys.path.insert(0, str(RENDER))
        sys.path.insert(1, str(SHARED))
        try:
            module = importlib.import_module("app")
            # _share imports stamp when it runs, after this has returned.
            stamp = importlib.import_module("stamp")
            return module, stamp
        finally:
            sys.path[:] = saved


def text_of(pdf_bytes):
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return [page.extract_text() for page in reader.pages]


def annotations_of(pdf_bytes):
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return [page.get("/Annots") for page in reader.pages]


@unittest.skipUnless(HAVE_PDF, "pypdf and reportlab are not installed")
class ShareRenderTest(unittest.TestCase):
    def setUp(self):
        self.app, self.stamp = load_render()
        self.app._s3 = mock.MagicMock()
        self.app._sql = mock.MagicMock()
        self.tenant = {"name": "TESTCO A", "plan": "base",
                       "brand_logo_key": None, "brand_deep": None,
                       "brand_mid": None, "brand_highlight": None,
                       "brand_light": None}
        self.app._tenant = lambda t: self.tenant
        self.app._memo = lambda t, m: {"bucket": "curated",
                                       "key": "tenants/1/memos/x/m.md",
                                       "generated_at": "now"}
        body = mock.MagicMock()
        body.read.return_value = self.app.PREVIEW_MARKDOWN.encode("utf-8")
        self.app._s3.get_object.return_value = {"Body": body}
        with mock.patch.dict(sys.modules, {"stamp": self.stamp}):
            self.result = self.app.lambda_handler({
                "tenant_id": 1, "memo_id": 11,
                "share": {"recipient_email": "j.ferrers@northbank.com",
                          "shared_at": "2026-10-01T14:03:22Z",
                          "prefix": "shares/1/11/" + "a" * 32 + "/"}}, None)
        self.puts = {c.kwargs["Key"]: c.kwargs["Body"]
                     for c in self.app._s3.put_object.call_args_list}

    def test_two_pdfs_under_the_prefix_and_nothing_else(self):
        prefix = "shares/1/11/" + "a" * 32 + "/"
        self.assertEqual(self.result["status"], "ok")
        self.assertEqual(sorted(self.puts),
                         [prefix + "base.pdf", prefix + "view.pdf"])

    def test_the_memo_row_and_its_pdf_are_not_touched(self):
        self.app._sql.assert_not_called()
        self.assertFalse(any(k.startswith("tenants/") for k in self.puts))

    def test_every_page_carries_the_recipient_and_the_tenant(self):
        for key, body in self.puts.items():
            for page in text_of(body):
                self.assertIn("j.ferrers@northbank.com", page, key)
                self.assertIn("TESTCO A", page, key)

    def test_the_view_says_when_it_was_shared_and_the_base_does_not(self):
        base = next(b for k, b in self.puts.items() if k.endswith("base.pdf"))
        view = next(b for k, b in self.puts.items() if k.endswith("view.pdf"))
        self.assertTrue(all("2026-10-01 14:03" in p for p in text_of(view)))
        self.assertFalse(any("2026-10-01 14:03" in p for p in text_of(base)))

    def test_burned_in_not_annotated(self):
        # The watermark adds no annotation: whatever the page had, it has.
        for body in self.puts.values():
            for annots in annotations_of(body):
                for a in (annots or []):
                    self.assertNotEqual(a.get_object().get("/Subtype"),
                                        "/Watermark")

    def test_a_download_carries_its_own_time(self):
        base = next(b for k, b in self.puts.items() if k.endswith("base.pdf"))
        line = self.stamp.downloaded_line("j.ferrers@northbank.com",
                                          "TESTCO A", "2026-11-02T09:15:00Z")
        downloaded = self.stamp.stamp(base, line=line)
        pages = text_of(downloaded)
        self.assertTrue(all("2026-11-02 09:15" in p for p in pages))
        self.assertFalse(any("2026-10-01 14:03" in p for p in pages))

    def test_a_prefix_outside_the_grant_is_refused(self):
        self.app._s3.reset_mock()
        with mock.patch.dict(sys.modules, {"stamp": self.stamp}):
            refused = self.app.lambda_handler({
                "tenant_id": 1, "memo_id": 11,
                "share": {"recipient_email": "x@y.com",
                          "shared_at": "2026-10-01T14:03:22Z",
                          "prefix": "tenants/1/memos/"}}, None)
        self.assertEqual(refused["status"], "bad-prefix")
        self.app._s3.put_object.assert_not_called()


if __name__ == "__main__":
    unittest.main()
