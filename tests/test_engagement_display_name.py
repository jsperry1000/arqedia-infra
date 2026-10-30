"""
What an engagement is shown as (migration 051, 29 October 2026).

    python -m unittest discover -s tests

A rename changes display_name and nothing else: the name is the folder in
every storage key and what a new upload is resolved by, so it never moves.
Empty puts the name back. A name another engagement in the workspace is
already shown as is refused, on a rename and on opening a new one. A
memorandum generated afterwards prints the shown name in its Engagement row.

Nothing reaches AWS: boto3 is replaced at import and _sql is a stub.
"""

import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 7
WORKSPACE = 3
NAME = "Meridian-Trading"
ENGAGEMENT_ID = 42
WHO = "partner@firm.com"


def plain(value):
    return None if value.get("isNull") else next(iter(value.values()))


def sent(params):
    return {p["name"]: plain(p["value"]) for p in params or []}


class Db:
    """One engagement, NAME, and whatever else the workspace shows."""

    def __init__(self, display=None, others=()):
        self.display = display
        # What other engagements are shown as, by their names.
        self.others = dict(others)
        self.statements = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        values = sent(params)
        self.statements.append((s, values))
        if s.startswith("SELECT engagement_id, name, subject_name, status, "
                        "display_name"):
            if values["n"].lower() != NAME.lower():
                return rows()
            return rows((ENGAGEMENT_ID, NAME, "Cocoa Ltd", "open",
                         self.display))
        if s.startswith("SELECT name FROM engagement"):
            for name, shown in self.others.items():
                if shown.lower() == values["s"].lower():
                    return rows((name,))
            return rows()
        return rows()

    def updates(self):
        return [(s, v) for s, v in self.statements if s.startswith("UPDATE")]


class RenameTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def rename(self, to, db=None, engagement=NAME):
        db = db or Db()
        with mock.patch.object(self.app, "_sql", db.sql):
            try:
                out = self.app.rename_engagement(
                    TENANT, WORKSPACE, WHO, engagement, to)
                return out, None, db
            except ValueError as exc:
                return None, exc, db

    def test_it_sets_what_is_shown_and_not_the_name(self):
        out, refused, db = self.rename("Meridian Trading plc")
        self.assertIsNone(refused)
        self.assertEqual(out["engagement"], NAME)
        self.assertEqual(out["engagement_shown"], "Meridian Trading plc")
        [(statement, values)] = db.updates()
        self.assertIn("SET display_name = :d", statement)
        self.assertNotIn(" name = ", statement.replace("display_name", ""))
        self.assertEqual(values["d"], "Meridian Trading plc")
        self.assertEqual(values["who"], WHO)

    def test_empty_puts_the_name_back(self):
        out, _, db = self.rename("   ", Db(display="Old shown"))
        self.assertIsNone(out["display_name"])
        self.assertEqual(out["engagement_shown"], NAME)
        [(_, values)] = db.updates()
        self.assertIsNone(values["d"])

    def test_its_own_name_is_stored_as_no_rename(self):
        out, _, db = self.rename(NAME, Db(display="Old shown"))
        self.assertIsNone(out["display_name"])
        self.assertIsNone(db.updates()[0][1]["d"])

    def test_spaces_inside_are_folded(self):
        out, _, _ = self.rename("  Meridian   Trading  ")
        self.assertEqual(out["display_name"], "Meridian Trading")

    def test_a_name_shown_elsewhere_is_refused(self):
        db = Db(others={"Other-One": "Meridian Trading"})
        out, refused, db = self.rename("meridian trading", db)
        self.assertIsNone(out)
        self.assertIn("already shown as", str(refused))
        self.assertEqual(db.updates(), [])

    def test_the_check_leaves_out_the_one_renamed(self):
        db = Db()
        self.rename("Meridian Trading", db)
        [(_, values)] = [(s, v) for s, v in db.statements
                         if s.startswith("SELECT name FROM engagement")]
        self.assertEqual(values["e"], ENGAGEMENT_ID)
        self.assertEqual(values["w"], WORKSPACE)

    def test_too_long_is_refused(self):
        _, refused, db = self.rename("x" * 121)
        self.assertIn("at most 120", str(refused))
        self.assertEqual(db.updates(), [])

    def test_control_characters_are_refused(self):
        _, refused, _ = self.rename("Meridian\x07")
        self.assertIn("control characters", str(refused))

    def test_an_engagement_that_is_not_there_is_none(self):
        out, refused, _ = self.rename("Anything", engagement="Nobody")
        self.assertIsNone(out)
        self.assertIsNone(refused)


class OpenTest(unittest.TestCase):
    """Opening a new name another engagement is shown as is refused, so the
    list never holds two rows that read the same."""

    def setUp(self):
        self.app = load_api()

    def test_a_new_name_shown_elsewhere_is_refused(self):
        db = Db(others={NAME: "Acme"})
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "engagement_id") as made:
            with self.assertRaises(ValueError) as refused:
                self.app.open_engagement(TENANT, WORKSPACE, WHO, "Acme")
        self.assertIn("already shown as Acme", str(refused.exception))
        made.assert_not_called()

    def test_an_existing_name_still_opens(self):
        db = Db(display="Shown")
        with mock.patch.object(self.app, "_sql", db.sql):
            found = self.app.open_engagement(TENANT, WORKSPACE, WHO, NAME)
        self.assertFalse(found["created"])
        self.assertEqual(found["engagement_shown"], "Shown")


class NewMemoTest(unittest.TestCase):
    """A memorandum generated after a rename prints the shown name in its
    Engagement row; with none set, the name it always printed."""

    def shown(self, display):
        from test_section_prompt import load_composition
        comp = load_composition()
        with mock.patch.object(comp, "_sql",
                               lambda s, p=None, tx=None: rows((display,))):
            return comp._shown_as(TENANT, ENGAGEMENT_ID, NAME)

    def test_the_display_name_when_set(self):
        self.assertEqual(self.shown("Meridian Trading plc"),
                         "Meridian Trading plc")

    def test_the_name_when_not(self):
        self.assertEqual(self.shown(None), NAME)
        self.assertEqual(self.shown("  "), NAME)


class RouteTest(unittest.TestCase):
    def test_the_route_is_in_terraform(self):
        from pathlib import Path
        api_tf = (Path(__file__).resolve().parents[1] / "api.tf").read_text()
        self.assertIn('"PUT /engagements/{id}/name"', api_tf)


if __name__ == "__main__":
    unittest.main()
