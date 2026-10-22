"""
No exception text reaches a person (copy review, 17 October 2026): the two
findings left open in the API after fix/copy-review-critical.

    python -m unittest discover -s tests

  * ERR-02: a rewrite composition could not be asked to start records our
    sentence on its row, and the exception goes to the log.
  * ERR-03: a value that is not a number, where a number belongs, is answered
    with our sentence rather than "invalid literal for int()". A deliberate
    refusal, also a ValueError, keeps its own words.

ERR-01, the per-section Update failure, is asserted in test_memo_update.

Nothing reaches AWS: boto3 is replaced at import and every collaborator is a
stub.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 7
EMAIL = "susan@vantage.test"


def event(route, path=None, query=None, body=None):
    return {
        "routeKey": route,
        "pathParameters": path or {},
        "queryStringParameters": query or {},
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "custom:tenant_id": str(TENANT), "email": EMAIL,
            "custom:role": "admin"}}}},
    }


def answer(reply):
    return reply["statusCode"], json.loads(reply["body"])


class RewriteNotStarted(unittest.TestCase):
    """ERR-02: start_rewrites when composition cannot be invoked."""

    def setUp(self):
        self.app = load_api()
        self.updates = []

        def sql(statement, params=None, tx=None):
            if "SELECT memo_id, workspace_id FROM memo" in statement:
                return rows((120, 3))
            if "INSERT INTO memo_rewrite" in statement:
                return {"generatedFields": [{"longValue": 501}]}
            if "UPDATE memo_rewrite" in statement:
                self.updates.append({p["name"]: p["value"] for p in params})
                return {}
            raise AssertionError("unexpected SQL: " + statement)

        patches = [
            mock.patch.object(self.app, "_sql", side_effect=sql),
            mock.patch.object(self.app._lambda, "invoke", side_effect=Exception(
                "An error occurred (TooManyRequestsException) when calling "
                "the Invoke operation: Rate exceeded")),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_the_row_carries_our_sentence_not_the_exception(self):
        started = self.app.start_rewrites(TENANT, EMAIL, 120, [
            {"heading": "## I. Summary", "text": "Meridian.",
             "prompt": "Shorter."}])
        self.assertEqual(started["rewrites"][0]["status"], "failed")
        self.assertEqual(len(self.updates), 1)
        error = self.updates[0]["e"]["stringValue"]
        self.assertEqual(error, self.app.REWRITE_NOT_STARTED)
        self.assertNotIn("TooManyRequests", error)
        self.assertNotIn("could not be started:", error)


class NotANumber(unittest.TestCase):
    """ERR-03: the dispatcher's answer to a value that is not a number."""

    def setUp(self):
        self.app = load_api()

    def test_a_query_value_that_is_not_a_number(self):
        status, body = answer(self.app._dispatch(
            event("GET /wallet/ledger", query={"limit": "abc"}), None))
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], self.app.REQUEST_NOT_A_NUMBER)
        self.assertNotIn("invalid literal", body["error"])

    def test_a_path_value_that_is_not_a_number(self):
        status, body = answer(self.app._dispatch(
            event("DELETE /documents/{document_id}",
                  path={"document_id": "12x"}), None))
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], self.app.REQUEST_NOT_A_NUMBER)

    def test_a_deliberate_refusal_keeps_its_own_words(self):
        status, body = answer(self.app._dispatch(
            event("PUT /engagements/{id}/state", path={"id": "Meridian"},
                  body={"status": "deleted"}), None))
        self.assertEqual(status, 400)
        self.assertEqual(body["error"],
                         "an engagement is open or archived, not 'deleted'")


if __name__ == "__main__":
    unittest.main()
