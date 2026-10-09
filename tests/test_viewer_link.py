"""
The signup function's half of feature/viewer-tenant-integration: which
sign-in an address belongs to (POST /sign-in/lookup), and the link from a
viewer account to the customer user made for the same address, at signup and
at accepting an invitation. Run from the repository root:

    python -m unittest discover -s tests

Nothing reaches AWS: boto3 is replaced at import (test_signup's loader),
Cognito and DynamoDB are mocks and the database is test_signup's fake.
"""

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

from api_modules import rows
from test_signup import EVENT, FakeSignupDb, load_signup

ROOT = Path(__file__).resolve().parents[1]
TABLE = {"VIEWER_ACCOUNT_TABLE": "viewer"}


def share_rules():
    spec = importlib.util.spec_from_file_location(
        "share_rules_for_link", ROOT / "lambda/shared/share_rules.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def made(sub="sub-123"):
    """What admin_create_user answers."""
    return {"User": {"Attributes": [{"Name": "email", "Value": "x"},
                                    {"Name": "sub", "Value": sub}]}}


class Base(unittest.TestCase):
    def setUp(self):
        self.signup = load_signup()
        self.signup._rds = mock.MagicMock()
        self.signup._rds.begin_transaction.return_value = {"transactionId": "tx"}
        self.signup._ses = mock.MagicMock()
        self.signup._idp = mock.MagicMock()
        self.not_found = type("UserNotFoundException", (Exception,), {})
        self.signup._idp.exceptions.UserNotFoundException = self.not_found
        self.signup._idp.admin_create_user.return_value = made()
        self.signup._ddb = mock.MagicMock()
        self.signup._ddb.get_item.return_value = {}
        self.env = mock.patch.dict(os.environ, TABLE)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def conditional_failure(self):
        exc = self.signup.ClientError("ConditionalCheckFailedException")
        exc.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
        return exc

    def viewer(self, registered):
        self.signup._ddb.get_item.return_value = {"Item": {
            "viewer_account_id": {"S": "x"},
            "registered": {"BOOL": registered}}}


class ViewerKeyTest(Base):
    def test_the_key_is_share_rules_own(self):
        rules = share_rules()
        for address in ("j.ferrers@northbank.com", " Mixed.Case@Firm.COM "):
            self.assertEqual(self.signup._viewer_account_id(address),
                             rules.viewer_account_id(address))


class LookupTest(Base):
    def lookup(self, email="a@firm.com"):
        reply = self.signup.lambda_handler(
            dict(EVENT, routeKey="POST /sign-in/lookup",
                 body=json.dumps({"email": email})), None)
        return reply["statusCode"], json.loads(reply["body"])

    def test_a_tenant_user_is_routed_to_the_tenant_pool(self):
        self.signup._idp.admin_get_user.return_value = {"Username": "a"}
        self.assertEqual(self.lookup(), (200, {"pool": "tenant"}))

    def test_a_registered_viewer_is_routed_to_the_viewer_pool(self):
        self.signup._idp.admin_get_user.side_effect = self.not_found()
        self.viewer(registered=True)
        self.assertEqual(self.lookup(), (200, {"pool": "viewer"}))

    def test_a_recipient_who_never_registered_has_no_sign_in(self):
        self.signup._idp.admin_get_user.side_effect = self.not_found()
        self.viewer(registered=False)
        self.assertEqual(self.lookup(), (200, {"pool": "none"}))

    def test_an_address_in_both_is_flagged_both(self):
        self.signup._idp.admin_get_user.return_value = {"Username": "a"}
        self.viewer(registered=True)
        self.assertEqual(self.lookup(), (200, {"pool": "both"}))

    def test_an_unknown_address_is_none(self):
        self.signup._idp.admin_get_user.side_effect = self.not_found()
        self.assertEqual(self.lookup(), (200, {"pool": "none"}))

    def test_the_viewer_key_is_the_hash_never_the_address(self):
        self.signup._idp.admin_get_user.side_effect = self.not_found()
        self.lookup("J.Ferrers@Northbank.com")
        key = self.signup._ddb.get_item.call_args.kwargs["Key"]
        self.assertEqual(key, {"viewer_account_id": {
            "S": share_rules().viewer_account_id("j.ferrers@northbank.com")}})

    def test_a_malformed_address_is_400(self):
        self.assertEqual(self.lookup("not-an-address")[0], 400)

    def test_without_the_table_a_viewer_reads_as_none(self):
        os.environ.pop("VIEWER_ACCOUNT_TABLE")
        self.signup._idp.admin_get_user.side_effect = self.not_found()
        self.assertEqual(self.lookup(), (200, {"pool": "none"}))
        self.signup._ddb.get_item.assert_not_called()


class SignupLinkTest(Base):
    def verify(self):
        db = FakeSignupDb(pending=(
            1, "firm.com", self.signup._sha("123456"), 0, "Firm", None,
            "us-east-2", None, None, "2999-01-01 00:00:00", None, None))
        with mock.patch.object(self.signup, "_sql", db.sql):
            return self.signup.verify(EVENT, {"email": "a@firm.com",
                                              "code": "123456",
                                              "password": "pw"})

    def test_signup_links_an_existing_viewer_account(self):
        reply = self.verify()
        self.assertEqual(reply["statusCode"], 200)
        call = self.signup._ddb.update_item.call_args.kwargs
        self.assertEqual(call["Key"], {"viewer_account_id": {
            "S": share_rules().viewer_account_id("a@firm.com")}})
        values = call["ExpressionAttributeValues"]
        self.assertEqual(values[":s"], {"S": "sub-123"})
        self.assertEqual(values[":t"], {"S": "42"})
        self.assertEqual(values[":via"], {"S": "signup"})
        # Only an account that exists, and only one not linked already.
        self.assertIn("attribute_exists(viewer_account_id)",
                      call["ConditionExpression"])
        self.assertIn("attribute_not_exists(customer_sub)",
                      call["ConditionExpression"])

    def test_no_viewer_account_is_a_plain_signup(self):
        self.signup._ddb.update_item.side_effect = self.conditional_failure()
        reply = self.verify()
        self.assertEqual(reply["statusCode"], 200)

    def test_a_link_that_fails_never_fails_the_signup(self):
        self.signup._ddb.update_item.side_effect = RuntimeError("throttled")
        reply = self.verify()
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(json.loads(reply["body"])["tenant_id"], 42)

    def test_a_signup_that_rolls_back_links_nothing(self):
        self.signup._idp.admin_set_user_password.side_effect = RuntimeError("no")
        reply = self.verify()
        self.assertEqual(reply["statusCode"], 500)
        self.signup._ddb.update_item.assert_not_called()

    def test_without_the_table_nothing_is_linked_and_signup_works(self):
        os.environ.pop("VIEWER_ACCOUNT_TABLE")
        reply = self.verify()
        self.assertEqual(reply["statusCode"], 200)
        self.signup._ddb.update_item.assert_not_called()


class InvitationLinkTest(Base):
    def test_accepting_an_invitation_links_too(self):
        token = "a-token-shown-once"

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            if s.startswith("SELECT invitation_id, tenant_id, role"):
                return rows((1, 4, "member", self.signup._sha(token),
                             "2099-01-01 00:00:00", "partner@firm.com"))
            if s.startswith("SELECT plan FROM tenant"):
                return rows(("business",))
            if s.startswith("SELECT COUNT(*) FROM seat"):
                return rows((1,))
            return rows()

        self.signup._password_policy_cache = {}
        with mock.patch.object(self.signup, "_sql", sql), \
                mock.patch.object(self.signup, "_record", lambda *a, **k: None):
            reply = self.signup.accept(EVENT, {
                "email": "newcomer@firm.com", "token": token,
                "password": "Zq7wTr4mPl9x"})
        self.assertEqual(reply["statusCode"], 200)
        values = self.signup._ddb.update_item.call_args.kwargs[
            "ExpressionAttributeValues"]
        self.assertEqual((values[":s"], values[":t"], values[":via"]),
                         ({"S": "sub-123"}, {"S": "4"}, {"S": "invitation"}))


if __name__ == "__main__":
    unittest.main()
