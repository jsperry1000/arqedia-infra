"""
Checkout, plan change, top-up and seat counting. Paddle is never called:
paddle_api is replaced. Run from the repository root:

    python -m unittest discover -s tests
"""

import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from api_modules import load_billing, rows

# The Data API's answer to a second topup_request under one key, as dev
# returned it on 17 September 2026.
DUPLICATE_CODE = "DatabaseErrorException"
DUPLICATE_MESSAGE = ("Duplicate entry '7-k' for key "
                     "'topup_request.uq_idempotency'; Error code: 1062; "
                     "SQLState: 23000")

# Ten columns: nine since migration 033 (18.5) - the three limits are field
# sets, sections, daily classification - and workspace_count since 046.
PLANS = rows(("base", "Base", 2, 2500, 500, 5, 3, 12, 500, 1),
             ("business", "Small Business", 5, 6500, 1500, None, 5, 25, 1500,
              5))


class FakeBillingDb:
    def __init__(self, subscription=None, workspaces=1):
        # (sub_id, status, ends, plan_key, customer_id)
        self.subscription = subscription
        self.workspaces = workspaces       # how many the tenant holds
        self.inserted_requests = []
        self.checkout_offered_at = None
        self.clock = 0
        # Keys topup_request already holds, and the error the Data API raises
        # for a second row under one of them (uq_idempotency).
        self.keys = set()
        self.duplicate_error = None

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        if "FROM subscription" in s:
            return rows(self.subscription) if self.subscription else rows()
        if "FROM plan" in s:
            return PLANS
        if s.startswith("SELECT COUNT(*) FROM workspace"):
            return rows((self.workspaces,))
        if s.startswith("INSERT INTO topup_request"):
            values = {p["name"]: p["value"] for p in params}
            key = values["k"]["stringValue"]
            if key in self.keys:
                raise self.duplicate_error
            self.keys.add(key)
            self.inserted_requests.append(values)
            return rows()
        if s.startswith("UPDATE tenant SET checkout_offered_at"):
            # NOW() moves on every call; the IS NULL guard is what keeps the
            # first value.
            self.clock += 1
            if ("checkout_offered_at IS NULL" in s
                    and self.checkout_offered_at is None):
                self.checkout_offered_at = "t%d" % self.clock
            return rows()
        return rows()


class BillingTest(unittest.TestCase):
    def setUp(self):
        self.billing = load_billing()
        self.paddle = mock.MagicMock()
        self.paddle.PLAN_PRICES = {"base": "pri_base",
                                   "business": "pri_business"}
        self.billing.paddle_api = self.paddle

    def use(self, db):
        return mock.patch.object(self.billing, "_sql", db.sql)

    def test_top_up_refused_with_no_subscription(self):
        with self.use(FakeBillingDb()):
            with self.assertRaises(self.billing.Refused) as raised:
                self.billing.top_up(7, "a@firm.com", "admin",
                                    {"increments": 2, "idempotency_key": "k"})
        self.assertEqual(str(raised.exception), "Subscribe first.")
        self.paddle.charge_topup.assert_not_called()

    def test_top_up_refused_when_past_due(self):
        db = FakeBillingDb(("sub_1", "past_due", None, "base", "ctm_1"))
        with self.use(db):
            with self.assertRaises(self.billing.Refused):
                self.billing.top_up(7, "a@firm.com", "admin",
                                    {"increments": 2, "idempotency_key": "k"})
        self.paddle.charge_topup.assert_not_called()
        self.assertEqual(db.inserted_requests, [])

    def test_top_up_records_the_request_then_charges(self):
        db = FakeBillingDb(("sub_1", "active", None, "base", "ctm_1"))
        with self.use(db):
            result = self.billing.top_up(
                7, "a@firm.com", "admin",
                {"increments": 3, "idempotency_key": "k"})
        self.assertEqual(len(db.inserted_requests), 1)
        self.paddle.charge_topup.assert_called_once_with("sub_1", 3)
        self.assertEqual(result["amount_cents"], 1500)

    def client_error(self, code, message):
        error = self.billing.ClientError(message)
        error.response = {"Error": {"Code": code, "Message": message}}
        return error

    def test_top_up_duplicate_key_is_repeated_and_never_charges(self):
        db = FakeBillingDb(("sub_1", "active", None, "base", "ctm_1"))
        db.keys.add("k")
        db.duplicate_error = self.client_error(DUPLICATE_CODE,
                                               DUPLICATE_MESSAGE)
        with self.use(db):
            result = self.billing.top_up(
                7, "a@firm.com", "admin",
                {"increments": 2, "idempotency_key": "k"})
        self.assertTrue(result["repeated"])
        self.assertEqual(result["amount_cents"], 1000)
        self.assertEqual(db.inserted_requests, [])
        self.paddle.charge_topup.assert_not_called()

    def test_top_up_twice_with_one_key_charges_once(self):
        db = FakeBillingDb(("sub_1", "active", None, "base", "ctm_1"))
        db.duplicate_error = self.client_error(DUPLICATE_CODE,
                                               DUPLICATE_MESSAGE)
        body = {"increments": 2, "idempotency_key": "k"}
        with self.use(db):
            first = self.billing.top_up(7, "a@firm.com", "admin", body)
            second = self.billing.top_up(7, "a@firm.com", "admin", body)
        self.assertTrue(first["requested"])
        self.assertTrue(second["repeated"])
        self.paddle.charge_topup.assert_called_once_with("sub_1", 2)

    def test_top_up_other_database_error_is_raised_not_repeated(self):
        db = FakeBillingDb(("sub_1", "active", None, "base", "ctm_1"))
        db.keys.add("k")
        db.duplicate_error = self.client_error(
            DUPLICATE_CODE, "Communications link failure; Error code: 0")
        with self.use(db):
            with self.assertRaises(self.billing.ClientError):
                self.billing.top_up(7, "a@firm.com", "admin",
                                    {"increments": 2, "idempotency_key": "k"})
        self.paddle.charge_topup.assert_not_called()

    def test_downgrade_refused_over_seats(self):
        db = FakeBillingDb(("sub_1", "active", None, "business", "ctm_1"))
        listing = {"taken": 3, "reserved": 1}
        with self.use(db), mock.patch.object(self.billing.seats, "listing",
                                             return_value=listing):
            with self.assertRaises(self.billing.Refused):
                self.billing.change_plan(7, "a@firm.com", "admin",
                                         {"plan": "base"})
        self.paddle.change_plan.assert_not_called()

    def test_downgrade_refused_over_workspaces(self):
        """PACK-02: Base holds 1. Nothing is deleted to make it fit."""
        db = FakeBillingDb(("sub_1", "active", None, "business", "ctm_1"),
                           workspaces=2)
        listing = {"taken": 1, "reserved": 0}
        with self.use(db), mock.patch.object(self.billing.seats, "listing",
                                             return_value=listing):
            with self.assertRaises(self.billing.Refused) as raised:
                self.billing.change_plan(7, "a@firm.com", "admin",
                                         {"plan": "base"})
        self.assertIn("holds 2 workspaces, and Base holds 1",
                      str(raised.exception))
        self.paddle.change_plan.assert_not_called()

    def test_downgrade_that_fits_goes_ahead(self):
        db = FakeBillingDb(("sub_1", "active", None, "business", "ctm_1"),
                           workspaces=1)
        listing = {"taken": 1, "reserved": 0}
        with self.use(db), mock.patch.object(self.billing.seats, "listing",
                                             return_value=listing):
            self.billing.change_plan(7, "a@firm.com", "admin", {"plan": "base"})
        self.paddle.change_plan.assert_called_once_with("sub_1", "base")

    def test_checkout_takes_the_tenant_from_the_token_not_the_body(self):
        self.paddle.create_checkout_transaction.return_value = "txn_1"
        body = {"plan": "base", "tenant_id": 99,
                "custom_data": {"tenant_id": 99}}
        with self.use(FakeBillingDb()):
            result = self.billing.checkout(7, "admin", body)
        self.paddle.create_checkout_transaction.assert_called_once_with(
            7, "base")
        self.assertEqual(result, {"transaction_id": "txn_1"})

    def test_checkout_sets_checkout_offered_at_once(self):
        self.paddle.create_checkout_transaction.side_effect = ["txn_1", "txn_2"]
        db = FakeBillingDb()
        with self.use(db):
            self.billing.checkout(7, "admin", {"plan": "business"})
            first = db.checkout_offered_at
            self.billing.checkout(7, "admin", {"plan": "business"})
        self.assertEqual(first, "t1")
        self.assertEqual(db.checkout_offered_at, "t1")

    def test_checkout_paddle_refused_sets_nothing(self):
        self.paddle.create_checkout_transaction.side_effect = RuntimeError("no")
        db = FakeBillingDb()
        with self.use(db):
            with self.assertRaises(RuntimeError):
                self.billing.checkout(7, "admin", {"plan": "base"})
        self.assertIsNone(db.checkout_offered_at)

    def test_member_cannot_check_out(self):
        with self.use(FakeBillingDb()):
            with self.assertRaises(PermissionError):
                self.billing.checkout(7, "member", {"plan": "base"})
        self.paddle.create_checkout_transaction.assert_not_called()


class PaymentMethodTest(unittest.TestCase):
    """Changing the payment method, and resuming a paused subscription.
    Paddle offers its payment-method transaction for active and past_due
    only; a paused subscription resumes instead."""

    def setUp(self):
        self.billing = load_billing()
        self.paddle = mock.MagicMock()
        self.billing.paddle_api = self.paddle
        self.paddle.payment_method_transaction.return_value = "txn_pm"

    def use(self, status):
        db = FakeBillingDb(("sub_1", status, None, "base", "ctm_1")
                           if status else None)
        return mock.patch.object(self.billing, "_sql", db.sql)

    def test_active_and_past_due_get_a_transaction(self):
        for status in ("active", "past_due"):
            with self.subTest(status=status), self.use(status):
                result = self.billing.payment_method(7, "admin")
            self.assertEqual(result, {"transaction_id": "txn_pm",
                                      "status": status})
        self.paddle.payment_method_transaction.assert_called_with("sub_1")

    def test_paused_cancelled_and_none_are_refused(self):
        for status in ("paused", "canceled", None):
            with self.subTest(status=status), self.use(status):
                with self.assertRaises(self.billing.Refused):
                    self.billing.payment_method(7, "admin")
        self.paddle.payment_method_transaction.assert_not_called()

    def test_member_cannot_change_the_payment_method(self):
        with self.use("active"):
            with self.assertRaises(PermissionError):
                self.billing.payment_method(7, "member")
        self.paddle.payment_method_transaction.assert_not_called()

    def test_paused_resumes(self):
        with self.use("paused"):
            self.assertEqual(self.billing.resume(7, "admin"),
                             {"requested": True})
        self.paddle.resume_subscription.assert_called_once_with("sub_1")

    def test_only_paused_resumes(self):
        for status in ("active", "past_due", "canceled", None):
            with self.subTest(status=status), self.use(status):
                with self.assertRaises(self.billing.Refused):
                    self.billing.resume(7, "admin")
        self.paddle.resume_subscription.assert_not_called()

    def test_member_cannot_resume(self):
        with self.use("paused"):
            with self.assertRaises(PermissionError):
                self.billing.resume(7, "member")
        self.paddle.resume_subscription.assert_not_called()


class PlansTest(unittest.TestCase):
    """What the Account screen is given, and what it must never be given.

    THE THREE LIMITS ARE THE POINT (18.5). They were sold on the pricing page
    and held nowhere, so the screen a tenant pays from could not show them.
    A test that only counted the plans would pass with all three missing."""

    def setUp(self):
        self.billing = load_billing()

    def plans(self):
        with mock.patch.object(self.billing, "_sql",
                               lambda *a, **k: PLANS):
            return self.billing._plans()

    def test_every_plan_carries_the_three_limits(self):
        for plan in self.plans():
            with self.subTest(plan=plan["plan_key"]):
                self.assertIn("field_sets_per_type", plan)
                self.assertIn("sections_per_template", plan)
                self.assertIn("daily_classification_cents", plan)

    def test_the_limits_are_the_row_s_own_values(self):
        base, business = self.plans()
        self.assertEqual(
            (base["field_sets_per_type"], base["sections_per_template"],
             base["daily_classification_cents"]), (3, 12, 500))
        self.assertEqual(
            (business["field_sets_per_type"],
             business["sections_per_template"],
             business["daily_classification_cents"]), (5, 25, 1500))

    def test_an_unlimited_share_allowance_is_still_null(self):
        """Null is unlimited here and not zero, and widening the SELECT must
        not have shifted a column onto it."""
        _, business = self.plans()
        self.assertIsNone(business["share_allowance"])

    def test_only_active_plans(self):
        with mock.patch.object(self.billing, "_sql",
                               lambda *a, **k: PLANS) as _:
            pass
        # The filter is in the statement rather than in Python, so assert it
        # is there: a screen offering an inactive plan offers a price nobody
        # can be billed at.
        seen = {}

        def sql(statement, params=None):
            seen["sql"] = " ".join(statement.split())
            return PLANS

        with mock.patch.object(self.billing, "_sql", sql):
            self.billing._plans()
        self.assertIn("WHERE active = 1", seen["sql"])

    def test_enterprise_is_never_among_them(self):
        """It is not a plan row, deliberately - plan.seat_count,
        monthly_price_cents and monthly_credit_cents are NOT NULL, and a
        negotiated price must not be a release. Its column on the screen is
        ENTERPRISE_COLUMN in ui/src/upgrade.tsx."""
        self.assertNotIn("enterprise",
                         [p["plan_key"] for p in self.plans()])


class TopUpFigureTest(unittest.TestCase):
    """The confirmation states what the card will be charged (18.5).

    Account.tsx held TOPUP_CENTS = 500 and billing charged
    TOPUP_INCREMENT_CENTS * increments - two numbers that happened to agree.
    subscription_view reports the one that charges."""

    def setUp(self):
        self.billing = load_billing()

    def test_the_view_reports_the_constant_that_charges(self):
        db = FakeBillingDb(("sub_1", "active", None, "base", "ctm_1"))
        with mock.patch.object(self.billing, "_sql", db.sql),              mock.patch.object(self.billing.wallet, "standing",
                               return_value="active"):
            view = self.billing.subscription_view(7)
        self.assertEqual(view["topup_increment_cents"],
                         self.billing.TOPUP_INCREMENT_CENTS)

    def test_it_is_the_figure_top_up_multiplies_by(self):
        """The test that would fail if the two ever parted."""
        db = FakeBillingDb(("sub_1", "active", None, "base", "ctm_1"))
        paddle = mock.MagicMock()
        self.billing.paddle_api = paddle
        with mock.patch.object(self.billing, "_sql", db.sql):
            charged = self.billing.top_up(
                7, "a@firm.com", "admin",
                {"increments": 3, "idempotency_key": "k"})
        with mock.patch.object(self.billing, "_sql", db.sql),              mock.patch.object(self.billing.wallet, "standing",
                               return_value="active"):
            view = self.billing.subscription_view(7)
        self.assertEqual(charged["amount_cents"],
                         view["topup_increment_cents"] * 3)


class WorkspaceLimitTest(unittest.TestCase):
    """How many workspaces a tenant may hold (PACK-02, settled 23 October
    2026): the subscription's plan, tenant.plan on a trial, the negotiated
    number on Enterprise, and none for tenant 0. The stub answers by
    statement, as SeatsBoughtTest's does."""

    def setUp(self):
        self.billing = load_billing()

    def db(self, subscription=None, tenant=None, by_key=None, cheapest=None,
           held=1):
        asked = []

        def sql(statement, params=None):
            s = " ".join(statement.split())
            asked.append(s)
            if "FROM subscription" in s:
                return rows(subscription) if subscription else rows()
            if "FROM tenant" in s:
                return rows(tenant) if tenant else rows()
            if "WHERE plan_key" in s:
                return rows(by_key) if by_key else rows()
            if "ORDER BY monthly_price_cents" in s:
                return rows(cheapest) if cheapest else rows()
            if s.startswith("SELECT COUNT(*) FROM workspace"):
                return rows((held,))
            return rows()

        return sql, asked

    def limit(self, tenant_id=7, **kw):
        sql, asked = self.db(**kw)
        with mock.patch.object(self.billing, "_sql", sql):
            return self.billing.workspace_limit(tenant_id), asked

    def test_the_subscription_s_plan_decides(self):
        got, asked = self.limit(subscription=(5,))
        self.assertEqual(got, 5)
        self.assertEqual(len(asked), 1)

    def test_a_trial_reads_tenant_plan_through_the_table(self):
        got, _ = self.limit(tenant=("base", None), by_key=(1,))
        self.assertEqual(got, 1)

    def test_enterprise_is_its_negotiated_number(self):
        got, asked = self.limit(tenant=("enterprise", 12))
        self.assertEqual(got, 12)
        self.assertFalse(any("WHERE plan_key" in s for s in asked))

    def test_enterprise_with_none_set_has_no_limit(self):
        got, _ = self.limit(tenant=("enterprise", None))
        self.assertIsNone(got)

    def test_the_negotiated_number_is_ignored_on_another_plan(self):
        got, _ = self.limit(tenant=("base", 12), by_key=(1,))
        self.assertEqual(got, 1)

    def test_an_unknown_plan_gets_the_smallest_active_one(self):
        got, _ = self.limit(tenant=("nobody-has-seen", None), cheapest=(1,))
        self.assertEqual(got, 1)

    def test_tenant_0_has_no_limit_and_asks_nothing(self):
        got, asked = self.limit(tenant_id=0, subscription=(1,))
        self.assertIsNone(got)
        self.assertEqual(asked, [])

    def room(self, tenant_id=7, **kw):
        sql, _ = self.db(**kw)
        with mock.patch.object(self.billing, "_sql", sql):
            self.billing.require_workspace_room(tenant_id)

    def test_at_the_limit_is_refused(self):
        with self.assertRaises(self.billing.Refused) as raised:
            self.room(subscription=(1,), held=1)
        self.assertEqual(str(raised.exception),
                         "Your plan holds 1 workspace, and it is in use. A "
                         "bigger plan is how a tenant gets more.")

    def test_over_the_limit_is_refused_and_says_how_many(self):
        with self.assertRaises(self.billing.Refused) as raised:
            self.room(subscription=(5,), held=5)
        self.assertIn("5 workspaces, and all 5 are in use",
                      str(raised.exception))

    def test_below_the_limit_goes_ahead(self):
        self.room(subscription=(5,), held=4)

    def test_no_workspace_yet_goes_ahead_on_base(self):
        """A new tenant's first workspace, made by Get started."""
        self.room(subscription=(1,), held=0)

    def test_no_limit_goes_ahead(self):
        self.room(tenant=("enterprise", None), held=40)
        self.room(tenant_id=0, held=40)


class PaddleApiTest(unittest.TestCase):
    def test_checkout_transaction_custom_data_is_the_argument(self):
        paddle_api = load_billing().paddle_api
        with mock.patch.object(paddle_api, "_request",
                               return_value={"data": {"id": "txn_1"}}) as req:
            self.assertEqual(
                paddle_api.create_checkout_transaction(7, "base"), "txn_1")
        method, path, body = req.call_args.args
        self.assertEqual((method, path), ("POST", "/transactions"))
        self.assertEqual(body["custom_data"], {"tenant_id": 7})
        self.assertEqual(body["items"],
                         [{"price_id": "pri_base", "quantity": 1}])

    def test_cancel_is_immediate_and_answers_the_status(self):
        paddle_api = load_billing().paddle_api
        with mock.patch.object(paddle_api, "_request",
                               return_value={"data": {"status": "canceled"}}
                               ) as req:
            self.assertEqual(
                paddle_api.cancel_subscription("sub_1"), "canceled")
        method, path, body = req.call_args.args
        self.assertEqual((method, path),
                         ("POST", "/subscriptions/sub_1/cancel"))
        self.assertEqual(body, {"effective_from": "immediately"})

    def test_payment_method_transaction_is_a_get_with_no_body(self):
        paddle_api = load_billing().paddle_api
        with mock.patch.object(paddle_api, "_request",
                               return_value={"data": {"id": "txn_pm"}}) as req:
            self.assertEqual(
                paddle_api.payment_method_transaction("sub_1"), "txn_pm")
        self.assertEqual(
            req.call_args.args,
            ("GET", "/subscriptions/sub_1/update-payment-method-transaction"))

    def test_resume_is_immediate_and_starts_a_new_period(self):
        paddle_api = load_billing().paddle_api
        with mock.patch.object(paddle_api, "_request",
                               return_value={"data": {}}) as req:
            paddle_api.resume_subscription("sub_1")
        method, path, body = req.call_args.args
        self.assertEqual((method, path),
                         ("POST", "/subscriptions/sub_1/resume"))
        self.assertEqual(body, {"effective_from": "immediately",
                                "on_resume": "start_new_billing_period"})

    def test_a_read_sends_no_body(self):
        """_request sends a body only where one is given; the writes above
        still pass theirs."""
        paddle_api = load_billing().paddle_api
        sent = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"data": {"url": "https://pdf"}}'

        def urlopen(request, timeout=None):
            sent["data"] = request.data
            sent["url"] = request.full_url
            return Response()

        with mock.patch.object(paddle_api, "_api_key", return_value="k"), \
             mock.patch.object(paddle_api.urllib.request, "urlopen", urlopen):
            paddle_api.invoice_pdf_url(TXN_A)
        self.assertIsNone(sent["data"])
        self.assertTrue(sent["url"].endswith("/transactions/%s/invoice"
                                             % TXN_A))

    def test_the_list_is_one_customer_and_one_subscription(self):
        paddle_api = load_billing().paddle_api
        with mock.patch.object(paddle_api, "_request",
                               return_value={"data": []}) as req:
            paddle_api.list_transactions("ctm_1", "sub_1", after=TXN_B)
        method, path = req.call_args.args
        self.assertEqual(method, "GET")
        query = parse_qs(urlsplit(path).query)
        self.assertEqual(query["customer_id"], ["ctm_1"])
        self.assertEqual(query["subscription_id"], ["sub_1"])
        self.assertEqual(query["status"],
                         ["completed,paid,past_due,canceled"])
        self.assertEqual(query["order_by"], ["billed_at[DESC]"])
        self.assertEqual(query["per_page"], ["30"])
        self.assertEqual(query["after"], [TXN_B])


TXN_A = "txn_" + "a" * 26
TXN_B = "txn_" + "b" * 26


def transaction(txn, status="completed", total="6500",
                items=(("pri_business", 1),),
                billed_at="2026-10-01T10:00:00.1Z"):
    return {"id": txn, "status": status, "billed_at": billed_at,
            "created_at": "2026-09-30T09:00:00Z", "currency_code": "USD",
            "invoice_number": "325-1",
            "details": {"totals": {"grand_total": total}},
            "items": [{"price": {"id": p}, "quantity": q} for p, q in items]}


class InvoicesTest(unittest.TestCase):
    """GET /billing/invoices: Paddle is the record, read a page at a time,
    by this tenant's customer AND subscription (decided 24 October 2026)."""

    def setUp(self):
        self.billing = load_billing()
        self.paddle = mock.MagicMock()
        self.paddle.PLAN_PRICES = {"base": "pri_base",
                                   "business": "pri_business"}
        self.paddle.TOPUP_PRICE = "pri_topup"
        self.billing.paddle_api = self.paddle
        self.db = FakeBillingDb(("sub_1", "active", None, "business",
                                 "ctm_1"))

    def invoices(self, query=None, role="admin"):
        with mock.patch.object(self.billing, "_sql", self.db.sql):
            return self.billing.invoices(7, role, query or {})

    def test_a_member_is_refused_and_paddle_is_not_asked(self):
        with self.assertRaises(PermissionError):
            self.invoices(role="member")
        self.paddle.list_transactions.assert_not_called()

    def test_no_customer_is_an_empty_list_without_asking_paddle(self):
        for sub in (None, ("sub_1", "active", None, "business", None)):
            with self.subTest(sub=sub):
                self.db.subscription = sub
                self.assertEqual(self.invoices(),
                                 {"invoices": [], "has_more": False,
                                  "after": None})
                self.assertIsNone(self.invoices({"pdf": TXN_A}))
        self.paddle.list_transactions.assert_not_called()

    def test_the_list_asks_by_customer_and_subscription(self):
        self.paddle.list_transactions.return_value = {"data": []}
        self.invoices()
        self.paddle.list_transactions.assert_called_once_with(
            "ctm_1", "sub_1", after=None)

    def test_rows_are_shaped_for_the_screen(self):
        self.paddle.list_transactions.return_value = {
            "data": [
                # A plan change: the plan moved from is at negative quantity
                # and is not what was bought.
                transaction(TXN_A, items=(("pri_business", 1),
                                          ("pri_base", -1))),
                transaction(TXN_B, status="canceled", total="500",
                            items=(("pri_topup", 2),), billed_at=None),
            ],
            "meta": {"pagination": {
                "has_more": True,
                "next": "https://x/transactions?after=%s&per_page=30"
                        % TXN_B}}}
        out = self.invoices()
        first, second = out["invoices"]
        self.assertEqual(first["what"], "Small Business")
        self.assertEqual(first["billed_at"], "2026-10-01 10:00:00")
        self.assertEqual(first["amount_cents"], 6500)
        self.assertTrue(first["has_pdf"])
        self.assertEqual(second["what"], "Top-up")
        # Never billed: when it was made is its only date.
        self.assertEqual(second["billed_at"], "2026-09-30 09:00:00")
        self.assertFalse(second["has_pdf"])
        self.assertEqual((out["has_more"], out["after"]), (True, TXN_B))

    def test_the_last_page_has_no_cursor(self):
        self.paddle.list_transactions.return_value = {
            "data": [], "meta": {"pagination": {
                "has_more": False, "next": "https://x/t?after=" + TXN_B}}}
        self.assertEqual(self.invoices()["after"], None)

    def test_a_zero_invoice_has_no_pdf(self):
        self.paddle.list_transactions.return_value = {
            "data": [transaction(TXN_A, total="0")]}
        self.assertFalse(self.invoices()["invoices"][0]["has_pdf"])

    def test_the_cursor_must_be_a_transaction_id(self):
        with self.assertRaises(ValueError):
            self.invoices({"after": "txn_1&customer_id=ctm_other"})
        self.paddle.list_transactions.assert_not_called()

    def test_a_pdf_is_this_tenant_s_before_it_is_asked_for(self):
        self.paddle.list_transactions.return_value = {
            "data": [transaction(TXN_A)]}
        self.paddle.invoice_pdf_url.return_value = "https://pdf"
        self.assertEqual(self.invoices({"pdf": TXN_A}), {"url": "https://pdf"})
        self.paddle.list_transactions.assert_called_once_with(
            "ctm_1", "sub_1", ids=[TXN_A])
        self.paddle.invoice_pdf_url.assert_called_once_with(TXN_A)

    def test_another_customer_s_pdf_is_not_found(self):
        self.paddle.list_transactions.return_value = {"data": []}
        self.assertIsNone(self.invoices({"pdf": TXN_A}))
        self.paddle.invoice_pdf_url.assert_not_called()

    def test_a_pdf_paddle_does_not_make_is_refused(self):
        self.paddle.list_transactions.return_value = {
            "data": [transaction(TXN_A, status="past_due")]}
        with self.assertRaises(self.billing.Refused):
            self.invoices({"pdf": TXN_A})
        self.paddle.invoice_pdf_url.assert_not_called()

    def test_the_pdf_must_be_a_transaction_id(self):
        with self.assertRaises(ValueError):
            self.invoices({"pdf": "../subscriptions/sub_1"})
        self.paddle.list_transactions.assert_not_called()


class SeatsBoughtTest(unittest.TestCase):
    """PLAN_SEATS and DEFAULT_SEATS are gone (18.5): the count comes from the
    plan table on every path, and from nowhere else.

    THE STUB ANSWERS BY STATEMENT, not by call order. The fallback is two
    queries now - tenant.plan, then plan by that key - and a stub returning a
    fixed row for "anything not the subscription" would have handed the word
    "business" back as a seat count."""

    def setUp(self):
        self.seats = load_billing().seats

    def db(self, subscription=None, tenant_plan=None, by_key=None,
           cheapest=None):
        asked = []

        def sql(statement, params=None):
            s = " ".join(statement.split())
            asked.append(s)
            if "FROM subscription" in s:
                return rows(subscription) if subscription else rows()
            if "FROM tenant" in s:
                return rows(tenant_plan) if tenant_plan else rows()
            if "WHERE plan_key" in s:
                return rows(by_key) if by_key else rows()
            if "ORDER BY monthly_price_cents" in s:
                return rows(cheapest) if cheapest else rows()
            return rows()

        return sql, asked

    def test_reads_the_plan_through_the_subscription(self):
        sql, asked = self.db(subscription=(5,))
        with mock.patch.object(self.seats, "_sql", sql):
            self.assertEqual(self.seats.seats_bought(7), 5)
        # And stops there: a subscription is the answer.
        self.assertEqual(len(asked), 1)

    def test_falls_back_to_tenant_plan_without_a_subscription(self):
        sql, asked = self.db(tenant_plan=("business",), by_key=(5,))
        with mock.patch.object(self.seats, "_sql", sql):
            self.assertEqual(self.seats.seats_bought(7), 5)
        self.assertTrue(any("WHERE plan_key" in s for s in asked))

    def test_the_fallback_reads_the_table_rather_than_a_map(self):
        """The whole of the change. 2 is what PLAN_SEATS held for base; this
        proves the answer now comes from the row."""
        sql, _ = self.db(tenant_plan=("base",), by_key=(9,))
        with mock.patch.object(self.seats, "_sql", sql):
            self.assertEqual(self.seats.seats_bought(7), 9)

    def test_an_unknown_plan_gets_the_smallest_active_one(self):
        """What DEFAULT_SEATS was for, read rather than written down."""
        sql, _ = self.db(tenant_plan=("something-nobody-has-seen",),
                         cheapest=(2,))
        with mock.patch.object(self.seats, "_sql", sql):
            self.assertEqual(self.seats.seats_bought(7), 2)

    def test_no_plan_table_at_all_is_zero_rather_than_a_guess(self):
        sql, _ = self.db(tenant_plan=("base",))
        with mock.patch.object(self.seats, "_sql", sql):
            self.assertEqual(self.seats.seats_bought(7), 0)

    def test_the_constants_are_gone(self):
        """A map that comes back is a third place seats are recorded."""
        self.assertFalse(hasattr(self.seats, "PLAN_SEATS"))
        self.assertFalse(hasattr(self.seats, "DEFAULT_SEATS"))


if __name__ == "__main__":
    unittest.main()
