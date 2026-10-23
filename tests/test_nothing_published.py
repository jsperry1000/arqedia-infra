"""
No uploading or filing in a workspace with nothing published (PACK-01 G8).
Run from the repository root:

    python -m unittest discover -s tests

An empty workspace has no revision in use, and active_revision() falls back
to revision 1, which holds nothing in a new workspace: a document was read
against nothing and filing it still charged. Both routes now refuse first,
before an engagement row is made or a charge is taken.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 5
WS = 14


def event(route, body):
    return {"routeKey": route, "pathParameters": {"id": "Meridian"},
            "queryStringParameters": {"workspace": str(WS)},
            "body": json.dumps(body),
            "requestContext": {"authorizer": {"jwt": {"claims": {
                "custom:tenant_id": str(TENANT), "custom:role": "admin",
                "email": "a@firm.com"}}}}}


class NothingPublishedTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def dispatch(self, route, body, active_revision):
        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            if s.startswith("SELECT workspace_id, name, active_revision"):
                return rows((WS, "Own report", active_revision))
            if s.startswith("SELECT active_revision FROM workspace"):
                return rows((active_revision,))
            return rows()
        with mock.patch.object(self.app, "_sql", sql), \
                mock.patch.object(self.app.config, "_sql", sql), \
                mock.patch.object(self.app, "upload_url",
                                  return_value={"url": "u"}) as up, \
                mock.patch.object(self.app, "file_documents",
                                  return_value={"filed": 1}) as filed:
            reply = self.app._dispatch(event(route, body), None)
        return (reply["statusCode"], json.loads(reply["body"]), up, filed)

    def test_an_upload_is_refused_before_anything_is_made(self):
        status, body, up, _ = self.dispatch(
            "POST /uploads", {"engagement": "Meridian", "filename": "a.pdf"},
            None)
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], self.app.NOTHING_PUBLISHED)
        up.assert_not_called()

    def test_filing_is_refused_before_the_charge(self):
        status, body, _, filed = self.dispatch(
            "POST /engagements/{id}/file", {"decisions": []}, None)
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], self.app.NOTHING_PUBLISHED)
        filed.assert_not_called()

    def test_a_published_workspace_goes_ahead(self):
        status, _, up, _ = self.dispatch(
            "POST /uploads", {"engagement": "Meridian", "filename": "a.pdf"},
            35)
        self.assertEqual(status, 200)
        up.assert_called_once()
        status, _, _, filed = self.dispatch(
            "POST /engagements/{id}/file", {"decisions": []}, 35)
        self.assertEqual(status, 200)
        filed.assert_called_once()

    def test_workspace_0_is_not_asked(self):
        """The pack tenant and rows from before workspaces read the tenant's
        own revision."""
        def sql(statement, params=None, tx=None):
            raise AssertionError("asked the database: %s" % statement)
        with mock.patch.object(self.app, "_sql", sql):
            self.app._require_published(TENANT, 0)


if __name__ == "__main__":
    unittest.main()
