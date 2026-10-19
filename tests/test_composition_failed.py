"""
What composition could not finish, finished (UX02 20.2).

    python -m unittest discover -s tests

Composition catches its own failures (20.1, test_generate_refund.py). These
are about the ones it cannot: a timeout, an out-of-memory kill, a crash at
start-up. Each arrives at lambda/composition_failed as an on-failure
invocation record, and what these assert is what decided on 19 October 2026:

  * A generation that died with no memo row is refunded and its run written
    failed. One that died after the row is not refunded - the memo opens.
  * An Update that died is refunded and its run written failed.
  * A rewrite that died has its row written failed, and is not charged.
  * Only what is still running is touched: a second delivery, or a run that
    finished in the meantime, changes nothing.
  * A message that cannot be handled goes back to the queue, by itself.
  * The three copies of where a run is kept agree.

Nothing reaches AWS: boto3 is replaced at import and every collaborator is a
stub.
"""

import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from api_modules import load_api, rows
from test_section_prompt import load_composition

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "lambda" / "shared"

TENANT = 7
ENGAGEMENT_ID = 42
ENTRY = 50
RUN = "c" * 32
EMAIL = "a@firm.com"
GEN_KEY = "tenants/7/runs/generate/42/%s.json" % RUN
UPD_KEY = "tenants/7/updates/memos/120/%s.json" % RUN


def load_handler():
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
    env = {"CURATED_BUCKET": "curated", "CLUSTER_ARN": "arn:cluster",
           "SECRET_ARN": "arn:secret", "DATABASE": "arqedia"}
    fakes = {"boto3": boto3, "botocore": botocore,
             "botocore.exceptions": exceptions}
    saved = list(sys.path)
    with mock.patch.dict(sys.modules, fakes), mock.patch.dict(os.environ, env):
        sys.modules.pop("wallet", None)
        sys.path.insert(0, str(SHARED))
        try:
            spec = importlib.util.spec_from_file_location(
                "composition_failed_app",
                ROOT / "lambda" / "composition_failed" / "app.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = saved
    return module


def record(payload, error="Task timed out after 900.00 seconds"):
    """An on-failure invocation record, as Lambda sends one to SQS."""
    return {"version": "1.0", "timestamp": "2026-10-19T12:00:00Z",
            "requestContext": {"requestId": "r-1",
                               "condition": "RetriesExhausted",
                               "approximateInvokeCount": 1},
            "requestPayload": payload,
            "responseContext": {"statusCode": 200,
                                "functionError": "Unhandled"},
            "responsePayload": {"errorMessage": error}}


def generation(**over):
    payload = {"tenant_id": TENANT, "engagement": "Meridian",
               "engagement_id": ENGAGEMENT_ID, "template_key": "credit",
               "generated_by": EMAIL, "entry_id": ENTRY, "run": RUN}
    payload.update(over)
    return payload


class Handler(unittest.TestCase):

    def setUp(self):
        self.app = load_handler()
        self.stored = {}
        self.puts = []
        self.refunds = []
        self.statements = []

        def get_object(Bucket, Key):
            if Key not in self.stored:
                raise self.app.ClientError("NoSuchKey")
            body = mock.MagicMock()
            body.read.return_value = json.dumps(self.stored[Key]).encode()
            return {"Body": body}

        def put_object(Bucket, Key, Body, ContentType):
            state = json.loads(Body.decode("utf-8"))
            self.stored[Key] = state
            self.puts.append((Key, state))

        def refund(tenant_id, entry_id, email=None):
            self.refunds.append((tenant_id, entry_id, email))
            return {"refunded": True, "amount_cents": 100, "repeated": False}

        def sql(statement, params=None):
            self.statements.append((" ".join(statement.split()),
                                    {p["name"]: next(iter(p["value"].values()))
                                     for p in params or []}))
            return {"numberOfRecordsUpdated": 1}

        for p in [
            mock.patch.object(self.app._s3, "get_object",
                              side_effect=get_object),
            mock.patch.object(self.app._s3, "put_object",
                              side_effect=put_object),
            mock.patch.object(self.app.wallet, "refund_generation",
                              side_effect=refund),
            mock.patch.object(self.app, "_sql", side_effect=sql),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def deliver(self, *records):
        return self.app.lambda_handler({"Records": [
            {"messageId": "m%d" % i, "body": json.dumps(r)}
            for i, r in enumerate(records)]}, None)

    # --- a generation ------------------------------------------------------

    def test_a_generation_that_died_before_its_memo_is_refunded(self):
        self.stored[GEN_KEY] = {"status": "running", "run": RUN,
                                "entry_id": ENTRY}
        out = self.deliver(record(generation()))
        self.assertEqual(out, {"batchItemFailures": []})
        self.assertEqual(self.refunds, [(TENANT, ENTRY, EMAIL)])
        state = self.stored[GEN_KEY]
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["refunded"])
        self.assertEqual(state["amount_cents"], 100)
        self.assertEqual(state["error"], self.app.GENERATE_FAULT)
        self.assertIn("timed out", state["died"])

    def test_a_generation_that_died_after_its_memo_is_not_refunded(self):
        """Decided 19 October: the memo exists and opens."""
        self.stored[GEN_KEY] = {"status": "running", "run": RUN,
                                "memo_id": 901}
        self.deliver(record(generation()))
        self.assertEqual(self.refunds, [])
        state = self.stored[GEN_KEY]
        self.assertEqual(state["status"], "done")
        self.assertTrue(state["incomplete"])

    def test_a_run_that_has_no_record_yet_is_still_refunded(self):
        """The API's first write failed, or composition crashed before any
        of its own. The charge is in the event."""
        self.deliver(record(generation()))
        self.assertEqual(len(self.refunds), 1)
        self.assertEqual(self.stored[GEN_KEY]["status"], "failed")

    def test_a_finished_run_is_left_as_it_is(self):
        for status in ("done", "failed"):
            self.stored[GEN_KEY] = {"status": status, "run": RUN}
            self.puts.clear()
            self.deliver(record(generation()))
            self.assertEqual(self.puts, [], status)
        self.assertEqual(self.refunds, [])

    def test_a_generation_without_a_run_refunds_nothing(self):
        """Invoked by hand: whether a memo was written cannot be told."""
        self.deliver(record(generation(run=None)))
        self.assertEqual(self.refunds, [])
        self.assertEqual(self.puts, [])

    # --- an Update and a rewrite -------------------------------------------

    def test_an_update_that_died_is_refunded(self):
        self.stored[UPD_KEY] = {"status": "running", "run": RUN}
        self.deliver(record({"action": "update", "tenant_id": TENANT,
                             "memo_id": 120, "run": RUN, "entry_id": ENTRY,
                             "requested_by": EMAIL, "config_revision": 9}))
        self.assertEqual(self.refunds, [(TENANT, ENTRY, EMAIL)])
        state = self.stored[UPD_KEY]
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["error"], self.app.UPDATE_FAULT)
        self.assertTrue(state["refunded"])

    def test_a_finished_update_is_left_as_it_is(self):
        self.stored[UPD_KEY] = {"status": "done", "run": RUN}
        self.deliver(record({"action": "update", "tenant_id": TENANT,
                             "memo_id": 120, "run": RUN, "entry_id": ENTRY}))
        self.assertEqual(self.refunds, [])
        self.assertEqual(self.puts, [])

    def test_a_rewrite_that_died_is_written_failed_and_not_charged(self):
        self.deliver(record({"action": "rewrite", "tenant_id": TENANT,
                             "rewrite_id": 77}))
        self.assertEqual(self.refunds, [])
        [(statement, values)] = self.statements
        self.assertIn("UPDATE memo_rewrite", statement)
        # Only a row still running.
        self.assertIn("status = 'running'", statement)
        self.assertEqual(values["r"], 77)
        self.assertEqual(values["error"], self.app.REWRITE_FAULT)

    # --- the queue ---------------------------------------------------------

    def test_a_message_that_cannot_be_handled_goes_back_alone(self):
        self.app.wallet.refund_generation.side_effect = RuntimeError("db")
        out = self.deliver(
            record({"action": "rewrite", "tenant_id": TENANT,
                    "rewrite_id": 77}),
            record(generation()))
        self.assertEqual(out, {"batchItemFailures": [{"itemIdentifier": "m1"}]})
        # The rewrite in the same batch was still handled.
        self.assertEqual(len(self.statements), 1)
        # And the run was not written failed with no refund behind it.
        self.assertNotIn(GEN_KEY, self.stored)


class KeysAgree(unittest.TestCase):
    """Where a run is kept is written three times. They must not drift."""

    def test_the_three_copies_agree(self):
        handler, api, comp = load_handler(), load_api(), load_composition()
        self.assertEqual(handler._generate_key(7, 42, RUN),
                         api._generate_key(7, 42, RUN))
        self.assertEqual(handler._generate_key(7, 42, RUN),
                         comp._generate_key(7, 42, RUN))
        self.assertEqual(handler._update_key(7, 120, RUN),
                         api._update_key(7, 120, RUN))
        self.assertEqual(handler._update_key(7, 120, RUN),
                         comp._update_key(7, 120, RUN))


class RowWrittenAtOnce(unittest.TestCase):
    """Composition says the memo exists the moment its row does, so a death
    afterwards is not refunded."""

    def test_the_run_names_the_memo_while_still_running(self):
        app = load_composition()
        puts = []
        with mock.patch.object(app._s3, "get_object",
                               side_effect=app.ClientError("NoSuchKey")), \
                mock.patch.object(app._s3, "put_object",
                                  side_effect=lambda **k: puts.append(
                                      json.loads(k["Body"].decode()))), \
                mock.patch.object(app.wallet, "refund_generation"):
            def compose(ev, written):
                written["row"] = True
                written["memo_id"] = 902
                written["on_row"](902)
                # Seen as the handler would see it, had the function died
                # here.
                self.assertEqual(puts[-1]["status"], "running")
                self.assertEqual(puts[-1]["memo_id"], 902)
                return {"status": "ok", "memo_id": 902}
            with mock.patch.object(app, "_compose_memo", side_effect=compose):
                app.lambda_handler(generation(), None)
        self.assertEqual(puts[-1]["status"], "done")


if __name__ == "__main__":
    unittest.main()
