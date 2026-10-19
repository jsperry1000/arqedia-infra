"""
A generation that writes no memo gives its charge back (UX02 20.1).

    python -m unittest discover -s tests

On 24 September a composition failed three times on Bedrock, the event was
dropped, and the dollar stayed taken with nothing on screen. What these are
about, in the order decided on 19 October 2026:

  * Composition never raises on a generation. A failure is written to the
    run and refunded; Lambda does not retry and spend the model again.
  * No memo row, a refund. A memo row, no refund - the memo opens.
  * The run records how it ended, so the screen can say so.
  * The API refunds where composition could not be started at all, and a
    repeated click is given the run it already paid for.
  * Update follows the same rule: a failed run is refunded, a run that
    finished with some sections failed is not.

Nothing reaches AWS: boto3 is replaced at import and every collaborator is a
stub. Whether the refund itself is right - once, what was paid, a new bucket
- is test_refund.py's.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows
from test_section_prompt import load_composition

TENANT = 7
ENGAGEMENT_ID = 42
ENTRY = 50
RUN = "b" * 32
EMAIL = "a@firm.com"
KEY = "tenants/7/runs/generate/42/%s.json" % RUN


def event(**over):
    base = {"tenant_id": TENANT, "engagement": "Meridian",
            "engagement_id": ENGAGEMENT_ID, "template_key": "credit",
            "generated_by": EMAIL, "entry_id": ENTRY, "run": RUN}
    base.update(over)
    return base


class Generation(unittest.TestCase):
    """composition's _generate, around a stubbed _compose_memo."""

    def setUp(self):
        self.app = load_composition()
        self.puts = []
        self.stored = None
        self.refunds = []

        def get_object(Bucket, Key):
            if self.stored is not None and Key == KEY:
                body = mock.MagicMock()
                body.read.return_value = json.dumps(self.stored).encode()
                return {"Body": body}
            raise self.app.ClientError("NoSuchKey")

        def refund(tenant_id, entry_id, email=None):
            self.refunds.append((tenant_id, entry_id, email))
            return {"refunded": True, "amount_cents": 100, "repeated": False}

        for p in [
            mock.patch.object(self.app._s3, "get_object",
                              side_effect=get_object),
            mock.patch.object(self.app._s3, "put_object",
                              side_effect=lambda **k: self.puts.append(k)),
            mock.patch.object(self.app.wallet, "refund_generation",
                              side_effect=refund),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def run_with(self, compose, ev=None):
        with mock.patch.object(self.app, "_compose_memo",
                               side_effect=compose) as composed:
            result = self.app.lambda_handler(ev or event(), None)
        state = (json.loads(self.puts[-1]["Body"].decode("utf-8"))
                 if self.puts else None)
        return result, state, composed

    # --- no memo, a refund -------------------------------------------------

    def test_a_model_failure_is_refunded_and_not_raised(self):
        def compose(ev, written):
            raise RuntimeError("ServiceUnavailableException")
        result, state, _ = self.run_with(compose)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.refunds, [(TENANT, ENTRY, EMAIL)])
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["refunded"])
        self.assertEqual(state["amount_cents"], 100)
        self.assertEqual(state["error"], self.app.GENERATE_FAULT)
        self.assertEqual(self.puts[-1]["Key"], KEY)

    def test_nothing_to_write_from_is_refunded_and_says_why(self):
        result, state, _ = self.run_with(
            lambda ev, written: {"status": "no-values"})
        self.assertEqual(result["status"], "no-values")
        self.assertEqual(len(self.refunds), 1)
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["error"],
                         self.app.GENERATE_REFUSED["no-values"])

    def test_a_refund_that_throws_is_reported_as_not_refunded(self):
        self.app.wallet.refund_generation.side_effect = RuntimeError("db")

        def compose(ev, written):
            raise RuntimeError("boom")
        result, state, _ = self.run_with(compose)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(state["refunded"])

    # --- a memo, no refund -------------------------------------------------

    def test_a_memo_written_is_not_refunded(self):
        def compose(ev, written):
            written.update(row=True, memo_id=900)
            return {"status": "ok", "memo_id": 900}
        result, state, _ = self.run_with(compose)
        self.assertEqual(result["memo_id"], 900)
        self.assertEqual(self.refunds, [])
        self.assertEqual(state["status"], "done")
        self.assertEqual(state["memo_id"], 900)

    def test_a_failure_after_the_memo_row_is_not_refunded(self):
        """Decided 19 October: the memo exists and opens, so the charge
        bought it. What failed was a record about it."""
        def compose(ev, written):
            written.update(row=True, memo_id=901)
            raise RuntimeError("claim insert failed")
        result, state, _ = self.run_with(compose)
        self.assertEqual(self.refunds, [])
        self.assertEqual(state["status"], "done")
        self.assertEqual(state["memo_id"], 901)
        self.assertTrue(state["incomplete"])
        self.assertEqual(result["status"], "ok")

    # --- once --------------------------------------------------------------

    def test_a_finished_run_is_not_run_again(self):
        self.stored = {"status": "failed", "run": RUN}
        result, _, composed = self.run_with(
            lambda ev, written: {"status": "ok"})
        self.assertEqual(result["status"], "already-failed")
        composed.assert_not_called()
        self.assertEqual(self.refunds, [])

    def test_an_event_without_a_run_writes_no_run_and_still_refunds(self):
        """Invoked by hand, or queued before this was deployed."""
        def compose(ev, written):
            raise RuntimeError("boom")
        self.run_with(compose, event(run=None))
        self.assertEqual(self.puts, [])
        self.assertEqual(len(self.refunds), 1)


class UpdateRefund(unittest.TestCase):
    """_update's finish: failed is refunded, done is not."""

    def setUp(self):
        self.app = load_composition()
        self.puts = []
        self.refunds = []
        for p in [
            mock.patch.object(self.app, "_get_update", return_value=None),
            mock.patch.object(self.app, "_put_update",
                              side_effect=lambda t, m, r, s:
                                  self.puts.append(dict(s))),
            mock.patch.object(self.app.wallet, "refund_generation",
                              side_effect=lambda t, e, by=None:
                                  self.refunds.append(e) or
                                  {"refunded": True, "amount_cents": 100}),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def update(self, sql):
        with mock.patch.object(self.app, "_sql", side_effect=sql):
            return self.app._update({
                "action": "update", "tenant_id": TENANT, "memo_id": 120,
                "engagement_id": ENGAGEMENT_ID, "template_key": "credit",
                "config_revision": 9, "run": RUN, "requested_by": EMAIL,
                "entry_id": ENTRY})

    def test_a_failed_update_is_refunded(self):
        result = self.update(lambda s, p=None: rows())   # memo not found
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.refunds, [ENTRY])
        self.assertTrue(self.puts[-1]["refunded"])
        self.assertEqual(self.puts[-1]["amount_cents"], 100)

    def test_an_update_that_raises_is_refunded(self):
        def sql(s, p=None):
            raise RuntimeError("cluster did not resume")
        result = self.update(sql)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.refunds, [ENTRY])


class GenerateRoute(unittest.TestCase):
    """The API's half."""

    def setUp(self):
        self.app = load_api()
        self.invocations, self.puts, self.refunds = [], [], []
        self.paid = {"entry_id": ENTRY, "repeated": False}
        registry = mock.MagicMock()
        registry.TEMPLATE_KEY = "credit"
        registry.has_template.return_value = True
        registry.label_for_template.return_value = "Credit Memorandum"

        def sql(statement, params=None, tx=None):
            if "FROM engagement WHERE" in statement:
                return rows((ENGAGEMENT_ID, "Meridian", "Meridian Ltd", "open"))
            return rows()

        for p in [
            mock.patch.object(self.app, "_sql", side_effect=sql),
            mock.patch.object(self.app.config, "for_tenant",
                              lambda t: registry),
            mock.patch.object(self.app.wallet, "charge",
                              side_effect=lambda *a, **k: self.paid),
            mock.patch.object(self.app.wallet, "refund_generation",
                              side_effect=lambda t, e, by=None:
                                  self.refunds.append(e) or
                                  {"refunded": True, "amount_cents": 100}),
            mock.patch.object(self.app._lambda, "invoke",
                              side_effect=lambda **k:
                                  self.invocations.append(k)),
            mock.patch.object(self.app._s3, "put_object",
                              side_effect=lambda **k: self.puts.append(k)),
        ]:
            p.start()
            self.addCleanup(p.stop)

    def generate(self):
        return self.app.generate(TENANT, EMAIL, "Meridian", "credit", "idem-1")

    def test_the_payload_carries_the_charge_and_the_run(self):
        out = self.generate()
        self.assertEqual(out["status"], "started")
        payload = json.loads(self.invocations[0]["Payload"])
        self.assertEqual(payload["entry_id"], ENTRY)
        self.assertEqual(payload["run"], out["run"])
        # The run exists before composition is asked to finish it.
        state = json.loads(self.puts[0]["Body"].decode("utf-8"))
        self.assertEqual(state["status"], "running")
        self.assertEqual(self.puts[0]["Key"],
                         "tenants/7/runs/generate/42/%s.json" % out["run"])

    def test_a_repeated_click_gets_its_run_and_starts_nothing(self):
        """The defect found on 16 October: one charge, two memos."""
        first = self.generate()
        self.paid = {"entry_id": ENTRY, "repeated": True}
        again = self.generate()
        self.assertEqual(again["status"], "repeated")
        self.assertEqual(again["run"], first["run"])
        self.assertEqual(len(self.invocations), 1)

    def test_composition_that_cannot_be_started_is_refunded(self):
        self.app._lambda.invoke.side_effect = RuntimeError("throttled")
        out = self.generate()
        self.assertEqual(out["status"], "failed")
        self.assertTrue(out["refunded"])
        self.assertEqual(self.refunds, [ENTRY])
        state = json.loads(self.puts[-1]["Body"].decode("utf-8"))
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["error"], self.app.GENERATE_NOT_STARTED)

    def test_an_update_that_cannot_be_started_is_refunded(self):
        memo = rows(("credit", ENGAGEMENT_ID, 100, 2))
        self.app._sql.side_effect = lambda s, p=None, tx=None: memo
        with mock.patch.object(self.app.config, "active_revision",
                               return_value=9), \
                mock.patch.object(self.app.config, "load",
                                  return_value=self.app.config.for_tenant(7)):
            self.app._lambda.invoke.side_effect = RuntimeError("throttled")
            out = self.app.update_memo(TENANT, EMAIL, 120, "idem-2")
        self.assertEqual(out["status"], "failed")
        self.assertEqual(self.refunds, [ENTRY])

    def test_the_memo_list_reports_the_run(self):
        with mock.patch.object(self.app, "generate_progress",
                               return_value={"status": "failed"}) as asked, \
                mock.patch.object(self.app, "list_memos", return_value=[]):
            reply = self.app._dispatch({
                "routeKey": "GET /engagements/{id}/memos",
                "pathParameters": {"id": "Meridian"},
                "queryStringParameters": {"run": RUN},
                "requestContext": {"authorizer": {"jwt": {"claims": {
                    "custom:tenant_id": str(TENANT), "email": EMAIL}}}},
            }, None)
        body = json.loads(reply["body"])
        self.assertEqual(body["run"], {"status": "failed"})
        asked.assert_called_once_with(TENANT, ENGAGEMENT_ID, RUN)

    def test_a_run_id_that_is_not_one_is_refused(self):
        with self.assertRaises(ValueError):
            self.app.generate_progress(TENANT, ENGAGEMENT_ID, "../../other")


if __name__ == "__main__":
    unittest.main()
