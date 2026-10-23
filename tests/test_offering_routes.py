"""
The API's half of offerings (PACK-02): which registry call each route makes,
and with what. The registry is replaced; its own decisions are tested in
test_pack_offer.py and test_set_offer.py. Run from the repository root:

    python -m unittest discover -s tests
"""

import json
import unittest
from unittest import mock

from test_curation_only import load_api

WORKSPACE = 3
OFFERING = 11


def event(route, tenant="5", role="admin", body=None, query=None):
    return {
        "routeKey": route,
        "body": json.dumps(body) if body is not None else None,
        "queryStringParameters": query,
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "custom:tenant_id": tenant, "custom:role": role,
            "email": "someone@firm.com"}}}},
    }


class OfferingRoutesTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()
        self.registry = mock.MagicMock()
        self.registry.PACK_TENANT = 0
        patches = [
            mock.patch.object(self.app, "registry", self.registry),
            mock.patch.object(self.app.config, "workspace",
                              mock.MagicMock(return_value=WORKSPACE)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def dispatch(self, *args, **kw):
        reply = self.app._dispatch(event(*args, **kw), None)
        return reply["statusCode"], json.loads(reply["body"])

    # --- POST /config/fork -------------------------------------------------

    def test_empty_makes_an_empty_workspace_and_forks_nothing(self):
        self.registry.new_workspace.return_value = {"workspace_id": 12}
        status, _ = self.dispatch("POST /config/fork",
                                  body={"name": "Real Estate", "empty": True})
        self.assertEqual(status, 201)
        self.registry.new_workspace.assert_called_once_with(
            5, "someone@firm.com", "Real Estate")
        self.registry.fork_base.assert_not_called()

    def test_the_pack_tenant_makes_a_new_offering_the_same_way(self):
        self.registry.new_workspace.return_value = {"workspace_id": 14}
        status, _ = self.dispatch("POST /config/fork", tenant="0",
                                  body={"name": "Real Estate", "empty": True})
        self.assertEqual(status, 201)
        self.registry.new_workspace.assert_called_once_with(
            0, "someone@firm.com", "Real Estate")

    def test_only_true_is_empty(self):
        # A string "true" or a 1 is not a decision to start with nothing.
        self.registry.fork_base.return_value = {"workspace_id": 12}
        self.dispatch("POST /config/fork",
                      body={"name": "Real Estate", "empty": "true"})
        self.registry.new_workspace.assert_not_called()
        self.registry.fork_base.assert_called_once()

    def test_the_offering_named_travels_to_the_fork(self):
        self.registry.fork_base.return_value = {"workspace_id": 12}
        status, _ = self.dispatch("POST /config/fork",
                                  body={"name": "Real Estate",
                                        "offering": OFFERING})
        self.assertEqual(status, 201)
        self.registry.fork_base.assert_called_once_with(
            5, "someone@firm.com", "Real Estate", pack_revision=None,
            offering=OFFERING)

    def test_unnamed_is_left_to_the_registry(self):
        # What a screen built before offerings sends.
        self.registry.fork_base.return_value = {"workspace_id": 12}
        self.dispatch("POST /config/fork", body={"name": "Trade Finance"})
        self.assertIsNone(self.registry.fork_base.call_args.kwargs["offering"])

    def test_a_member_makes_no_workspace_either_way(self):
        for body in ({"name": "x", "empty": True}, {"name": "x"}):
            with self.subTest(body=body):
                status, _ = self.dispatch("POST /config/fork", role="member",
                                          body=body)
                self.assertEqual(status, 403)
        self.registry.new_workspace.assert_not_called()
        self.registry.fork_base.assert_not_called()

    # --- GET /config/templates/available -----------------------------------

    def test_the_active_workspaces_own(self):
        self.registry.template_packs.return_value = []
        self.dispatch("GET /config/templates/available",
                      query={"workspace": str(WORKSPACE)})
        self.registry.template_packs.assert_called_once_with(5, WORKSPACE)

    def test_a_named_offering_resolves_no_workspace(self):
        # For a workspace not yet made: the tenant may hold several, and
        # none of them is the one being asked about.
        self.registry.template_packs.return_value = []
        status, _ = self.dispatch("GET /config/templates/available",
                                  query={"offering": str(OFFERING)})
        self.assertEqual(status, 200)
        self.registry.template_packs.assert_called_once_with(
            5, None, offering=OFFERING)
        self.app.config.workspace.assert_not_called()

    def test_an_offering_that_is_not_a_number_is_refused(self):
        status, _ = self.dispatch("GET /config/templates/available",
                                  query={"offering": "trade"})
        self.assertEqual(status, 400)
        self.registry.template_packs.assert_not_called()

    # --- the catalogue, one offering at a time -----------------------------

    def test_the_offer_read_is_the_active_workspaces(self):
        self.registry.offer.return_value = {"revision": 9}
        self.dispatch("GET /config/offer", tenant="0",
                      query={"workspace": str(OFFERING)})
        self.registry.offer.assert_called_once_with(WORKSPACE)

    def test_the_offer_set_is_the_active_workspaces(self):
        self.registry.set_offer.return_value = {"revision": 9}
        self.dispatch("PUT /config/offer", tenant="0",
                      body={"revision": 9, "templates": ["credit"]})
        self.registry.set_offer.assert_called_once_with(
            WORKSPACE, 9, ["credit"], "someone@firm.com")


class ShareHistoryRouteTest(unittest.TestCase):
    """GET /shares lists the requested workspace's shares (PACK-01)."""

    def setUp(self):
        self.app = load_api()
        p = mock.patch.object(self.app.config, "workspace",
                              mock.MagicMock(return_value=WORKSPACE))
        p.start()
        self.addCleanup(p.stop)

    def test_the_resolved_workspace_reaches_the_listing(self):
        share = mock.MagicMock()
        share.listing.return_value = {"grants": [], "allowance": {}}
        with mock.patch.dict("sys.modules", {"share": share}):
            reply = self.app._dispatch(event(
                "GET /shares", query={"workspace": str(WORKSPACE)}), None)
        self.assertEqual(reply["statusCode"], 200)
        share.listing.assert_called_once_with(5, WORKSPACE)


class ConfigStateRevisionTest(unittest.TestCase):
    """An empty workspace has no revision in use, and GET /config says so
    rather than passing on config.active_revision's fallback of 1, which is
    another workspace's revision (found walking PACK-02)."""

    def setUp(self):
        self.app = load_api()
        for name, value in (
                ("workspaces", []),
                ("active_revision", 1),
                ("for_workspace", mock.MagicMock()),
        ):
            p = mock.patch.object(self.app.config, name,
                                  value if callable(value)
                                  else mock.MagicMock(return_value=value))
            p.start()
            self.addCleanup(p.stop)

    def state(self, revisions):
        with mock.patch.object(self.app.registry, "revisions",
                               return_value=revisions), \
             mock.patch.object(self.app.registry, "validate",
                               return_value={}):
            return self.app.config_state(0, 13)

    def test_nothing_published_is_null(self):
        found = self.state([{"revision": 0, "is_draft": True}])
        self.assertIsNone(found["active_revision"])
        self.assertEqual(found["revisions"], [])
        self.app.config.active_revision.assert_not_called()

    def test_a_published_workspace_says_its_revision(self):
        self.app.config.active_revision.return_value = 34
        found = self.state([{"revision": 34, "is_draft": False},
                            {"revision": 0, "is_draft": True}])
        self.assertEqual(found["active_revision"], 34)
        self.assertEqual([r["revision"] for r in found["revisions"]], [34])


if __name__ == "__main__":
    unittest.main()
