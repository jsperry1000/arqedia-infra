"""
Values held under a field the revision does not have. Run from the
repository root:

    python -m unittest discover -s tests

A value is read once, at filing, under the key its field had then. A later
revision that drops the field, or replaces it with another key, leaves the
value held and drawn on by no memorandum. Found 27 October 2026: Trade
Finance's f_credit_lines, read under revision 10 and replaced at 16 by
f_existing_bank_lines. Three places now say so: the document drawer, the
memo, and the draft's warnings before it is published.
"""

import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 5
WS = 3


class FakeRegistry(object):
    def __init__(self, labels):
        self.labels = labels

    def label_for(self, key):
        return self.labels.get(key, key)

    def group_columns(self, key):
        return None


# Labels as each revision gave them. Revision 10 named the field; the draft
# and revision 40 do not have it.
REGISTRIES = {10: FakeRegistry({"f_credit_lines": "Credit Lines"}),
              12: FakeRegistry({"f_credit_lines": "Credit Lines",
                                "f_old_ratio": "Old Ratio"})}


def load(tenant_id, workspace_id, revision):
    return REGISTRIES.get(int(revision), FakeRegistry({}))


class NotInRevisionTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()
        self.asked = []

    def run_with(self, answers, active_revision=40, call=None):
        """answers: revision asked about -> rows of (field_id, read_under,
        documents, values)."""
        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            self.asked.append((s, params))
            if s.startswith("SELECT active_revision FROM workspace"):
                return rows((active_revision,))
            if "NOT EXISTS ( SELECT 1 FROM config_field" in s:
                asked = next(p["value"]["longValue"] for p in params
                             if p["name"] == "r")
                return rows(*answers.get(asked, []))
            return rows()
        with mock.patch.object(self.app, "_sql", sql), \
                mock.patch.object(self.app.config, "_sql", sql), \
                mock.patch.object(self.app.config, "load", load):
            return call()

    def test_values_are_grouped_by_field_across_read_revisions(self):
        found = self.run_with(
            {40: [("f_credit_lines", 10, 1, 1),
                  ("f_credit_lines", 12, 2, 2)]},
            call=lambda: self.app._not_in_revision(
                TENANT, WS, 40, "v.document_id = :d",
                [self.app._p("d", 1090)]))
        self.assertEqual(found, [{"field_id": "f_credit_lines",
                                  "label": "Credit Lines",
                                  "documents": 3, "values": 3}])

    def test_the_draft_warns_of_a_field_it_drops(self):
        warnings = self.run_with(
            {0: [("f_credit_lines", 10, 3, 3)], 40: []},
            call=lambda: self.app._left_behind(TENANT, WS))
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["kind"], "field-dropped-with-values")
        self.assertEqual(warnings[0]["field"], "f_credit_lines")
        self.assertIn("'Credit Lines' is not in this draft", warnings[0]["detail"])
        self.assertIn("3 filed documents hold values", warnings[0]["detail"])

    def test_one_document_is_said_in_the_singular(self):
        warnings = self.run_with(
            {0: [("f_credit_lines", 10, 1, 1)], 40: []},
            call=lambda: self.app._left_behind(TENANT, WS))
        self.assertIn("1 filed document holds values", warnings[0]["detail"])

    def test_a_field_already_left_behind_is_not_warned_of_again(self):
        """The revision in use already lacks it: an earlier publish dropped
        it, and every draft would otherwise warn about it for ever."""
        warnings = self.run_with(
            {0: [("f_credit_lines", 10, 3, 3), ("f_old_ratio", 12, 1, 1)],
             40: [("f_credit_lines", 10, 3, 3)]},
            call=lambda: self.app._left_behind(TENANT, WS))
        self.assertEqual([w["field"] for w in warnings], ["f_old_ratio"])

    def test_nothing_published_warns_of_nothing(self):
        warnings = self.run_with(
            {0: [("f_credit_lines", 10, 3, 3)]}, active_revision=None,
            call=lambda: self.app._left_behind(TENANT, WS))
        self.assertEqual(warnings, [])

    def test_the_documents_are_those_composition_reads(self):
        self.run_with({}, call=lambda: self.app._left_behind(TENANT, WS))
        scoped = [s for s, _ in self.asked if "NOT EXISTS" in s]
        self.assertTrue(scoped)
        for s in scoped:
            self.assertIn("d.workspace_id = :w AND d.state = 'filed' "
                          "AND d.active = 1", s)

    def test_validation_keeps_its_own_warnings_and_adds_these(self):
        own = {"revision": 0, "may_publish": True, "fatal": [],
               "warnings": [{"kind": "type-feeds-no-schema", "detail": "x"}]}
        with mock.patch.object(self.app.registry, "validate",
                               return_value=own):
            validation = self.run_with(
                {0: [("f_credit_lines", 10, 3, 3)], 40: []},
                call=lambda: self.app.validate_draft(TENANT, WS))
        self.assertEqual([w["kind"] for w in validation["warnings"]],
                         ["type-feeds-no-schema",
                          "field-dropped-with-values"])
        self.assertTrue(validation["may_publish"])


if __name__ == "__main__":
    unittest.main()
