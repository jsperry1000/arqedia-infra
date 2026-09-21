"""
Adding a fact does not take one that exists (17.1).

    python -m unittest discover -s tests

THE BUG. POST /config/draft/fields serves both adding and amending, and the
write is INSERT ... ON DUPLICATE KEY UPDATE. A person adding "Company
Summary" where f_company_summary already existed had its label, shape,
description and group rewritten, and was told a fact had been created. It
happened on dev on 20 September, to tenant 0 - the catalogue every other
tenant forks from.

THE CONTRACT. A body with no key is a create: the key is minted from the
label and a fact already holding it is a refusal. A body with a key names a
fact that exists and updates it. The two were indistinguishable before
because the screen minted the key itself and sent it on both.

editor.py is imported from lambda/shared, which is the docprocessing layer -
so these run against the same file the Lambdas get, and a layer that has not
been rebuilt is a deploy problem rather than a test problem.
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

TENANT = 7
EXISTING_KEY = "f_company_summary"
EXISTING_LABEL = "Company Summary"


def load_editor():
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
            "editor_shared", ROOT / "lambda/shared/editor.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def plain(value):
    return None if value.get("isNull") else next(iter(value.values()))


class Db:
    """The draft, as much of it as save_field asks about."""

    def __init__(self, held=()):
        # field_key -> label, for fields the draft already holds.
        self.held = dict(held)
        self.statements = []

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        values = {p["name"]: plain(p["value"]) for p in params or []}
        self.statements.append((s, values))

        if s.startswith("SELECT revision FROM config_revision"):
            return rows((0,))
        if s.startswith("SELECT schema_key, label FROM config_field"):
            key = values.get("k")
            return rows(("unrouted", self.held[key])) if key in self.held \
                else rows()
        return {"records": []}

    def wrote(self, prefix):
        return [v for s, v in self.statements if s.startswith(prefix)]

    def upserts(self):
        return self.wrote("INSERT INTO config_field")


class CreateTest(unittest.TestCase):
    def setUp(self):
        self.editor = load_editor()

    def save(self, body, held=()):
        db = Db(held)
        with mock.patch.object(self.editor, "_sql", db.sql):
            out = self.editor.save_field(TENANT, body)
        return out, db

    def test_a_new_name_is_created(self):
        out, db = self.save({"label": "Shipping Terms"})
        self.assertEqual(out["key"], "f_shipping_terms")
        [wrote] = db.upserts()
        self.assertEqual(wrote["k"], "f_shipping_terms")
        self.assertEqual(wrote["label"], "Shipping Terms")

    def test_an_existing_name_is_refused_and_nothing_is_written(self):
        """The whole point. The refusal names the fact in the way, because
        the name on screen is the label and the thing in the way is a key
        nobody typed."""
        with self.assertRaises(ValueError) as caught:
            self.save({"label": EXISTING_LABEL},
                      held={EXISTING_KEY: EXISTING_LABEL})
        said = str(caught.exception)
        self.assertIn(EXISTING_KEY, said)
        self.assertIn(EXISTING_LABEL, said)

    def test_the_existing_fact_is_untouched_by_the_refusal(self):
        db = Db({EXISTING_KEY: EXISTING_LABEL})
        with mock.patch.object(self.editor, "_sql", db.sql):
            with self.assertRaises(ValueError):
                self.editor.save_field(TENANT, {
                    "label": EXISTING_LABEL,
                    "cardinality": "many",
                    "description": "Something else entirely",
                })
        # Not one write of any kind: no upsert, no column rewrite, no delete.
        self.assertEqual(db.upserts(), [])
        self.assertEqual([s for s, _ in db.statements
                          if s.startswith(("INSERT", "UPDATE", "DELETE"))], [])

    def test_a_label_that_slugs_onto_an_existing_key_is_refused(self):
        """"company summary" and "Company Summary" are one key. The collision
        is on the key, which is what the person never sees."""
        with self.assertRaises(ValueError):
            self.save({"label": "company   summary"},
                      held={EXISTING_KEY: EXISTING_LABEL})


class EditTest(unittest.TestCase):
    """A key in the body means the fact exists. Editing is unchanged."""

    def setUp(self):
        self.editor = load_editor()

    def test_editing_an_existing_fact_still_saves(self):
        db = Db({EXISTING_KEY: EXISTING_LABEL})
        with mock.patch.object(self.editor, "_sql", db.sql):
            out = self.editor.save_field(TENANT, {
                "key": EXISTING_KEY,
                "label": "Company Summary",
                "cardinality": "many",
                "description": "Rewritten deliberately",
            })
        self.assertEqual(out["key"], EXISTING_KEY)
        [wrote] = db.upserts()
        self.assertEqual(wrote["card"], "many")
        self.assertEqual(wrote["desc"], "Rewritten deliberately")

    def test_a_key_for_a_fact_that_does_not_exist_yet_still_creates(self):
        """The proposer and any caller minting its own key: naming a key
        nothing holds is not a collision, and refusing it would break the
        only other way a fact is made."""
        out, db = self.save_with_key()
        self.assertEqual(out["key"], "f_own_key")
        self.assertEqual(len(db.upserts()), 1)

    def save_with_key(self):
        db = Db({EXISTING_KEY: EXISTING_LABEL})
        with mock.patch.object(self.editor, "_sql", db.sql):
            out = self.editor.save_field(TENANT, {
                "key": "f_own_key", "label": "Own Key"})
        return out, db

    def test_an_empty_key_is_a_create_not_an_edit(self):
        """A form sending key: "" is saying nothing, not naming a fact."""
        db = Db({EXISTING_KEY: EXISTING_LABEL})
        with mock.patch.object(self.editor, "_sql", db.sql):
            with self.assertRaises(ValueError):
                self.editor.save_field(TENANT, {
                    "key": "  ", "label": EXISTING_LABEL})


if __name__ == "__main__":
    unittest.main()
