"""
An ended trial is not reported as a live trial (18.5 follow-up).

    python -m unittest discover -s tests

WHAT WAS WRONG. standing() read the subscription table and nothing else, so a
tenant with no subscription came back "trial" for ever. A workspace six months
past trial_ends_at reported the same standing as one on its first day, and
Account.tsx - which decided "on trial" from the absence of a Paddle status -
went on counting down to a date in the past.

WHAT MUST NOT CHANGE, and is asserted here as hard as the fix itself: what the
wallet allows and refuses. standing() reaches money in exactly two places,
wallet.py:186 and :483, and both ask `== PURCHASED_ONLY` and nothing else. A
new value that is not PURCHASED_ONLY therefore cannot alter a charge - and
these tests prove it rather than reason it, because the next person to add a
standing will not read that sentence.

The bucket is what stops the spending, and it did so before this change: the
trial credit carries trial_ends_at as its own expires_at, and every query
selecting spendable money requires expires_at > NOW().

Nothing reaches AWS: _sql is a stub throughout.
"""

import unittest
from unittest import mock

from api_modules import load_billing, rows


class ClassifyTest(unittest.TestCase):
    """The table, as a pure function. Every rule lives here."""

    def setUp(self):
        self.c = load_billing().wallet.classify_standing

    def test_a_live_trial(self):
        self.assertEqual(self.c(False, None, False), "trial")
        self.assertEqual(self.c(False, None, False, trial_over=False), "trial")

    def test_an_ended_trial(self):
        self.assertEqual(self.c(False, None, False, trial_over=True),
                         "trial_ended")

    def test_the_default_keeps_every_older_caller(self):
        """trial_over defaults to False, so the three-argument form - which is
        what test_wallet_gate asserts - means exactly what it did."""
        self.assertEqual(self.c(False, None, False), "trial")

    def test_a_subscription_ignores_the_trial_entirely(self):
        """Somebody who checked out mid-trial is on their plan, whatever the
        date says. trial_over must not reach these four."""
        for over in (False, True):
            with self.subTest(trial_over=over):
                self.assertEqual(
                    self.c(True, "active", False, trial_over=over), "active")
                self.assertEqual(
                    self.c(True, "past_due", False, trial_over=over),
                    "purchased_only")
                self.assertEqual(
                    self.c(True, "canceled", False, trial_over=over), "active")
                self.assertEqual(
                    self.c(True, "canceled", True, trial_over=over),
                    "purchased_only")


class StandingTest(unittest.TestCase):
    """What standing() answers, given what the database holds."""

    def setUp(self):
        self.wallet = load_billing().wallet

    def db(self, subscription=None, trial_over=None):
        """subscription: (paddle_status, period_over) or None.
           trial_over:   True, False, or None for "no tenant row"."""
        asked = []

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            asked.append(s)
            if "FROM subscription" in s:
                return rows(subscription) if subscription else rows()
            if "FROM tenant" in s:
                return rows() if trial_over is None else rows(
                    (1 if trial_over else 0,))
            return rows()

        return sql, asked

    def standing(self, **kw):
        sql, asked = self.db(**kw)
        with mock.patch.object(self.wallet, "_sql", sql):
            return self.wallet.standing(7), asked

    # --- the four answers -------------------------------------------------

    def test_a_trial_that_is_running(self):
        said, _ = self.standing(trial_over=False)
        self.assertEqual(said, "trial")

    def test_a_trial_that_has_run_out(self):
        said, _ = self.standing(trial_over=True)
        self.assertEqual(said, "trial_ended")

    def test_a_subscription_is_what_it_is(self):
        self.assertEqual(self.standing(subscription=("active", 0))[0], "active")
        self.assertEqual(self.standing(subscription=("past_due", 0))[0],
                         "purchased_only")
        self.assertEqual(self.standing(subscription=("canceled", 1))[0],
                         "purchased_only")

    # --- the edges --------------------------------------------------------

    def test_no_tenant_row_is_a_trial_not_an_ended_one(self):
        """Nothing should ever end a trial because a row could not be read."""
        said, _ = self.standing(trial_over=None)
        self.assertEqual(said, "trial")

    def test_a_null_trial_ends_at_is_not_over(self):
        """Tenants made before signup existed carry no date. The SQL answers 0
        for them - `trial_ends_at IS NOT NULL AND ...` - and 0 is a live
        trial, not an expired one."""
        said, _ = self.standing(trial_over=False)
        self.assertEqual(said, "trial")

    def test_the_tenant_is_not_read_when_there_is_a_subscription(self):
        """One extra query, on the one path that needs it. A tenant who has
        checked out pays nothing for this change."""
        _, asked = self.standing(subscription=("active", 0))
        self.assertEqual([s for s in asked if "FROM tenant" in s], [])

    def test_the_tenant_is_read_when_there_is_not(self):
        _, asked = self.standing(trial_over=True)
        self.assertEqual(len(
            [s for s in asked if "FROM tenant" in s]), 1)


class TheWalletGateIsUnchangedTest(unittest.TestCase):
    """The constraint on this change, asserted directly.

    standing() is consulted for money in two places and both compare against
    PURCHASED_ONLY. These tests would fail the day somebody made trial_ended
    narrow what may be spent."""

    def setUp(self):
        self.wallet = load_billing().wallet

    def test_trial_ended_is_not_purchased_only(self):
        self.assertNotEqual(self.wallet.TRIAL_ENDED,
                            self.wallet.PURCHASED_ONLY)

    def test_the_gate_asks_only_about_purchased_only(self):
        """Read from the source rather than trusted: every comparison of
        standing() in wallet.py is against PURCHASED_ONLY."""
        import inspect
        source = inspect.getsource(self.wallet)
        uses = [line.strip() for line in source.splitlines()
                if "standing(tenant_id)" in line and "def " not in line]
        self.assertEqual(len(uses), 2, uses)
        for line in uses:
            self.assertIn("== PURCHASED_ONLY", line)

    def test_an_ended_trial_spends_exactly_what_a_live_one_would(self):
        """The behaviour, not the constant. Both standings take the same
        branch, so purchased_only is False in each."""
        for over in (False, True):
            with self.subTest(trial_over=over):
                def sql(statement, params=None, tx=None):
                    s = " ".join(statement.split())
                    if "FROM subscription" in s:
                        return rows()
                    if "FROM tenant" in s:
                        return rows((1 if over else 0,))
                    if "FROM meter_price" in s:
                        return rows((25,))
                    if "COALESCE(SUM" in s:
                        # The fake narrows exactly as _live_buckets does.
                        return rows((0,)) if "kind IN" in s else rows((500,))
                    return rows()

                with mock.patch.object(self.wallet, "_sql", sql):
                    quoted = self.wallet.quote(7, "document_filed", 1)
                self.assertFalse(quoted["purchased_only"])
                # 500 is the unnarrowed answer. Had the gate narrowed, this
                # would be 0 and affordable would be False.
                self.assertEqual(quoted["available_cents"], 500)
                self.assertTrue(quoted["affordable"])


if __name__ == "__main__":
    unittest.main()
