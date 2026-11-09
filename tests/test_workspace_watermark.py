"""
A workspace's own watermark text (9 November 2026, migration 055).

    python -m unittest discover -s tests -p "test_workspace_watermark.py"

An administrator sets text that goes in front of the diagonal mark on what
the workspace shares from then on. The recipient's address and the tenant
are always there after it. Read when a share is rendered, and never again.

Nothing reaches AWS: boto3 is replaced at import and every collaborator is a
stub.
"""

import sys
import unittest
from unittest import mock

from api_modules import load_api, rows
from test_share_render import HAVE_PDF, load_render, text_of
from test_memo_update import value


class SetWatermark(unittest.TestCase):

    def setUp(self):
        self.app = load_api()
        self.ws = self.app.workspaces
        self.writes = []
        self.deleted = None

        def sql(statement, params=None):
            if statement.startswith("SELECT workspace_id, name, deleted_at"):
                return rows((3, "Trade Finance", self.deleted, None, None,
                             False))
            if statement.startswith("UPDATE workspace"):
                self.writes.append((statement,
                                    {p["name"]: value(p) for p in params}))
                return {}
            raise AssertionError("unexpected SQL: " + statement)

        p = mock.patch.object(self.ws, "_sql", side_effect=sql)
        p.start()
        self.addCleanup(p.stop)

    def put(self, text, role="admin"):
        return self.ws.set_watermark(5, "a@b.com", role, 3,
                                     {"watermark_text": text})

    def test_sets_the_text_with_its_spaces_tidied(self):
        out = self.put("  STRICTLY   CONFIDENTIAL ")
        self.assertEqual(out["watermark_text"], "STRICTLY CONFIDENTIAL")
        self.assertEqual(self.writes[0][1]["x"], "STRICTLY CONFIDENTIAL")

    def test_empty_clears_it(self):
        self.assertIsNone(self.put("   ")["watermark_text"])
        self.assertIn("watermark_text = NULL", self.writes[0][0])

    def test_a_member_is_refused(self):
        with self.assertRaises(PermissionError):
            self.put("X", role="member")
        self.assertEqual(self.writes, [])

    def test_too_long_is_refused(self):
        with self.assertRaises(ValueError):
            self.put("x" * 61)
        self.assertEqual(self.writes, [])

    def test_a_deleted_workspace_is_refused(self):
        self.deleted = "2026-11-01 00:00:00"
        with self.assertRaises(self.ws.Refused):
            self.put("X")


@unittest.skipUnless(HAVE_PDF, "pypdf and reportlab are not installed")
class StampedWithIt(unittest.TestCase):

    def share(self, own_text):
        app, stamp = load_render()
        app._s3 = mock.MagicMock()
        app._sql = mock.MagicMock(return_value=rows((own_text,)))
        app._tenant = lambda t: {"name": "TESTCO A", "plan": "base",
                                 "brand_logo_key": None, "brand_deep": None,
                                 "brand_mid": None, "brand_highlight": None,
                                 "brand_light": None}
        app._memo = lambda t, m: {"bucket": "curated",
                                  "key": "tenants/1/memos/x/m.md",
                                  "generated_at": "now", "workspace_id": 3}
        body = mock.MagicMock()
        body.read.return_value = app.PREVIEW_MARKDOWN.encode("utf-8")
        app._s3.get_object.return_value = {"Body": body}
        with mock.patch.dict(sys.modules, {"stamp": stamp}):
            result = app.lambda_handler({
                "tenant_id": 1, "memo_id": 11,
                "share": {"recipient_email": "j.ferrers@northbank.com",
                          "shared_at": "2026-10-01T14:03:22Z",
                          "prefix": "shares/1/11/" + "a" * 32 + "/"}}, None)
        self.assertEqual(result["status"], "ok")
        return [c.kwargs["Body"] for c in app._s3.put_object.call_args_list]

    def test_every_page_carries_the_text_and_still_the_recipient(self):
        for pdf in self.share("NORTHBANK EYES ONLY"):
            for page in text_of(pdf):
                self.assertIn("NORTHBANK EYES ONLY", page)
                self.assertIn("j.ferrers@northbank.com", page)
                self.assertIn("TESTCO A", page)

    def test_no_text_is_the_mark_as_it_was(self):
        for pdf in self.share(None):
            for page in text_of(pdf):
                self.assertNotIn("EYES ONLY", page)
                self.assertIn("j.ferrers@northbank.com", page)


if __name__ == "__main__":
    unittest.main()
