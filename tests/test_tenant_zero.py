"""
Nobody joins the ARQEDIA workspace by invitation: seats refuses to invite into
tenant 0, and accepting an invitation that names it is refused. Cognito, SES
and the database are replaced. Run from the repository root:

    python -m unittest discover -s tests
"""

import unittest
from unittest import mock

from api_modules import load_billing, rows
from test_signup import FakeSignupDb, load_signup, EVENT


class InviteTest(unittest.TestCase):
    """seats.invite, the sending end."""

    def setUp(self):
        self.seats = load_billing().seats

    def invite(self, tenant_id):
        def sql(statement, params=None):
            return rows()
        with mock.patch.object(self.seats, "_sql", sql):
            return self.seats.invite(tenant_id, "admin@arqedia.com",
                                     "somebody@example.com", "member")

    def test_refuses_tenant_zero(self):
        with self.assertRaises(ValueError) as raised:
            self.invite(0)
        self.assertIn("ARQEDIA workspace", str(raised.exception))

    def test_refuses_anything_below_zero(self):
        with self.assertRaises(ValueError):
            self.invite(-1)

    def test_a_real_tenant_is_not_refused_by_this_guard(self):
        # It gets as far as the address check, which is the next thing invite
        # does - so the tenant guard let it through.
        with self.assertRaises(ValueError) as raised:
            with mock.patch.object(self.seats, "_sql",
                                   lambda s, p=None: rows()):
                self.seats.invite(7, "a@firm.com", "not-an-address", "member")
        self.assertIn("email address", str(raised.exception))


class AcceptTest(unittest.TestCase):
    """signup.accept, the receiving end."""

    def setUp(self):
        self.signup = load_signup()
        self.signup._rds = mock.MagicMock()
        self.signup._ses = mock.MagicMock()
        self.signup._idp = mock.MagicMock()

    def accept(self, tenant_id):
        code = self.signup._sha("token-1")
        invitation = (1, tenant_id, "admin", code, "2999-01-01 00:00:00",
                      "admin@arqedia.com")

        class Db(FakeSignupDb):
            def sql(self, statement, params=None, tx=None):
                s = " ".join(statement.split())
                if s.startswith("SELECT invitation_id"):
                    return rows(invitation)
                if "COUNT(*) FROM seat" in s:
                    return rows((0,))
                if s.startswith("SELECT plan FROM tenant"):
                    return rows(("base",))
                return super().sql(statement, params, tx)

        db = Db()
        with mock.patch.object(self.signup, "_sql", db.sql):
            reply = self.signup.accept(EVENT, {"email": "somebody@example.com",
                                               "token": "token-1",
                                               "password": "pw"})
        return reply, db

    def test_refuses_an_invitation_naming_tenant_zero(self):
        reply, db = self.accept(0)
        self.assertEqual(reply["statusCode"], 400)
        self.assertIn("ARQEDIA workspace", reply["body"])
        self.assertEqual(db.inserted("seat"), [])
        self.signup._idp.admin_create_user.assert_not_called()

    def test_records_the_refusal_as_an_attempt(self):
        _, db = self.accept(0)
        [attempt] = db.inserted("signup_attempt")
        self.assertEqual(attempt["o"], "invite_refused")

    def test_a_real_tenant_still_takes_its_seat(self):
        reply, db = self.accept(7)
        self.assertEqual(reply["statusCode"], 200)
        [seat] = db.inserted("seat")
        self.assertEqual((seat["t"], seat["e"]), (7, "somebody@example.com"))
        self.signup._idp.admin_create_user.assert_called_once()


if __name__ == "__main__":
    unittest.main()
