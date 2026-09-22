"""
The staff console reads every tenant, and can do nothing else (Group 16.2).

    python -m unittest discover -s tests

Three kinds of test here, and the middle one is the point:

  the shape of each route, so a screen can be written against it;
  that a customer's token cannot reach the function, which is settled in
    admin_api.tf rather than in code - so the test reads the Terraform;
  that nothing in the module can write, checked three ways, because
    "it only issues SELECTs" is a claim about every line somebody might add
    tomorrow rather than about the lines here today.
"""

import importlib
import json
import os
import re
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from api_modules import rows

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "lambda" / "admin"
TERRAFORM = (ROOT / "admin_api.tf").read_text(encoding="utf-8")

# The same file with its comment lines removed. Several tests assert that a
# name is ABSENT, and the comments name the customer API deliberately - to
# say what this file must not become. A test that could not tell a warning
# from a reference would fail on the explanation of why it passes.
CODE = "\n".join(line for line in TERRAFORM.splitlines()
                 if not line.lstrip().startswith("#"))

ISSUER = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_STAFF"
CUSTOMER_ISSUER = "https://cognito-idp.us-east-2.amazonaws.com/us-east-2_CUST"

ENV = {
    "CLUSTER_ARN": "arn:cluster",
    "SECRET_ARN": "arn:secret",
    "DATABASE": "arqedia",
    "STAFF_POOL_ISSUER": ISSUER,
}


def load_admin():
    """app and cross_tenant, with nothing reaching AWS."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    fakes = {"boto3": boto3, "botocore": botocore,
             "botocore.exceptions": exceptions}

    saved = list(sys.path)
    with mock.patch.dict(sys.modules, fakes), mock.patch.dict(os.environ, ENV):
        for name in ("app", "cross_tenant"):
            sys.modules.pop(name, None)
        sys.path.insert(0, str(ADMIN))
        try:
            app = importlib.import_module("app")
            return app, importlib.import_module("cross_tenant")
        finally:
            sys.path[:] = saved


def event(route, path_params=None, query=None, issuer=ISSUER):
    return {
        "routeKey": route,
        "pathParameters": path_params,
        "queryStringParameters": query,
        "requestContext": {
            "authorizer": {"jwt": {"claims": {"iss": issuer, "sub": "s-1"}}}
        },
    }


class Db:
    """The database, answering by the shape of the statement asked."""

    def __init__(self, **answers):
        self.answers = answers
        self.asked = []

    def read(self, statement, params=None):
        s = " ".join(statement.split())
        self.asked.append(s)
        if "FROM tenant t" in s:
            return self.answers.get("tenants", rows())
        if s.startswith("SELECT name FROM tenant"):
            return self.answers.get("tenant_name", rows())
        if "FROM seat " in s or s.endswith("FROM seat"):
            return self.answers.get("seats", rows())
        if "FROM seat_invitation" in s:
            return self.answers.get("invitations", rows())
        if "COUNT(*) FROM signup_attempt" in s:
            return self.answers.get("signup_count", rows((0,)))
        if "FROM signup_attempt" in s:
            return self.answers.get("signups", rows())
        raise AssertionError("unexpected statement: %s" % s)


class RouteTest(unittest.TestCase):
    def setUp(self):
        self.app, self.cross = load_admin()

    def call(self, ev, db):
        with mock.patch.object(self.cross, "_read", db.read):
            out = self.app.lambda_handler(ev, None)
        return out["statusCode"], json.loads(out["body"])

    def test_tenants_carries_plan_seats_and_created(self):
        db = Db(tenants=rows(
            (1, "Testco", "business", "business", "active", 3,
             "2026-09-01 10:00:00", None, 16),
            (2, "Other", "base", None, None, 0,
             "2026-09-10 09:00:00", "2026-10-10 09:00:00", None),
        ))
        status, body = self.call(event("GET /tenants"), db)
        self.assertEqual(status, 200)
        self.assertEqual(len(body["tenants"]), 2)
        first = body["tenants"][0]
        self.assertEqual(first["tenant_id"], 1)
        self.assertEqual(first["name"], "Testco")
        self.assertEqual(first["plan"], "business")
        self.assertEqual(first["seats"], 3)
        self.assertEqual(first["created_at"], "2026-09-01 10:00:00")

    def test_tenants_shows_both_plans_so_a_drift_is_visible(self):
        """tenant.plan is a copy of the subscription's. A screen showing one
        of them is where the copy having drifted becomes invisible."""
        db = Db(tenants=rows((1, "Testco", "base", "business", "active", 1,
                              "2026-09-01 10:00:00", None, 16)))
        _, body = self.call(event("GET /tenants"), db)
        self.assertEqual(body["tenants"][0]["plan"], "base")
        self.assertEqual(body["tenants"][0]["subscription_plan"], "business")

    def test_seats_returns_seats_and_open_invitations(self):
        db = Db(
            tenant_name=rows(("Testco",)),
            seats=rows((5, "a@testco.com", "admin", None,
                        "2026-09-02 11:00:00")),
            invitations=rows((9, "b@testco.com", "member", "a@testco.com",
                              "2026-09-20 12:00:00", "2026-09-27 12:00:00")),
        )
        status, body = self.call(
            event("GET /tenants/{id}/seats", {"id": "1"}), db)
        self.assertEqual(status, 200)
        self.assertEqual(body["tenant_id"], 1)
        self.assertEqual(body["name"], "Testco")
        self.assertEqual(body["seats"][0]["email"], "a@testco.com")
        self.assertEqual(body["seats"][0]["role"], "admin")
        self.assertEqual(body["invitations"][0]["invitation_id"], 9)
        self.assertEqual(body["invitations"][0]["expires_at"],
                         "2026-09-27 12:00:00")

    def test_an_invitation_that_lapsed_is_not_open(self):
        """The WHERE clause does it, so the test is on the statement: an
        empty list from a tenant with a revoked invitation would pass a test
        that only looked at the output."""
        db = Db(tenant_name=rows(("Testco",)))
        self.call(event("GET /tenants/{id}/seats", {"id": "1"}), db)
        [invitation] = [s for s in db.asked if "FROM seat_invitation" in s]
        self.assertIn("revoked_at IS NULL", invitation)
        self.assertIn("expires_at > NOW()", invitation)

    def test_a_tenant_that_does_not_exist_is_404(self):
        db = Db(tenant_name=rows())
        status, body = self.call(
            event("GET /tenants/{id}/seats", {"id": "77"}), db)
        self.assertEqual(status, 404)
        self.assertIn("77", body["error"])

    def test_a_tenant_id_that_is_not_a_number_is_400(self):
        db = Db()
        status, _ = self.call(
            event("GET /tenants/{id}/seats", {"id": "../1"}), db)
        self.assertEqual(status, 400)

    def test_signups_are_newest_first_and_paged(self):
        db = Db(
            signups=rows(
                (16, "ebl-finance.com", "h16", "1.2.3.4", "created", None,
                 "2026-09-21 10:00:00"),
                (15, "gmail.com", "h15", "5.6.7.8", "refused",
                 "domain already claimed", "2026-09-21 09:00:00"),
            ),
            signup_count=rows((16,)),
        )
        status, body = self.call(event("GET /signups"), db)
        self.assertEqual(status, 200)
        self.assertEqual(body["attempts"][0]["attempt_id"], 16)
        self.assertEqual(body["attempts"][1]["outcome"], "refused")
        self.assertEqual(body["limit"], 50)
        self.assertEqual(body["offset"], 0)
        self.assertEqual(body["total"], 16)
        # One page covers sixteen rows, so there is no next one.
        self.assertIsNone(body["next_offset"])
        [statement] = [s for s in db.asked if "FROM signup_attempt" in s
                       and "COUNT" not in s]
        self.assertIn("ORDER BY attempt_id DESC", statement)

    def test_signups_offers_the_next_page_when_there_is_one(self):
        db = Db(signups=rows((16, "a.com", "h", None, "created", None, "t")),
                signup_count=rows((120,)))
        _, body = self.call(
            event("GET /signups", query={"limit": "10", "offset": "20"}), db)
        self.assertEqual(body["limit"], 10)
        self.assertEqual(body["offset"], 20)
        self.assertEqual(body["next_offset"], 30)

    def test_a_limit_beyond_the_maximum_is_clamped_not_refused(self):
        db = Db(signups=rows(), signup_count=rows((0,)))
        _, body = self.call(
            event("GET /signups", query={"limit": "100000"}), db)
        self.assertEqual(body["limit"], self.cross.SIGNUP_PAGE_MAX)

    def test_signups_never_carry_an_address(self):
        """signup_attempt keeps a domain and a hash. If a column holding an
        address is ever added, this says so before a screen shows it."""
        db = Db(signups=rows((1, "ebl-finance.com", "h1", "1.2.3.4",
                              "created", None, "2026-09-21 10:00:00")),
                signup_count=rows((1,)))
        _, body = self.call(event("GET /signups"), db)
        self.assertEqual(
            set(body["attempts"][0]),
            {"attempt_id", "email_domain", "email_hash", "ip", "outcome",
             "detail", "created_at"})


class CustomerTokenTest(unittest.TestCase):
    """A customer's token is refused by construction, in admin_api.tf.

    The gateway verifies the audience and the issuer before this code runs,
    so the control is the authorizer's configuration and these read it."""

    def setUp(self):
        self.app, self.cross = load_admin()

    def authorizer(self):
        block = re.search(
            r'resource "aws_apigatewayv2_authorizer" "staff" \{(.*?)\n\}',
            TERRAFORM, re.S)
        self.assertIsNotNone(block, "the staff authorizer is not declared")
        return block.group(1)

    def test_the_audience_is_the_staff_client_and_no_other(self):
        said = self.authorizer()
        self.assertIn("audience = [aws_cognito_user_pool_client.admin.id]",
                      " ".join(said.split()))
        self.assertNotIn("aws_cognito_user_pool_client.web", said)

    def test_the_issuer_is_the_staff_pool_and_no_other(self):
        said = self.authorizer()
        self.assertIn("aws_cognito_user_pool.staff.id", said)
        self.assertNotIn("aws_cognito_user_pool.main.id", said)

    def test_every_route_is_behind_that_authorizer(self):
        block = re.search(
            r'resource "aws_apigatewayv2_route" "admin" \{(.*?)\n\}',
            TERRAFORM, re.S).group(1)
        self.assertIn('authorization_type = "JWT"', " ".join(block.split()))
        self.assertIn("aws_apigatewayv2_authorizer.staff.id", block)
        # The customer API's authorizer is not reachable from this file.
        self.assertNotIn("aws_apigatewayv2_authorizer.cognito", CODE)

    def test_the_gateway_is_its_own_and_not_the_customers(self):
        self.assertNotIn("aws_apigatewayv2_api.main", CODE)

    def test_one_origin_may_call_it(self):
        block = re.search(r"cors_configuration \{(.*?)\n  \}", CODE,
                          re.S).group(1)
        self.assertIn('allow_origins = ["https://${local.admin_host}"]',
                      " ".join(block.split()))
        self.assertNotIn("browser_origins", CODE)

    def test_a_token_from_another_pool_is_refused_in_the_handler_too(self):
        """Second reading of the same claim. If the authorizer were ever
        pointed elsewhere, every request fails here rather than succeeding
        quietly."""
        out = self.app.lambda_handler(
            event("GET /tenants", issuer=CUSTOMER_ISSUER), None)
        self.assertEqual(out["statusCode"], 403)
        self.assertEqual(json.loads(out["body"])["error"], "not a staff token")

    def test_no_token_at_all_is_refused(self):
        out = self.app.lambda_handler({"routeKey": "GET /tenants"}, None)
        self.assertEqual(out["statusCode"], 403)


class ReadOnlyTest(unittest.TestCase):
    """Nothing in the module can write."""

    def setUp(self):
        self.app, self.cross = load_admin()
        self.source = (ADMIN / "cross_tenant.py").read_text(encoding="utf-8")

    def test_the_door_refuses_anything_that_is_not_a_select(self):
        for statement in ("INSERT INTO tenant VALUES (1)",
                          "UPDATE tenant SET plan = 'business'",
                          "DELETE FROM tenant",
                          "  update tenant set plan = 'x'",
                          "REPLACE INTO seat VALUES (1)",
                          "TRUNCATE TABLE signup_attempt"):
            with self.assertRaises(self.cross.NotASelect, msg=statement):
                self.cross._read(statement)

    def test_every_statement_in_the_module_is_a_select(self):
        for name in dir(self.cross):
            if name.startswith("__"):
                continue  # the module's own docstring quotes its statements
            value = getattr(self.cross, name)
            if isinstance(value, str) and " FROM " in value.upper():
                self.assertTrue(
                    value.lstrip().upper().startswith("SELECT"),
                    "%s is not a SELECT" % name)

    def test_the_source_contains_no_write(self):
        """Not only the statements that exist: the words themselves are
        absent, so a write added tomorrow fails this before it is deployed."""
        for word in ("INSERT ", "UPDATE ", "DELETE ", "REPLACE INTO",
                     "TRUNCATE", "CREATE TABLE", "ALTER TABLE", "DROP "):
            found = [line for line in self.source.splitlines()
                     if word in line.upper()
                     and "NotASelect" not in line
                     and not line.lstrip().startswith("#")]
            self.assertEqual(found, [], "%r appears in cross_tenant.py" % word)

    def test_no_transaction_is_reachable(self):
        for word in ("begin_transaction", "commit_transaction",
                     "rollback_transaction", "transactionId"):
            self.assertNotIn(word, self.source)

    def test_the_role_holds_two_actions_and_no_transaction(self):
        block = re.search(
            r'data "aws_iam_policy_document" "admin" \{(.*?)\n\}\n',
            TERRAFORM, re.S).group(1)
        self.assertIn('"rds-data:ExecuteStatement"', block)
        self.assertIn('"secretsmanager:GetSecretValue"', block)
        for action in ("BeginTransaction", "CommitTransaction",
                       "RollbackTransaction", "s3:", "ses:",
                       "lambda:InvokeFunction", "kms:"):
            self.assertNotIn(action, block, "%s is granted" % action)

    def test_the_role_can_read_the_reader_secret_and_not_the_master(self):
        """16.9. The actions above permit a write to be ATTEMPTED; what
        refuses it is the identity this role can present. A role that can
        read the master secret can be arqedia_admin, and arqedia_admin can
        write anything."""
        block = re.search(
            r'data "aws_iam_policy_document" "admin" \{(.*?)\n\}\n',
            TERRAFORM, re.S).group(1)
        self.assertIn("aws_secretsmanager_secret.admin_reader.arn", block)
        self.assertNotIn("master_user_secret", block)

    def test_the_function_reads_the_database_as_the_reader(self):
        block = re.search(
            r'resource "aws_lambda_function" "admin" \{(.*?)\n\}\n',
            TERRAFORM, re.S).group(1)
        said = " ".join(block.split())
        self.assertIn(
            "SECRET_ARN = aws_secretsmanager_secret.admin_reader.arn", said)
        self.assertNotIn("master_user_secret", block)

    def test_the_master_secret_appears_nowhere_in_this_file(self):
        """Not in the role, not in the environment, not anywhere else it
        could be reintroduced by a later resource."""
        self.assertNotIn("master_user_secret", CODE)

    def test_every_route_is_a_get(self):
        block = re.search(r"admin_routes = \[(.*?)\]", TERRAFORM, re.S).group(1)
        declared = re.findall(r'"([A-Z]+) ([^"]+)"', block)
        self.assertEqual([m for m, _ in declared], ["GET", "GET", "GET"])
        self.assertEqual(sorted(p for _, p in declared),
                         ["/signups", "/tenants", "/tenants/{id}/seats"])

    def test_the_handler_serves_exactly_the_declared_routes(self):
        block = re.search(r"admin_routes = \[(.*?)\]", TERRAFORM, re.S).group(1)
        declared = set(re.findall(r'"([A-Z]+ [^"]+)"', block))
        self.assertEqual(set(self.app.ROUTES), declared)


class SeparationTest(unittest.TestCase):
    """The staff console shares the database with the customer path and
    nothing else."""

    def test_nothing_here_imports_from_lambda_api(self):
        api_modules = {
            path.stem for path in (ROOT / "lambda" / "api").glob("*.py")}
        for path in ADMIN.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for name in sorted(api_modules):
                self.assertNotIn(
                    "import %s" % name, source,
                    "%s imports %s from lambda/api" % (path.name, name))

    def test_nothing_here_imports_from_the_layer(self):
        shared = {path.stem for path in (ROOT / "lambda" / "shared").glob("*.py")}
        for path in ADMIN.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for name in sorted(shared):
                self.assertNotIn("import %s" % name, source)

    def test_the_function_carries_no_layer(self):
        block = re.search(
            r'resource "aws_lambda_function" "admin" \{(.*?)\n\}\n',
            TERRAFORM, re.S).group(1)
        self.assertNotIn("layers", block)


if __name__ == "__main__":
    unittest.main()
