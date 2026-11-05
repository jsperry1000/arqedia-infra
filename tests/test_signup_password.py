"""
A password Cognito would refuse costs a sentence at sign-up, not a failure.

    python -m unittest discover -s tests

A real sign-up on 5 November 2026 was answered "The account could not be
created" twice, for a password with no upper case letter. The check accepting
an invitation has had since 10.7 was never put on this path, and the screen
asked only for twelve characters.

Nothing here reaches AWS. The loader is test_signup's; boto3 is replaced at
import and the database is a stub.
"""

import json
import re
import unittest
from pathlib import Path
from unittest import mock

from test_invitation_password import POLICY, Refused
from test_signup import EVENT, FakeSignupDb, load_signup

ROOT = Path(__file__).resolve().parents[1]
GOOD = "Zq7wTr4mPl9x"
NO_UPPER = "zq7wtr4mpl9x"


class VerifyPasswordTest(unittest.TestCase):
    def setUp(self):
        self.signup = load_signup()
        self.signup._rds = mock.MagicMock()
        self.signup._rds.begin_transaction.return_value = {"transactionId": "tx"}
        self.signup._ses = mock.MagicMock()
        self.signup._idp = mock.MagicMock()
        self.signup._idp.describe_user_pool.return_value = {
            "UserPool": {"Policies": {"PasswordPolicy": POLICY}}}

    def pending(self):
        return (1, "firm.com", self.signup._sha("123456"), 0, "Firm", None,
                "us-east-2", None, None, "2999-01-01 00:00:00", None, None)

    def verify(self, db, password, code="123456"):
        with mock.patch.object(self.signup, "_sql", db.sql):
            reply = self.signup.verify(EVENT, {
                "email": "a@firm.com", "code": code, "password": password,
                "accept_terms": True, "agreement_version": 1})
        return reply, json.loads(reply["body"])

    def test_a_password_short_of_the_rules_is_told_what_it_needs(self):
        db = FakeSignupDb(pending=self.pending())
        reply, body = self.verify(db, NO_UPPER)
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(body["error"], "That password needs an upper case letter.")

    def test_it_costs_nothing(self):
        """Nothing made, nothing rolled back, and no attempt spent: a refused
        password must not count toward the hourly limit, or a person fixing
        it is told to come back in an hour."""
        db = FakeSignupDb(pending=self.pending())
        self.verify(db, NO_UPPER)
        self.assertEqual(db.inserted("tenant"), [])
        self.assertEqual(db.inserted("signup_attempt"), [])
        self.signup._rds.begin_transaction.assert_not_called()
        self.signup._idp.admin_create_user.assert_not_called()

    def test_the_code_stays_good_for_the_next_try(self):
        db = FakeSignupDb(pending=self.pending())
        self.verify(db, NO_UPPER)
        for sent, _ in db.statements:
            self.assertNotIn("DELETE FROM pending_signup", sent)
            self.assertNotIn("attempts = attempts + 1", sent)
        reply, _ = self.verify(db, GOOD)
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(len(db.inserted("tenant")), 1)

    def test_a_wrong_code_is_answered_first(self):
        """Nobody learns anything about a password without the code."""
        db = FakeSignupDb(pending=self.pending())
        _, body = self.verify(db, NO_UPPER, code="000000")
        self.assertEqual(body["error"], "That code is not right.")

    def test_cognitos_own_refusal_is_400_in_our_words(self):
        """Where the policy cannot be read, the password reaches Cognito.
        Rolled back, as ever, and said for what it is rather than as a 500."""
        self.signup._idp.describe_user_pool.side_effect = Exception("AccessDenied")
        self.signup._idp.admin_set_user_password.side_effect = Refused(
            "InvalidPasswordException", "Password must have uppercase characters")
        db = FakeSignupDb(pending=self.pending())
        reply, body = self.verify(db, NO_UPPER)
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(body["error"], self.signup.PASSWORD_REFUSED)
        self.signup._rds.rollback_transaction.assert_called_once()
        self.signup._idp.admin_delete_user.assert_called_once()

    def test_any_other_failure_is_still_a_500(self):
        self.signup._idp.admin_create_user.side_effect = Refused(
            "InternalErrorException", "boom")
        db = FakeSignupDb(pending=self.pending())
        reply, body = self.verify(db, GOOD)
        self.assertEqual(reply["statusCode"], 500)
        self.assertIn("could not be created", body["error"])


class TheScreenAndThePoolAgreeTest(unittest.TestCase):
    """The sign-up screen holds a copy of auth.tf's policy, because it has no
    account to read the pool with. A copy that drifts is the original bug."""

    def setUp(self):
        self.rules = (ROOT / "ui/src/passwordrules.ts").read_text(encoding="utf-8")
        tf = (ROOT / "auth.tf").read_text(encoding="utf-8")
        self.policy = dict(re.findall(
            r"^\s*(minimum_length|require_\w+)\s*=\s*(\w+)",
            re.search(r"password_policy \{(.*?)\}", tf, re.S).group(1), re.M))

    def test_the_length(self):
        self.assertIn("MINIMUM_LENGTH = %s;" % self.policy["minimum_length"],
                      self.rules)

    def test_the_kinds_of_character(self):
        self.assertEqual(self.policy["require_uppercase"], "true")
        self.assertEqual(self.policy["require_lowercase"], "true")
        self.assertEqual(self.policy["require_numbers"], "true")
        # A symbol is not asked for here. If the pool starts wanting one, this
        # fails, and the screen has to learn it.
        self.assertEqual(self.policy["require_symbols"], "false")

    def test_the_servers_sentences_are_the_ones_the_screen_recognises(self):
        signup = load_signup()
        self.assertTrue(signup.PASSWORD_REFUSED.startswith("That password"))
        signup._idp = mock.MagicMock()
        signup._idp.describe_user_pool.return_value = {
            "UserPool": {"Policies": {"PasswordPolicy": POLICY}}}
        for bad in ("", "short", NO_UPPER):
            self.assertTrue(signup._password_problem(bad).startswith("That password"))
        self.assertIn('message.startsWith("That password")', self.rules)


if __name__ == "__main__":
    unittest.main()
