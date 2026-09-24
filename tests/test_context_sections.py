"""
What a composed section reads (CFG-02).

    python -m unittest discover -s tests

THE BUG. save_section wrote context_sections on every save, and the section
drawer never sent it, so editing a composed section's wording set it to NULL
and the section came out empty from then on. Absent now means "keep it".

THE RULES. A composed section may read any assembled section of its own
memorandum, wherever it sits, and a composed one only where that one sorts
before it - composition writes composed sections in order, and a later one
does not exist yet. Publishing refuses a composed section reading nothing,
or reading a composed section that has since moved after it.

editor.py and registry.py are imported from lambda/shared, the docprocessing
layer, as test_field_overwrite.py does.
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

TENANT = 1
MEMO = "lender-information-memorandum-2"

# (section_key, title, kind, sort_order) - the memorandum as the draft holds it.
SECTIONS = [
    ("identity", "Identity", "extract", 1),
    ("summary", "Summary", "composed", 2),
    ("financing-requested", "Financing requested", "composed", 7),
    ("ownership", "Ownership", "extract", 8),
    ("outlook", "Outlook", "composed", 9),
]


def load(name):
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
            name + "_shared", ROOT / "lambda/shared" / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def plain(value):
    return None if value.get("isNull") else next(iter(value.values()))


class Db:
    def __init__(self, context=None):
        # section_key -> stored context_sections, for validate.
        self.context = dict(context or {})
        self.statements = []

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        values = {p["name"]: plain(p["value"]) for p in params or []}
        self.statements.append((s, values))

        if s.startswith("SELECT revision FROM config_revision"):
            return rows((0,))
        if s.startswith("SELECT section_key, title, kind, sort_order"):
            return rows(*SECTIONS)
        if s.startswith("SELECT s.template_key, s.section_key"):
            return rows(*[(MEMO, k, t, kind, sort, self.context.get(k),
                           "Lender IM") for k, t, kind, sort in SECTIONS])
        return {"records": []}

    def upsert(self):
        [(s, v)] = [(s, v) for s, v in self.statements
                    if s.startswith("INSERT INTO config_section")]
        return s, v


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.editor = load("editor")

    def save(self, body):
        db = Db()
        base = {"key": "financing-requested", "template_key": MEMO,
                "title": "Financing requested", "kind": "composed"}
        with mock.patch.object(self.editor, "_sql", db.sql):
            self.editor.save_section(TENANT, {**base, **body})
        return db.upsert()

    def test_absent_leaves_the_stored_value_alone(self):
        """The bug. A save without it must not touch it."""
        s, _ = self.save({"prompt": "Reworded"})
        update = s.split("ON DUPLICATE KEY UPDATE", 1)[1]
        self.assertNotIn("context_sections", update)

    def test_sent_is_stored_comma_separated_in_the_order_given(self):
        s, v = self.save({"context_sections": ["identity", "summary",
                                               "ownership", "identity"]})
        self.assertIn("context_sections = :context",
                      s.split("ON DUPLICATE KEY UPDATE", 1)[1])
        self.assertEqual(v["context"], "identity,summary,ownership")

    def test_an_assembled_section_after_it_may_be_read(self):
        _, v = self.save({"context_sections": ["ownership"]})
        self.assertEqual(v["context"], "ownership")

    def test_an_empty_list_clears_it(self):
        _, v = self.save({"context_sections": []})
        self.assertIsNone(v["context"])

    def test_itself_is_refused(self):
        with self.assertRaises(ValueError):
            self.save({"context_sections": ["financing-requested"]})

    def test_a_key_outside_the_memorandum_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.save({"context_sections": ["identity", "elsewhere"]})
        self.assertIn("elsewhere", str(caught.exception))

    def test_a_composed_section_after_it_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.save({"context_sections": ["outlook"]})
        self.assertIn("Outlook", str(caught.exception))

    def test_order_is_judged_at_the_position_being_saved(self):
        """Moved to 10 in the same save, Outlook (9) now comes before it."""
        _, v = self.save({"context_sections": ["outlook"], "sort_order": 10})
        self.assertEqual(v["context"], "outlook")


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.registry = load("registry")

    def fatal(self, context):
        db = Db(context)
        with mock.patch.object(self.registry, "_sql", db.sql):
            return self.registry.validate(TENANT)["fatal"]

    def test_a_composed_section_reading_nothing_refuses(self):
        found = self.fatal({"summary": "identity", "outlook": "identity"})
        [f] = found
        self.assertEqual(f["kind"], "composed-without-context")
        self.assertEqual(f["section"], "financing-requested")
        self.assertIn("'Financing requested' is written from other sections",
                      f["detail"])

    def test_reading_a_later_composed_section_refuses(self):
        found = self.fatal({"summary": "outlook",
                            "financing-requested": "identity",
                            "outlook": "identity"})
        [f] = found
        self.assertEqual(f["kind"], "composed-reads-later-section")
        self.assertEqual(f["section"], "summary")

    def test_well_formed_publishes(self):
        self.assertEqual(self.fatal({
            "summary": "identity,ownership",
            "financing-requested": "identity,summary,ownership",
            "outlook": "summary,financing-requested",
        }), [])


if __name__ == "__main__":
    unittest.main()
