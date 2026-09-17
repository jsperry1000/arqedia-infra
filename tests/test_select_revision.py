"""
Which published revision is in use, and what a draft opens from. The database
is replaced. Run from the repository root:

    python -m unittest discover -s tests

The SQL itself is not exercised here.
"""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from api_modules import rows

ROOT = Path(__file__).resolve().parents[1]


def load_registry():
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    env = {"CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
           "DATABASE": "arqedia"}
    modules = {"boto3": boto3, "botocore": botocore,
               "botocore.exceptions": exceptions}
    with mock.patch.dict(sys.modules, modules), mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "shared_registry", ROOT / "lambda/shared/registry.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def plain(value):
    return None if "isNull" in value else next(iter(value.values()))


class FakeDb:
    """Answers registry's statements for one tenant."""

    def __init__(self, revisions, active=None, draft_from=None):
        # {revision: status}
        self.revisions = dict(revisions)
        self.active = active
        # What config_revision.forked_from holds for the draft, or None where
        # no draft is open.
        self.draft_from = draft_from
        self.statements = []

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        values = {p["name"]: plain(p["value"]) for p in params or []}
        self.statements.append((s, values))
        if s.startswith("SELECT forked_from FROM config_revision"):
            return rows((self.draft_from,)) if self.draft_from else rows()
        if s.startswith("SELECT status FROM config_revision"):
            status = self.revisions.get(values["r"])
            return rows((status,)) if status else rows()
        if s.startswith("SELECT active_revision FROM tenant"):
            return rows((self.active,))
        if "COALESCE(MAX(revision), 0)" in s:
            published = [r for r, st in self.revisions.items()
                         if st == "published"]
            return rows((max(published) if published else 0,))
        if s.startswith("SELECT revision FROM config_revision WHERE tenant_id"):
            return rows((0,)) if self.draft_from else rows()
        if s.startswith("UPDATE tenant SET active_revision"):
            self.active = values["r"]
            return rows()
        return rows()

    def wrote(self, prefix):
        return [v for s, v in self.statements if s.startswith(prefix)]


class SelectRevisionTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def select(self, db, revision, tenant_id=7):
        with mock.patch.object(self.registry, "_sql", db.sql):
            return self.registry.select_revision(tenant_id, revision)

    def test_selects_a_published_revision(self):
        db = FakeDb({1: "published", 2: "published"}, active=2)
        self.assertEqual(self.select(db, 1), {"active_revision": 1})
        self.assertEqual(db.active, 1)

    def test_refuses_the_draft(self):
        db = FakeDb({1: "published"}, active=1)
        with self.assertRaises(ValueError):
            self.select(db, 0)
        self.assertEqual(db.active, 1)
        self.assertEqual(db.wrote("UPDATE tenant SET active_revision"), [])

    def test_refuses_while_a_draft_is_open_and_names_its_revision(self):
        db = FakeDb({1: "published", 2: "published"}, active=2,
                    draft_from="7:2")
        with self.assertRaises(ValueError) as raised:
            self.select(db, 1)
        self.assertIn("revision 2", str(raised.exception))
        self.assertEqual(db.active, 2)
        self.assertEqual(db.wrote("UPDATE tenant SET active_revision"), [])

    def test_refuses_a_revision_that_is_not_published(self):
        db = FakeDb({1: "published", 2: "retired"}, active=1)
        with self.assertRaises(ValueError):
            self.select(db, 2)
        self.assertEqual(db.active, 1)

    def test_refuses_a_revision_this_tenant_does_not_have(self):
        db = FakeDb({1: "published"}, active=1)
        with self.assertRaises(ValueError):
            self.select(db, 99)
        self.assertEqual(db.wrote("UPDATE tenant SET active_revision"), [])

    def test_refuses_nothing_and_nonsense(self):
        db = FakeDb({1: "published"}, active=1)
        for bad in (None, "", "latest", True):
            with self.assertRaises(ValueError):
                self.select(db, bad)
        self.assertEqual(db.wrote("UPDATE tenant SET active_revision"), [])

    def test_the_update_is_scoped_to_the_callers_tenant(self):
        db = FakeDb({1: "published", 2: "published"}, active=2)
        self.select(db, 1, tenant_id=7)
        [written] = db.wrote("UPDATE tenant SET active_revision")
        self.assertEqual((written["t"], written["r"]), (7, 1))


class OpenDraftTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def open_draft(self, db, from_revision=None):
        with mock.patch.object(self.registry, "_sql", db.sql), \
                mock.patch.object(self.registry, "_copy") as copy:
            result = self.registry.open_draft(7, "a@firm.com", from_revision)
        return result, copy

    def test_opens_from_the_selected_revision_not_the_newest(self):
        db = FakeDb({1: "published", 2: "published", 3: "published"}, active=1)
        result, copy = self.open_draft(db)
        self.assertEqual(result["copied_from"], 1)
        copy.assert_called_once_with(7, 1, 7, 0)

    def test_falls_back_to_the_newest_where_nothing_is_selected(self):
        db = FakeDb({1: "published", 2: "published"}, active=None)
        result, _ = self.open_draft(db)
        self.assertEqual(result["copied_from"], 2)

    def test_a_named_revision_still_wins(self):
        db = FakeDb({1: "published", 2: "published"}, active=2)
        result, _ = self.open_draft(db, from_revision=1)
        self.assertEqual(result["copied_from"], 1)

    def test_an_open_draft_is_returned_untouched(self):
        db = FakeDb({1: "published"}, active=1, draft_from="7:1")
        result, copy = self.open_draft(db)
        self.assertEqual(result, {"revision": 0, "created": False})
        copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
