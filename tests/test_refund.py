"""
Giving the money back when a read fails. Run from the repository root:

    python -m unittest discover -s tests

The test that matters most is the duplicate: three failure points can call
refund for one document, and a Textract notification can be delivered twice.
Exactly one refund per document is the whole claim, and the unique key on the
ledger is what makes it true rather than a check anyone can forget.
"""

import unittest
from unittest import mock

from api_modules import load_billing, rows


class FakeDb:
    """Answers wallet.refund's statements.

    duplicate=True makes the ledger insert collide, as the Data API reports it
    - a DatabaseErrorException carrying MySQL's 1062 and the constraint name,
    not a typed error.
    """

    def __init__(self, unit_cents=25, entry_exists=True, duplicate=False):
        self.unit_cents = unit_cents
        self.entry_exists = entry_exists
        self.duplicate = duplicate
        self.statements = []
        self.committed = False
        self.rolled_back = False

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        values = {p["name"]: next(iter(p["value"].values()))
                  for p in params or []}
        self.statements.append((s, values, tx))

        if s.startswith("SELECT unit_cents, event_type FROM wallet_ledger"):
            return rows((self.unit_cents, "document_filed")) \
                if self.entry_exists else rows()
        if s.startswith("INSERT INTO wallet_ledger") and self.duplicate:
            raise self.error_class(
                "An error occurred (DatabaseErrorException): Duplicate entry "
                "'7-refund:691' for key 'wallet_ledger.uq_idempotency'; "
                "Error code: 1062")
        return rows()

    def sent(self, prefix):
        return [(s, v, t) for s, v, t in self.statements if s.startswith(prefix)]


class RefundTest(unittest.TestCase):
    def setUp(self):
        self.wallet = load_billing().wallet
        self.wallet._rds = mock.MagicMock()
        self.wallet._rds.begin_transaction.return_value = {"transactionId": "tx"}

    def run_refund(self, db, document_id=691, entry_id=7):
        db.error_class = self.wallet.ClientError
        with mock.patch.object(self.wallet, "_sql", db.sql):
            return self.wallet.refund(7, document_id, entry_id, "a@firm.com")

    # --- the money ---------------------------------------------------------

    def test_gives_back_what_was_paid(self):
        db = FakeDb(unit_cents=25)
        out = self.run_refund(db)
        self.assertTrue(out["refunded"])
        self.assertEqual(out["amount_cents"], 25)

    def test_the_amount_comes_from_the_entry_not_from_meter_price(self):
        # A price changed between the charge and the failure must not change
        # what comes back. meter_price is never consulted.
        db = FakeDb(unit_cents=40)
        out = self.run_refund(db)
        self.assertEqual(out["amount_cents"], 40)
        self.assertEqual(db.sent("SELECT unit_cents FROM meter_price"), [])
        [(_, values, _)] = db.sent("INSERT INTO wallet_bucket")
        self.assertEqual(values["c"], 40)

    def test_the_ledger_row_is_negative(self):
        db = FakeDb(unit_cents=25)
        self.run_refund(db)
        [(sent, values, _)] = db.sent("INSERT INTO wallet_ledger")
        self.assertEqual(values["a"], -25)
        self.assertEqual(values["u"], 25)
        self.assertEqual(values["e"], "document_filed_refund")

    def test_the_bucket_is_a_refund_with_thirty_days(self):
        db = FakeDb()
        self.run_refund(db)
        [(sent, values, _)] = db.sent("INSERT INTO wallet_bucket")
        self.assertIn("'refund'", sent)
        self.assertIn("INTERVAL :d DAY", sent)
        self.assertEqual(values["d"], 30)
        # The reference names the charge it reverses.
        self.assertEqual(values["ref"], "7")

    # --- exactly once ------------------------------------------------------

    def test_the_ledger_row_goes_first(self):
        # It carries the unique key, so it is the gate. The other order grants
        # money and then discovers it was a repeat.
        db = FakeDb()
        self.run_refund(db)
        writes = [s.split(" (")[0] for s, _, _ in db.statements
                  if s.startswith("INSERT INTO")]
        self.assertEqual(writes[0], "INSERT INTO wallet_ledger")
        self.assertEqual(writes[1], "INSERT INTO wallet_bucket")

    def test_a_second_refund_is_refused_and_grants_nothing(self):
        db = FakeDb(duplicate=True)
        out = self.run_refund(db)
        self.assertTrue(out["repeated"])
        self.assertFalse(out["refunded"])
        self.assertEqual(db.sent("INSERT INTO wallet_bucket"), [])
        self.wallet._rds.rollback_transaction.assert_called_once()
        self.wallet._rds.commit_transaction.assert_not_called()

    def test_the_key_is_the_document(self):
        db = FakeDb()
        self.run_refund(db, document_id=691)
        [(_, values, _)] = db.sent("INSERT INTO wallet_ledger")
        self.assertEqual(values["k"], "refund:691")

    def test_every_write_is_in_one_transaction(self):
        db = FakeDb()
        self.run_refund(db)
        for s, _, tx in db.statements:
            if s.startswith("INSERT INTO"):
                self.assertEqual(tx, "tx")
        self.wallet._rds.commit_transaction.assert_called_once()

    # --- nothing to give back ----------------------------------------------

    def test_no_charge_recorded_refunds_nothing(self):
        # Filed before migration 026, or never charged for.
        db = FakeDb()
        with mock.patch.object(self.wallet, "_sql", db.sql):
            out = self.wallet.refund(7, 691, None, "a@firm.com")
        self.assertFalse(out["refunded"])
        self.assertEqual(db.statements, [])

    def test_a_charge_that_is_not_there_refunds_nothing(self):
        db = FakeDb(entry_exists=False)
        out = self.run_refund(db)
        self.assertFalse(out["refunded"])
        self.assertEqual(db.sent("INSERT INTO wallet_ledger"), [])

    def test_a_charge_of_nothing_refunds_nothing(self):
        db = FakeDb(unit_cents=0)
        out = self.run_refund(db)
        self.assertFalse(out["refunded"])
        self.assertEqual(db.sent("INSERT INTO wallet_ledger"), [])


class RefundGenerationTest(unittest.TestCase):
    """A memorandum charged for and never written (UX02 20.1)."""

    def setUp(self):
        self.wallet = load_billing().wallet
        self.wallet._rds = mock.MagicMock()
        self.wallet._rds.begin_transaction.return_value = {"transactionId": "tx"}

    def run_refund(self, db, entry_id=50):
        db.error_class = self.wallet.ClientError
        with mock.patch.object(self.wallet, "_sql", db.sql):
            return self.wallet.refund_generation(7, entry_id, "a@firm.com")

    def generation(self, **kw):
        db = FakeDb(unit_cents=100, **kw)
        original = db.sql

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            if s.startswith("SELECT unit_cents, event_type FROM wallet_ledger"):
                db.statements.append((s, {}, tx))
                return rows((db.unit_cents, db.event)) \
                    if db.entry_exists else rows()
            return original(statement, params, tx)
        db.event = "memo_generated"
        db.sql = sql
        return db

    def test_gives_back_the_dollar(self):
        db = self.generation()
        out = self.run_refund(db)
        self.assertTrue(out["refunded"])
        self.assertEqual(out["amount_cents"], 100)
        [(_, values, _)] = db.sent("INSERT INTO wallet_ledger")
        self.assertEqual(values["a"], -100)
        self.assertEqual(values["e"], "memo_generated_refund")

    def test_the_key_is_the_charge_and_not_a_document_number(self):
        # Entry 691 and document 691 must not share a key, or whichever is
        # refunded second is refused as a repeat.
        db = self.generation()
        self.run_refund(db, entry_id=691)
        [(_, values, _)] = db.sent("INSERT INTO wallet_ledger")
        self.assertEqual(values["k"], "refund:memo:691")

    def test_the_bucket_is_a_refund_with_thirty_days(self):
        db = self.generation()
        self.run_refund(db)
        [(sent, values, _)] = db.sent("INSERT INTO wallet_bucket")
        self.assertIn("'refund'", sent)
        self.assertEqual(values["d"], 30)
        self.assertEqual(values["ref"], "50")

    def test_a_second_refund_is_refused_and_grants_nothing(self):
        db = self.generation(duplicate=True)
        out = self.run_refund(db)
        self.assertTrue(out["repeated"])
        self.assertFalse(out["refunded"])
        self.assertEqual(db.sent("INSERT INTO wallet_bucket"), [])

    def test_an_update_of_one_section_is_refunded_as_itself(self):
        # 31 October 2026: fifty cents back, named for what it reverses.
        db = self.generation()
        db.event = "memo_section_updated"
        db.unit_cents = 50
        out = self.run_refund(db)
        self.assertTrue(out["refunded"])
        self.assertEqual(out["amount_cents"], 50)
        [(_, values, _)] = db.sent("INSERT INTO wallet_ledger")
        self.assertEqual(values["e"], "memo_section_updated_refund")
        self.assertEqual(values["a"], -50)
        self.assertEqual(values["k"], "refund:memo:50")

    def test_an_entry_that_is_not_a_generation_is_not_refunded(self):
        # A wrong id must not hand back a filing or a top-up.
        db = self.generation()
        db.event = "document_filed"
        out = self.run_refund(db)
        self.assertFalse(out["refunded"])
        self.assertEqual(db.sent("INSERT INTO wallet_ledger"), [])

    def test_no_entry_refunds_nothing(self):
        db = self.generation()
        with mock.patch.object(self.wallet, "_sql", db.sql):
            out = self.wallet.refund_generation(7, None)
        self.assertFalse(out["refunded"])
        self.assertEqual(db.statements, [])


if __name__ == "__main__":
    unittest.main()
