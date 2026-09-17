"""
Signup's plan and intent: checked at begin, held on pending_signup, copied to
the tenant at verify; and the trial length. Cognito, SES and the database are
replaced. Run from the repository root:

    python -m unittest discover -s tests

The SQL itself is not exercised here and is unverified until it runs against
dev with migration 019 applied.
"""

import datetime
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from api_modules import rows

ROOT = Path(__file__).resolve().parents[1]
EVENT = {"requestContext": {"http": {"sourceIp": "203.0.113.9"}}}


def load_signup():
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    env = {"CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
           "DATABASE": "arqedia", "USER_POOL_ID": "pool",
           "SENDER": "no-reply@arqedia.test"}
    modules = {"boto3": boto3, "botocore": botocore,
               "botocore.exceptions": exceptions}
    with mock.patch.dict(sys.modules, modules), mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "signup_app", ROOT / "lambda/signup/app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def plain(value):
    return None if "isNull" in value else next(iter(value.values()))


class FakeSignupDb:
    def __init__(self, plans=("base", "business"), pending=None):
        self.plans = set(plans)
        self.pending = pending
        self.statements = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        values = {p["name"]: plain(p["value"]) for p in params or []}
        self.statements.append((s, values))
        if s.startswith("SELECT 1 FROM plan"):
            return rows((1,)) if values["k"] in self.plans else rows()
        if "COUNT(*)" in s:
            return rows((0,))
        if s.startswith("SELECT pending_id"):
            return rows(self.pending) if self.pending else rows()
        if s.startswith("INSERT INTO tenant ("):
            return {"generatedFields": [{"longValue": 42}]}
        return rows()

    def inserted(self, table):
        return [v for s, v in self.statements
                if s.startswith("INSERT INTO %s (" % table)]


class SignupTest(unittest.TestCase):
    def setUp(self):
        self.signup = load_signup()
        self.signup._rds = mock.MagicMock()
        self.signup._rds.begin_transaction.return_value = {"transactionId": "tx"}
        self.signup._ses = mock.MagicMock()
        self.signup._idp = mock.MagicMock()
        not_found = type("UserNotFoundException", (Exception,), {})
        self.signup._idp.exceptions.UserNotFoundException = not_found
        self.signup._idp.admin_get_user.side_effect = not_found()

    def begin(self, db, **extra):
        body = {"email": "a@firm.com", "org_name": "Firm"}
        body.update(extra)
        with mock.patch.object(self.signup, "_sql", db.sql):
            return self.signup.begin(EVENT, body)

    def test_begin_refuses_an_unknown_plan(self):
        db = FakeSignupDb()
        reply = self.begin(db, plan="gold", intent="subscribe")
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(db.inserted("pending_signup"), [])
        self.signup._ses.send_email.assert_not_called()

    def test_begin_refuses_an_inactive_plan(self):
        db = FakeSignupDb(plans=("base",))
        reply = self.begin(db, plan="business", intent="subscribe")
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(db.inserted("pending_signup"), [])

    def test_begin_refuses_an_unknown_intent(self):
        db = FakeSignupDb()
        reply = self.begin(db, plan="base", intent="lifetime")
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(db.inserted("pending_signup"), [])
        self.signup._ses.send_email.assert_not_called()

    def test_begin_refuses_subscribe_without_a_plan(self):
        db = FakeSignupDb()
        reply = self.begin(db, intent="subscribe")
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(db.inserted("pending_signup"), [])

    def test_begin_holds_plan_and_intent_on_pending_signup(self):
        db = FakeSignupDb()
        reply = self.begin(db, plan="business", intent="subscribe")
        self.assertEqual(reply["statusCode"], 200)
        [held] = db.inserted("pending_signup")
        self.assertEqual((held["plan"], held["intent"]),
                         ("business", "subscribe"))

    def test_begin_without_plan_or_intent_holds_nulls(self):
        db = FakeSignupDb()
        reply = self.begin(db)
        self.assertEqual(reply["statusCode"], 200)
        [held] = db.inserted("pending_signup")
        self.assertEqual((held["plan"], held["intent"]), (None, None))

    def pending(self, plan, intent):
        return (1, "firm.com", self.signup._sha("123456"), 0, "Firm", None,
                "us-east-2", None, None, "2999-01-01 00:00:00", plan, intent)

    def verify(self, db):
        with mock.patch.object(self.signup, "_sql", db.sql):
            return self.signup.verify(EVENT, {"email": "a@firm.com",
                                              "code": "123456",
                                              "password": "pw"})

    def test_verify_copies_plan_and_intent_to_the_tenant(self):
        db = FakeSignupDb(pending=self.pending("business", "subscribe"))
        reply = self.verify(db)
        self.assertEqual(reply["statusCode"], 200)
        [tenant] = db.inserted("tenant")
        self.assertEqual((tenant["sp"], tenant["si"]),
                         ("business", "subscribe"))

    def test_trial_is_fourteen_days(self):
        db = FakeSignupDb(pending=self.pending(None, "trial"))
        self.verify(db)
        [tenant] = db.inserted("tenant")
        ends = datetime.datetime.strptime(tenant["trial"], "%Y-%m-%d %H:%M:%S")
        expected = datetime.datetime.utcnow() + datetime.timedelta(days=14)
        self.assertLess(abs((ends - expected).total_seconds()), 60)
        [bucket] = db.inserted("wallet_bucket")
        self.assertEqual(bucket["exp"], tenant["trial"])


if __name__ == "__main__":
    unittest.main()
