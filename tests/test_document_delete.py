"""
Deleting a document, and what a memo made from it looks like afterwards
(8.2, decision of 20 September). Run from the repository root:

    python -m unittest discover -s tests

Nothing reaches AWS: boto3 is replaced at import, _sql is patched, and the S3
client and the transaction calls are recorded rather than made. This tests
what the handler DECIDES and in what order; the SQL itself is unverified until
it runs against dev, as every other test here is.
"""

import unittest
from unittest import mock

from api_modules import load_api, rows

DOC = 41
TENANT = 7
NAME = "Manty-SA-Articles.pdf"
KEY = "tenants/7/docs/Meridian/Manty-SA-Articles.pdf"


class FakeDb:
    """The statements the handler runs, in the order it runs them."""

    def __init__(self, state="filed", siblings=0, memo_sources=(DOC,)):
        self.state = state
        self.siblings = siblings
        self.memo_sources = list(memo_sources)
        self.ran = []
        self.ledger = [("document_filed", 25, "1 documents filed")]

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        self.ran.append((s, tx))

        if s.startswith("SELECT s3_key, state, page_from"):
            # s3_key, state, page_from, part_index, filename
            return rows((KEY, self.state, None, None, NAME))
        if s.startswith("SELECT COUNT(*) FROM document WHERE tenant_id = :t AND s3_key"):
            return rows((self.siblings,))
        return rows()


def fake_s3():
    s3 = mock.MagicMock()
    s3.deleted = []
    def delete_object(Bucket, Key):          # noqa: N803 - boto3's own names
        s3.deleted.append((Bucket, Key))
    s3.delete_object.side_effect = delete_object
    return s3


class DeleteTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def run_delete(self, db):
        s3 = fake_s3()
        rds = mock.MagicMock()
        rds.begin_transaction.return_value = {"transactionId": "tx-1"}
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_s3", s3), \
                mock.patch.object(self.app, "_rds", rds):
            outcome = self.app.remove_document(TENANT, DOC)
        return outcome, s3, rds

    def statements(self, db):
        return [s for s, _ in db.ran]

    # --- what goes, and in what order ------------------------------------

    def test_a_filed_document_is_deleted_with_its_facts(self):
        db = FakeDb(state="filed")
        outcome, s3, rds = self.run_delete(db)
        self.assertEqual(outcome, {"removed": DOC})

        wrote = [s for s in self.statements(db)
                 if s.startswith(("UPDATE", "DELETE"))]
        self.assertEqual(
            [w.split(" WHERE")[0].split(" SET")[0] for w in wrote],
            ["UPDATE memo_source",
             "DELETE FROM claim_evidence",
             "DELETE FROM extracted_value",
             "DELETE FROM document"])

        # Every write inside the one transaction, and it is committed.
        self.assertTrue(all(tx == "tx-1" for s, tx in db.ran
                            if s.startswith(("UPDATE", "DELETE"))))
        rds.commit_transaction.assert_called_once()
        rds.rollback_transaction.assert_not_called()

    def test_the_name_is_kept_on_the_memo_source_before_the_row_goes(self):
        db = FakeDb()
        self.run_delete(db)
        wrote = [s for s in self.statements(db)
                 if s.startswith(("UPDATE memo_source", "DELETE FROM document"))]
        self.assertTrue(wrote[0].startswith("UPDATE memo_source"))
        self.assertTrue(wrote[1].startswith("DELETE FROM document"))

    def test_memo_and_ledger_are_not_touched(self):
        db = FakeDb()
        self.run_delete(db)
        for s in self.statements(db):
            for table in ("memo ", "wallet_ledger", "wallet_allocation",
                          "wallet_bucket", "claim "):
                self.assertNotIn("DELETE FROM " + table, s)
                self.assertNotIn("UPDATE " + table, s)
        # memo_source is kept: it is updated, never deleted.
        self.assertNotIn("DELETE FROM memo_source", " ".join(self.statements(db)))
        self.assertEqual(db.ledger, [("document_filed", 25, "1 documents filed")])

    def test_both_envelopes_and_the_upload_go(self):
        db = FakeDb(siblings=0)
        _, s3, _ = self.run_delete(db)
        keys = [k for _, k in s3.deleted]
        self.assertEqual(keys, [KEY + ".normalized.json",
                                KEY + ".analysed.json",
                                KEY])

    def test_the_upload_stays_while_another_part_still_reads_it(self):
        db = FakeDb(siblings=2)
        _, s3, _ = self.run_delete(db)
        keys = [k for _, k in s3.deleted]
        self.assertEqual(keys, [KEY + ".normalized.json",
                                KEY + ".analysed.json"])

    # --- what is refused --------------------------------------------------

    def test_a_document_being_read_is_refused(self):
        db = FakeDb(state="reading")
        outcome, s3, rds = self.run_delete(db)
        self.assertEqual(outcome, {"refused": "reading"})
        self.assertEqual(s3.deleted, [])
        rds.begin_transaction.assert_not_called()
        self.assertNotIn("DELETE FROM document", " ".join(self.statements(db)))

    def test_every_other_state_may_go(self):
        for state in ("filed", "analysed", "unreadable", "rejected"):
            db = FakeDb(state=state)
            outcome, _, _ = self.run_delete(db)
            self.assertEqual(outcome, {"removed": DOC}, state)

    def test_a_document_that_is_not_there_is_not_found(self):
        db = FakeDb()
        db.sql = lambda statement, params=None, tx=None: rows()
        s3 = fake_s3()
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_s3", s3):
            self.assertIsNone(self.app.remove_document(TENANT, DOC))
        self.assertEqual(s3.deleted, [])

    def test_a_failure_rolls_the_whole_thing_back(self):
        db = FakeDb()
        s3 = fake_s3()
        s3.delete_object.side_effect = RuntimeError("S3 said no")
        rds = mock.MagicMock()
        rds.begin_transaction.return_value = {"transactionId": "tx-1"}
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_s3", s3), \
                mock.patch.object(self.app, "_rds", rds):
            with self.assertRaises(RuntimeError):
                self.app.remove_document(TENANT, DOC)
        rds.rollback_transaction.assert_called_once()
        rds.commit_transaction.assert_not_called()
        # The row delete never ran, so the rollback has something to restore.
        self.assertNotIn("DELETE FROM document", " ".join(self.statements(db)))


class MemoAfterwardsTest(unittest.TestCase):
    """What the memo screen reads once one of its sources has been deleted."""

    def setUp(self):
        self.app = load_api()

    def memo_with_sources(self, source_rows):
        s3 = mock.MagicMock()
        s3.get_object.return_value = {
            "Body": mock.MagicMock(read=lambda: b"# Memo\n\nA sentence.\n")}

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            if "FROM memo WHERE" in s:
                return rows(("curated", "tenants/7/memos/1.md", "2026-03-04",
                             "a@firm.com", None, None, 1, None, None))
            if "FROM memo_source ms" in s:
                return rows(*source_rows)
            return rows()

        with mock.patch.object(self.app, "_sql", sql), \
                mock.patch.object(self.app, "_s3", s3):
            return self.app.get_memo(TENANT, 1)

    def test_the_memo_still_renders(self):
        memo = self.memo_with_sources([(DOC, NAME, 1)])
        self.assertIn("A sentence.", memo["markdown"])

    def test_a_deleted_source_is_still_listed_and_marked(self):
        # The LEFT JOIN answers document_id IS NULL as 1 for a source whose
        # document has gone, and the name comes from memo_source.
        memo = self.memo_with_sources([(DOC, NAME, 1), (42, "Live.pdf", 0)])
        self.assertEqual(memo["sources"], [
            {"document_id": DOC, "filename": NAME, "removed": True},
            {"document_id": 42, "filename": "Live.pdf", "removed": False},
        ])

    def test_a_source_deleted_before_the_name_was_kept_says_so(self):
        memo = self.memo_with_sources([(DOC, None, 1)])
        self.assertEqual(memo["sources"][0]["filename"], "a deleted document")
        self.assertTrue(memo["sources"][0]["removed"])


if __name__ == "__main__":
    unittest.main()
