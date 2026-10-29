"""
The head of the memo page names the engagement (29 October 2026).

    python -m unittest discover -s tests

GET /memos/{id} returns the engagement's name beside the workspace's, read
through memo.engagement_id. Nothing reaches AWS: boto3 is replaced at import
and _sql is a stub.
"""

import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 7


class MemoHeadEngagementTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def read(self, engagement):
        asked = {}

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            if "FROM memo m" in s and "s3_bucket" in s:
                asked["memo"] = s
                return rows(("curated", "k.md", "2026-10-29 10:00:00",
                             "a@firm.com", None, None, 1, None, None,
                             "Trade Finance", 3, 12, engagement))
            return rows()

        with mock.patch.object(self.app, "_sql", sql), \
                mock.patch.object(self.app, "_not_in_revision",
                                  lambda *a, **k: []), \
                mock.patch.object(self.app.config, "workspace_of",
                                  lambda *a, **k: 12), \
                mock.patch.object(self.app, "_s3") as s3:
            s3.get_object.return_value = {
                "Body": mock.MagicMock(read=lambda: b"# A memo\n")}
            return self.app.get_memo(TENANT, 11), asked

    def test_the_engagement_name_is_returned(self):
        out, asked = self.read("NOVAL-ENERGY")
        self.assertEqual(out["engagement"], "NOVAL-ENERGY")
        self.assertEqual(out["workspace"], "Trade Finance")
        self.assertIn("LEFT JOIN engagement e ON e.engagement_id = "
                      "m.engagement_id AND e.tenant_id = m.tenant_id",
                      asked["memo"])

    def test_a_memo_with_no_engagement_says_none(self):
        out, _ = self.read(None)
        self.assertIsNone(out["engagement"])


if __name__ == "__main__":
    unittest.main()
