"""
The memo list names each memo by the template's name AS IT STOOD IN THAT
MEMO'S OWN REVISION. Run from the repository root:

    python -m unittest discover -s tests

Nothing reaches AWS: boto3 is replaced at import and _sql is patched. The
registry is patched too, so these exercise what list_memos decides rather than
config.py's SQL.
"""

import unittest
from unittest import mock

from api_modules import load_api, rows

TEMPLATE = "credit-memo"

# The same template, named differently in two published revisions. Renaming is
# free and mints no new key (Configure.tsx: "the key is minted once and never
# follows the label"), which is exactly why the key cannot say what a memo was
# called.
LABELS = {
    3: {TEMPLATE: "Credit Memorandum"},
    5: {TEMPLATE: "Credit Review"},
    # Revision 7 dropped the template altogether.
    7: {},
}


class FakeRegistry:
    """What config.load returns: one revision, loaded and immutable."""

    def __init__(self, revision):
        self.revision = revision

    def label_for_template(self, template_key):
        # config.py:321-323 - the key where the revision does not name it.
        return LABELS.get(self.revision, {}).get(template_key) or template_key


def memo_row(memo_id, config_revision, template_key=TEMPLATE,
             parent=None, revision=1, pdf_key=None):
    """One row of list_memos' SELECT, in its column order:
    memo_id, template_key, generated_at, generated_by, parent_memo_id,
    revision, modified_by, modified_at, pdf_key, config_revision, and since
    Group 14 state, archived_by, archived_at."""
    return (memo_id, template_key, "2026-03-04 10:00:00", "a@firm.com",
            parent, revision, None, None, pdf_key, config_revision,
            "live", None, None)


class MemoListTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()
        self.loaded = []

    def listing(self, *memo_rows):
        """list_memos over the given rows, with the registry faked."""
        def load(tenant_id, revision):
            self.loaded.append((tenant_id, revision))
            return FakeRegistry(revision)

        with mock.patch.object(self.app, "_sql",
                               lambda s, p=None: rows(*memo_rows)), \
                mock.patch.object(self.app.config, "load", load):
            # An engagement_id since stage 4; _sql is faked, so the value
            # only has to be the shape the function now takes.
            return self.app.list_memos(7, 42)

    def test_a_memo_is_named_from_its_own_revision(self):
        [memo] = self.listing(memo_row(11, 3))
        self.assertEqual(memo["template_label"], "Credit Memorandum")
        # The key is untouched: it is the identity, and screens that match on
        # it must keep working.
        self.assertEqual(memo["template"], TEMPLATE)
        # Read from the memo's revision, not from the tenant's active one.
        self.assertEqual(self.loaded, [(7, 3)])

    def test_a_rename_does_not_rename_a_memo_already_written(self):
        # Memo 11 was written in March under revision 3; the memorandum was
        # renamed and republished as revision 5, and memo 12 written under it.
        older, newer = self.listing(memo_row(12, 5), memo_row(11, 3))
        self.assertEqual(
            [(m["memo_id"], m["template_label"]) for m in (older, newer)],
            [(12, "Credit Review"), (11, "Credit Memorandum")])
        # One template, one key, two names.
        self.assertEqual({m["template"] for m in (older, newer)}, {TEMPLATE})

    def test_a_revision_that_no_longer_names_it_falls_back_to_the_key(self):
        [memo] = self.listing(memo_row(13, 7))
        self.assertEqual(memo["template_label"], TEMPLATE)

    def test_a_row_with_no_revision_reads_revision_one(self):
        # config_revision is NOT NULL in the schema, so this is belt and
        # braces: what it must not do is raise and take the whole list with it.
        [memo] = self.listing(memo_row(14, None))
        self.assertEqual(memo["template_label"], TEMPLATE)
        self.assertEqual(self.loaded, [(7, 1)])

    def test_every_other_field_is_as_it_was(self):
        [memo] = self.listing(memo_row(11, 3, parent=9, revision=2,
                                       pdf_key="tenants/7/memos/9-r2.pdf"))
        self.assertEqual(memo["memo_id"], 11)
        self.assertEqual(memo["parent_memo_id"], 9)
        self.assertEqual(memo["revision"], 2)
        self.assertEqual(memo["label"], "9.2")
        self.assertTrue(memo["has_pdf"])
        self.assertEqual(memo["generated_by"], "a@firm.com")


if __name__ == "__main__":
    unittest.main()
