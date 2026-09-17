"""
The Paddle processor's decisions, against an in-memory store. Run from the
repository root:

    python -m unittest discover -s tests

This tests what the processor decides. The SQL in DataApiStore is not
exercised here and is unverified until it runs against dev.
"""

import importlib.util
import io
import os
import sys
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BASE, BUSINESS, TOPUP = "pri_base", "pri_business", "pri_topup"
EMAIL = "buyer@example.com"


def load_processor():
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    env = {"CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
           "DATABASE": "arqedia", "PADDLE_PRICE_BASE": BASE,
           "PADDLE_PRICE_BUSINESS": BUSINESS, "PADDLE_PRICE_TOPUP": TOPUP}
    modules = {"boto3": boto3, "botocore": botocore,
               "botocore.exceptions": exceptions}
    with mock.patch.dict(sys.modules, modules), mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "paddle_processor_app", ROOT / "lambda/paddle_processor/app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class FakeStore:
    def __init__(self, tenants=(7,)):
        self.tenants = set(tenants)
        self.events = {}
        self.subscriptions = {}
        self.tenant_plan = {}
        self.buckets = []
        self.requests = []
        self.credit = {"base": 500, "business": 1500}

    def tenant_exists(self, tenant_id):
        return tenant_id in self.tenants

    def insert_event(self, event_id, event_type, occurred_at, tenant_id,
                     entity_id, needs_review):
        if event_id in self.events:
            return False
        self.events[event_id] = {"type": event_type, "tenant_id": tenant_id,
                                 "needs_review": needs_review}
        return True

    def flag_review(self, event_id):
        self.events[event_id]["needs_review"] = True

    def subscription_event_at(self, tenant_id):
        row = self.subscriptions.get(tenant_id)
        return None if row is None else row["paddle_event_at"]

    def monthly_credit_cents(self, plan_key):
        return self.credit[plan_key]

    def upsert_subscription(self, **row):
        old = self.subscriptions.get(row["tenant_id"], {})
        if row["current_period_ends_at"] is None:
            row["current_period_ends_at"] = old.get("current_period_ends_at")
        self.subscriptions[row["tenant_id"]] = row

    def copy_plan_to_tenant(self, tenant_id, plan_key):
        self.tenant_plan[tenant_id] = plan_key

    def bucket_exists(self, tenant_id, kind, reference):
        return any(b["tenant_id"] == tenant_id and b["kind"] == kind
                   and b["reference"] == reference for b in self.buckets)

    def grant(self, tenant_id, kind, cents, expires_at, reference):
        self.buckets.append({"tenant_id": tenant_id, "kind": kind,
                             "cents": cents, "expires_at": expires_at,
                             "reference": reference})

    def match_topup(self, tenant_id, increments, transaction_id):
        for r in self.requests:
            if (r["tenant_id"] == tenant_id and r["increments"] == increments
                    and r["paddle_transaction_id"] is None):
                r["paddle_transaction_id"] = transaction_id
                return True
        return False


def subscription_event(event_id, occurred_at, status="active", price=BASE,
                       tenant_id=7):
    return {"event_id": event_id, "event_type": "subscription.updated",
            "occurred_at": occurred_at,
            "data": {"id": "sub_1", "customer_id": "ctm_1", "status": status,
                     "custom_data": {"tenant_id": tenant_id},
                     "items": [{"price": {"id": price}, "quantity": 1}],
                     "current_billing_period": {
                         "starts_at": "2026-09-16T10:00:00Z",
                         "ends_at": "2026-10-16T10:00:00Z"}}}


def transaction_event(event_id, transaction_id, origin, price, quantity=1,
                      tenant_id=7):
    return {"event_id": event_id, "event_type": "transaction.completed",
            "occurred_at": "2026-09-16T10:00:00.123456789Z",
            "data": {"id": transaction_id, "origin": origin,
                     "customer_id": "ctm_1", "subscription_id": "sub_1",
                     "custom_data": {"tenant_id": tenant_id, "email": EMAIL},
                     "items": [{"price": {"id": price}, "quantity": quantity}],
                     "billing_period": {"starts_at": "2026-09-16T10:00:00Z",
                                        "ends_at": "2026-10-16T10:00:00Z"}}}


class ProcessorTest(unittest.TestCase):
    def setUp(self):
        self.app = load_processor()
        self.store = FakeStore()

    def apply(self, event):
        return self.app.apply(event, self.store)

    def test_duplicate_event_id_is_applied_once(self):
        event = transaction_event("evt_1", "txn_1", "web", BASE)
        self.assertEqual(self.apply(event), "credit-granted")
        self.assertEqual(self.apply(event), "duplicate")
        self.assertEqual(len(self.store.buckets), 1)

    def test_out_of_order_subscription_update_is_skipped(self):
        newer = subscription_event("evt_2", "2026-09-16T12:00:00Z",
                                   status="active", price=BUSINESS)
        older = subscription_event("evt_1", "2026-09-16T11:00:00Z",
                                   status="past_due", price=BASE)
        self.assertEqual(self.apply(newer), "applied")
        self.assertEqual(self.apply(older), "stale")
        row = self.store.subscriptions[7]
        self.assertEqual(row["paddle_status"], "active")
        self.assertEqual(row["plan_key"], "business")
        self.assertEqual(self.store.tenant_plan[7], "business")
        self.assertIn("evt_1", self.store.events)

    def test_plan_transaction_grants_monthly_credit(self):
        self.assertEqual(self.apply(transaction_event("evt_1", "txn_1", "web", BASE)),
                         "credit-granted")
        self.assertEqual(self.store.buckets, [{
            "tenant_id": 7, "kind": "monthly_credit", "cents": 500,
            "expires_at": "2026-10-16 10:00:00.000000", "reference": "txn_1"}])

    def test_topup_of_three_increments(self):
        self.store.requests.append({"tenant_id": 7, "increments": 3,
                                    "paddle_transaction_id": None})
        event = transaction_event("evt_1", "txn_9", "subscription_charge",
                                  TOPUP, quantity=3)
        self.assertEqual(self.apply(event), "topup-granted")
        self.assertEqual(self.store.buckets, [{
            "tenant_id": 7, "kind": "purchased", "cents": 1500,
            "expires_at": "2026-10-16 10:00:00.123456", "reference": "txn_9"}])
        self.assertEqual(self.store.requests[0]["paddle_transaction_id"], "txn_9")

    def test_duplicate_transaction_reference_grants_once(self):
        first = transaction_event("evt_1", "txn_1", "web", BASE)
        second = transaction_event("evt_2", "txn_1", "web", BASE)
        self.assertEqual(self.apply(first), "credit-granted")
        self.assertEqual(self.apply(second), "credit-reference-exists")
        self.assertEqual(len(self.store.buckets), 1)

    def test_unknown_tenant_is_recorded_for_review_and_applies_nothing(self):
        event = transaction_event("evt_1", "txn_1", "web", BASE, tenant_id=99)
        self.assertEqual(self.apply(event), "review")
        self.assertTrue(self.store.events["evt_1"]["needs_review"])
        self.assertIsNone(self.store.events["evt_1"]["tenant_id"])
        self.assertEqual(self.store.buckets, [])

    def test_refund_is_flagged_and_changes_nothing(self):
        event = {"event_id": "evt_1", "event_type": "adjustment.created",
                 "occurred_at": "2026-09-16T10:00:00Z",
                 "data": {"id": "adj_1", "action": "refund",
                          "transaction_id": "txn_1", "customer_id": "ctm_1"}}
        self.assertEqual(self.apply(event), "review")
        self.assertTrue(self.store.events["evt_1"]["needs_review"])
        self.assertEqual(self.store.buckets, [])
        self.assertEqual(self.store.subscriptions, {})

    def test_handler_never_logs_the_payload(self):
        event = transaction_event("evt_1", "txn_1", "web", BASE)
        out = io.StringIO()
        with mock.patch.object(self.app, "DataApiStore") as store_class, \
                redirect_stdout(out):
            store_class.return_value.__enter__.return_value = self.store
            self.app.lambda_handler(event, None)
        self.assertIn("event=evt_1", out.getvalue())
        self.assertNotIn(EMAIL, out.getvalue())


if __name__ == "__main__":
    unittest.main()
