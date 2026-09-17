"""
The standing gate in wallet.py: what a tenant may spend when payment has
failed or a cancelled subscription has run out. Run from the repository root:

    python -m unittest discover -s tests
"""

import unittest
from unittest import mock

from api_modules import load_billing, rows


class FakeDb:
    """Answers wallet.py's statements from a list of buckets."""

    def __init__(self, status, period_over, buckets):
        self.status = status
        self.period_over = period_over
        self.buckets = buckets
        self.allocated = []
        self.ledger_written = False

    def _visible(self, statement):
        only = "kind = 'purchased'" in statement
        return [b for b in self.buckets if not only or b["kind"] == "purchased"]

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        if "FROM subscription" in s:
            if self.status is None:
                return rows()
            return rows((self.status, 1 if self.period_over else 0))
        if "FROM meter_price" in s:
            return rows((25,))
        if s.startswith("SELECT entry_id, amount_cents FROM wallet_ledger"):
            return rows()
        if "AS remaining" in s:
            return rows(*[(b["bucket_id"], b["remaining"])
                          for b in self._visible(s)])
        if "COALESCE(SUM" in s:
            return rows((sum(b["remaining"] for b in self._visible(s)),))
        if s.startswith("INSERT INTO wallet_ledger"):
            self.ledger_written = True
            return rows()
        if "LAST_INSERT_ID" in s:
            return rows((1,))
        if s.startswith("INSERT INTO wallet_allocation"):
            bucket = next(p for p in params if p["name"] == "b")
            self.allocated.append(bucket["value"]["longValue"])
        return rows()


MONTHLY = {"bucket_id": 1, "kind": "monthly_credit", "remaining": 500}
PURCHASED = {"bucket_id": 2, "kind": "purchased", "remaining": 500}


class GateTest(unittest.TestCase):
    def setUp(self):
        self.wallet = load_billing().wallet
        self.wallet._rds = mock.MagicMock()
        self.wallet._rds.begin_transaction.return_value = {"transactionId": "tx"}

    def charge(self, db):
        with mock.patch.object(self.wallet, "_sql", db.sql):
            return self.wallet.charge(7, "a@firm.com", "document_filed", 1,
                                      "1 document filed", "key-1")

    def test_classify_standing(self):
        c = self.wallet.classify_standing
        self.assertEqual(c(False, None, False), "trial")
        self.assertEqual(c(True, "active", False), "active")
        self.assertEqual(c(True, "past_due", False), "purchased_only")
        self.assertEqual(c(True, "canceled", False), "active")
        self.assertEqual(c(True, "canceled", True), "purchased_only")

    def test_past_due_spends_purchased_only(self):
        db = FakeDb("past_due", False, [MONTHLY, PURCHASED])
        self.charge(db)
        self.assertEqual(db.allocated, [2])

    def test_past_due_refuses_monthly_credit(self):
        db = FakeDb("past_due", False, [MONTHLY])
        with self.assertRaises(self.wallet.InsufficientFunds) as raised:
            self.charge(db)
        self.assertTrue(raised.exception.purchased_only)
        self.assertFalse(db.ledger_written)

    def test_canceled_after_period_spends_purchased_only(self):
        db = FakeDb("canceled", True, [MONTHLY, PURCHASED])
        self.charge(db)
        self.assertEqual(db.allocated, [2])

    def test_canceled_after_period_refuses_monthly_credit(self):
        db = FakeDb("canceled", True, [MONTHLY])
        with self.assertRaises(self.wallet.InsufficientFunds):
            self.charge(db)
        self.assertFalse(db.ledger_written)

    def test_canceled_before_period_end_spends_monthly_credit(self):
        db = FakeDb("canceled", False, [MONTHLY, PURCHASED])
        self.charge(db)
        self.assertEqual(db.allocated, [1])

    def test_trial_spends_whatever_it_holds(self):
        db = FakeDb(None, False, [MONTHLY])
        self.charge(db)
        self.assertEqual(db.allocated, [1])


if __name__ == "__main__":
    unittest.main()
