"""
Rewrite given the section's facts on file (8 November 2026).

    python -m unittest discover -s tests

A rewrite saw only the section's text, so "include the date of incorporation"
did nothing once that date had been read from a document filed after the
section was written. It is now given the values read for the section under
the configuration in use, as Update writes from, each masked with the same
citation tokens as the section.

WHAT THESE CANNOT SHOW. Whether the model adds a fact only where asked. The
model is a stub; that is observed on dev, not asserted.

Nothing reaches AWS: boto3 is replaced at import and every collaborator is a
stub.
"""

import unittest
from unittest import mock

from api_modules import load_api, rows
from test_memo_update import value
from test_section_prompt import load_composition

TENANT = 5
MEMO = 349
WORKSPACE = 3

SECTION_TEXT = (
    "## I. Introduction\n\n"
    "Noval Energy Ltd is a Ltd entity domiciled in Mauritius. *a.pdf, page 1*\n"
)


def section(key, num, title, kind="extract", fields=(), context=()):
    return {"key": key, "num": num, "title": title, "kind": kind,
            "prompt": None, "fields": list(fields),
            "context_sections": list(context)}


class Registry:
    def __init__(self, sections):
        self.sections = sections

    def has_template(self, key):
        return key == "brief"

    def sections_for(self, key):
        return list(self.sections)

    def sections_of_kind(self, kind, key=None):
        return [s for s in self.sections if s["kind"] == kind]

    def label_for(self, field_id):
        return {"f_date_of_incorporation": "Date of Incorporation",
                "f_legal_name": "Legal Name"}.get(field_id, field_id)

    def group_columns(self, field_id):
        return None


# The memo was written under 82, which had no date field; 84 binds it.
REVISION_82 = [section("introduction", "I", "Introduction",
                       fields=["f_legal_name"])]
REVISION_84 = [
    section("introduction", "I", "Introduction",
            fields=["f_legal_name", "f_date_of_incorporation"]),
    section("summary", "II", "Summary", kind="composed",
            context=["introduction"]),
]

VALUES = [
    {"value_id": 1, "field_id": "f_legal_name", "value": "Noval Energy Ltd",
     "locator_kind": "page", "locator_index": 1, "row_ordinal": None,
     "document_id": 10, "filename": "a.pdf", "engagement_id": 49},
    {"value_id": 2, "field_id": "f_date_of_incorporation",
     "value": "25th day of June 2026", "locator_kind": "page",
     "locator_index": 1, "row_ordinal": None, "document_id": 11,
     "filename": "coi.pdf", "engagement_id": 49},
]


class RewriteWithFacts(unittest.TestCase):

    def setUp(self):
        self.app = load_composition()
        self.engagement = 49
        self.heading = "## I. Introduction"
        self.updates = []
        self.calls = []
        self.reply = ("Noval Energy Ltd, incorporated on the 25th day of June "
                      "2026 [[C2]], is domiciled in Mauritius. [[C1]]")
        registries = {82: Registry(REVISION_82), 84: Registry(REVISION_84)}

        def sql(statement, params=None):
            if "FROM memo_rewrite" in statement and "SELECT" in statement:
                return rows((MEMO, "Include the date of incorporation.",
                             SECTION_TEXT, "running", self.heading))
            if "FROM memo WHERE" in statement and "template_key" in statement:
                return rows(("brief", 82, self.engagement, WORKSPACE))
            if "UPDATE memo_rewrite" in statement:
                self.updates.append({p["name"]: value(p) for p in params})
                return {}
            raise AssertionError("unexpected SQL: " + statement)

        def invoke(prompt, system=None, stage="?", section="?", chars_in=0):
            self.calls.append((prompt, system))
            return self.reply, {"input_tokens": 10, "output_tokens": 5}

        patches = [
            mock.patch.object(self.app, "_sql", side_effect=sql),
            mock.patch.object(self.app, "_invoke", side_effect=invoke),
            mock.patch.object(self.app, "_subject_of_memo", return_value=None),
            mock.patch.object(self.app, "_load_values", return_value=VALUES),
            mock.patch.object(self.app.config, "workspace_of",
                              return_value=WORKSPACE, create=True),
            mock.patch.object(self.app.config, "active_revision",
                              return_value=84, create=True),
            mock.patch.object(self.app.config, "load",
                              side_effect=lambda t, w, r: registries[r],
                              create=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_rewrite(self):
        return self.app._rewrite({"action": "rewrite", "tenant_id": TENANT,
                                  "rewrite_id": 256})

    def test_the_facts_in_use_are_in_the_prompt_with_shared_tokens(self):
        self.run_rewrite()
        prompt, system = self.calls[0]
        self.assertIn("FACTS ON FILE START", prompt)
        self.assertIn("25th day of June 2026", prompt)
        # a.pdf is cited by the section and the facts: one token, C1.
        self.assertNotIn("a.pdf", prompt)
        self.assertNotIn("coi.pdf", prompt)
        self.assertIn("[[C1]]", prompt)
        self.assertIn("[[C2]]", prompt)
        self.assertIn("FACTS ON FILE", system)

    def test_a_fact_added_comes_back_with_its_citation(self):
        # The token the facts give the date, read from a first prompt.
        self.run_rewrite()
        import re
        token = re.search(r"25th day of June 2026\s+\*?\s*(\[\[C\d+\]\])",
                          self.calls[0][0]).group(1)
        self.reply = ("Noval Energy Ltd, incorporated on the 25th day of "
                      "June 2026 " + token + ", is domiciled in Mauritius. "
                      "[[C1]]")
        result = self.run_rewrite()
        self.assertEqual(result["status"], "done")
        out = self.updates[-1]["output"]
        self.assertTrue(out.startswith("## I. Introduction\n\n"))
        self.assertIn("June 2026 *coi.pdf, page 1*", out)
        self.assertIn("*a.pdf, page 1*", out)

    def test_the_row_carries_the_revision_the_facts_came_from(self):
        self.run_rewrite()
        self.assertEqual(self.updates[-1]["revision"], 84)

    def test_a_fact_left_unused_is_not_a_dropped_citation(self):
        self.reply = "Noval Energy Ltd is domiciled in Mauritius. [[C1]]"
        result = self.run_rewrite()
        self.assertEqual(result["citations_dropped"], 0)

    def test_a_section_citation_lost_is_still_counted(self):
        self.reply = "Noval Energy Ltd is domiciled in Mauritius."
        self.assertEqual(self.run_rewrite()["citations_dropped"], 1)

    def test_no_engagement_rewrites_as_before(self):
        self.engagement = None
        self.run_rewrite()
        prompt, system = self.calls[0]
        self.assertNotIn("FACTS ON FILE", prompt)
        self.assertNotIn("FACTS ON FILE", system)
        self.assertIsNone(self.updates[-1]["revision"])

    def test_a_heading_no_revision_writes_gets_no_facts(self):
        # A heading retyped in the memo: neither revision writes it.
        self.heading = "## I. Our own heading"
        self.run_rewrite()
        self.assertNotIn("FACTS ON FILE", self.calls[0][0])

    def test_a_fault_reading_the_facts_still_rewrites(self):
        with mock.patch.object(self.app, "_load_values",
                               side_effect=RuntimeError("boom")):
            result = self.run_rewrite()
        self.assertEqual(result["status"], "done")
        self.assertNotIn("FACTS ON FILE", self.calls[0][0])

    def test_a_composed_section_gets_the_facts_of_what_it_reads(self):
        facts, revision = self.app._rewrite_facts(TENANT, MEMO, "## II. Summary")
        self.assertEqual(revision, 84)
        self.assertIn("## Introduction", facts)
        self.assertIn("25th day of June 2026", facts)


class SaveTakesRewriteSources(unittest.TestCase):
    """The API's half: a save accepting a rewrite given facts may cite a
    document filed since, as a save accepting an Update may."""

    def setUp(self):
        self.app = load_api()
        self.count = 0

        def sql(statement, params=None):
            if "config_revision IS NOT NULL" in statement:
                return rows((self.count,))
            return rows()

        p = mock.patch.object(self.app, "_sql", side_effect=sql)
        p.start()
        self.addCleanup(p.stop)

    def test_a_rewrite_with_facts_is_found(self):
        self.count = 1
        self.assertTrue(self.app._rewrites_with_facts(TENANT, MEMO, [256]))

    def test_a_rewrite_without_is_not(self):
        self.assertFalse(self.app._rewrites_with_facts(TENANT, MEMO, [256]))

    def test_no_rewrites_asks_nothing(self):
        self.assertFalse(self.app._rewrites_with_facts(TENANT, MEMO, []))


if __name__ == "__main__":
    unittest.main()
