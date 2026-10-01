"""
The four AI Review routes (REV-01). Run from the repository root:

    python -m unittest discover -s tests

THE CONTRACT. The API adds the administrator gate every draft route has, and
relays everything else to the reviewer unchanged. The plan gate, the draft
check, the price and the charge are the reviewer's, and are not decided a
second time here - so the API must not read the database on these routes,
and must answer with whatever status the reviewer chose.

Nothing reaches AWS: boto3 is replaced at import, the reviewer's invocation is
a stub, and _sql fails the test if it is called.
"""

import io
import json
import unittest
from unittest import mock

from api_modules import ROOT, load_api

TENANT = 7
EMAIL = "susan@vantage.test"
SESSION = "a" * 32

ROUTES = [
    "POST /config/draft/review",
    "GET /config/draft/review",
    "POST /config/draft/review/accept",
    "POST /config/draft/review/close",
]


def event(route, role="admin", body=None, query=None):
    return {
        "routeKey": route,
        "body": json.dumps(body or {}),
        "queryStringParameters": query,
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "custom:tenant_id": str(TENANT), "email": EMAIL,
            "custom:role": role}}}},
    }


class ReviewRoutesTest(unittest.TestCase):

    def setUp(self):
        self.app = load_api()
        self.invocations = []
        self.answer = {"status": 200, "body": {"ok": True}}

        def invoke(**kwargs):
            self.invocations.append(kwargs)
            return {"Payload": io.BytesIO(
                json.dumps(self.answer).encode("utf-8"))}

        def no_sql(*args, **kwargs):
            raise AssertionError("the API read the database on a review "
                                 "route; the reviewer holds those checks")

        patches = [
            mock.patch.object(self.app._lambda, "invoke", side_effect=invoke),
            mock.patch.object(self.app, "_sql", side_effect=no_sql),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def dispatch(self, *args, **kwargs):
        return self.app._dispatch(event(*args, **kwargs), None)

    def payload(self):
        [call] = self.invocations
        return json.loads(call["Payload"])

    # --- who may -----------------------------------------------------------

    def test_a_member_is_refused_on_every_route_and_nothing_is_invoked(self):
        for route in ROUTES:
            with self.subTest(route=route):
                reply = self.dispatch(route, role="member")
                self.assertEqual(reply["statusCode"], 403)
                self.assertIn("administrator",
                              json.loads(reply["body"])["error"])
        self.assertEqual(self.invocations, [])

    def test_the_refusal_does_not_claim_a_read_is_a_change(self):
        """Polling changes nothing. The refusal names reviewing, on every
        route, and is the reviewer's own sentence."""
        for route in ROUTES:
            with self.subTest(route=route):
                reply = self.dispatch(route, role="member",
                                      query={"session": SESSION})
                error = json.loads(reply["body"])["error"]
                self.assertNotIn("change", error)
                self.assertEqual(error, "only an administrator may review "
                                        "the configuration")

    # --- what is relayed ---------------------------------------------------

    def test_open_invokes_the_reviewer_and_waits_for_its_answer(self):
        self.answer = {"status": 202,
                       "body": {"session_id": SESSION, "status": "starting",
                                "price_cents": 100}}
        reply = self.dispatch("POST /config/draft/review")

        [call] = self.invocations
        self.assertEqual(call["FunctionName"], "reviewer")
        self.assertEqual(call["InvocationType"], "RequestResponse")
        self.assertEqual(self.payload(), {"action": "open", "tenant_id": TENANT,
                                          "email": EMAIL, "role": "admin"})
        self.assertEqual(reply["statusCode"], 202)
        self.assertEqual(json.loads(reply["body"])["session_id"], SESSION)

    def test_poll_takes_the_session_from_the_query(self):
        self.dispatch("GET /config/draft/review", query={"session": SESSION})
        sent = self.payload()
        self.assertEqual(sent["action"], "poll")
        self.assertEqual(sent["session_id"], SESSION)

    def test_accept_relays_the_suggestion_and_the_persons_edit(self):
        self.dispatch("POST /config/draft/review/accept", body={
            "session": SESSION, "suggestion_id": "s-0003",
            "value": "The registered name.",
            "bind_to": {"template_key": "credit", "section_key": "summary"}})
        sent = self.payload()
        self.assertEqual(sent["action"], "accept")
        self.assertEqual(sent["session_id"], SESSION)
        self.assertEqual(sent["suggestion_id"], "s-0003")
        self.assertEqual(sent["value"], "The registered name.")
        self.assertEqual(sent["bind_to"], {"template_key": "credit",
                                           "section_key": "summary"})

    def test_close_relays_the_session(self):
        self.dispatch("POST /config/draft/review/close",
                      body={"session": SESSION})
        sent = self.payload()
        self.assertEqual(sent["action"], "close")
        self.assertEqual(sent["session_id"], SESSION)

    def test_the_tenant_and_role_come_from_the_token_never_the_body(self):
        self.dispatch("POST /config/draft/review/accept", body={
            "session": SESSION, "suggestion_id": "s-0001",
            "tenant_id": 99, "role": "admin", "email": "x@y.z"})
        sent = self.payload()
        self.assertEqual(sent["tenant_id"], TENANT)
        self.assertEqual(sent["email"], EMAIL)

    # --- the reviewer decides, the API relays ------------------------------

    def test_the_reviewers_refusals_arrive_unchanged(self):
        """The plan gate, money and staleness are the reviewer's. The status
        it chose and the sentence it wrote are what the screen receives."""
        for status, body in (
            (403, {"error": "AI Review is available on Business and "
                            "Enterprise"}),
            (402, {"error": "Not enough balance. Top up to continue.",
                   "needed_cents": 100, "available_cents": 10,
                   "purchased_only": False}),
            (409, {"error": "this has changed since the review read it, so "
                            "the suggestion no longer applies",
                   "stale": True}),
            (400, {"error": "no draft is open"}),
        ):
            with self.subTest(status=status):
                self.invocations.clear()
                self.answer = {"status": status, "body": body}
                reply = self.dispatch("POST /config/draft/review/accept",
                                      body={"session": SESSION,
                                            "suggestion_id": "s-0001"})
                self.assertEqual(reply["statusCode"], status)
                self.assertEqual(json.loads(reply["body"]), body)

    def test_a_reviewer_crash_is_a_500_that_leaks_nothing(self):
        self.answer = {"errorMessage": "KeyError: 'secret internals'",
                       "errorType": "KeyError"}
        reply = self.dispatch("POST /config/draft/review")
        self.assertEqual(reply["statusCode"], 500)
        self.assertNotIn("secret internals", reply["body"])

    # --- the gateway -------------------------------------------------------

    def test_every_route_is_in_the_terraform(self):
        """A route the dispatcher answers and API Gateway does not carry is a
        404 at the gateway, before any of this runs."""
        terraform = (ROOT / "api.tf").read_text(encoding="utf-8")
        for route in ROUTES:
            with self.subTest(route=route):
                self.assertIn('"%s"' % route, terraform)
        self.assertIn("REVIEWER_FUNCTION", terraform)
        self.assertIn("aws_lambda_function.reviewer.arn", terraform)


if __name__ == "__main__":
    unittest.main()
