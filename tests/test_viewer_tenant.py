"""
The viewer function's half of feature/viewer-tenant-integration: "Shared
with me" for a tenant user linked to a viewer account, the line between the
two pools' tokens, and the trial prompt. Against moto, on test_share_routes'
tables and grant. Run from the repository root:

    python -m unittest discover -s tests

NEEDS moto, boto3, pypdf and reportlab, as test_share_routes does.
"""

import datetime
import unittest

import boto3

from test_share_routes import HAVE, REGION, ViewerTest

EMAIL = "j.ferrers@northbank.com"


def tenant_claims(sub="cust-sub-1", email=EMAIL, tenant="9", verified="true"):
    """A customer pool ID token's claims, as the gateway passes them."""
    return {"sub": sub, "email": email, "email_verified": verified,
            "custom:tenant_id": tenant, "custom:role": "admin"}


def viewer_claims(email=EMAIL):
    """A viewer pool ID token's claims: no tenant."""
    return {"sub": "viewer-sub", "email": email, "email_verified": "true"}


@unittest.skipUnless(HAVE, "moto, boto3, pypdf or reportlab not installed")
class SharedWithMeTest(ViewerTest):
    def setUp(self):
        super().setUp()
        self.accounts = boto3.resource("dynamodb", region_name=REGION) \
            .Table("viewer")

    def link(self, sub="cust-sub-1"):
        self.accounts.update_item(
            Key={"viewer_account_id": self.viewer},
            UpdateExpression="SET customer_sub = :s, customer_tenant_id = :t",
            ExpressionAttributeValues={":s": sub, ":t": "9"})

    def other_grant(self, address="someone.else@harbour.de", tenant=2):
        """A grant to a different address, from another tenant."""
        viewer = self.rules.viewer_account_id(address)
        grant = dict(self.grant, grant_id=self.rules.grant_id(12, viewer),
                     memo_id=12, viewer_account_id=viewer, tenant_id=tenant,
                     recipient_email=address, memo_label="Other 12.1",
                     tenant_name="OTHERCO")
        self.grants.put_item(Item=grant)
        return grant["grant_id"]

    def test_a_linked_tenant_sees_what_was_shared_with_its_address(self):
        self.link()
        status, body = self.call("GET /me/shared", token=None, device=None,
                                 claims=tenant_claims())
        self.assertEqual(status, 200)
        self.assertTrue(body["linked"])
        self.assertEqual([s["grant_id"] for s in body["shares"]], [self.gid])

    def test_never_another_address_or_another_tenants_grants(self):
        self.link()
        other = self.other_grant()
        _, body = self.call("GET /me/shared", token=None, device=None,
                            claims=tenant_claims())
        self.assertNotIn(other, [s["grant_id"] for s in body["shares"]])
        status, _ = self.call("GET /me/shared/{grant_id}", gid=other,
                              token=None, device=None, claims=tenant_claims())
        self.assertEqual(status, 404)

    def test_a_different_customer_user_is_not_the_linked_one(self):
        self.link(sub="cust-sub-1")
        status, body = self.call("GET /me/shared", token=None, device=None,
                                 claims=tenant_claims(sub="cust-sub-2"))
        self.assertEqual((status, body), (200, {"linked": False, "shares": []}))
        status, _ = self.call("GET /me/shared/{grant_id}", token=None,
                              device=None,
                              claims=tenant_claims(sub="cust-sub-2"))
        self.assertEqual(status, 404)

    def test_no_viewer_account_is_unlinked_and_empty(self):
        status, body = self.call(
            "GET /me/shared", token=None, device=None,
            claims=tenant_claims(email="nobody@firm.com"))
        self.assertEqual((status, body), (200, {"linked": False, "shares": []}))

    def test_first_visit_links_an_unlinked_account_to_this_user(self):
        status, body = self.call("GET /me/shared", token=None, device=None,
                                 claims=tenant_claims(sub="cust-sub-7"))
        self.assertTrue(body["linked"])
        held = self.accounts.get_item(
            Key={"viewer_account_id": self.viewer})["Item"]
        self.assertEqual((held["customer_sub"], held["linked_via"]),
                         ("cust-sub-7", "first-visit"))

    def test_an_unverified_address_is_never_linked(self):
        _, body = self.call("GET /me/shared", token=None, device=None,
                            claims=tenant_claims(verified="false"))
        self.assertFalse(body["linked"])
        held = self.accounts.get_item(
            Key={"viewer_account_id": self.viewer})["Item"]
        self.assertNotIn("customer_sub", held)

    def test_a_linked_tenant_opens_the_watermarked_copy(self):
        self.link()
        status, page = self.call("GET /me/shared/{grant_id}", token=None,
                                 device=None, claims=tenant_claims())
        self.assertEqual(status, 200)
        self.assertIn("view.pdf", page["view_url"])

    def test_a_viewer_token_is_refused_on_the_tenant_routes(self):
        self.link()
        status, _ = self.call("GET /me/shared", token=None, device=None,
                              claims=viewer_claims())
        self.assertEqual(status, 403)

    def test_a_tenant_token_is_refused_on_the_viewer_routes(self):
        self.link()
        status, _ = self.call("GET /viewer/shares", token=None, device=None,
                              claims=tenant_claims())
        self.assertEqual(status, 403)


@unittest.skipUnless(HAVE, "moto, boto3, pypdf or reportlab not installed")
class TrialPromptTest(ViewerTest):
    def setUp(self):
        super().setUp()
        self.accounts = boto3.resource("dynamodb", region_name=REGION) \
            .Table("viewer")

    def due(self):
        status, body = self.call("GET /viewer/shares", token=None,
                                 device=None, claims=viewer_claims())
        self.assertEqual(status, 200)
        return body["trial_prompt"]

    def answer(self, answer):
        return self.call("POST /viewer/trial-prompt", token=None, device=None,
                         claims=viewer_claims(), body={"answer": answer})

    def answered(self, days_ago, answer="not_now"):
        at = self.rules.now() - datetime.timedelta(days=days_ago)
        self.accounts.update_item(
            Key={"viewer_account_id": self.viewer},
            UpdateExpression="SET trial_prompt_answer = :a, "
                             "trial_prompt_answered_at = :at",
            ExpressionAttributeValues={":a": answer,
                                       ":at": self.rules.iso(at)})

    def test_asked_on_a_first_sign_in(self):
        self.assertTrue(self.due())

    def test_not_now_is_not_asked_again_on_the_next_sign_in(self):
        status, body = self.answer("not_now")
        self.assertEqual(status, 200)
        self.assertEqual(body["answer"], "not_now")
        self.assertFalse(self.due())
        self.assertFalse(self.due())

    def test_asked_again_after_thirty_days(self):
        self.answered(days_ago=29)
        self.assertFalse(self.due())
        self.answered(days_ago=30)
        self.assertTrue(self.due())

    def test_yes_is_also_held_for_thirty_days(self):
        self.answer("yes")
        self.assertFalse(self.due())

    def test_a_linked_tenant_is_never_asked(self):
        self.accounts.update_item(
            Key={"viewer_account_id": self.viewer},
            UpdateExpression="SET customer_sub = :s",
            ExpressionAttributeValues={":s": "cust-sub-1"})
        self.assertFalse(self.due())

    def test_any_other_answer_is_refused(self):
        status, _ = self.answer("maybe")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
