"""
What is on offer is the mark, and a second take makes a second memorandum.
The database is replaced. Run from the repository root:

    python -m unittest discover -s tests

The SQL itself is exercised on dev, not here; what is tested here is what the
code decides and which statements it sends.
"""

import importlib.util
import os
import re
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


# The five marks as migration 024 writes them, and the memoranda revision 9
# holds.
MARKS = {
    ("base", "base"): (0, 9, None),
    ("TRADEFINANCE-Credit", "template"): (0, 9, "credit-memorandum"),
    ("TRADEFINANCE-KYC", "template"): (0, 9, "kyc-customer-due-diligence-memorandum"),
}


class FakeDb:
    """Answers registry's statements for a pack tenant and one customer."""

    def __init__(self, marks=None, held_templates=(), held_fields=(),
                 bound_fields=("f_borrower",), published=1, active=1):
        self.marks = dict(MARKS if marks is None else marks)
        self.held_templates = set(held_templates)
        self.held_fields = set(held_fields)
        self.bound_fields = set(bound_fields)
        self.published = published
        self.active = active
        self.statements = []

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        values = {p["name"]: plain(p["value"]) for p in params or []}
        self.statements.append((s, values))

        if s.startswith("SELECT o.tenant_id, o.revision, o.template_key"):
            found = self.marks.get((values["key"], values["k"]))
            return rows(found) if found else rows()
        if "COUNT(*) FROM config_field WHERE tenant_id" in s:
            return rows((5,))          # the marked revision holds facts
        if "COALESCE(MAX(revision), 0)" in s:
            return rows((self.published,))
        if s.startswith("SELECT active_revision FROM tenant"):
            return rows((self.active,))
        if s.startswith("SELECT revision FROM config_revision WHERE tenant_id"):
            return rows((0,))          # a draft is open
        if s.startswith("SELECT DISTINCT template_key FROM config_template"):
            return rows(*[(k,) for k in sorted(self.held_templates)])
        if s.startswith("SELECT DISTINCT field_key FROM config_section_field"):
            return rows(*[(k,) for k in sorted(self.bound_fields)])
        if s.startswith("SELECT DISTINCT field_key FROM config_field"):
            return rows(*[(k,) for k in sorted(self.held_fields)])
        if s.startswith("SELECT DISTINCT"):
            return rows()
        if s.startswith("SELECT (SELECT COUNT(*) FROM config_section"):
            return rows((0, 0))
        return rows()

    def sent(self, prefix):
        return [(s, v) for s, v in self.statements if s.startswith(prefix)]

    def tables_written(self):
        out = []
        for s, _ in self.statements:
            m = re.match(r"INSERT (?:IGNORE )?INTO (\w+)", s)
            if m:
                out.append(m.group(1))
        return out


class OfferTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def test_reads_the_mark(self):
        db = FakeDb()
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.assertEqual(self.registry._offer("base", "base"),
                             {"tenant_id": 0, "revision": 9,
                              "template_key": None})
            self.assertEqual(
                self.registry._offer("TRADEFINANCE-KYC", "template"),
                {"tenant_id": 0, "revision": 9,
                 "template_key": "kyc-customer-due-diligence-memorandum"})

    def test_nothing_on_offer_is_none(self):
        db = FakeDb(marks={})
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.assertIsNone(self.registry._offer("base", "base"))

    def test_the_mark_must_name_a_published_revision(self):
        # The join in the statement is what enforces it: the fake answers
        # nothing, as the database would for an unpublished revision.
        db = FakeDb(marks={})
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.assertIsNone(
                self.registry._offer("TRADEFINANCE-Credit", "template"))
        [(sent, _)] = db.sent("SELECT o.tenant_id")
        self.assertIn("r.status = 'published'", sent)


class ForkBaseTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def fork(self, db, **kw):
        with mock.patch.object(self.registry, "_sql", db.sql):
            return self.registry.fork_base(7, "a@firm.com", **kw)

    def test_takes_the_vocabulary_and_not_our_memoranda(self):
        db = FakeDb(published=0)
        result = self.fork(db)
        self.assertEqual(result["from"], "pack:0:9")
        written = db.tables_written()
        for table in ("config_category", "config_document_type",
                      "config_schema", "config_type_schema", "config_field"):
            self.assertIn(table, written)
        for table in ("config_template", "config_section",
                      "config_section_field"):
            self.assertNotIn(table, written)

    def test_refuses_where_nothing_is_on_offer(self):
        db = FakeDb(marks={}, published=0)
        with self.assertRaises(ValueError):
            self.fork(db)

    def test_refuses_a_tenant_that_already_published(self):
        db = FakeDb(published=3)
        with self.assertRaises(ValueError):
            self.fork(db)


class ForkTemplateTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def fork(self, db, pack_key="TRADEFINANCE-KYC"):
        with mock.patch.object(self.registry, "_sql", db.sql):
            return self.registry.fork_template(7, "a@firm.com", pack_key)

    def keys_used(self, db):
        [(_, values)] = db.sent("INSERT IGNORE INTO config_template")
        return values["src_key"], values["new_key"], values["suffix"]

    def test_first_take_keeps_the_key_and_the_label(self):
        db = FakeDb(held_fields={"f_borrower"})
        result = self.fork(db)
        self.assertEqual(result["template_key"],
                         "kyc-customer-due-diligence-memorandum")
        self.assertEqual(result["copy"], 1)
        src, new, suffix = self.keys_used(db)
        self.assertEqual((src, new, suffix),
                         ("kyc-customer-due-diligence-memorandum",
                          "kyc-customer-due-diligence-memorandum", ""))

    def test_second_take_makes_a_second_memorandum(self):
        db = FakeDb(held_fields={"f_borrower"},
                    held_templates={"kyc-customer-due-diligence-memorandum"})
        result = self.fork(db)
        self.assertEqual(result["template_key"],
                         "kyc-customer-due-diligence-memorandum-2")
        self.assertEqual(result["copy"], 2)
        _, new, suffix = self.keys_used(db)
        self.assertEqual((new, suffix),
                         ("kyc-customer-due-diligence-memorandum-2", " (2)"))

    def test_third_take_counts_on(self):
        db = FakeDb(held_fields={"f_borrower"},
                    held_templates={"kyc-customer-due-diligence-memorandum",
                                    "kyc-customer-due-diligence-memorandum-2"})
        result = self.fork(db)
        self.assertEqual(result["copy"], 3)
        _, new, suffix = self.keys_used(db)
        self.assertEqual((new, suffix),
                         ("kyc-customer-due-diligence-memorandum-3", " (3)"))

    def test_only_the_marked_memorandum_travels(self):
        db = FakeDb(held_fields={"f_borrower"})
        self.fork(db)
        for prefix in ("INSERT IGNORE INTO config_template",
                       "INSERT IGNORE INTO config_section ",
                       "INSERT IGNORE INTO config_section_field"):
            [(sent, values)] = db.sent(prefix)
            self.assertIn("template_key = :src_key", sent)
            self.assertEqual(values["src_key"],
                             "kyc-customer-due-diligence-memorandum")

    def test_refuses_where_nothing_is_on_offer(self):
        db = FakeDb(marks={})
        with self.assertRaises(ValueError):
            self.fork(db)

    def test_refuses_a_fact_the_base_does_not_define(self):
        # Bound in the memorandum, held by neither the draft nor the base.
        db = FakeDb(bound_fields={"f_invented"}, held_fields=set())
        with self.assertRaises(ValueError) as raised:
            self.fork(db)
        self.assertIn("f_invented", str(raised.exception))


class PacksTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def test_packs_reads_the_marks(self):
        db = FakeDb()
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.registry.packs()
        [(sent, _)] = db.sent("SELECT o.revision, o.pack_key")
        self.assertIn("FROM pack_offer o", sent)
        self.assertIn("o.kind = 'base'", sent)
        self.assertNotIn("MAX(", sent)

    def test_template_packs_counts_one_memorandum_per_mark(self):
        db = FakeDb()
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.registry.template_packs(7)
        [(sent, _)] = db.sent("SELECT o.revision, o.pack_key, r.note, o.tenant_id")
        self.assertIn("FROM pack_offer o", sent)
        self.assertIn("s.template_key = o.template_key", sent)
        self.assertIn("f.template_key = o.template_key", sent)


if __name__ == "__main__":
    unittest.main()
