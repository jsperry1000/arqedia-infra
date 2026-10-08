"""
GET /memos: every live memorandum across engagements, for "Share a memo"
(feature/share-multi-memo). Run from the repository root:

    python -m unittest discover -s tests

Nothing reaches AWS: boto3 is replaced at import, _sql and S3 are patched.
What is tested is what list_all_memos decides - the columns, the number a
person reads, and which memoranda are greyed out for unsaved changes.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows


class FakeRegistry:
    def __init__(self, revision):
        self.revision = revision

    def label_for_template(self, key):
        return {"lender": "Lender Brief"}.get(key, key)


def memo_row(memo_id, parent=None, revision=1, engagement="Knightsbridge",
             subject="Knightsbridge Ltd", generated="2026-10-01 10:00:00"):
    """list_all_memos' SELECT, in column order: memo_id, template_key,
    config_revision, parent_memo_id, revision, generated_at, engagement name,
    subject_name."""
    return (memo_id, "lender", 3, parent, revision, generated, engagement,
            subject)


class AllMemosTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()
        self.kept = {}          # memo_id -> what this person's working copy holds
        self.statements = []

        def get_object(Bucket, Key):
            memo_id = int(Key.split("/working/memos/")[1].split("/")[0])
            if memo_id not in self.kept:
                # The harness's ClientError is a bare stand-in; the real one
                # carries .response, which is what _has_unsaved reads.
                missing = self.app.ClientError("NoSuchKey")
                missing.response = {"Error": {"Code": "NoSuchKey"}}
                raise missing
            body = mock.MagicMock()
            body.read.return_value = json.dumps(
                {"working": self.kept[memo_id]}).encode("utf-8")
            return {"Body": body}

        self.app._s3 = mock.MagicMock()
        self.app._s3.get_object.side_effect = get_object

    def listing(self, *memo_rows, email="sp@ebl.test"):
        def sql(statement, params=None):
            self.statements.append(" ".join(statement.split()))
            return rows(*memo_rows)
        with mock.patch.object(self.app, "_sql", sql), \
                mock.patch.object(self.app.config, "load",
                                  lambda t, r: FakeRegistry(r)):
            return self.app.list_all_memos(7, email)["memos"]

    def test_the_four_columns_and_the_number_a_person_reads(self):
        [m] = self.listing(memo_row(150, parent=148, revision=2))
        self.assertEqual(m["label"], "Lender Brief")
        self.assertEqual(m["number"], "148.2")
        self.assertEqual(m["engagement"], "Knightsbridge")
        self.assertEqual(m["generated_at"], "2026-10-01 10:00:00")
        self.assertFalse(m["unsaved"])

    def test_an_original_is_numbered_from_itself(self):
        [m] = self.listing(memo_row(122))
        self.assertEqual(m["number"], "122.1")

    def test_unsaved_changes_grey_a_memo_out_and_cleared_ones_do_not(self):
        self.kept = {11: {"text": "edited"}, 12: None}
        memos = self.listing(memo_row(11), memo_row(12), memo_row(13))
        self.assertEqual({m["memo_id"]: m["unsaved"] for m in memos},
                         {11: True, 12: False, 13: False})

    def test_unsaved_is_this_persons_own(self):
        self.kept = {11: {"text": "edited"}}
        self.listing(memo_row(11), email="sp@ebl.test")
        keys = [c.kwargs["Key"]
                for c in self.app._s3.get_object.call_args_list]
        self.assertEqual(keys, [self.app._working_key(7, 11, "sp@ebl.test")])

    def test_only_live_memoranda_of_this_tenant(self):
        self.listing(memo_row(11))
        self.assertIn("m.tenant_id = :t", self.statements[0])
        self.assertIn("m.state = 'live'", self.statements[0])


if __name__ == "__main__":
    unittest.main()
