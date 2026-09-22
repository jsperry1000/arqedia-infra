"""
An engagement names its subject, and nothing is read until it does (SUBJ-01).

    python -m unittest discover -s tests

The defect being closed: memo 120 described GoodFlow - a BUYER - as the
specialist originator and gave it 2025 sales, under a citation to a page
that names Cocoa Empire Uganda Limited and to a company incorporated in May
2026. The citation was right. The description was right. Nothing in the
pipeline had ever been told which company the memorandum was about.

The gate a person meets is in file_documents, above the charge, because
filing is the only thing in the product that writes .normalized.json and
therefore the only way into extraction. Extraction's own refusal is tested
in test_extraction_failure.py.

Nothing reaches AWS: boto3 is replaced at import and _sql is a stub.
"""

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

from api_modules import load_api, rows

ROOT = Path(__file__).resolve().parents[1]

TENANT = 7
NAME = "Meridian-Trading"
ENGAGEMENT_ID = 42
SUBJECT = "Cocoa Empire Uganda Limited"


def load_cleanup():
    """cleanup.py on its own. It imports nothing, so it loads as it is."""
    spec = importlib.util.spec_from_file_location(
        "cleanup_module", ROOT / "lambda/composition/cleanup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plain(value):
    return None if value.get("isNull") else next(iter(value.values()))


def sent(params):
    return {p["name"]: plain(p["value"]) for p in params or []}


class Db:
    """Answers the subject lookup and records everything asked."""

    def __init__(self, subject=SUBJECT, engagement=ENGAGEMENT_ID):
        self.subject = subject
        self.engagement = engagement
        self.statements = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        self.statements.append((s, sent(params)))
        if s.startswith("SELECT subject_name FROM engagement"):
            return rows((self.subject,)) if self.engagement else rows()
        if s.startswith("SELECT engagement_id FROM engagement"):
            return rows((self.engagement,)) if self.engagement else rows()
        return rows()

    def kinds(self):
        return [" ".join(s.split()[:4]) for s, _ in self.statements]


# --- the gate ---------------------------------------------------------------

class FilingGateTest(unittest.TestCase):
    """Nothing is filed into an engagement with no subject, and nothing is
    charged for trying."""

    def setUp(self):
        self.app = load_api()

    def file_into(self, subject):
        db = Db(subject=subject)
        decisions = [{"document_id": 1, "document_type": "invoice",
                      "include": True}]
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "wallet") as wallet, \
                mock.patch.object(self.app, "config"), \
                mock.patch.object(self.app, "_s3"):
            wallet.charge.return_value = {"entry_id": 5}
            try:
                out = self.app.file_documents(
                    TENANT, "partner@firm.com", NAME, decisions, "key-1")
                return out, None, wallet, db
            except ValueError as exc:
                return None, exc, wallet, db

    def test_no_subject_refuses_the_whole_filing(self):
        out, refused, _, _ = self.file_into(None)
        self.assertIsNone(out)
        self.assertIn("Name the subject", str(refused))

    def test_nothing_is_charged_for_a_refused_filing(self):
        """ABOVE the charge, not beside it. A guard that runs after the money
        moves is not a guard."""
        _, _, wallet, _ = self.file_into(None)
        wallet.charge.assert_not_called()

    def test_nothing_is_written_for_a_refused_filing(self):
        """The subject is read and nothing else happens: no state change, no
        envelope, no charge_entry_id."""
        _, _, _, db = self.file_into(None)
        self.assertEqual(
            [k for k in db.kinds() if k.startswith("UPDATE")], [])

    def test_a_whitespace_subject_is_no_subject(self):
        _, refused, wallet, _ = self.file_into("   ")
        self.assertIn("Name the subject", str(refused))
        wallet.charge.assert_not_called()

    def test_a_subject_lets_the_filing_proceed(self):
        """The gate is the only thing this adds. Everything past it is the
        filing that was already there."""
        out, refused, wallet, _ = self.file_into(SUBJECT)
        self.assertIsNone(refused)
        self.assertIsNotNone(out)
        wallet.charge.assert_called_once()


# --- setting it -------------------------------------------------------------

class SetSubjectTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def set_it(self, value, engagement=NAME):
        db = Db()
        with mock.patch.object(self.app, "_sql", db.sql):
            try:
                return self.app.set_subject(
                    TENANT, "partner@firm.com", engagement, value), None, db
            except ValueError as exc:
                return None, exc, db

    def test_a_subject_is_stored_verbatim(self):
        """NOT _clean()ed. That exists to make a string safe for a storage
        key and would turn "Cocoa Empire Uganda Ltd." into
        "Cocoa-Empire-Uganda-Ltd". This goes into a prompt and onto the front
        matter of a memorandum."""
        out, refused, db = self.set_it("Cocoa Empire Uganda Ltd.")
        self.assertIsNone(refused)
        self.assertEqual(out["subject_name"], "Cocoa Empire Uganda Ltd.")
        wrote = [v for s, v in db.statements
                 if s.startswith("UPDATE engagement SET subject_name")]
        self.assertEqual(len(wrote), 1)
        self.assertEqual(wrote[0]["s"], "Cocoa Empire Uganda Ltd.")

    def test_it_is_trimmed(self):
        out, _, _ = self.set_it("  Cocoa Empire  ")
        self.assertEqual(out["subject_name"], "Cocoa Empire")

    def test_an_empty_subject_is_refused(self):
        _, refused, _ = self.set_it("")
        self.assertIn("A subject is required", str(refused))

    def test_whitespace_alone_is_refused(self):
        _, refused, _ = self.set_it("   ")
        self.assertIn("A subject is required", str(refused))

    def test_a_control_character_is_refused(self):
        """It reaches a prompt and a rendered page. A newline in the middle
        of the name breaks both."""
        _, refused, _ = self.set_it("Cocoa\nEmpire")
        self.assertIn("control characters", str(refused))

    def test_longer_than_the_column_is_refused(self):
        _, refused, _ = self.set_it("C" * 256)
        self.assertIn("255", str(refused))

    def test_the_column_width_is_allowed(self):
        out, refused, _ = self.set_it("C" * 255)
        self.assertIsNone(refused)
        self.assertEqual(len(out["subject_name"]), 255)

    def test_naming_a_subject_opens_the_engagement(self):
        """One route for both. The row is resolved or created by name, the
        same rule /uploads uses, so a subject can be named before anything
        has been uploaded."""
        _, _, db = self.set_it(SUBJECT)
        self.assertIn("SELECT engagement_id FROM engagement", db.kinds())

    def test_an_empty_engagement_name_is_refused(self):
        _, refused, _ = self.set_it(SUBJECT, engagement="   ")
        self.assertIn("engagement is required", str(refused))


class ReadSubjectTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def test_it_is_looked_up_by_the_cleaned_name(self):
        """The row carries the cleaned name, because upload_url cleans before
        creating it. A lookup on the raw path parameter would miss the row
        for any name typed with a space in it."""
        db = Db()
        with mock.patch.object(self.app, "_sql", db.sql):
            self.app.engagement_subject(TENANT, "Meridian Trading")
        _, asked = db.statements[0]
        self.assertEqual(asked["n"], "Meridian-Trading")

    def test_an_engagement_with_no_row_has_no_subject(self):
        db = Db(engagement=None)
        with mock.patch.object(self.app, "_sql", db.sql):
            self.assertIsNone(self.app.engagement_subject(TENANT, NAME))

    def test_a_null_column_is_no_subject(self):
        db = Db(subject=None)
        with mock.patch.object(self.app, "_sql", db.sql):
            self.assertIsNone(self.app.engagement_subject(TENANT, NAME))


class EngagementListTest(unittest.TestCase):
    """The list names the subject, so the question is answerable before
    anybody opens an engagement and uploads into it."""

    def setUp(self):
        self.app = load_api()

    def listing(self, subject):
        # Since stage 4 the list comes FROM the engagement table, so the
        # columns are the row's own: id, name, subject, count, last activity.
        def sql(statement, params=None, tx=None):
            return rows((42, NAME, subject, 3, "2026-09-21 10:00:00",
                         "open", None, None))
        with mock.patch.object(self.app, "_sql", sql):
            return self.app.list_engagements(TENANT)

    def test_the_subject_is_on_the_row(self):
        self.assertEqual(self.listing(SUBJECT)[0]["subject_name"], SUBJECT)

    def test_an_engagement_without_one_is_listed_anyway(self):
        """Every engagement opened before migration 031 has no subject, and a
        list that dropped them would hide the ones that need one."""
        row = self.listing(None)[0]
        self.assertIsNone(row["subject_name"])
        self.assertEqual(row["engagement"], NAME)
        self.assertEqual(row["documents"], 3)
        self.assertEqual(row["engagement_id"], 42)


# --- the prompts ------------------------------------------------------------

class SubjectRuleTest(unittest.TestCase):
    """What composition tells the model. One rule, three passes."""

    def setUp(self):
        self.cleanup = load_cleanup()

    def test_the_rule_names_the_subject(self):
        rule = self.cleanup.subject_rule(SUBJECT)
        self.assertIn(SUBJECT, rule)

    def test_the_rule_allows_the_variants(self):
        """"Cocoa Empire" has to reach "Cocoa Empire Uganda Limited" and
        "CE". No matching we could write would do that honestly."""
        rule = self.cleanup.subject_rule(SUBJECT)
        self.assertIn("Treat any name that refers to the same company", rule)

    def test_the_rule_forbids_the_thing_that_went_wrong(self):
        rule = self.cleanup.subject_rule(SUBJECT)
        self.assertIn("Never state a fact about another company as a fact "
                      "about the subject", rule)
        self.assertIn("buyer", rule)

    def test_no_subject_adds_nothing(self):
        """Behaviour stays as it was. A guessed subject in a prompt is worse
        than none, because the model would then attribute facts to it."""
        self.assertEqual(self.cleanup.subject_rule(None), "")
        self.assertEqual(self.cleanup.subject_rule(""), "")
        self.assertEqual(self.cleanup.subject_rule("   "), "")

    def test_subject_from_still_counts_legal_names(self):
        """Kept as the fallback for every engagement that has no
        subject_name, which is all of them until somebody names one."""
        values = [{"field_id": "f_legal_name", "value": "Cocoa Empire Ltd"},
                  {"field_id": "f_legal_name", "value": "Cocoa Empire Ltd"},
                  {"field_id": "f_legal_name", "value": "GoodFlow BV"}]
        self.assertEqual(self.cleanup.subject_from(values),
                         "Cocoa Empire Ltd")

    def test_the_front_matter_falls_back_to_the_engagement(self):
        block = self.cleanup.front_matter(None, NAME, "21 September 2026",
                                          3, 3)
        self.assertIn("| **Subject** | Meridian-Trading |", block)

    def test_the_front_matter_prefers_the_subject_given(self):
        block = self.cleanup.front_matter(SUBJECT, NAME, "21 September 2026",
                                          3, 3)
        self.assertIn("| **Subject** | %s |" % SUBJECT, block)


if __name__ == "__main__":
    unittest.main()
