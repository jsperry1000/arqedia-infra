"""
A password Cognito would refuse costs a sentence, not a seat (10.7).

    python -m unittest discover -s tests

Accepting an invitation writes the seat BEFORE it makes the account, so that
nobody can sign in to a workspace that does not list them. That ordering used
to mean a password two characters short was discovered inside
admin_set_user_password: seat written, account half made, everything rolled
back, and a 500 telling somebody the system had broken.

Nothing here reaches AWS. The loader is test_signup's, so there is one copy of
it; boto3 is replaced at import and the database is a stub.
"""

import json
import unittest
from unittest import mock

from api_modules import rows
from test_signup import load_signup

EVENT = {"requestContext": {"http": {"sourceIp": "203.0.113.9"}}}

TENANT = 4
INVITEE = "newcomer@firm.com"
TOKEN = "a-token-shown-once"

# auth.tf's policy, as Cognito reports it.
POLICY = {
    "MinimumLength": 12,
    "RequireUppercase": True,
    "RequireLowercase": True,
    "RequireNumbers": True,
    "RequireSymbols": False,
}


class Refused(Exception):
    """What botocore raises, in the shape the handler reads."""

    def __init__(self, code, message):
        super().__init__("An error occurred (%s) when calling the "
                         "AdminSetUserPassword operation: %s" % (code, message))
        self.response = {"Error": {"Code": code, "Message": message}}


class FakeDb:
    """Only what accept() asks for, in the order it asks."""

    def __init__(self, token_hash, expires="2099-01-01 00:00:00", taken=1):
        self.token_hash = token_hash
        self.expires = expires
        self.taken = taken
        self.statements = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        self.statements.append(s)
        if s.startswith("SELECT invitation_id, tenant_id, role"):
            return rows((1, TENANT, "member", self.token_hash, self.expires,
                         "partner@firm.com"))
        if s.startswith("SELECT plan FROM tenant"):
            return rows(("business",))
        if s.startswith("SELECT COUNT(*) FROM seat"):
            return rows((self.taken,))
        return rows()

    def wrote_a_seat(self):
        return any(s.startswith("INSERT INTO seat") for s in self.statements)


class InvitationPasswordTest(unittest.TestCase):
    def setUp(self):
        self.app = load_signup()
        # The policy is cached for the life of the container; each test starts
        # from a fresh one.
        self.app._password_policy_cache = None

    def accept(self, password, db=None, policy=POLICY, set_password=None):
        db = db or FakeDb(self.app._sha(TOKEN))
        idp = mock.MagicMock()
        if policy is None:
            idp.describe_user_pool.side_effect = Exception("AccessDenied")
        else:
            idp.describe_user_pool.return_value = {
                "UserPool": {"Policies": {"PasswordPolicy": policy}}}
        if set_password is not None:
            idp.admin_set_user_password.side_effect = set_password

        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_idp", idp), \
                mock.patch.object(self.app, "_record", lambda *a, **k: None):
            reply = self.app.accept(EVENT, {
                "email": INVITEE, "token": TOKEN, "password": password})
        return reply, json.loads(reply["body"]), db, idp

    def test_a_short_password_is_400_and_no_seat_is_written(self):
        reply, body, db, idp = self.accept("short")
        self.assertEqual(reply["statusCode"], 400)
        self.assertFalse(db.wrote_a_seat())
        idp.admin_create_user.assert_not_called()
        # The requirement, not the failure, and every missing rule at once.
        self.assertIn("at least 12 characters", body["error"])
        self.assertIn("an upper case letter", body["error"])
        self.assertIn("a number", body["error"])

    def test_one_missing_rule_reads_as_one_sentence(self):
        _, body, _, _ = self.accept("noupperhere123")
        self.assertEqual(body["error"],
                         "That password needs an upper case letter.")

    def test_a_good_password_goes_through_and_writes_the_seat(self):
        reply, body, db, idp = self.accept("Zq7wTr4mPl9x")
        self.assertEqual(reply["statusCode"], 200)
        self.assertTrue(db.wrote_a_seat())
        self.assertEqual(body["tenant_id"], TENANT)
        self.assertEqual(body["role"], "member")
        idp.admin_create_user.assert_called_once()
        idp.admin_set_user_password.assert_called_once()

    def test_the_policy_is_read_from_the_pool_not_written_here(self):
        """A pool wanting eight characters and no digits accepts what this
        one would refuse. The check must follow the pool."""
        loose = {"MinimumLength": 8, "RequireUppercase": False,
                 "RequireLowercase": True, "RequireNumbers": False,
                 "RequireSymbols": False}
        reply, _, db, _ = self.accept("plainword", policy=loose)
        self.assertEqual(reply["statusCode"], 200)
        self.assertTrue(db.wrote_a_seat())

    def test_an_unreadable_policy_refuses_nothing_itself(self):
        """The permission is new and the deployed function may not hold it.
        Where the policy cannot be read the check passes everything, and
        Cognito is left to refuse - which it does, below."""
        reply, _, db, idp = self.accept("short", policy=None)
        self.assertEqual(reply["statusCode"], 200)
        self.assertTrue(db.wrote_a_seat())
        idp.describe_user_pool.assert_called_once()

    def test_cognitos_own_refusal_is_400_in_its_own_words(self):
        """The fallback: the policy could not be read, so the password
        reached Cognito. The seat is given back and the sentence shown is the
        one Cognito wrote - not "the account could not be created"."""
        said = ("Password did not conform with policy: Password must have "
                "uppercase characters")
        reply, body, db, idp = self.accept(
            "short", policy=None,
            set_password=Refused("InvalidPasswordException", said))
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(body["error"], said)
        # Written, then given back: the row does not survive the refusal.
        self.assertTrue(db.wrote_a_seat())
        self.assertTrue(any(s.startswith("DELETE FROM seat")
                            for s in db.statements))
        idp.admin_delete_user.assert_called_once()

    def test_anything_else_is_still_a_500(self):
        """A failure that is not about the password keeps the sentence it
        had. A 400 saying the password was wrong, when it was not, sends
        somebody to change a password that is fine."""
        reply, body, _, _ = self.accept(
            "Zq7wTr4mPl9x",
            set_password=Refused("InternalErrorException", "boom"))
        self.assertEqual(reply["statusCode"], 500)
        self.assertIn("could not be created", body["error"])

    def test_the_link_is_checked_before_the_password(self):
        """An expired invitation is not answered with a complaint about the
        password: the link is dead whatever they typed."""
        db = FakeDb(self.app._sha(TOKEN), expires="2020-01-01 00:00:00")
        reply, body, db, _ = self.accept("short", db=db)
        self.assertEqual(reply["statusCode"], 400)
        self.assertIn("expired", body["error"])
        self.assertFalse(db.wrote_a_seat())

    def test_a_full_workspace_is_checked_before_the_password(self):
        db = FakeDb(self.app._sha(TOKEN), taken=5)
        reply, body, db, _ = self.accept("short", db=db)
        self.assertEqual(reply["statusCode"], 409)
        self.assertIn("Every seat", body["error"])
        self.assertFalse(db.wrote_a_seat())


if __name__ == "__main__":
    unittest.main()
