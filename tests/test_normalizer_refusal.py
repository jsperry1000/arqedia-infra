"""
No upload ends in silence. Run from the repository root:

    python -m unittest discover -s tests

Every exit below the fetch must write a terminal row. The tests that matter
most are the ones proving a row WAS written, because the defect being closed
is an exit that wrote nothing - a refused file left no trace, and the review
screen waited ten minutes for something no process would ever create.
"""

import importlib.util
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
        def __init__(self, reason):
            super().__init__(reason)
            self.reason = reason

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

    def refuse_with(self, reason):
        self.extractors.extract.side_effect = \
            self.extractors.UnreadableDocument(reason)
        return self.run_handler()

    def row(self):
        inserts = self.db.inserts()
        self.assertEqual(len(inserts), 1, "expected exactly one row")
        return inserts[0][1]

    # --- a row is written, whatever the reason -----------------------------

    def test_a_scan_writes_a_row(self):
        result = self.refuse_with("no_text_layer")
        values = self.row()
        self.assertEqual(values["code"], "no_text_layer")
        self.assertIn("scan", values["reason"])
        self.assertIn("OCR process on your side", values["reason"])
        self.assertEqual(result["status"], "unreadable")

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
        self.refuse_with("no_text_layer")
        sent, values = self.db.inserts()[0]
        self.assertIn("'unreadable'", sent)
        self.assertEqual(values["tenant_id"], 9)
        self.assertEqual(values["filename"], "Manty-SA-Articles.pdf")
        self.assertEqual(values["s3_key"], KEY)
        self.assertEqual(values["uploaded_by"], "walk1@deus-ex.co")
        self.assertEqual(values["config_revision"], 7)

    def test_no_envelope_is_written(self):
        # There is no text to put in one, and nothing downstream reads it.
        self.refuse_with("no_text_layer")
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


if __name__ == "__main__":
    unittest.main()
