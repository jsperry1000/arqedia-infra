"""
Sending, re-sending, revoking and viewing a share, against DynamoDB and S3
as moto emulates them. Run from the repository root:

    python -m unittest discover -s tests

WHY MOTO AND NOT A FAKE. The rules that matter here live in DynamoDB
expressions - a condition that refuses the twenty-first share of the day, an
ADD that returns the new count, a put that will not overwrite an active
grant. A fake written alongside the code would agree with the code by
construction. moto at least evaluates the expressions.

WHAT IS NOT EXERCISED, and is therefore unverified until deployed: Aurora
(every read of a memo, a plan or a tenant is stubbed), the wallet (stubbed -
its own tests are test_wallet_gate and test_refund), the renderer (stubbed
to write two PDFs), SES, and the whole of Cognito - registration, MFA setup
and sign-in have no test here, because moto's TOTP support cannot be relied
on to behave as Cognito does.

NEEDS moto, boto3, pypdf and reportlab. Skipped where they are not
installed, and the skip says so.
"""

import datetime
import importlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "lambda" / "api"
SHARED = ROOT / "lambda" / "shared"
VIEWER = ROOT / "lambda" / "share_viewer"

try:
    import boto3
    from moto import mock_aws
    import pypdf  # noqa: F401
    from reportlab.pdfgen import canvas
    HAVE = True
except ImportError:
    HAVE = False

REGION = "us-east-2"
ENV = {
    "AWS_DEFAULT_REGION": REGION, "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
    "DATABASE": "arqedia", "CURATED_BUCKET": "curated",
    "RENDER_FUNCTION": "render", "APP_URL": "https://app.test",
    "SHARE_GRANT_TABLE": "grant", "VIEWER_ACCOUNT_TABLE": "viewer",
    "SHARE_ACCESS_LOG_TABLE": "log", "SHARE_USAGE_TABLE": "usage",
    "VIEWER_POOL_ID": "us-east-2_x", "VIEWER_CLIENT_ID": "client",
}


def make_tables():
    ddb = boto3.client("dynamodb", region_name=REGION)
    ddb.create_table(
        TableName="grant", BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": n, "AttributeType": t} for n, t in (
                ("grant_id", "S"), ("tenant_id", "N"), ("created_at", "S"),
                ("viewer_account_id", "S"))],
        KeySchema=[{"AttributeName": "grant_id", "KeyType": "HASH"}],
        GlobalSecondaryIndexes=[
            {"IndexName": "tenant-index", "Projection": {"ProjectionType": "ALL"},
             "KeySchema": [{"AttributeName": "tenant_id", "KeyType": "HASH"},
                           {"AttributeName": "created_at", "KeyType": "RANGE"}]},
            {"IndexName": "viewer-index", "Projection": {"ProjectionType": "ALL"},
             "KeySchema": [{"AttributeName": "viewer_account_id", "KeyType": "HASH"},
                           {"AttributeName": "created_at", "KeyType": "RANGE"}]}])
    ddb.create_table(
        TableName="viewer", BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "viewer_account_id",
                               "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "viewer_account_id", "KeyType": "HASH"}])
    ddb.create_table(
        TableName="log", BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "grant_id", "AttributeType": "S"},
                              {"AttributeName": "occurred_at", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "grant_id", "KeyType": "HASH"},
                   {"AttributeName": "occurred_at", "KeyType": "RANGE"}])
    ddb.create_table(
        TableName="usage", BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "tenant_id", "AttributeType": "N"},
                              {"AttributeName": "period", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "tenant_id", "KeyType": "HASH"},
                   {"AttributeName": "period", "KeyType": "RANGE"}])
    boto3.client("s3", region_name=REGION).create_bucket(
        Bucket="curated",
        CreateBucketConfiguration={"LocationConstraint": REGION})


def a_pdf():
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 720, "A memorandum")
    c.showPage()
    c.save()
    return buffer.getvalue()


def load(module_dir, name, extra=()):
    saved = list(sys.path)
    for n in (name, "share_rules", "stamp", "mail", "wallet", "config") \
            + tuple(extra):
        sys.modules.pop(n, None)
    sys.path.insert(0, str(module_dir))
    sys.path.insert(1, str(SHARED))
    try:
        module = importlib.import_module(name)
        # Imported where it is used, inside a function, in both the renderer
        # and the viewer - so it is imported here while the path is set.
        if module_dir != SHARED:
            importlib.import_module("stamp")
        return module
    finally:
        sys.path[:] = saved


@unittest.skipUnless(HAVE, "moto, boto3, pypdf or reportlab not installed")
class SendTest(unittest.TestCase):
    """The tenant side: lambda/api/share.py."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.aws = mock_aws()
        self.aws.start()
        make_tables()
        sys.modules.pop("app", None)
        self.share = load(API, "share")
        s = self.share
        self.wallet = s.wallet
        self.s3 = boto3.client("s3", region_name=REGION)

        # Aurora, stubbed.
        self.plan = {"base": 10, "business": 25}
        self.standing = self.wallet.ACTIVE
        self.sub = {"plan_key": "base",
                    "period_ends_at": "2026-10-20 20:26:37"}
        s._memo = lambda t, m: {"memo_id": int(m), "label": "KYC 11.1",
                                "subject": "Meridian Trading Ltd"} \
            if int(m) in (11, 12) else None
        s._tenant_name = lambda t: "TESTCO A"
        s._plan_allowance = lambda k: self.plan[k]
        s._subscription = lambda t: self.sub
        s._trial_ends_at = lambda t: "2026-10-14 00:00:00"

        # The wallet, stubbed.
        self.prices = {"share_overage_base": 100, "share_overage_business": 25}
        self.charges = []
        self.balance = 500
        self.wallet.standing = lambda t: self.standing

        def unit_price(t, e):
            if e not in self.prices:
                raise self.wallet.Unpriced(e)
            return self.prices[e]
        self.wallet.unit_price = unit_price
        self.wallet.available = lambda t, purchased_only=False: self.balance

        def charge(t, email, event, n, reference, idempotency_key):
            if any(c[3] == idempotency_key for c in self.charges):
                return {"entry_id": 1, "amount_cents": self.prices[event],
                        "repeated": True}
            if self.balance < self.prices[event]:
                raise self.wallet.InsufficientFunds(self.prices[event],
                                                    self.balance)
            self.charges.append((t, event, n, idempotency_key))
            return {"entry_id": 900 + len(self.charges),
                    "amount_cents": self.prices[event], "repeated": False}
        self.wallet.charge = charge

        # The renderer, stubbed to write what share mode writes.
        def render(tenant_id, memo_id, recipient, shared_at, prefix):
            for name in ("base.pdf", "view.pdf"):
                self.s3.put_object(Bucket="curated", Key=prefix + name,
                                   Body=a_pdf())
            return prefix + "base.pdf", prefix + "view.pdf"
        s._render = render

        self.mails = []
        s.mail.send = lambda to, subject, body, reply_to=None: \
            self.mails.append((to, subject, body, reply_to)) or True

    def tearDown(self):
        self.aws.stop()
        self.env.stop()

    def send(self, memo=11, to="j.ferrers@northbank.com", key="k1", **extra):
        body = dict({"recipient": to, "authority_affirmed": True,
                     "idempotency_key": key}, **extra)
        return self.share.send(1, "sp@ebl.test", memo, body)

    def usage(self, period):
        return self.share._counted(1, period)

    def objects(self):
        return [o["Key"] for o in self.s3.list_objects_v2(
            Bucket="curated").get("Contents", [])]

    def today(self):
        return "d" + datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%d")

    # --- the first send ------------------------------------------------------

    def test_a_send_within_the_allowance_is_free_and_active(self):
        sent = self.send()
        self.assertTrue(sent["sent"])
        self.assertEqual(sent["charged_cents"], 0)
        self.assertNotIn("link_token", sent)
        self.assertEqual(self.charges, [])
        self.assertEqual(self.usage("p2026-10-20 20:26:37"), 1)
        self.assertEqual(self.usage(self.today()), 1)
        grant = self.share._table("grant").get_item(
            Key={"grant_id": sent["grant_id"]})["Item"]
        self.assertEqual(grant["status"], "active")
        self.assertIn("#t=" + grant["link_token"], self.mails[0][2])
        self.assertEqual(self.mails[0][3], "sp@ebl.test")

    def test_the_authority_box_is_required(self):
        with self.assertRaises(ValueError):
            self.share.send(1, "sp@ebl.test", 11, {
                "recipient": "a@b.com", "idempotency_key": "k"})
        self.assertEqual(self.objects(), [])

    def test_a_memo_this_tenant_does_not_hold_is_not_found(self):
        self.assertIsNone(self.send(memo=99))

    def test_a_verified_recipient_gets_two_weeks(self):
        sent = self.send()
        ends = datetime.datetime.strptime(sent["expires_at"],
                                          "%Y-%m-%dT%H:%M:%SZ")
        began = datetime.datetime.strptime(sent["sent_at"],
                                           "%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(ends - began, datetime.timedelta(days=14))
        self.assertFalse(sent["expiry_set_by_tenant"])

    def test_a_tenant_date_is_recorded_as_one(self):
        sent = self.send(expiry_days=30)
        self.assertTrue(sent["expiry_set_by_tenant"])

    # --- the allowance -------------------------------------------------------

    def fill(self, n):
        self.share._table("usage").put_item(Item={
            "tenant_id": 1, "period": "p2026-10-20 20:26:37", "count": n})

    def test_past_the_allowance_without_the_price_nothing_happens(self):
        self.fill(10)
        with self.assertRaises(self.share.OverageNotAccepted) as caught:
            self.send()
        self.assertEqual(caught.exception.unit_cents, 100)
        self.assertEqual(self.usage("p2026-10-20 20:26:37"), 10)
        self.assertEqual(self.usage(self.today()), 0)
        self.assertEqual(self.objects(), [])
        self.assertEqual(self.share._table("grant").scan()["Items"], [])
        self.assertEqual(self.mails, [])

    def test_past_the_allowance_with_the_price_it_is_charged(self):
        self.fill(10)
        sent = self.send(accept_overage_cents=100)
        self.assertEqual(sent["charged_cents"], 100)
        self.assertEqual(self.charges, [(1, "share_overage_base", 1, "k1")])
        self.assertEqual(self.usage("p2026-10-20 20:26:37"), 11)

    def test_business_is_charged_its_own_price_past_25(self):
        self.sub = {"plan_key": "business", "period_ends_at": "2026-11-01"}
        self.share._table("usage").put_item(Item={
            "tenant_id": 1, "period": "p2026-11-01", "count": 25})
        sent = self.send(accept_overage_cents=25)
        self.assertEqual(self.charges[0][1], "share_overage_business")
        self.assertEqual(sent["charged_cents"], 25)

    def test_a_charge_refused_undoes_the_send(self):
        self.fill(10)
        self.balance = 0
        self.standing = self.wallet.ACTIVE
        # Not capped by the gate (available is read once, above), refused by
        # the wallet - the race the undo exists for.
        self.wallet.available = mock.MagicMock(side_effect=[1, 0])
        with self.assertRaises(self.wallet.InsufficientFunds):
            self.send(accept_overage_cents=100)
        self.assertEqual(self.usage("p2026-10-20 20:26:37"), 10)
        self.assertEqual(self.usage(self.today()), 0)
        self.assertEqual(self.objects(), [])
        self.assertEqual(self.share._table("grant").scan()["Items"], [])

    def test_a_trial_is_bases_ten_once_for_the_whole_trial(self):
        self.standing = self.wallet.TRIAL
        self.sub = {"plan_key": "business", "period_ends_at": "x"}
        state = self.share.allowance(1)
        self.assertEqual((state["plan"], state["period"], state["allowance"],
                          state["overage_event"]),
                         ("base", "trial", 10, "share_overage_base"))

    def test_a_capped_workspace_cannot_send(self):
        self.balance = 0
        with self.assertRaises(self.share.Capped):
            self.send()
        self.assertEqual(self.usage(self.today()), 0)

    def test_the_twenty_first_today_is_refused(self):
        self.share._table("usage").put_item(Item={
            "tenant_id": 1, "period": self.today(), "count": 20})
        with self.assertRaises(self.share.RateLimited):
            self.send()
        self.assertEqual(self.usage(self.today()), 20)
        self.assertEqual(self.objects(), [])

    # --- a send that failed part way ----------------------------------------

    def test_a_retry_after_the_charge_does_not_charge_again(self):
        self.fill(10)
        grants = self.share._table("grant")

        # Fail at the activation, after the charge was recorded.
        original = self.share._table

        class Failing:
            def __init__(self, table):
                self.table = table

            def __getattr__(self, name):
                return getattr(self.table, name)

            def update_item(self, **kwargs):
                if ":active" in kwargs.get("ExpressionAttributeValues", {}) \
                        and "activated_at" in kwargs["UpdateExpression"]:
                    raise RuntimeError("lost the connection")
                return self.table.update_item(**kwargs)

        self.share._table = lambda name: Failing(original(name)) \
            if name == "grant" else original(name)
        with self.assertRaises(RuntimeError):
            self.send(accept_overage_cents=100)
        self.share._table = original

        pending = grants.scan()["Items"][0]
        self.assertEqual(pending["status"], "pending")
        self.assertIn("charge_entry_id", pending)

        # Same click: activates, does not charge, does not count again.
        sent = self.send(accept_overage_cents=100)
        self.assertEqual(len(self.charges), 1)
        self.assertEqual(self.usage("p2026-10-20 20:26:37"), 11)
        self.assertEqual(sent["charged_cents"], 100)

    # --- re-sending and revoking --------------------------------------------

    def test_a_resend_is_the_same_grant_and_uses_no_allowance(self):
        first = self.send(key="k1")
        token = self.share._table("grant").get_item(
            Key={"grant_id": first["grant_id"]})["Item"]["link_token"]
        again = self.send(key="k2")
        self.assertEqual(again["grant_id"], first["grant_id"])
        self.assertEqual(self.usage("p2026-10-20 20:26:37"), 1)
        self.assertEqual(self.usage(self.today()), 2)
        self.assertEqual(len(self.share._table("grant").scan()["Items"]), 1)
        self.assertIn("#t=" + token, self.mails[1][2])

    def test_revoke_then_resend_reinstates_the_same_item(self):
        first = self.send()
        revoked = self.share.revoke(1, "other@ebl.test", first["grant_id"])
        self.assertTrue(revoked["revoked"])
        self.assertEqual(revoked["revoked_by"], "other@ebl.test")
        again = self.send(key="k9")
        self.assertTrue(again["reinstated"])
        item = self.share._table("grant").get_item(
            Key={"grant_id": first["grant_id"]})["Item"]
        self.assertFalse(item["revoked"])
        self.assertNotIn("revoked_at", item)
        self.assertEqual(item["reinstated_by"], "sp@ebl.test")
        self.assertEqual(self.charges, [])

    def test_another_tenant_cannot_revoke(self):
        first = self.send()
        self.assertIsNone(self.share.revoke(2, "x@y.z", first["grant_id"]))

    def test_revoking_works_when_capped(self):
        first = self.send()
        self.balance = 0
        self.assertTrue(self.share.revoke(1, "sp@ebl.test",
                                          first["grant_id"])["revoked"])

    def test_the_list_shows_active_grants_and_the_allowance(self):
        self.send(memo=11)
        self.send(memo=12, key="k2")
        listed = self.share.listing(1)
        self.assertEqual(len(listed["grants"]), 2)
        self.assertEqual(listed["allowance"]["used"], 2)
        self.assertEqual(listed["allowance"]["remaining"], 8)
        self.assertTrue(all("link_token" not in g for g in listed["grants"]))

    def test_purge_takes_everything_the_tenant_had(self):
        self.send()
        self.share.purge_tenant(1)
        self.assertEqual(self.share._table("grant").scan()["Items"], [])
        self.assertEqual(self.share._table("usage").scan()["Items"], [])
        self.assertEqual(self.objects(), [])


@unittest.skipUnless(HAVE, "moto, boto3, pypdf or reportlab not installed")
class ViewerTest(unittest.TestCase):
    """The recipient's side: lambda/share_viewer/app.py."""

    def setUp(self):
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.aws = mock_aws()
        self.aws.start()
        make_tables()
        self.app = load(VIEWER, "app")
        self.rules = sys.modules["share_rules"]
        self.app._lambda = mock.MagicMock()
        self.s3 = boto3.client("s3", region_name=REGION)
        self.grants = boto3.resource("dynamodb", region_name=REGION).Table("grant")
        self.viewer = self.rules.viewer_account_id("j.ferrers@northbank.com")
        self.gid = self.rules.grant_id(11, self.viewer)
        prefix = "shares/1/11/%s/20261001T140322Z/" % self.viewer
        for name in ("base.pdf", "view.pdf"):
            self.s3.put_object(Bucket="curated", Key=prefix + name,
                               Body=a_pdf())
        now = self.rules.now()
        self.grant = {
            "grant_id": self.gid, "tenant_id": 1, "memo_id": 11,
            "viewer_account_id": self.viewer,
            "recipient_email": "j.ferrers@northbank.com",
            "status": "active", "created_at": self.rules.iso(now),
            "sent_at": self.rules.iso(now),
            "expires_at": self.rules.iso(now + datetime.timedelta(days=14)),
            "expiry_set_by_tenant": False, "revoked": False,
            "link_token": "secret-token", "base_key": prefix + "base.pdf",
            "view_key": prefix + "view.pdf", "memo_label": "KYC 11.1",
            "subject": "Meridian", "tenant_name": "TESTCO A",
            "opens": 0, "downloads": 0}
        self.grants.put_item(Item=self.grant)
        self.context = mock.MagicMock(function_name="share-viewer")

    def tearDown(self):
        self.aws.stop()
        self.env.stop()

    def call(self, route, token="secret-token", gid=None, body=None,
             claims=None):
        event = {"routeKey": route,
                 "pathParameters": {"grant_id": gid or self.gid},
                 "headers": {"authorization": "Share " + token} if token else {},
                 "body": json.dumps(body or {}),
                 "requestContext": {"http": {"sourceIp": "1.2.3.4",
                                             "userAgent": "test"}}}
        if claims:
            event["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
        reply = self.app.lambda_handler(event, self.context)
        return reply["statusCode"], json.loads(reply["body"])

    def test_the_link_opens_the_watermarked_copy(self):
        status, page = self.call("GET /view/{grant_id}")
        self.assertEqual(status, 200)
        self.assertIn("view.pdf", page["view_url"])
        self.assertNotIn("markdown", page)
        self.assertFalse(page["registered"])

    def test_every_refusal_reads_the_same(self):
        said = set()
        status, body = self.call("GET /view/{grant_id}", token="wrong")
        said.add((status, body["error"]))
        self.grants.update_item(Key={"grant_id": self.gid},
                                UpdateExpression="SET revoked = :y",
                                ExpressionAttributeValues={":y": True})
        said.add(tuple(self.call("GET /view/{grant_id}")[0:1])
                 + (self.call("GET /view/{grant_id}")[1]["error"],))
        status, body = self.call("GET /view/{grant_id}",
                                 gid="11#" + "0" * 32)
        said.add((status, body["error"]))
        self.assertEqual(len(said), 1)
        self.assertEqual(said.pop()[0], 404)

    def test_revoked_is_refused_on_the_very_next_request(self):
        self.assertEqual(self.call("GET /view/{grant_id}")[0], 200)
        self.grants.update_item(Key={"grant_id": self.gid},
                                UpdateExpression="SET revoked = :y",
                                ExpressionAttributeValues={":y": True})
        self.assertEqual(self.call("GET /view/{grant_id}")[0], 404)

    def test_expired_and_pending_are_refused(self):
        self.grants.update_item(
            Key={"grant_id": self.gid},
            UpdateExpression="SET expires_at = :e",
            ExpressionAttributeValues={":e": "2020-01-01T00:00:00Z"})
        self.assertEqual(self.call("GET /view/{grant_id}")[0], 404)
        self.grants.put_item(Item=dict(self.grant, status="pending"))
        self.assertEqual(self.call("GET /view/{grant_id}")[0], 404)

    def test_the_first_open_makes_a_verified_viewer_once(self):
        self.call("GET /view/{grant_id}")
        accounts = boto3.resource("dynamodb", region_name=REGION).Table("viewer")
        first = accounts.get_item(Key={"viewer_account_id": self.viewer})["Item"]
        self.call("GET /view/{grant_id}")
        again = accounts.get_item(Key={"viewer_account_id": self.viewer})["Item"]
        self.assertEqual(first["verified_at"], again["verified_at"])
        self.assertFalse(again["registered"])

    def test_a_download_is_a_new_copy_with_its_own_time(self):
        status, body = self.call("POST /view/{grant_id}/download")
        self.assertEqual(status, 200)
        keys = [o["Key"] for o in self.s3.list_objects_v2(
            Bucket="curated").get("Contents", [])]
        copies = [k for k in keys if "/downloads/" in k]
        self.assertEqual(len(copies), 1)
        text = pypdf.PdfReader(io.BytesIO(self.s3.get_object(
            Bucket="curated", Key=copies[0])["Body"].read())).pages[0] \
            .extract_text()
        self.assertIn("Downloaded by j.ferrers@northbank.com", text)
        self.assertIn("attachment", body["download_url"])

    def test_the_access_log_is_written_off_the_hot_path(self):
        self.call("GET /view/{grant_id}")
        queued = json.loads(
            self.app._lambda.invoke.call_args.kwargs["Payload"])
        self.assertEqual(self.app._lambda.invoke.call_args.kwargs[
            "InvocationType"], "Event")
        self.app.lambda_handler(queued, self.context)
        item = self.grants.get_item(Key={"grant_id": self.gid})["Item"]
        self.assertEqual(int(item["opens"]), 1)
        self.assertEqual(item["first_opened_at"], queued["at"])
        log = boto3.resource("dynamodb", region_name=REGION).Table("log") \
            .scan()["Items"]
        self.assertEqual([e["action"] for e in log], ["view"])
        self.assertNotIn("1.2.3.4", json.dumps(queued))

    def test_registering_extends_from_each_grants_own_send(self):
        sent = self.rules.now() - datetime.timedelta(days=150)
        self.grants.put_item(Item=dict(
            self.grant, sent_at=self.rules.iso(sent),
            expires_at=self.rules.iso(sent + datetime.timedelta(days=14))))
        other = self.rules.grant_id(12, self.viewer)
        self.grants.put_item(Item=dict(
            self.grant, grant_id=other, memo_id=12,
            expiry_set_by_tenant=True, expires_at="2026-12-01T00:00:00Z"))
        self.assertEqual(self.app._extend(self.viewer), 1)
        moved = self.grants.get_item(Key={"grant_id": self.gid})["Item"]
        self.assertEqual(moved["expires_at"],
                         self.rules.iso(self.rules.add_months(sent, 6)))
        kept = self.grants.get_item(Key={"grant_id": other})["Item"]
        self.assertEqual(kept["expires_at"], "2026-12-01T00:00:00Z")

    def test_a_signed_in_viewer_sees_only_their_own(self):
        status, _ = self.call("GET /viewer/shares/{grant_id}", token=None,
                              claims={"email": "someone@else.com"})
        self.assertEqual(status, 404)
        status, page = self.call("GET /viewer/shares/{grant_id}", token=None,
                                 claims={"email": "J.Ferrers@northbank.com"})
        self.assertEqual(status, 200)
        status, mine = self.call("GET /viewer/shares", token=None,
                                 claims={"email": "j.ferrers@northbank.com"})
        self.assertEqual([s["grant_id"] for s in mine["shares"]], [self.gid])


class RulesTest(unittest.TestCase):
    """share_rules, which needs nothing installed."""

    def setUp(self):
        self.rules = load(SHARED, "share_rules")

    def test_six_months_clamps_to_the_end_of_february(self):
        start = datetime.datetime(2026, 8, 31, tzinfo=datetime.timezone.utc)
        self.assertEqual(self.rules.add_months(start, 6).date(),
                         datetime.date(2027, 2, 28))

    def test_a_tenant_date_wins_over_registering(self):
        sent = datetime.datetime(2026, 10, 1, tzinfo=datetime.timezone.utc)
        ceiling = sent + datetime.timedelta(days=7)
        self.assertEqual(self.rules.expires_at(sent, True, ceiling), ceiling)

    def test_the_viewer_id_ignores_case_and_space(self):
        self.assertEqual(self.rules.viewer_account_id(" A@B.com "),
                         self.rules.viewer_account_id("a@b.com"))
        self.assertEqual(len(self.rules.viewer_account_id("a@b.com")), 32)

    def test_a_malformed_grant_id_is_nothing(self):
        for bad in ("", "11", "x#" + "a" * 32, "11#short", "11#" + "G" * 32):
            self.assertIsNone(self.rules.split_grant_id(bad), bad)

    def test_the_token_comes_from_the_share_scheme_only(self):
        self.assertEqual(self.rules.token_from_header(
            {"Authorization": "Share abc"}), "abc")
        self.assertIsNone(self.rules.token_from_header(
            {"authorization": "eyJ.jwt.token"}))


if __name__ == "__main__":
    unittest.main()
