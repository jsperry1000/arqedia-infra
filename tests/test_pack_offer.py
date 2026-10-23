"""
What is on offer is the mark, and a second take makes a second memorandum.
The database is replaced. Run from the repository root:

    python -m unittest discover -s tests

The SQL itself is exercised on dev, not here; what is tested here is what the
code decides and which statements it sends.

PACK-01: forking a base makes a new workspace beside whatever the tenant
already holds, and a memorandum is taken into one workspace's draft.

PACK-02: what is on offer is an OFFERING - a workspace of the pack tenant
with a base of its own. A fork takes one and records it; a memorandum comes
from the workspace's own offering and no other; a workspace may be made
empty.
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

WORKSPACE = 3          # the customer's workspace a memorandum is taken into
NEW_WORKSPACE = 12     # what INSERT INTO workspace answers
OFFERING = 11          # the pack tenant's Trade Finance workspace (044)
OTHER_OFFERING = 14    # a second offering, Real Estate


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
                 bound_fields=("f_borrower",), published=1, active=1,
                 offerings=(OFFERING,), link=OFFERING, names=()):
        self.marks = dict(MARKS if marks is None else marks)
        self.held_templates = set(held_templates)
        self.held_fields = set(held_fields)
        self.bound_fields = set(bound_fields)
        self.published = published
        self.active = active
        # The offerings with a base on offer, and the one the customer's
        # workspace was started from (None: unlinked or made empty).
        self.offerings = list(offerings)
        self.link = link
        # The names of the tenant's live workspaces.
        self.names = list(names)
        self.statements = []
        self.in_tx = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        values = {p["name"]: plain(p["value"]) for p in params or []}
        self.statements.append((s, values))
        self.in_tx.append((s, tx))

        if s.startswith("INSERT INTO workspace"):
            return {"generatedFields": [{"longValue": NEW_WORKSPACE}]}
        if s.startswith("SELECT workspace_id FROM config_revision "
                        "WHERE tenant_id = :t AND workspace_id <> :w"):
            return rows()              # no other workspace has a draft
        if s.startswith("SELECT workspace_id FROM config_revision"):
            # The pack tenant's revisions are in its offering's workspace.
            return rows((OFFERING if values["t"] == 0 else WORKSPACE,))
        if s.startswith("SELECT forked_from_workspace_id FROM workspace"):
            return rows((self.link,))
        if s.startswith("SELECT name FROM workspace"):
            return rows(*[(n,) for n in self.names])

        if s.startswith("SELECT o.revision, o.pack_key, r.note, (SELECT"):
            # packs(): one base per offering.
            return rows(*[(9, "base", None, 3, 5, w, "Offering %d" % w)
                          for w in self.offerings])
        if s.startswith("SELECT o.tenant_id, o.revision, o.template_key"):
            if values["o"] not in self.offerings:
                return rows()
            found = self.marks.get((values["key"], values["k"]))
            return rows(found) if found else rows()
        if "COUNT(*) FROM config_field WHERE tenant_id" in s:
            return rows((5,))          # the marked revision holds facts
        if "COALESCE(MAX(revision), 0)" in s:
            return rows((self.published,))
        if s.startswith("SELECT active_revision FROM workspace"):
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
            self.assertEqual(self.registry._offer("base", "base", OFFERING),
                             {"tenant_id": 0, "revision": 9,
                              "template_key": None})
            self.assertEqual(
                self.registry._offer("TRADEFINANCE-KYC", "template",
                                     OFFERING),
                {"tenant_id": 0, "revision": 9,
                 "template_key": "kyc-customer-due-diligence-memorandum"})

    def test_nothing_on_offer_is_none(self):
        db = FakeDb(marks={})
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.assertIsNone(self.registry._offer("base", "base", OFFERING))

    def test_the_mark_must_name_a_published_revision(self):
        # The join in the statement is what enforces it: the fake answers
        # nothing, as the database would for an unpublished revision.
        db = FakeDb(marks={})
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.assertIsNone(
                self.registry._offer("TRADEFINANCE-Credit", "template",
                                     OFFERING))
        [(sent, _)] = db.sent("SELECT o.tenant_id")
        self.assertIn("r.status = 'published'", sent)

    def test_one_offerings_marks_and_no_others(self):
        """'base' is a key in every offering, so the offering is part of
        the question - found by the workspace of the revision the mark
        names, which reads the same before migration 044 as after."""
        db = FakeDb()
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.assertIsNone(
                self.registry._offer("base", "base", OTHER_OFFERING))
        [(sent, values)] = db.sent("SELECT o.tenant_id")
        self.assertIn("r.workspace_id = :o", sent)
        self.assertNotIn("o.workspace_id", sent)
        self.assertEqual(values["o"], OTHER_OFFERING)


class ForkBaseTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def fork(self, db, name="Real Estate", tenant_id=7, **kw):
        with mock.patch.object(self.registry, "_sql", db.sql):
            return self.registry.fork_base(tenant_id, "a@firm.com", name, **kw)

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

    def test_a_tenant_that_already_published_gets_a_new_workspace(self):
        """It used to be refused: the only place a base could land was over
        the tenant's own configuration. It now lands beside it, numbered from
        the tenant's one counter, and nothing of the existing workspace is
        written."""
        db = FakeDb(published=3)
        result = self.fork(db)
        self.assertEqual((result["workspace_id"], result["revision"],
                          result["name"]), (NEW_WORKSPACE, 4, "Real Estate"))
        [(_, made)] = db.sent("INSERT INTO workspace")
        self.assertEqual((made["t"], made["name"], made["from_ws"],
                          made["from_rev"]), (7, "Real Estate", OFFERING, 9))
        [(_, revision)] = db.sent("INSERT INTO config_revision")
        self.assertEqual((revision["w"], revision["r"]), (NEW_WORKSPACE, 4))
        for s, values in db.statements:
            if s.startswith("INSERT INTO config_") and "to_ws" in values:
                self.assertEqual(values["to_ws"], NEW_WORKSPACE)
                self.assertEqual(values["from_ws"], OFFERING)
        [(_, active)] = db.sent("UPDATE workspace SET active_revision")
        self.assertEqual((active["w"], active["r"]), (NEW_WORKSPACE, 4))

    def test_a_first_fork_makes_the_first_workspace(self):
        db = FakeDb(published=0)
        result = self.fork(db, name="Trade Finance")
        self.assertEqual((result["workspace_id"], result["revision"]),
                         (NEW_WORKSPACE, 1))

    def test_refused_without_a_name(self):
        for name in (None, "", "   "):
            with self.subTest(name=name):
                db = FakeDb(published=0)
                with self.assertRaises(ValueError):
                    self.fork(db, name=name)
                self.assertEqual(db.sent("INSERT"), [])

    def test_the_pack_tenant_does_not_fork_from_itself(self):
        db = FakeDb(published=9)
        with self.assertRaises(ValueError):
            self.fork(db, tenant_id=0)
        self.assertEqual(db.sent("INSERT"), [])

    def test_the_whole_fork_is_one_transaction(self):
        """A workspace with no configuration would be offered everywhere and
        extract nothing, so the row, the revision and the copy go together."""
        db = FakeDb(published=0)
        self.fork(db)
        writes = [(s, tx) for s, tx in db.in_tx
                  if s.startswith(("INSERT", "UPDATE"))]
        self.assertTrue(writes)
        self.assertTrue(all(tx is not None for _, tx in writes))

    # --- which offering (PACK-02) ------------------------------------------

    def test_it_records_the_offering_it_was_taken_from(self):
        db = FakeDb(published=0)
        result = self.fork(db)
        self.assertEqual(result["offering"], OFFERING)
        [(_, made)] = db.sent("INSERT INTO workspace")
        self.assertEqual(made["from_ws"], OFFERING)

    def test_unnamed_takes_the_only_offering(self):
        # What a screen built before offerings sends.
        db = FakeDb(published=0)
        self.fork(db)
        [(_, asked)] = db.sent("SELECT o.tenant_id")
        self.assertEqual(asked["o"], OFFERING)

    def test_unnamed_is_refused_where_there_are_several(self):
        db = FakeDb(published=0, offerings=(OFFERING, OTHER_OFFERING))
        with self.assertRaises(ValueError) as raised:
            self.fork(db)
        self.assertIn("choose", str(raised.exception))
        self.assertEqual(db.sent("INSERT"), [])

    def test_a_named_offering_is_the_one_taken(self):
        db = FakeDb(published=0, offerings=(OFFERING, OTHER_OFFERING))
        result = self.fork(db, offering=OTHER_OFFERING)
        [(_, asked)] = db.sent("SELECT o.tenant_id")
        self.assertEqual(asked["o"], OTHER_OFFERING)
        self.assertEqual(result["workspace_id"], NEW_WORKSPACE)

    def test_an_offering_that_is_not_on_offer_is_refused(self):
        db = FakeDb(published=0)
        with self.assertRaises(ValueError):
            self.fork(db, offering=OTHER_OFFERING)
        self.assertEqual(db.sent("INSERT"), [])

    def test_nothing_on_offer_is_refused(self):
        db = FakeDb(published=0, offerings=())
        with self.assertRaises(ValueError):
            self.fork(db)
        self.assertEqual(db.sent("INSERT"), [])


class NewWorkspaceTest(unittest.TestCase):
    """An empty workspace and its draft (PACK-02, settled items 6 and 7)."""

    def setUp(self):
        self.registry = load_registry()

    def make(self, db, tenant_id=7, name="Real Estate"):
        with mock.patch.object(self.registry, "_sql", db.sql), \
             mock.patch.object(self.registry, "_begin", lambda: "tx-1"), \
             mock.patch.object(self.registry, "_commit", lambda tx: None), \
             mock.patch.object(self.registry, "_rollback", lambda tx: None):
            return self.registry.new_workspace(tenant_id, "a@firm.com", name)

    def test_a_workspace_and_an_empty_draft_in_one_transaction(self):
        db = FakeDb()
        result = self.make(db)
        self.assertEqual(result, {"workspace_id": NEW_WORKSPACE,
                                  "name": "Real Estate", "revision": 0,
                                  "empty": True})
        [(_, made)] = db.sent("INSERT INTO workspace")
        self.assertNotIn("from_ws", made)
        [(_, draft)] = db.sent("INSERT INTO config_revision")
        self.assertEqual((draft["w"], draft["d"]), (NEW_WORKSPACE, 0))
        writes = [(s, tx) for s, tx in db.in_tx if s.startswith("INSERT")]
        self.assertEqual(len(writes), 2)
        self.assertTrue(all(tx == "tx-1" for _, tx in writes))

    def test_nothing_is_copied_published_or_put_in_use(self):
        db = FakeDb()
        self.make(db)
        self.assertEqual(db.tables_written(), ["workspace", "config_revision"])
        self.assertEqual(db.sent("UPDATE"), [])
        self.assertEqual(db.sent("SELECT o."), [])

    def test_the_pack_tenant_may_make_one_its_new_offering(self):
        db = FakeDb()
        result = self.make(db, tenant_id=0, name="Real Estate")
        self.assertEqual(result["workspace_id"], NEW_WORKSPACE)

    def test_refused_without_a_name(self):
        for name in (None, "", "   ", "x" * 129):
            with self.subTest(name=name):
                db = FakeDb()
                with self.assertRaises(ValueError):
                    self.make(db, name=name)
                self.assertEqual(db.sent("INSERT"), [])

    # --- a name already used (found walking PACK-02, 23 October 2026) ------

    def test_a_name_already_held_is_refused_whatever_its_case_or_spacing(self):
        for asked in ("REAL ESTATE", "Real Estate", "  real   estate "):
            with self.subTest(asked=asked):
                db = FakeDb(names=["Trade Finance", "REAL ESTATE"])
                with self.assertRaises(ValueError) as raised:
                    self.make(db, name=asked)
                self.assertIn("already have a workspace called",
                              str(raised.exception))
                self.assertEqual(db.sent("INSERT"), [])

    def test_only_live_workspaces_are_asked(self):
        """A deleted workspace's name is free to use again."""
        db = FakeDb(names=["Trade Finance"])
        self.make(db, name="Real Estate")
        [(sent, values)] = db.sent("SELECT name FROM workspace")
        self.assertIn("deleted_at IS NULL", sent)
        self.assertEqual(values["t"], 7)

    def test_a_different_name_goes_ahead(self):
        db = FakeDb(names=["Trade Finance", "Real Estate"])
        result = self.make(db, name="Real Estate II")
        self.assertEqual(result["name"], "Real Estate II")

    def test_forking_a_base_is_refused_a_name_held_too(self):
        db = FakeDb(published=0, names=["Real Estate"])
        with mock.patch.object(self.registry, "_sql", db.sql):
            with self.assertRaises(ValueError):
                self.registry.fork_base(7, "a@firm.com", "real estate")
        self.assertEqual(db.sent("INSERT"), [])


class ForkTemplateTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def fork(self, db, pack_key="TRADEFINANCE-KYC"):
        with mock.patch.object(self.registry, "_sql", db.sql):
            return self.registry.fork_template(7, WORKSPACE, "a@firm.com",
                                               pack_key)

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

    def test_it_lands_in_the_workspaces_own_draft(self):
        db = FakeDb(held_fields={"f_borrower"})
        self.fork(db)
        for prefix in ("INSERT IGNORE INTO config_template",
                       "INSERT IGNORE INTO config_section ",
                       "INSERT IGNORE INTO config_section_field"):
            [(_, values)] = db.sent(prefix)
            self.assertEqual((values["to_w"], values["to_r"]), (WORKSPACE, 0))
            # From the pack tenant's revision, in its offering's workspace.
            self.assertEqual(values["from_w"], OFFERING)

    # --- the workspace's own offering (PACK-02) ----------------------------

    def test_the_memorandum_and_its_facts_come_from_its_own_offering(self):
        db = FakeDb(held_fields={"f_borrower"},
                    offerings=(OFFERING, OTHER_OFFERING), link=OFFERING)
        self.fork(db)
        asked = [v["o"] for _, v in db.sent("SELECT o.tenant_id")]
        # The memorandum's mark, then the base its facts come from.
        self.assertEqual(asked, [OFFERING, OFFERING])

    def test_a_workspace_from_no_offering_is_refused_and_untouched(self):
        db = FakeDb(held_fields={"f_borrower"}, link=None)
        with self.assertRaises(ValueError) as raised:
            self.fork(db)
        self.assertEqual(str(raised.exception),
                         self.registry.NOT_FROM_AN_OFFERING)
        self.assertEqual(db.sent("INSERT"), [])
        self.assertEqual(db.sent("SELECT o.tenant_id"), [])

    def test_another_offerings_memorandum_is_not_on_offer_here(self):
        # Linked to an offering that does not mark this memorandum.
        db = FakeDb(held_fields={"f_borrower"}, link=OTHER_OFFERING)
        with self.assertRaises(ValueError):
            self.fork(db)
        self.assertEqual(db.sent("INSERT"), [])

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
            self.registry.template_packs(7, WORKSPACE)
        [(sent, _)] = db.sent("SELECT o.revision, o.pack_key, r.note, o.tenant_id")
        self.assertIn("FROM pack_offer o", sent)
        self.assertIn("s.template_key = o.template_key", sent)
        self.assertIn("f.template_key = o.template_key", sent)

    # --- offerings (PACK-02) -----------------------------------------------

    def test_packs_names_each_offering(self):
        db = FakeDb(offerings=(OFFERING, OTHER_OFFERING))
        with mock.patch.object(self.registry, "_sql", db.sql):
            found = self.registry.packs()
        self.assertEqual([(p["workspace_id"], p["name"]) for p in found],
                         [(OFFERING, "Offering 11"),
                          (OTHER_OFFERING, "Offering 14")])
        [(sent, _)] = db.sent("SELECT o.revision, o.pack_key")
        # LEFT: before migration 044 the one offering has no workspace row.
        self.assertIn("LEFT JOIN workspace w", sent)

    def test_template_packs_are_the_workspaces_own_offerings(self):
        db = FakeDb(link=OTHER_OFFERING)
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.registry.template_packs(7, WORKSPACE)
        [(sent, values)] = db.sent(
            "SELECT o.revision, o.pack_key, r.note, o.tenant_id")
        self.assertIn("r.workspace_id = :o", sent)
        self.assertEqual(values["o"], OTHER_OFFERING)

    def test_a_workspace_from_no_offering_is_offered_nothing(self):
        db = FakeDb(link=None)
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.assertEqual(self.registry.template_packs(7, WORKSPACE), [])
        self.assertEqual(db.sent("SELECT o."), [])

    def test_a_named_offering_for_a_workspace_not_yet_made(self):
        # Get started, before the fork: nothing is held, so nothing of any
        # workspace is read.
        db = FakeDb(link=None)
        with mock.patch.object(self.registry, "_sql", db.sql):
            self.registry.template_packs(7, None, offering=OTHER_OFFERING)
        [(_, values)] = db.sent(
            "SELECT o.revision, o.pack_key, r.note, o.tenant_id")
        self.assertEqual(values["o"], OTHER_OFFERING)
        self.assertEqual(db.sent("SELECT forked_from_workspace_id"), [])
        self.assertEqual(db.sent("SELECT DISTINCT template_key"), [])


if __name__ == "__main__":
    unittest.main()
