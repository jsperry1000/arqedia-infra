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
        # The database's NOW(), as a DATETIME(6) string.
        self.now = "2026-09-16 10:00:00.000000"

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

    def monthly_credit_granted(self, tenant_id):
        return sum(b["cents"] for b in self.buckets
                   if b["tenant_id"] == tenant_id
                   and b["kind"] == "monthly_credit"
                   and b["expires_at"] > self.now)

    def current_plan(self, tenant_id):
        row = self.subscriptions.get(tenant_id)
        if row is None:
            return None, None, None
        return (row["plan_key"], row.get("previous_plan_key"),
                row["current_period_ends_at"])

    def upsert_subscription(self, **row):
        old = self.subscriptions.get(row["tenant_id"], {})
        if row["current_period_ends_at"] is None:
            row["current_period_ends_at"] = old.get("current_period_ends_at")
        # As the SQL does: the plan the row had, when this write changes it;
        # otherwise whatever previous plan it already held.
        if old and old["plan_key"] != row["plan_key"]:
            row["previous_plan_key"] = old["plan_key"]
        else:
            row["previous_plan_key"] = old.get("previous_plan_key")
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


def plan_change_event(event_id, transaction_id, to_price, from_price,
                      tenant_id=7):
    """A proration transaction in the shape Paddle sends: the plan moved to at
    quantity 1, the plan moved from at quantity -1. Taken from
    txn_01m2xc3cn4kr6dmsn99hy67818 (sandbox, 19 September 2026), which carried
    pri_business at 1 and pri_base at -1."""
    event = transaction_event(event_id, transaction_id, "subscription_update",
                              to_price, tenant_id=tenant_id)
    event["data"]["items"].append({"price": {"id": from_price},
                                   "quantity": -1})
    return event


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

    PERIOD_END = "2026-10-16 10:00:00.000000"

    def on_plan(self, plan_key, previous=None, period_end=PERIOD_END):
        """A subscription on plan_key, with the period's own monthly credit
        already granted, as the checkout or renewal transaction would have."""
        self.store.subscriptions[7] = {
            "plan_key": plan_key, "previous_plan_key": previous,
            "paddle_event_at": "2026-09-16 09:00:00.000000",
            "current_period_ends_at": period_end}
        self.store.grant(7, "monthly_credit", self.store.credit[plan_key],
                         period_end, "txn_period")

    def change_buckets(self):
        """Buckets granted by plan changes, not the period's own grant."""
        return [b for b in self.store.buckets
                if b["reference"] not in ("txn_period", "txn_old", "txn_renew")]

    def test_upgrade_grants_the_difference(self):
        self.on_plan("base")
        event = plan_change_event("evt_1", "txn_up", BUSINESS, BASE)
        self.assertEqual(self.apply(event), "upgrade-credit-granted")
        self.assertEqual(self.change_buckets(), [{
            "tenant_id": 7, "kind": "monthly_credit", "cents": 1000,
            "expires_at": "2026-10-16 10:00:00.000000", "reference": "txn_up"}])

    def test_downgrade_grants_nothing(self):
        self.on_plan("business")
        event = plan_change_event("evt_1", "txn_down", BASE, BUSINESS)
        self.assertEqual(self.apply(event), "downgrade-no-grant")
        self.assertEqual(self.change_buckets(), [])

    def test_duplicate_upgrade_reference_grants_once(self):
        self.on_plan("base")
        first = plan_change_event("evt_1", "txn_up", BUSINESS, BASE)
        second = plan_change_event("evt_2", "txn_up", BUSINESS, BASE)
        self.assertEqual(self.apply(first), "upgrade-credit-granted")
        self.assertEqual(self.apply(second), "upgrade-reference-exists")
        self.assertEqual(len(self.change_buckets()), 1)

    def test_subscription_update_records_the_previous_plan(self):
        self.on_plan("base")
        update = subscription_event("evt_1", "2026-09-16T12:00:00Z",
                                    price=BUSINESS)
        self.assertEqual(self.apply(update), "applied")
        row = self.store.subscriptions[7]
        self.assertEqual((row["plan_key"], row["previous_plan_key"]),
                         ("business", "base"))

    def test_transaction_before_subscription_updated_grants_once(self):
        self.on_plan("base")
        upgrade = plan_change_event("evt_1", "txn_up", BUSINESS, BASE)
        update = subscription_event("evt_2", "2026-09-16T12:00:00Z",
                                    price=BUSINESS)
        redelivered = plan_change_event("evt_3", "txn_up", BUSINESS, BASE)
        self.assertEqual(self.apply(upgrade), "upgrade-credit-granted")
        self.assertEqual(self.apply(update), "applied")
        self.assertEqual(self.apply(redelivered), "upgrade-reference-exists")
        self.assertEqual([b["cents"] for b in self.change_buckets()], [1000])

    def test_subscription_updated_before_transaction_grants_once(self):
        self.on_plan("base")
        update = subscription_event("evt_1", "2026-09-16T12:00:00Z",
                                    price=BUSINESS)
        upgrade = plan_change_event("evt_2", "txn_up", BUSINESS, BASE)
        redelivered = plan_change_event("evt_3", "txn_up", BUSINESS, BASE)
        self.assertEqual(self.apply(update), "applied")
        self.assertEqual(self.apply(upgrade), "upgrade-credit-granted")
        self.assertEqual(self.apply(redelivered), "upgrade-reference-exists")
        self.assertEqual([b["cents"] for b in self.change_buckets()], [1000])
        self.assertFalse(self.store.events["evt_2"]["needs_review"])

    def test_downgrade_after_subscription_updated_grants_nothing(self):
        self.on_plan("business")
        update = subscription_event("evt_1", "2026-09-16T12:00:00Z",
                                    price=BASE)
        downgrade = plan_change_event("evt_2", "txn_down", BASE, BUSINESS)
        self.assertEqual(self.apply(update), "applied")
        self.assertEqual(self.apply(downgrade), "downgrade-no-grant")
        self.assertEqual(self.change_buckets(), [])

    def test_single_item_change_with_no_lower_plan_is_flagged_for_review(self):
        # No negative item, so the row is the only source, and it already
        # shows the new plan with no previous plan recorded.
        self.on_plan("business")
        event = transaction_event("evt_1", "txn_up", "subscription_update",
                                  BUSINESS)
        self.assertEqual(self.apply(event), "review")
        self.assertTrue(self.store.events["evt_1"]["needs_review"])
        self.assertEqual(self.change_buckets(), [])

    def test_single_item_change_reads_the_old_plan_from_the_row(self):
        """The fallback, granting: a plan change carrying no negative item."""
        self.on_plan("base")
        event = transaction_event("evt_1", "txn_up", "subscription_update",
                                  BUSINESS)
        self.assertEqual(self.apply(event), "upgrade-credit-granted")
        self.assertEqual([b["cents"] for b in self.change_buckets()], [1000])

    def test_plan_change_with_no_subscription_row_is_flagged_for_review(self):
        # No subscription is no plan change, however completely the payload
        # names both plans (19 September).
        event = plan_change_event("evt_1", "txn_up", BUSINESS, BASE)
        self.assertEqual(self.apply(event), "review")
        self.assertTrue(self.store.events["evt_1"]["needs_review"])
        self.assertEqual(self.change_buckets(), [])

    def test_upgrade_downgrade_upgrade_grants_ten_dollars_once(self):
        self.on_plan("base")
        steps = [
            (plan_change_event("evt_1", "txn_up_1", BUSINESS, BASE),
             "upgrade-credit-granted"),
            (subscription_event("evt_2", "2026-09-16T12:00:00Z",
                                price=BUSINESS), "applied"),
            (plan_change_event("evt_3", "txn_down", BASE, BUSINESS),
             "downgrade-no-grant"),
            (subscription_event("evt_4", "2026-09-16T13:00:00Z",
                                price=BASE), "applied"),
            (plan_change_event("evt_5", "txn_up_2", BUSINESS, BASE),
             "upgrade-capped"),
        ]
        for event, outcome in steps:
            self.assertEqual(self.apply(event), outcome)
        self.assertEqual(sum(b["cents"] for b in self.change_buckets()), 1000)

    def test_upgrade_after_a_renewal_grant_is_measured_from_the_renewal(self):
        # Last period on business, expired. This period renewed on base.
        self.store.now = "2026-10-20 10:00:00.000000"
        self.store.grant(7, "monthly_credit", 1500,
                         "2026-10-16 10:00:00.000000", "txn_old")
        self.store.subscriptions[7] = {
            "plan_key": "base", "previous_plan_key": "business",
            "paddle_event_at": "2026-10-16 10:00:00.000000",
            "current_period_ends_at": "2026-11-16 10:00:00.000000"}
        self.store.grant(7, "monthly_credit", 500,
                         "2026-11-16 10:00:00.000000", "txn_renew")
        event = plan_change_event("evt_1", "txn_up", BUSINESS, BASE)
        event["data"]["billing_period"]["ends_at"] = "2026-11-16T10:00:00Z"
        self.assertEqual(self.apply(event), "upgrade-credit-granted")
        self.assertEqual(self.change_buckets(), [{
            "tenant_id": 7, "kind": "monthly_credit", "cents": 1000,
            "expires_at": "2026-11-16 10:00:00.000000", "reference": "txn_up"}])

    def test_cap_holds_when_period_ends_differ_by_one_second(self):
        self.on_plan("base")   # renewal bucket expires 10:00:00
        first = plan_change_event("evt_1", "txn_up_1", BUSINESS, BASE)
        first["data"]["billing_period"]["ends_at"] = "2026-10-16T10:00:01Z"
        self.assertEqual(self.apply(first), "upgrade-credit-granted")
        self.assertEqual([(b["cents"], b["expires_at"])
                          for b in self.change_buckets()],
                         [(1000, "2026-10-16 10:00:01.000000")])
        self.apply(subscription_event("evt_2", "2026-09-16T12:00:00Z",
                                      price=BUSINESS))
        self.apply(subscription_event("evt_3", "2026-09-16T13:00:00Z",
                                      price=BASE))
        again = plan_change_event("evt_4", "txn_up_2", BUSINESS, BASE)
        again["data"]["billing_period"]["ends_at"] = "2026-10-16T10:00:01Z"
        self.assertEqual(self.apply(again), "upgrade-capped")
        self.assertEqual(sum(b["cents"] for b in self.change_buckets()), 1000)


if __name__ == "__main__":
    unittest.main()
