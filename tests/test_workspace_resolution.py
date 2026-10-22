"""
Which workspace a request works in (PACK-01). The database is replaced. Run
from the repository root:

    python -m unittest discover -s tests

THE RULE (decision of 22 October 2026):
  - a workspace named by the request must be one of the token's tenant's;
  - none named, the tenant's only workspace;
  - none named and several held, refused - never guessed;
  - a tenant with none (the pack tenant) is workspace 0.
A row stored at workspace 0 by code that predates workspaces reads as the
tenant's only workspace.
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


def load_config():
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
            "shared_config", ROOT / "lambda/shared/config.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class Held:
    """The workspace table, for one tenant."""

    def __init__(self, *ids, active=None):
        self.ids = ids
        self.active = active
        self.asked = []

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        values = {p["name"]: next(iter(p["value"].values()))
                  for p in params or []}
        self.asked.append((s, values))
        if s.startswith("SELECT workspace_id, name, active_revision"):
            return rows(*[(w, "W%d" % w, self.active) for w in self.ids])
        if s.startswith("SELECT active_revision FROM workspace"):
            return rows((self.active,))
        if s.startswith("SELECT active_revision FROM tenant"):
            return rows((self.active,))
        return rows()


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def resolve(self, held, asked=None):
        with mock.patch.object(self.config, "_sql", held.sql):
            return self.config.workspace(7, asked)

    def test_none_named_and_one_held_is_that_one(self):
        self.assertEqual(self.resolve(Held(4)), 4)

    def test_none_named_and_several_held_is_refused(self):
        with self.assertRaises(self.config.WorkspaceRequired) as raised:
            self.resolve(Held(4, 9))
        self.assertEqual(str(raised.exception),
                         self.config.CHOOSE_A_WORKSPACE)
        # A ValueError, so every route answers it as 400 with the sentence.
        self.assertIsInstance(raised.exception, ValueError)

    def test_a_named_workspace_of_this_tenant_is_used(self):
        self.assertEqual(self.resolve(Held(4, 9), "9"), 9)

    def test_a_workspace_of_another_tenant_is_refused(self):
        """The tenant is the token's; the number is the request's. This is
        the check between them."""
        held = Held(4, 9)
        with self.assertRaises(ValueError):
            self.resolve(held, 12)
        [(statement, values)] = held.asked
        self.assertIn("WHERE tenant_id = :t", statement)
        self.assertEqual(values["t"], 7)

    def test_a_name_that_is_not_a_number_is_refused(self):
        with self.assertRaises(ValueError):
            self.resolve(Held(4), "trade-finance")

    def test_a_tenant_with_none_is_workspace_0(self):
        self.assertEqual(self.resolve(Held()), 0)
        self.assertEqual(self.resolve(Held(), 0), 0)

    def test_workspace_0_cannot_be_named_by_a_tenant_that_has_workspaces(self):
        with self.assertRaises(ValueError):
            self.resolve(Held(4), 0)


class WorkspaceOfTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_a_row_carrying_its_workspace_is_read_in_it(self):
        held = Held(4, 9)
        with mock.patch.object(self.config, "_sql", held.sql):
            self.assertEqual(self.config.workspace_of(7, 9), 9)
        self.assertEqual(held.asked, [])

    def test_a_row_at_0_is_the_tenants_only_workspace(self):
        with mock.patch.object(self.config, "_sql", Held(4).sql):
            self.assertEqual(self.config.workspace_of(7, 0), 4)
            self.assertEqual(self.config.workspace_of(7, None), 4)

    def test_a_row_at_0_with_several_workspaces_is_refused(self):
        with mock.patch.object(self.config, "_sql", Held(4, 9).sql):
            with self.assertRaises(ValueError):
                self.config.workspace_of(7, 0)


class ActiveRevisionTest(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_a_workspace_reads_its_own_row(self):
        held = Held(4, active=12)
        with mock.patch.object(self.config, "_sql", held.sql):
            self.assertEqual(self.config.active_revision(7, 4), 12)
        [(statement, values)] = held.asked
        self.assertTrue(statement.startswith(
            "SELECT active_revision FROM workspace"))
        self.assertEqual((values["t"], values["w"]), (7, 4))

    def test_workspace_0_reads_the_tenant_row(self):
        held = Held(active=33)
        with mock.patch.object(self.config, "_sql", held.sql):
            self.assertEqual(self.config.active_revision(0, 0), 33)
        self.assertTrue(held.asked[0][0].startswith(
            "SELECT active_revision FROM tenant"))

    def test_none_selected_is_revision_1(self):
        with mock.patch.object(self.config, "_sql", Held(4, active=None).sql):
            self.assertEqual(self.config.active_revision(7, 4), 1)

    def test_the_cache_is_keyed_by_workspace(self):
        """Two workspaces never share a loaded revision, even where a number
        were to repeat."""
        with mock.patch.object(self.config, "Registry",
                               side_effect=lambda t, w, r: (t, w, r)):
            self.assertEqual(self.config.load(7, 4, 2), (7, 4, 2))
            self.assertEqual(self.config.load(7, 9, 2), (7, 9, 2))


if __name__ == "__main__":
    unittest.main()
