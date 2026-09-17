"""
Checkout, plan change, top-up and seat counting. Paddle is never called:
paddle_api is replaced. Run from the repository root:

    python -m unittest discover -s tests
"""

import unittest
from unittest import mock

from api_modules import load_billing, rows

# The Data API's answer to a second topup_request under one key, as dev
# returned it on 17 September 2026.
DUPLICATE_CODE = "DatabaseErrorException"
DUPLICATE_MESSAGE = ("Duplicate entry '7-k' for key "
                     "'topup_request.uq_idempotency'; Error code: 1062; "
                     "SQLState: 23000")

PLANS = rows(("base", "Base", 2, 2500, 500, 5),
             ("business", "Small Business", 5, 6500, 1500, None))


class FakeBillingDb:
    def __init__(self, subscription=None):
        self.subscription = subscription   # (sub_id, status, ends, plan_key)
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
        db = FakeBillingDb(("sub_1", "past_due", None, "base"))
        with self.use(db):
            with self.assertRaises(self.billing.Refused):
                self.billing.top_up(7, "a@firm.com", "admin",
                                    {"increments": 2, "idempotency_key": "k"})
        self.paddle.charge_topup.assert_not_called()
        self.assertEqual(db.inserted_requests, [])

    def test_top_up_records_the_request_then_charges(self):
        db = FakeBillingDb(("sub_1", "active", None, "base"))
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
        db = FakeBillingDb(("sub_1", "active", None, "base"))
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
        db = FakeBillingDb(("sub_1", "active", None, "base"))
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
        db = FakeBillingDb(("sub_1", "active", None, "base"))
        db.keys.add("k")
        db.duplicate_error = self.client_error(
            DUPLICATE_CODE, "Communications link failure; Error code: 0")
        with self.use(db):
            with self.assertRaises(self.billing.ClientError):
                self.billing.top_up(7, "a@firm.com", "admin",
                                    {"increments": 2, "idempotency_key": "k"})
        self.paddle.charge_topup.assert_not_called()

    def test_downgrade_refused_over_seats(self):
        db = FakeBillingDb(("sub_1", "active", None, "business"))
        listing = {"taken": 3, "reserved": 1}
        with self.use(db), mock.patch.object(self.billing.seats, "listing",
                                             return_value=listing):
            with self.assertRaises(self.billing.Refused):
                self.billing.change_plan(7, "a@firm.com", "admin",
                                         {"plan": "base"})
        self.paddle.change_plan.assert_not_called()

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


class SeatsBoughtTest(unittest.TestCase):
    def setUp(self):
        self.seats = load_billing().seats

    def test_reads_the_plan_through_the_subscription(self):
        def sql(statement, params=None):
            if "FROM subscription" in statement:
                return rows((5,))
            return rows(("base",))
        with mock.patch.object(self.seats, "_sql", sql):
            self.assertEqual(self.seats.seats_bought(7), 5)

    def test_falls_back_to_tenant_plan_without_a_subscription(self):
        def sql(statement, params=None):
            if "FROM subscription" in statement:
                return rows()
            return rows(("business",))
        with mock.patch.object(self.seats, "_sql", sql):
            self.assertEqual(self.seats.seats_bought(7), 5)


if __name__ == "__main__":
    unittest.main()
