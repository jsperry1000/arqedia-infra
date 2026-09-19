"""
No upload ends in silence. Run from the repository root:

    python -m unittest discover -s tests

Every exit below the fetch must write a terminal row. The tests that matter
most are the ones proving a row WAS written, because the defect being closed
is an exit that wrote nothing - a refused file left no trace, and the review
screen waited ten minutes for something no process would ever create.
"""

import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

KEY = "tenants/9/docs/Test-Engagement-One/Manty-SA-Articles.pdf"


def load_normalizer():
    """The normalizer, with boto3, config, extractors and segment replaced.

    extractors is a real module object rather than a MagicMock because the
    handler catches extractors.UnreadableDocument by identity: a mock would
    give a different class each time and the except clause would not fire."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions

    extractors = types.ModuleType("extractors")

    class UnreadableDocument(Exception):
        def __init__(self, reason, pages=None, chars=None):
            super().__init__(reason)
            self.reason = reason
            self.pages = pages
            self.chars = chars

    extractors.UnreadableDocument = UnreadableDocument
    extractors.extract = mock.MagicMock()

    config = types.ModuleType("config")
    config.active_revision = mock.MagicMock(return_value=7)
    config.load = mock.MagicMock()

    segment = types.ModuleType("segment")
    segment.segment = mock.MagicMock(return_value=([], {}))

    env = {"REVIEW_BUCKET": "review", "CLUSTER_ARN": "arn:cluster",
           "SECRET_ARN": "arn:secret", "DATABASE": "arqedia"}
    modules = {"boto3": boto3, "botocore": botocore,
               "botocore.exceptions": exceptions, "extractors": extractors,
               "config": config, "segment": segment}
    with mock.patch.dict(sys.modules, modules), mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "normalizer_app", ROOT / "lambda/normalizer/app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, extractors


def plain(value):
    return None if "isNull" in value else next(iter(value.values()))


class FakeDb:
    def __init__(self):
        self.statements = []

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        self.statements.append((s, {p["name"]: plain(p["value"])
                                    for p in params or []}))
        return {"records": []}

    def inserts(self):
        return [(s, v) for s, v in self.statements
                if s.startswith("INSERT INTO document")]


def event(key=KEY):
    return {"detail": {"bucket": {"name": "docs"}, "object": {"key": key}}}


class RefusalTest(unittest.TestCase):
    def setUp(self):
        self.app, self.extractors = load_normalizer()
        self.db = FakeDb()
        body = mock.MagicMock()
        body.read.return_value = b"%PDF-1.4 not really"
        self.app._s3.get_object.return_value = {
            "Body": body, "VersionId": "v1",
            "Metadata": {"uploaded-by": "walk1@deus-ex.co"},
        }

    def run_handler(self):
        with mock.patch.object(self.app, "_sql", self.db.sql):
            return self.app.lambda_handler(event(), None)

    def refuse_with(self, reason, pages=None, chars=None):
        self.extractors.extract.side_effect = \
            self.extractors.UnreadableDocument(reason, pages, chars)
        return self.run_handler()

    def row(self):
        inserts = self.db.inserts()
        self.assertEqual(len(inserts), 1, "expected exactly one row")
        return inserts[0][1]

    # --- a row is written, whatever the reason -----------------------------

    def test_a_corrupt_file_writes_a_row(self):
        self.refuse_with("pdf-parse-failed: something broke")
        values = self.row()
        self.assertEqual(values["code"], "pdf_parse_failed")
        self.assertIn("carries nothing readable", values["reason"])

    def test_an_empty_file_writes_a_row(self):
        self.refuse_with("no-pages")
        values = self.row()
        self.assertEqual(values["code"], "no_pages")
        self.assertIn("carries nothing readable", values["reason"])

    def test_an_unexpected_exception_writes_a_row(self):
        self.extractors.extract.side_effect = RuntimeError("boom")
        result = self.run_handler()
        values = self.row()
        self.assertEqual(values["code"], "error")
        self.assertIn("Nothing was charged", values["reason"])
        self.assertEqual(result["status"], "unreadable")

    def test_an_unexpected_exception_is_not_re_raised(self):
        # Re-raising would have EventBridge retry twice and write three rows
        # for one file.
        self.extractors.extract.side_effect = RuntimeError("boom")
        self.run_handler()  # must not raise

    def test_a_failure_after_extraction_still_writes_a_row(self):
        # The point of wrapping the whole of _analyse: an exit that writes
        # nothing is the defect, and a fifth one must not be possible.
        self.extractors.extract.return_value = ("text", [{"index": 1}], "pdf")
        self.app.config.load.side_effect = RuntimeError("registry died")
        self.run_handler()
        self.assertEqual(self.row()["code"], "error")

    # --- what the row says -------------------------------------------------

    def test_the_row_is_terminal_and_identifies_the_file(self):
        self.refuse_with("no-pages")
        sent, values = self.db.inserts()[0]
        self.assertIn("'unreadable'", sent)
        self.assertEqual(values["tenant_id"], 9)
        self.assertEqual(values["filename"], "Manty-SA-Articles.pdf")
        self.assertEqual(values["s3_key"], KEY)
        self.assertEqual(values["uploaded_by"], "walk1@deus-ex.co")
        self.assertEqual(values["config_revision"], 7)

    def test_no_envelope_is_written_for_a_refusal(self):
        # There is no text to put in one, and nothing downstream reads it.
        # A SCAN is the opposite case and must have one - see ScanTest.
        self.refuse_with("no-pages")
        self.app._s3.put_object.assert_not_called()

    def test_an_unknown_reason_becomes_error_rather_than_a_new_code(self):
        self.refuse_with("something-nobody-has-seen")
        self.assertEqual(self.row()["code"], "error")

    def test_the_error_prefix_is_the_one_stage_5_filters_on(self):
        self.extractors.extract.side_effect = RuntimeError("boom")
        with mock.patch("builtins.print") as printed:
            self.run_handler()
        said = " ".join(str(c.args[0]) for c in printed.call_args_list if c.args)
        self.assertIn("[normalizer-error]", said)

    # --- the success path is untouched -------------------------------------

    def test_a_readable_document_writes_no_refusal(self):
        self.extractors.extract.return_value = ("plenty of text", [], "pdf")
        self.app.segment.segment.return_value = (
            [{"part_index": 1, "page_from": None, "page_to": None,
              "document_type": "invoice", "confidence": "high", "why": "x"}],
            {})
        result = self.run_handler()
        self.assertEqual(result["status"], "ok")
        for _, values in self.db.inserts():
            self.assertIsNone(values.get("code"))


class ScanTest(unittest.TestCase):
    """no_text_layer is not a refusal any more. It is a document with no type
    yet, bound for OCR at filing (decision record, 18 September, item 3)."""

    def setUp(self):
        self.app, self.extractors = load_normalizer()
        self.db = FakeDb()
        body = mock.MagicMock()
        body.read.return_value = b"%PDF-1.4 a scan"
        self.app._s3.get_object.return_value = {
            "Body": body, "VersionId": "v1",
            "Metadata": {"uploaded-by": "walk1@deus-ex.co"},
        }
        self.extractors.extract.side_effect =             self.extractors.UnreadableDocument("no_text_layer", pages=12,
                                               chars=340)

    def run_handler(self):
        with mock.patch.object(self.app, "_sql", self.db.sql):
            return self.app.lambda_handler(event(), None)

    def row(self):
        inserts = self.db.inserts()
        self.assertEqual(len(inserts), 1, "expected exactly one row")
        return inserts[0]

    def test_it_is_fileable_not_refused(self):
        # state travels as a bound parameter here, unlike the refusal INSERT
        # which inlines 'unreadable'.
        result = self.run_handler()
        sent, values = self.row()
        self.assertEqual(result["status"], "scan")
        self.assertEqual(values["state"], "analysed")
        self.assertNotIn("'unreadable'", sent)

    def test_thin_text_is_set_so_filing_sends_it_to_ocr(self):
        # This is the flag file_documents reads to choose OCR. Without it the
        # scan would go to extraction and yield nothing.
        self.run_handler()
        self.assertEqual(self.row()[1]["thin_text"], 1)

    def test_no_type_is_proposed(self):
        # Nothing to classify from. A type guessed from a filename would put a
        # guess where a reading belongs.
        self.run_handler()
        values = self.row()[1]
        self.assertIsNone(values["document_type"])
        self.assertIsNone(values["type_confidence"])

    def test_classification_is_skipped_entirely(self):
        self.run_handler()
        self.app.segment.segment.assert_not_called()
        values = self.row()[1]
        self.assertIsNone(values["classify_tokens_in"])
        self.assertIsNone(values["classify_tokens_out"])

    def test_the_reason_goes_in_type_reason_not_refusal(self):
        # A scan is not a refusal. refusal_* stays for the three that are.
        self.run_handler()
        sent, values = self.row()
        self.assertEqual(values["type_reason"], self.app.SCAN_REASON)
        self.assertIn("A scan, no readable text", values["type_reason"])
        self.assertNotIn("refusal_code", sent)
        self.assertNotIn("refusal_reason", sent)

    def test_the_measured_counts_are_kept(self):
        # The gate had both numbers when it refused and used to discard them,
        # leaving the screen saying "? pages" about a file it had counted.
        self.run_handler()
        values = self.row()[1]
        self.assertEqual(values["page_count"], 12)
        self.assertEqual(values["char_count"], 340)

    def test_an_envelope_is_written_and_it_is_empty(self):
        # The collector READS this object when OCR finishes and overwrites its
        # fields. Without it the job completes with nowhere to put the result.
        self.run_handler()
        self.app._s3.put_object.assert_called_once()
        body = self.app._s3.put_object.call_args.kwargs["Body"]
        envelope = json.loads(body.decode("utf-8"))
        self.assertEqual(envelope["raw_text"], "")
        self.assertEqual(envelope["units"], [])
        self.assertTrue(envelope["thin_text"])
        self.assertIsNone(envelope["document_type"])

    def test_one_part_and_no_page_range(self):
        self.run_handler()
        values = self.row()[1]
        self.assertEqual(values["part_index"], 1)
        self.assertIsNone(values["page_from"])
        self.assertIsNone(values["page_to"])



if __name__ == "__main__":
    unittest.main()
