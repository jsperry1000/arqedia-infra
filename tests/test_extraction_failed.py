"""
What extraction could not finish, finished (EXT-02 case 3), and the
backstop for extraction that never started (case 4).

    python -m unittest discover -s tests

Extraction marks and refunds its own failures (test_extraction_failure.py).
These are about the ones it cannot catch - a timeout, an out-of-memory kill,
a crash at start-up - which reach lambda/extraction_failed as on-failure
invocation records. Decided 5 November 2026:

  * The document is marked failed, so the screen stops saying
    "extracting...", and refunded if it holds no values.
  * A document extraction already settled is left exactly as it is.
  * A refund that failed is retried on the next delivery, even though the
    row is already marked - by this function.
  * A message that cannot be handled goes back to the queue, by itself.

And for reconcile: a document charged an hour ago and never marked is named
on a [stuck] line while it is under two hours old, and only counted after;
one already refunded is not stuck.

Nothing reaches AWS: boto3 is replaced at import and every collaborator is a
stub.
"""

import importlib.util
import io
import json
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "lambda" / "shared"

TENANT = 7
DOC = 1229
ENTRY = 167
KEY = "tenants/7/ws/eng/file.pdf.normalized.json"


def fake_boto():
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")

    class ClientError(Exception):
        def __init__(self, code="NoSuchKey"):
            super().__init__(code)
            self.response = {"Error": {"Code": code}}
    exceptions.ClientError = ClientError
    botocore.exceptions = exceptions
    return {"boto3": boto3, "botocore": botocore,
            "botocore.exceptions": exceptions}


def load(path, name, env):
    saved = list(sys.path)
    with mock.patch.dict(sys.modules, fake_boto()), \
            mock.patch.dict(os.environ, env):
        sys.modules.pop("wallet", None)
        sys.path.insert(0, str(SHARED))
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = saved
    return module


DB = {"CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
      "DATABASE": "arqedia"}


def load_handler():
    return load(ROOT / "lambda" / "extraction_failed" / "app.py",
                "extraction_failed_app", DB)


def load_reconcile():
    return load(ROOT / "lambda" / "reconcile" / "app.py", "reconcile_app",
                dict(DB, DOCS_BUCKET="docs"))


def record(key=KEY, error="Task timed out after 300.00 seconds"):
    """An on-failure invocation record for the EventBridge event that
    started extraction."""
    event = {"detail-type": "Object Created", "source": "aws.s3",
             "detail": {"bucket": {"name": "review"},
                        "object": {"key": key}}}
    return {"version": "1.0",
            "requestContext": {"condition": "RetriesExhausted"},
            "requestPayload": event,
            "responseContext": {"functionError": "Unhandled"},
            "responsePayload": {"errorMessage": error}}


def cell(value):
    if value is None:
        return {"isNull": True}
    if isinstance(value, int):
        return {"longValue": value}
    return {"stringValue": value}


class Handler(unittest.TestCase):

    def setUp(self):
        self.app = load_handler()
        # The document as the database holds it.
        self.row = {"extracted_at": None, "extraction_error": None,
                    "values": 0, "entry": ENTRY}
        self.refunds = []
        self.envelope = {"tenant_id": TENANT, "document_id": DOC}

        def get_object(Bucket, Key):
            body = mock.MagicMock()
            body.read.return_value = json.dumps(self.envelope).encode()
            return {"Body": body}

        def sql(statement, params=None):
            s = " ".join(statement.split())
            if s.startswith("UPDATE document"):
                if (self.row["extracted_at"] is None
                        and self.row["extraction_error"] is None):
                    self.row["extracted_at"] = "now"
                    self.row["extraction_error"] = self.app.ERROR_DIED
                    return {"numberOfRecordsUpdated": 1}
                return {"numberOfRecordsUpdated": 0}
            if s.startswith("SELECT d.charge_entry_id"):
                return {"records": [[cell(self.row["entry"]),
                                     cell(self.row["values"]),
                                     cell(self.row["extraction_error"])]]}
            return {}

        def refund(tenant_id, document_id, entry, email=None):
            self.refunds.append((tenant_id, document_id, entry))
            return {"refunded": True, "amount_cents": 25, "repeated": False}

        for p in [
            mock.patch.object(self.app._s3, "get_object",
                              side_effect=get_object),
            mock.patch.object(self.app, "_sql", side_effect=sql),
            mock.patch.object(self.app.wallet, "refund", side_effect=refund),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def deliver(self, *records):
        with redirect_stdout(io.StringIO()):
            return self.app.lambda_handler({"Records": [
                {"messageId": "m%d" % i, "body": json.dumps(r)}
                for i, r in enumerate(records)]}, None)

    def test_a_document_that_died_reading_nothing_is_marked_and_refunded(self):
        out = self.deliver(record())
        self.assertEqual(out, {"batchItemFailures": []})
        self.assertEqual(self.row["extraction_error"], self.app.ERROR_DIED)
        self.assertEqual(self.refunds, [(TENANT, DOC, ENTRY)])

    def test_one_holding_values_is_marked_and_keeps_its_charge(self):
        """21 September: a document holding some values keeps its charge."""
        self.row["values"] = 4
        self.deliver(record())
        self.assertEqual(self.row["extraction_error"], self.app.ERROR_DIED)
        self.assertEqual(self.refunds, [])

    def test_one_extraction_settled_itself_is_left_alone(self):
        """Its run finished after all, or failed in the ordinary way and
        refunded there."""
        self.row.update(extracted_at="earlier", extraction_error=None)
        self.deliver(record())
        self.assertIsNone(self.row["extraction_error"])
        self.assertEqual(self.refunds, [])
        self.row.update(extraction_error="schema_failed")
        self.deliver(record())
        self.assertEqual(self.row["extraction_error"], "schema_failed")
        self.assertEqual(self.refunds, [])

    def test_a_refund_that_failed_is_tried_again_on_redelivery(self):
        """The row is marked before the refund. A second delivery finds it
        marked - by this function - and must still refund; the key makes a
        repeat harmless."""
        self.app.wallet.refund.side_effect = RuntimeError("db")
        out = self.deliver(record())
        self.assertEqual(out, {"batchItemFailures": [{"itemIdentifier": "m0"}]})
        self.assertEqual(self.row["extraction_error"], self.app.ERROR_DIED)

        given = []
        self.app.wallet.refund.side_effect = (
            lambda *a, **k: given.append(a) or {"refunded": True})
        self.assertEqual(self.deliver(record()), {"batchItemFailures": []})
        self.assertEqual(given, [(TENANT, DOC, ENTRY)])

    def test_not_an_envelope_touches_nothing(self):
        self.deliver(record(key="tenants/7/other.json"))
        self.assertIsNone(self.row["extraction_error"])
        self.assertEqual(self.refunds, [])

    def test_an_envelope_naming_no_document_touches_nothing(self):
        self.envelope = {"tenant_id": TENANT}
        self.deliver(record())
        self.assertIsNone(self.row["extraction_error"])
        self.assertEqual(self.refunds, [])

    def test_a_message_that_cannot_be_handled_goes_back_alone(self):
        calls = {"n": 0}
        real = self.app._s3.get_object.side_effect

        def flaky(Bucket, Key):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("s3")
            return real(Bucket, Key)
        self.app._s3.get_object.side_effect = flaky
        out = self.deliver(record(), record())
        self.assertEqual(out, {"batchItemFailures": [{"itemIdentifier": "m0"}]})
        self.assertEqual(self.refunds, [(TENANT, DOC, ENTRY)])


class Stuck(unittest.TestCase):
    """EXT-02 case 4: reported, never acted on."""

    def setUp(self):
        self.app = load_reconcile()
        self.asked = []

    def run_with(self, stuck_rows):
        def sql(statement, params=None):
            s = " ".join(statement.split())
            self.asked.append(s)
            if "FROM document d JOIN wallet_ledger" in s:
                return {"records": [[cell(t), cell(d), cell(st), cell(age)]
                                    for t, d, st, age in stuck_rows]}
            return {"records": []}
        out = io.StringIO()
        with mock.patch.object(self.app, "_sql", side_effect=sql), \
                mock.patch.object(self.app._s3, "list_objects_v2",
                                  return_value={"Contents": []}), \
                redirect_stdout(out):
            result = self.app.lambda_handler({}, None)
        return result, out.getvalue()

    def test_a_young_stuck_document_is_named(self):
        result, log = self.run_with([(5, DOC, "filed", 75)])
        self.assertIn("[stuck] tenant=5 doc=%d state=filed" % DOC, log)
        self.assertEqual((result["stuck"], result["stuck_reported"]), (1, 1))

    def test_an_old_one_is_counted_and_not_named(self):
        """So the alarm fires for a new one rather than staying in ALARM."""
        result, log = self.run_with([(5, DOC, "filed", 11687)])
        self.assertNotIn("[stuck] ", log)
        self.assertIn("stuck=1 stuck_reported=0", log)
        self.assertEqual(result["stuck_reported"], 0)

    def test_the_question_excludes_what_was_refunded_and_writes_nothing(self):
        self.run_with([])
        [question] = [s for s in self.asked if "wallet_ledger" in s]
        self.assertIn("CONCAT('refund:', d.document_id)", question)
        self.assertIn("NOT EXISTS", question)
        self.assertIn("extracted_at IS NULL", question)
        self.assertIn("extraction_error IS NULL", question)
        # The charge's time, not the upload's.
        self.assertIn("l.created_at", question)
        for s in self.asked:
            self.assertTrue(s.startswith("SELECT"), s)

    def test_the_summary_line_is_always_printed(self):
        _, log = self.run_with([])
        self.assertIn("[reconcile] ", log)
        self.assertIn("stuck=0 stuck_reported=0", log)


if __name__ == "__main__":
    unittest.main()
