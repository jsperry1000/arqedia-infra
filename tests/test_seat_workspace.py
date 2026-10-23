"""
Which workspaces a seat may reach (PACK-02 C, migration 045). The database is
replaced. Run from the repository root:

    python -m unittest discover -s tests

An administrator reaches every workspace; a member only those assigned to
their seat. What is tested here is what seats.py decides and writes, and what
the dispatcher refuses. The SQL itself is exercised on dev.
"""

import json
import re
import unittest
from unittest import mock

from api_modules import rows
from test_curation_only import load_api

TENANT = 2
ADMIN_SEAT, MEMBER_SEAT = 3, 7
TRADE, AR, OTHER = 2, 9, 12      # tenant 2's workspaces, and another tenant's


def plain(value):
    return None if "isNull" in value else next(iter(value.values()))


class SeatsDb:
    """Answers seats.py's statements for tenant 2: two workspaces, an
    administrator and a member."""

    def __init__(self, assigned=(TRADE,)):
        self.assigned = set(assigned)
        self.statements = []

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        values = {p["name"]: plain(p["value"]) for p in params or []}
        self.statements.append((s, values))
        if s.startswith("SELECT workspace_id FROM workspace WHERE tenant_id"):
            return rows((TRADE,), (AR,))
        if s.startswith("SELECT role FROM seat WHERE seat_id"):
            return rows(("admin",) if values["s"] == ADMIN_SEAT
                        else ("member",))
        if s.startswith("SELECT email, role FROM seat WHERE seat_id"):
            return rows(("a@b.c", "admin" if values["s"] == ADMIN_SEAT
                         else "member"))
        if s.startswith("SELECT sw.workspace_id FROM seat s"):
            return rows(*[(w,) for w in sorted(self.assigned)])
        if s.startswith("SELECT COUNT(*) FROM seat WHERE tenant_id"):
            return rows((2,))
        if s.startswith("SELECT invitation_id FROM seat_invitation WHERE email"):
            return rows((41,))
        if s.startswith("SELECT tenant_id FROM seat WHERE email"):
            return rows()
        return rows()

    def sent(self, prefix):
        return [(s, v) for s, v in self.statements if s.startswith(prefix)]


class SeatsTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()
        self.seats = self.app.seats

    def run_with(self, db, fn, *args, **kwargs):
        with mock.patch.object(self.seats, "_sql", db.sql):
            return fn(*args, **kwargs)

    # --- who reaches what -------------------------------------------------

    def test_an_administrator_reaches_every_workspace(self):
        db = SeatsDb()
        self.assertIsNone(self.run_with(
            db, self.seats.allowed_workspaces, TENANT, "a@b.c", "admin"))
        self.assertEqual(db.statements, [])

    def test_a_member_reaches_what_their_seat_is_assigned(self):
        db = SeatsDb(assigned=(AR,))
        self.assertEqual(self.run_with(
            db, self.seats.allowed_workspaces, TENANT, "M@B.C", "member"),
            {AR})
        [(_, values)] = db.sent("SELECT sw.workspace_id")
        self.assertEqual(values["e"], "m@b.c")

    # --- setting a member's workspaces ------------------------------------

    def test_set_replaces_the_seats_workspaces(self):
        db = SeatsDb()
        result = self.run_with(db, self.seats.set_workspaces, TENANT,
                               "admin@b.c", MEMBER_SEAT, [AR, TRADE, AR])
        self.assertEqual(result["workspaces"], [AR, TRADE])
        [(delete, values)] = db.sent("DELETE FROM seat_workspace")
        self.assertIn("workspace_id NOT IN", delete)
        inserted = [v["w"] for _, v in db.sent("INSERT IGNORE INTO seat_workspace")]
        self.assertEqual(inserted, [AR, TRADE])

    def test_set_refuses_none_another_tenants_and_an_administrator(self):
        for seat, wanted in ((MEMBER_SEAT, []), (MEMBER_SEAT, [OTHER]),
                             (MEMBER_SEAT, "2"), (MEMBER_SEAT, [True]),
                             (ADMIN_SEAT, [TRADE])):
            with self.subTest(seat=seat, wanted=wanted):
                db = SeatsDb()
                with self.assertRaises(ValueError):
                    self.run_with(db, self.seats.set_workspaces, TENANT,
                                  "admin@b.c", seat, wanted)
                self.assertEqual(db.sent("DELETE"), [])
                self.assertEqual(db.sent("INSERT"), [])

    # --- inviting ---------------------------------------------------------

    def invite(self, db, role, workspaces):
        with mock.patch.object(self.seats, "listing",
                               return_value={"invitations": [], "free": 2,
                                             "bought": 5}):
            return self.run_with(db, self.seats.invite, TENANT, "admin@b.c",
                                 "new@b.c", role, workspaces)

    def test_a_members_invitation_names_its_workspaces(self):
        db = SeatsDb()
        made = self.invite(db, "member", [AR])
        self.assertEqual(made["workspaces"], [AR])
        [(_, cleared)] = db.sent("DELETE FROM seat_invitation_workspace")
        self.assertEqual(cleared["i"], 41)
        [(_, written)] = db.sent("INSERT INTO seat_invitation_workspace")
        self.assertEqual((written["i"], written["w"]), (41, AR))

    def test_a_member_must_be_given_at_least_one(self):
        for workspaces in (None, []):
            with self.subTest(workspaces=workspaces):
                db = SeatsDb()
                with self.assertRaises(ValueError):
                    self.invite(db, "member", workspaces)
                self.assertEqual(db.sent("INSERT"), [])

    def test_an_administrators_invitation_names_none(self):
        db = SeatsDb()
        made = self.invite(db, "admin", [AR])
        self.assertIsNone(made["workspaces"])
        self.assertEqual(db.sent("INSERT INTO seat_invitation_workspace"), [])

    # --- changing rights --------------------------------------------------

    def test_an_administrator_made_a_member_keeps_every_workspace(self):
        db = SeatsDb()
        self.run_with(db, self.seats.set_role, TENANT, ADMIN_SEAT, "member")
        [(insert, values)] = db.sent("INSERT IGNORE INTO seat_workspace")
        self.assertIn("FROM workspace WHERE tenant_id = :t", insert)
        self.assertEqual((values["t"], values["s"]), (TENANT, ADMIN_SEAT))

    def test_a_member_made_an_administrator_gets_nothing_written(self):
        db = SeatsDb()
        self.run_with(db, self.seats.set_role, TENANT, MEMBER_SEAT, "admin")
        self.assertEqual(db.sent("INSERT"), [])


def event(route, role="member", query=None, path=None, body=None):
    return {
        "routeKey": route,
        "pathParameters": path,
        "queryStringParameters": query,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "custom:tenant_id": str(TENANT), "custom:role": role,
            "email": "m@b.c"}}}},
    }


class DispatchTest(unittest.TestCase):
    """What the dispatcher lets a member reach."""

    def setUp(self):
        self.app = load_api()
        self.held = [{"workspace_id": TRADE, "name": "Trade Finance",
                      "active_revision": 1},
                     {"workspace_id": AR, "name": "AR FINANCING",
                      "active_revision": 1}]
        for target, value in (
                (self.app.config, "workspaces"),):
            p = mock.patch.object(target, value, return_value=self.held)
            p.start()
            self.addCleanup(p.stop)
        self.listed = []
        p = mock.patch.object(self.app, "list_engagements",
                              side_effect=lambda t, w, a: self.listed.append(w)
                              or [])
        p.start()
        self.addCleanup(p.stop)

    def dispatch(self, ev, assigned):
        with mock.patch.object(self.app.seats, "allowed_workspaces",
                               return_value=assigned):
            reply = self.app._dispatch(ev, None)
        return reply["statusCode"], json.loads(reply["body"])

    def test_unnamed_is_the_members_only_workspace(self):
        status, _ = self.dispatch(event("GET /engagements"), {AR})
        self.assertEqual(status, 200)
        self.assertEqual(self.listed, [AR])

    def test_unnamed_with_several_asks_which(self):
        status, body = self.dispatch(event("GET /engagements"), {TRADE, AR})
        self.assertEqual(status, 400)
        self.assertEqual(self.listed, [])

    def test_a_named_workspace_not_assigned_is_refused(self):
        status, body = self.dispatch(
            event("GET /engagements", query={"workspace": str(TRADE)}), {AR})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], self.app.NOT_YOUR_WORKSPACE)
        self.assertEqual(self.listed, [])

    def test_a_member_with_none_is_told_so(self):
        status, body = self.dispatch(event("GET /engagements"), set())
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], self.app.NO_WORKSPACE_ASSIGNED)

    def test_an_administrator_is_not_narrowed(self):
        status, _ = self.dispatch(
            event("GET /engagements", role="admin",
                  query={"workspace": str(TRADE)}), None)
        self.assertEqual(status, 200)
        self.assertEqual(self.listed, [TRADE])

    def memo_route(self, memo_workspace, assigned):
        def answer(statement, params=None, tx=None):
            if re.search(r"SELECT workspace_id FROM memo", statement):
                return rows((memo_workspace,))
            return rows()
        with mock.patch.object(self.app, "_sql", answer), \
                mock.patch.object(self.app, "get_memo",
                                  return_value={"memo_id": 11}) as read:
            status, _ = self.dispatch(
                event("GET /memos/{memo_id}", path={"memo_id": "11"}),
                assigned)
        return status, read

    def test_a_memo_by_number_in_another_workspace_is_not_found(self):
        status, read = self.memo_route(TRADE, {AR})
        self.assertEqual(status, 404)
        read.assert_not_called()

    def test_a_memo_by_number_in_their_own_workspace_is_read(self):
        status, read = self.memo_route(AR, {AR})
        self.assertEqual(status, 200)
        read.assert_called_once()

    def test_settings_lists_a_members_own_workspaces(self):
        with mock.patch.object(self.app, "get_settings",
                               return_value={"workspaces": [
                                   {"workspace_id": TRADE, "name": "TF"},
                                   {"workspace_id": AR, "name": "AR"}]}):
            status, body = self.dispatch(event("GET /settings"), {AR})
        self.assertEqual(status, 200)
        self.assertEqual([w["workspace_id"] for w in body["workspaces"]], [AR])

    def test_a_seat_change_naming_only_workspaces_leaves_the_role(self):
        with mock.patch.object(self.app.seats, "set_role") as role, \
                mock.patch.object(self.app.seats, "set_workspaces",
                                  return_value={"workspaces": [AR]}) as ws:
            status, body = self.dispatch(
                event("PUT /seats/{seat_id}", role="admin",
                      path={"seat_id": str(MEMBER_SEAT)},
                      body={"workspaces": [AR]}), None)
        self.assertEqual(status, 200)
        role.assert_not_called()
        ws.assert_called_once_with(TENANT, "m@b.c", str(MEMBER_SEAT), [AR])

    def test_a_seat_change_naming_only_the_role_is_as_before(self):
        with mock.patch.object(self.app.seats, "set_role",
                               return_value={"role": "admin"}) as role, \
                mock.patch.object(self.app.seats, "set_workspaces") as ws:
            self.dispatch(event("PUT /seats/{seat_id}", role="admin",
                                path={"seat_id": str(MEMBER_SEAT)},
                                body={"role": "admin"}), None)
        role.assert_called_once()
        ws.assert_not_called()

    def test_a_member_asking_for_ai_review_is_told_it_is_an_administrators(self):
        status, body = self.dispatch(event("POST /config/draft/review"), {AR})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "only an administrator may review "
                                        "the configuration")


if __name__ == "__main__":
    unittest.main()
