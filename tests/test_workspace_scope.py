"""
Uploads, engagements and lists in one workspace (PACK-01, Prompt 4). Run from
the repository root:

    python -m unittest discover -s tests

THE CONTRACT.
  - An upload's key carries its workspace, and the link signs no workspace
    header: a header the browser does not send back is an upload S3 refuses.
  - The normalizer reads the workspace off the key, and reads a key from
    before workspaces as having none.
  - An engagement is found, created and listed within one workspace.
  - Share a memo lists the active workspace's memoranda.
  - /settings names the tenant's workspaces, for the selector.

Nothing reaches AWS: boto3 is replaced and _sql is faked. The SQL itself runs
on dev only after migration 042.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows
from test_normalizer_refusal import load_normalizer

TENANT = 7
WORKSPACE = 3


def plain(value):
    return None if value.get("isNull") else next(iter(value.values()))


class Recorder:
    def __init__(self, answer=None):
        self.statements = []
        self.answer = answer or (lambda s, v: rows())

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        v = {p["name"]: plain(p["value"]) for p in params or []}
        self.statements.append((s, v))
        return self.answer(s, v)


class UploadKeyTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def upload(self, workspace=WORKSPACE):
        with mock.patch.object(self.app, "_sql",
                               lambda s, p=None, tx=None: rows() if "FROM document" in s
                               else rows((11,))), \
                mock.patch.object(self.app, "_s3") as s3:
            s3.generate_presigned_url.return_value = "https://signed"
            out = self.app.upload_url(TENANT, workspace, "a@firm.com",
                                      "Meridian", "Articles.pdf")
        return out, s3.generate_presigned_url.call_args

    def test_the_key_carries_the_workspace(self):
        out, _ = self.upload()
        self.assertEqual(out["key"], "tenants/7/w/3/docs/Meridian/Articles.pdf")
        self.assertEqual(out["workspace_id"], WORKSPACE)

    def test_no_workspace_header_is_signed(self):
        """Every signed header must come back from the browser. The screen
        sends uploaded-by and, from a folder, source-folder - nothing else."""
        _, call = self.upload()
        metadata = call.kwargs["Params"]["Metadata"]
        self.assertEqual(set(metadata), {"uploaded-by"})

    def test_workspace_0_keeps_the_old_layout(self):
        out, _ = self.upload(workspace=0)
        self.assertEqual(out["key"], "tenants/7/docs/Meridian/Articles.pdf")


class NormalizerKeyTest(unittest.TestCase):
    def setUp(self):
        self.norm, _ = load_normalizer()

    def test_a_workspace_key(self):
        self.assertEqual(
            self.norm._parse_key("tenants/7/w/3/docs/Meridian/Articles.pdf"),
            (7, 3, "Meridian", "Articles.pdf"))

    def test_a_key_from_before_workspaces(self):
        self.assertEqual(
            self.norm._parse_key("tenants/7/docs/Meridian/Articles.pdf"),
            (7, None, "Meridian", "Articles.pdf"))

    def test_the_engagement_is_found_in_its_workspace(self):
        db = Recorder(lambda s, v: rows((42,)))
        with mock.patch.object(self.norm, "_sql", db.sql):
            self.assertEqual(
                self.norm._engagement_id(TENANT, WORKSPACE, "Meridian"), 42)
        [(statement, values)] = db.statements
        self.assertIn("workspace_id = :w", statement)
        self.assertEqual(values["w"], WORKSPACE)


class EngagementScopeTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def test_a_new_engagement_is_made_in_the_workspace(self):
        found = iter([rows(), rows(), rows((42,))])
        db = Recorder(lambda s, v: next(found))
        with mock.patch.object(self.app, "_sql", db.sql):
            self.assertEqual(self.app.engagement_id(TENANT, WORKSPACE,
                                                    "Meridian", "a@firm.com"),
                             42)
        insert = [v for s, v in db.statements if s.startswith("INSERT")]
        self.assertEqual(insert[0]["w"], WORKSPACE)
        for s, v in db.statements:
            self.assertIn("workspace_id", s)

    def test_the_list_is_the_workspaces_own(self):
        db = Recorder()
        with mock.patch.object(self.app, "_sql", db.sql):
            self.app.list_engagements(TENANT, WORKSPACE)
        [(statement, values)] = db.statements
        self.assertIn("e.workspace_id = :workspace_id", statement)
        self.assertEqual(values["workspace_id"], WORKSPACE)

    def test_a_name_is_looked_up_in_the_workspace(self):
        db = Recorder()
        with mock.patch.object(self.app, "_sql", db.sql):
            self.assertIsNone(self.app.engagement_named(TENANT, WORKSPACE,
                                                        "Meridian"))
        [(statement, values)] = db.statements
        self.assertIn("workspace_id = :w", statement)

    def test_share_a_memo_lists_the_workspaces_memoranda(self):
        db = Recorder()
        with mock.patch.object(self.app, "_sql", db.sql):
            self.app.list_all_memos(TENANT, WORKSPACE, "a@firm.com")
        [(statement, values)] = db.statements
        self.assertIn("m.workspace_id = :w", statement)
        self.assertEqual(values["w"], WORKSPACE)

    def test_the_route_resolves_the_asked_workspace(self):
        """GET /engagements?workspace=9 lists workspace 9, checked against
        the token's tenant first."""
        held = [(3, "Trade Finance", 5), (9, "Real Estate", 2)]

        def answer(s, v):
            if s.startswith("SELECT workspace_id, name, active_revision"):
                return rows(*held)
            return rows()
        db = Recorder(answer)
        # A member assigned both (PACK-02 C).
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app.config, "_sql", db.sql), \
                mock.patch.object(self.app.seats, "allowed_workspaces",
                                  return_value={3, 9}):
            reply = self.app._dispatch({
                "routeKey": "GET /engagements",
                "queryStringParameters": {"workspace": "9"},
                "requestContext": {"authorizer": {"jwt": {"claims": {
                    "custom:tenant_id": str(TENANT), "email": "a@firm.com",
                    "custom:role": "member"}}}},
            }, None)
        self.assertEqual(reply["statusCode"], 200)
        listed = [v for s, v in db.statements if "FROM engagement e" in s]
        self.assertEqual(listed[0]["workspace_id"], 9)

    def test_another_tenants_workspace_is_refused(self):
        def answer(s, v):
            if s.startswith("SELECT workspace_id, name, active_revision"):
                return rows((3, "Trade Finance", 5))
            return rows()
        db = Recorder(answer)
        # A member with nothing assigned: another tenant's number is still a
        # 400, refused by the tenant check before the member's own.
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app.config, "_sql", db.sql), \
                mock.patch.object(self.app.seats, "allowed_workspaces",
                                  return_value=set()):
            reply = self.app._dispatch({
                "routeKey": "GET /engagements",
                "queryStringParameters": {"workspace": "12"},
                "requestContext": {"authorizer": {"jwt": {"claims": {
                    "custom:tenant_id": str(TENANT), "email": "a@firm.com"}}}},
            }, None)
        self.assertEqual(reply["statusCode"], 400)
        self.assertFalse(any("FROM engagement e" in s for s, _ in db.statements))


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def test_settings_names_the_workspaces(self):
        def answer(s, v):
            if s.startswith("SELECT name, plan"):
                return rows(("Firm", "business", None, None, None, None, None))
            if s.startswith("SELECT workspace_id, name, active_revision"):
                return rows((3, "Trade Finance", 5), (9, "Real Estate", 2))
            return rows()
        db = Recorder(answer)
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app.config, "_sql", db.sql), \
                mock.patch.object(self.app.billing, "workspace_limit",
                                  return_value=5), \
                mock.patch.object(self.app.billing, "workspaces_held",
                                  return_value=2):
            out = self.app.get_settings(TENANT, "member")
        self.assertEqual(out["workspaces"],
                         [{"workspace_id": 3, "name": "Trade Finance"},
                          {"workspace_id": 9, "name": "Real Estate"}])
        # PACK-02: the limit and the count travel with them, for the screen.
        self.assertEqual((out["workspace_limit"], out["workspaces_held"]),
                         (5, 2))


if __name__ == "__main__":
    unittest.main()
