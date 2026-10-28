"""
An upload under a name the engagement already holds is refused (28 October
2026).

    python -m unittest discover -s tests

THE BUG THIS CLOSES. The key is the engagement and the file name, and the
envelope that starts extraction is named after the key. Three files sent
twice into MANTY-TEST-2 replaced their first copies' files and envelopes, and
the first three documents said "extracting..." for ever, paid for.

Nothing reaches AWS: boto3 is replaced at import and _sql is a stub.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 5
WORKSPACE = 3
EMAIL = "partner@firm.com"
KEY = "tenants/5/w/3/docs/MANTY-TEST-2/Trade-Register.pdf"


class Db:
    """Engagement lookups answer a row; the document check answers `held`."""

    def __init__(self, held):
        self.held = held
        self.asked = []

    def sql(self, statement, params=None, tx=None):
        if "FROM document" in statement:
            self.asked.append({p["name"]: next(iter(p["value"].values()))
                               for p in params or []})
            self.asked[-1]["statement"] = " ".join(statement.split())
            return rows((1231,)) if self.held else rows()
        return rows((48,))


class UploadHeldTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def upload(self, held):
        db = Db(held)
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_s3") as s3:
            s3.generate_presigned_url.return_value = "https://signed"
            try:
                out = self.app.upload_url(TENANT, WORKSPACE, EMAIL,
                                          "MANTY-TEST-2", "Trade Register.pdf")
            finally:
                self.signed = s3.generate_presigned_url.called
        return out, db

    def test_a_name_already_held_is_refused_and_nothing_is_signed(self):
        with self.assertRaises(self.app.AlreadyHeld) as caught:
            self.upload(held=True)
        self.assertFalse(self.signed)
        self.assertEqual(str(caught.exception),
                         "MANTY-TEST-2 already holds Trade-Register.pdf. To "
                         "upload a new version, remove the one there first.")

    def test_a_new_name_is_signed_as_before(self):
        out, _ = self.upload(held=False)
        self.assertEqual(out["key"], KEY)
        self.assertTrue(self.signed)

    def test_it_asks_by_the_key_it_would_write_and_skips_rejected_rows(self):
        """A rejected row is in no list, so nobody could remove it; it must
        not block the name for ever."""
        _, db = self.upload(held=False)
        [asked] = db.asked
        self.assertEqual((asked["t"], asked["k"]), (TENANT, KEY))
        self.assertIn("state <> 'rejected'", asked["statement"])

    def test_the_route_answers_409_with_the_sentence(self):
        db = Db(held=True)
        event = {
            "routeKey": "POST /uploads",
            "body": json.dumps({"engagement": "MANTY-TEST-2",
                                "filename": "Trade Register.pdf"}),
            "queryStringParameters": {"workspace": str(WORKSPACE)},
            "requestContext": {"authorizer": {"jwt": {"claims": {
                "custom:tenant_id": str(TENANT), "email": EMAIL,
                "custom:role": "admin"}}}},
        }
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_s3"), \
                mock.patch.object(self.app, "_require_published"), \
                mock.patch.object(self.app.config, "workspace",
                                  return_value=WORKSPACE), \
                mock.patch.object(self.app.seats, "allowed_workspaces",
                                  return_value=None):
            reply = self.app._dispatch(event, None)
        self.assertEqual(reply["statusCode"], 409)
        self.assertIn("already holds Trade-Register.pdf",
                      json.loads(reply["body"])["error"])


if __name__ == "__main__":
    unittest.main()
