"""
Setting the catalogue: one revision, and the memoranda offered from it.

    python -m unittest discover -s tests

The SQL itself is exercised on dev, not here; what is tested here is what the
code decides, which statements it sends, and - the point of most of it - what
it refuses to send at all. A half-written catalogue would take every
memorandum off offer and leave Get started with nothing, so the tests that
matter most are the ones proving nothing was written.
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


CREDIT = "credit-memorandum"
KYC = "kyc-customer-due-diligence-memorandum"

# The marks as they stand: revision 9, two memoranda, the base with them.
STANDING = [(9, "base", None, "2026-09-17 10:00", "migration 024"),
            (9, "template", CREDIT, "2026-09-17 10:00", "migration 024"),
            (9, "template", KYC, "2026-09-17 10:00", "migration 024")]


class FakeDb:
    def __init__(self, status="published", facts=5, held=(CREDIT, KYC),
                 defined=("f_borrower",), bound=None, standing=None,
                 fail_on=None):
        self.status = status
        self.facts = facts
        self.held = set(held)
        self.defined = set(defined)
        # Per memorandum; anything unnamed binds f_borrower, which is defined.
        self.bound = dict(bound or {})
        self.standing = STANDING if standing is None else standing
        self.fail_on = fail_on
        self.statements = []
        self.committed = False
        self.rolled_back = False

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        values = {p["name"]: plain(p["value"]) for p in params or []}
        self.statements.append((s, values, tx))

        if self.fail_on and s.startswith(self.fail_on):
            raise RuntimeError("the database said no")

        if s.startswith("SELECT revision, kind, template_key"):
            return rows(*self.standing)
        if s.startswith("SELECT status FROM config_revision"):
            return rows((self.status,)) if self.status else rows()
        if "COUNT(*) FROM config_field WHERE tenant_id" in s:
            return rows((self.facts,))
        if s.startswith("SELECT DISTINCT template_key FROM config_template"):
            return rows(*[(k,) for k in sorted(self.held)])
        if s.startswith("SELECT DISTINCT field_key FROM config_section_field"):
            wanted = self.bound.get(values.get("tk"), {"f_borrower"})
            return rows(*[(k,) for k in sorted(wanted)])
        if s.startswith("SELECT DISTINCT field_key FROM config_field"):
            return rows(*[(k,) for k in sorted(self.defined)])
        return rows()

    def sent(self, prefix):
        return [(s, v, t) for s, v, t in self.statements if s.startswith(prefix)]

    def wrote_anything(self):
        return any(s.startswith(("DELETE FROM pack_offer", "INSERT INTO pack_offer"))
                   for s, _, _ in self.statements)


class SetOfferTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def run_it(self, db, revision=9, templates=(CREDIT, KYC)):
        with mock.patch.object(self.registry, "_sql", db.sql), \
             mock.patch.object(self.registry, "_begin", lambda: "tx-1"), \
             mock.patch.object(self.registry, "_commit",
                               lambda tx: setattr(db, "committed", True)), \
             mock.patch.object(self.registry, "_rollback",
                               lambda tx: setattr(db, "rolled_back", True)):
            return self.registry.set_offer(revision, list(templates),
                                           "admin@arqedia.com")

    # --- what it writes ---------------------------------------------------

    def test_writes_the_base_and_one_row_per_memorandum(self):
        db = FakeDb()
        self.run_it(db)
        [(_, base, _)] = db.sent("INSERT INTO pack_offer (pack_key, kind, tenant_id, revision, template_key, marked_by) VALUES ('base'")
        self.assertEqual(base["r"], 9)
        self.assertEqual(base["t"], 0)
        written = [v for s, v, _ in db.statements
                   if s.startswith("INSERT INTO pack_offer") and "k" in v]
        self.assertEqual(sorted(v["k"] for v in written), sorted([CREDIT, KYC]))

    def test_the_pack_key_is_the_template_key(self):
        # Nothing downstream remembers a pack key, so there is not a second
        # identity to invent. The statement writes :k into both columns.
        db = FakeDb()
        self.run_it(db)
        [(sent, values, _)] = [(s, v, t) for s, v, t in db.statements
                               if s.startswith("INSERT INTO pack_offer")
                               and v.get("k") == CREDIT]
        self.assertIn("VALUES (:k, 'template', :t, :r, :k, :who)", sent)
        self.assertEqual(values["who"], "admin@arqedia.com")

    def test_every_write_is_in_one_transaction_and_commits(self):
        db = FakeDb()
        self.run_it(db)
        writes = [(s, t) for s, _, t in db.statements
                  if s.startswith(("DELETE FROM pack_offer",
                                   "INSERT INTO pack_offer"))]
        self.assertTrue(writes)
        for _, tx in writes:
            self.assertEqual(tx, "tx-1")
        self.assertTrue(db.committed)
        self.assertFalse(db.rolled_back)

    def test_it_clears_before_it_writes(self):
        # The base is not a separate choice: the delete is what stops a mark
        # from an earlier revision surviving underneath a new one.
        db = FakeDb()
        self.run_it(db)
        kinds = [s.split(" pack_offer")[0] for s, _, _ in db.statements
                 if s.startswith(("DELETE FROM pack_offer",
                                  "INSERT INTO pack_offer"))]
        self.assertEqual(kinds[0], "DELETE FROM")

    def test_a_failed_write_rolls_back(self):
        db = FakeDb(fail_on="INSERT INTO pack_offer")
        with self.assertRaises(RuntimeError):
            self.run_it(db)
        self.assertTrue(db.rolled_back)
        self.assertFalse(db.committed)

    # --- what it reports --------------------------------------------------

    def test_it_reports_what_changed(self):
        db = FakeDb(held=(CREDIT, KYC, "lender"))
        result = self.run_it(db, templates=(CREDIT, "lender"))
        self.assertEqual(result["added"], ["lender"])
        self.assertEqual(result["removed"], [KYC])
        self.assertIsNone(result["moved_from"])

    def test_moving_the_offer_names_where_it_came_from(self):
        db = FakeDb()
        result = self.run_it(db, revision=10)
        self.assertEqual(result["moved_from"], 9)
        self.assertEqual(result["revision"], 10)

    def test_a_save_that_changes_nothing_says_so(self):
        db = FakeDb()
        result = self.run_it(db)
        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])
        self.assertIsNone(result["moved_from"])

    # --- what it refuses, having written nothing --------------------------

    def refuse(self, db, **kw):
        with self.assertRaises(ValueError) as raised:
            self.run_it(db, **kw)
        self.assertFalse(db.wrote_anything(),
                         "refused, but it had already written")
        return str(raised.exception)

    def test_refuses_the_draft(self):
        self.assertIn("publish", self.refuse(FakeDb(), revision=0))

    def test_refuses_a_revision_that_is_not_a_number(self):
        self.refuse(FakeDb(), revision="9")

    def test_refuses_a_boolean_dressed_as_a_revision(self):
        # True == 1 in Python, so an isinstance check alone would offer
        # revision 1 to everybody.
        self.refuse(FakeDb(), revision=True)

    def test_refuses_a_revision_that_does_not_exist(self):
        self.assertIn("no revision", self.refuse(FakeDb(status=None)))

    def test_refuses_an_unpublished_revision(self):
        self.assertIn("not published", self.refuse(FakeDb(status="draft")))

    def test_refuses_a_revision_holding_no_facts(self):
        # A memorandum-only revision cannot carry the base, and the base is
        # never a separate mark.
        self.assertIn("no facts", self.refuse(FakeDb(facts=0)))

    def test_refuses_an_empty_catalogue(self):
        self.assertIn("at least one", self.refuse(FakeDb(), templates=()))

    def test_refuses_a_memorandum_the_revision_does_not_hold(self):
        said = self.refuse(FakeDb(held=(CREDIT,)), templates=(CREDIT, KYC))
        self.assertIn(KYC, said)

    def test_refuses_a_memorandum_binding_an_undefined_fact(self):
        # Item 8's refusal, landing on the curator instead of the customer.
        db = FakeDb(bound={KYC: {"f_invented"}})
        said = self.refuse(db)
        self.assertIn("f_invented", said)
        self.assertIn(KYC, said)

    def test_names_every_missing_memorandum_not_just_the_first(self):
        db = FakeDb(held=(CREDIT,))
        said = self.refuse(db, templates=(CREDIT, KYC, "lender"))
        self.assertIn(KYC, said)
        self.assertIn("lender", said)

    def test_a_repeated_name_is_offered_once(self):
        db = FakeDb()
        result = self.run_it(db, templates=(CREDIT, CREDIT, KYC))
        self.assertEqual(result["templates"], [CREDIT, KYC])


class OfferReadTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()

    def test_reads_one_revision_and_its_memoranda(self):
        db = FakeDb()
        with mock.patch.object(self.registry, "_sql", db.sql):
            found = self.registry.offer()
        self.assertEqual(found["revision"], 9)
        self.assertEqual(found["templates"], sorted([CREDIT, KYC]))
        self.assertEqual(found["marked_by"], "migration 024")

    def test_nothing_marked_is_a_broken_catalogue_not_a_default(self):
        db = FakeDb(standing=[])
        with mock.patch.object(self.registry, "_sql", db.sql):
            found = self.registry.offer()
        self.assertIsNone(found["revision"])
        self.assertEqual(found["templates"], [])


if __name__ == "__main__":
    unittest.main()
