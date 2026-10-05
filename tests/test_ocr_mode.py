"""
How a scan is read: text mode, and only when the layer is thin (decided
5 October 2026). Run from the repository root:

    python -m unittest discover -s tests

The configuration still says FORMS and always-OCR for twelve and four types;
these prove the API no longer obeys either, because both cost money for
output nothing reads (see the note above _start_ocr in lambda/api/app.py).
"""

import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 2
ENGAGEMENT = "MERIDIAN"


class Registry:
    """What config.for_tenant returns, configured the old way."""

    DOCUMENT_TYPES = {"audited-statements": {}}

    def read_mode_for(self, document_type):
        return "forms"

    def always_ocr(self, document_type):
        return True


class Db:
    """Answers the reads file_documents makes, and records every write."""

    def __init__(self, thin):
        self.thin = thin
        self.writes = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        if s.startswith("SELECT subject_name"):
            return rows(("Meridian Trading Ltd",))
        if s.startswith("SELECT document_id, filename, state"):
            return rows((7, "accounts.pdf", "analysed", None,
                         "audited-statements"))
        if s.startswith("SELECT s3_key, thin_text"):
            return rows(("tenants/2/docs/MERIDIAN/accounts.pdf", self.thin,
                         None, None))
        self.writes.append(s)
        return {"records": []}


class OcrModeTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def test_the_override_is_text_and_thin_only(self):
        self.assertEqual(self.app.OCR_READ_MODE, "text")
        self.assertTrue(self.app.OCR_ONLY_WHEN_THIN)

    def test_ocr_asks_textract_for_text_whatever_the_type_says(self):
        with mock.patch.object(self.app, "textract") as textract, \
                mock.patch.object(self.app, "_sql"):
            textract.start.return_value = ("job-1", "text")
            self.app._start_ocr(Registry(), TENANT, "k",
                                [(7, "audited-statements")])
        self.assertEqual(textract.start.call_args.kwargs["read_mode"], "text")

    def test_none_restores_the_configured_mode(self):
        """The undo is one name: OCR_READ_MODE = None."""
        with mock.patch.object(self.app, "textract") as textract, \
                mock.patch.object(self.app, "_sql"), \
                mock.patch.object(self.app, "OCR_READ_MODE", None):
            textract.start.return_value = ("job-1", "forms")
            self.app._start_ocr(Registry(), TENANT, "k",
                                [(7, "audited-statements")])
        self.assertEqual(textract.start.call_args.kwargs["read_mode"], "forms")

    def file(self, thin):
        db = Db(thin)
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "wallet") as wallet, \
                mock.patch.object(self.app, "config") as config, \
                mock.patch.object(self.app, "_s3") as s3, \
                mock.patch.object(self.app, "_start_ocr") as start_ocr:
            config.for_tenant.return_value = Registry()
            wallet.charge.return_value = {"entry_id": 5}
            s3.get_object.return_value = {
                "Body": mock.MagicMock(read=lambda: b"{}")}
            out = self.app.file_documents(
                TENANT, "clerk@firm.com", ENGAGEMENT,
                [{"document_id": 7}], "key-1")
        return out, start_ocr

    def test_a_usable_layer_is_filed_not_ocrd_despite_always_ocr(self):
        """22 of 24 such layers carried 92-100% of OCR's numbers on dev."""
        out, start_ocr = self.file(thin=False)
        start_ocr.assert_not_called()
        self.assertEqual(out["filed"], 1)
        self.assertEqual(out["reading"], 0)

    def test_a_thin_layer_still_goes_to_ocr(self):
        out, start_ocr = self.file(thin=True)
        start_ocr.assert_called_once()
        self.assertEqual(out["reading"], 1)


if __name__ == "__main__":
    unittest.main()
