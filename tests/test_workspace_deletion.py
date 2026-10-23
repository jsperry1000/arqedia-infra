"""
Deleting a workspace, and restoring one (PACK-02 D, settled 23 October 2026).
Run from the repository root:

    python -m unittest discover -s tests

THE CONTRACT.
  - Administrators only, and never the ARQEDIA workspace's offerings.
  - The last workspace cannot be deleted.
  - Deleting takes the name typed exactly and an emailed code: fifteen
    minutes, five tries, one a minute.
  - Members who see only this workspace move to one the administrator names;
    without one, nothing is deleted.
  - Members move, shares are suspended, and only then is the workspace hidden
    and the code spent - each step safe to run again.
  - Restoring lifts the suspension and unhides it, before its date and where
    the plan has room.

Nothing reaches AWS: boto3 is replaced, _sql is a fake that answers by
statement, and share and mail are stand-ins.
"""

import re
import sys
import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 7
WS = 3
OTHER = 9
ADMIN = "a@firm.com"


def plain(value):
    return None if value.get("isNull") else next(iter(value.values()))


class FakeDb:
    def __init__(self, name="Real Estate", deleted=False, restorable=True,
                 recent=0, code_row=None, seats=(), invitations=(),
                 other_live=True):
        self.name = name
        self.deleted = deleted
        self.restorable = restorable
        self.recent = recent
        self.code_row = code_row        # (deletion_id, hash, tries, valid)
        self.seats = list(seats)        # (seat_id, email)
        self.invitations = list(invitations)
        self.other_live = other_live
        self.done = []                  # (statement, values), writes only

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        v = {p["name"]: plain(p["value"]) for p in params or []}
        if s.startswith(("INSERT", "UPDATE")):
            self.done.append((s, v))
        if s.startswith("SELECT workspace_id, name, deleted_at") and \
                "AND workspace_id = :w" in s:
            if v["w"] == WS:
                return rows((WS, self.name,
                             "2026-10-23 10:00:00" if self.deleted else None,
                             ADMIN if self.deleted else None,
                             "2027-04-23 10:00:00" if self.deleted else None,
                             self.restorable if self.deleted else None))
            if v["w"] == OTHER and self.other_live:
                return rows((OTHER, "Trade Finance", None, None, None, None))
            return rows()
        if s.startswith("SELECT COUNT(*) FROM workspace_deletion"):
            return rows((self.recent,))
        if s.startswith("SELECT deletion_id, code_hash"):
            return rows(self.code_row) if self.code_row else rows()
        if "FROM seat s" in s:
            return rows(*self.seats)
        if "FROM seat_invitation i" in s:
            return rows(*self.invitations)
        return rows()

    def wrote(self, pattern):
        return [v for s, v in self.done if re.search(pattern, s)]


class DeletionTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()
        self.ws = self.app.workspaces
        self.share = mock.MagicMock()
        self.share.suspend_workspace.return_value = 2
        self.share.lift_workspace.return_value = 2
        self.share.live_count.return_value = 2
        patches = [
            mock.patch.dict(sys.modules, {"share": self.share}),
            mock.patch.object(self.ws.billing, "workspaces_held",
                              return_value=2),
            mock.patch.object(self.ws.billing, "require_workspace_room"),
            mock.patch.object(self.ws.mail, "send", return_value=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def use(self, db):
        return mock.patch.object(self.ws, "_sql", db.sql)

    def good_code(self, code="123456", tries=0, valid=True):
        return (41, self.ws._hash(TENANT, WS, code), tries, valid)

    def delete(self, db, **body):
        body = dict({"name": "Real Estate", "code": "123456"}, **body)
        with self.use(db):
            return self.ws.delete(TENANT, ADMIN, "admin", WS, body)

    # --- who --------------------------------------------------------------

    def test_a_member_may_not(self):
        with self.use(FakeDb()):
            with self.assertRaises(PermissionError):
                self.ws.request_code(TENANT, ADMIN, "member", WS)
            with self.assertRaises(PermissionError):
                self.ws.restore(TENANT, ADMIN, "member", WS)

    def test_an_offering_is_not_deleted_here(self):
        with self.use(FakeDb()):
            with self.assertRaises(PermissionError):
                self.ws.request_code(0, ADMIN, "admin", WS)

    def test_another_tenants_number_is_not_found(self):
        with self.use(FakeDb()):
            self.assertIsNone(self.ws.request_code(TENANT, ADMIN, "admin", 55))

    def test_the_last_workspace_cannot_be_deleted(self):
        self.ws.billing.workspaces_held.return_value = 1
        with self.use(FakeDb()):
            with self.assertRaises(self.ws.Refused) as raised:
                self.ws.request_code(TENANT, ADMIN, "admin", WS)
        self.assertIn("only workspace", str(raised.exception))

    # --- the code ---------------------------------------------------------

    def test_a_code_is_stored_hashed_and_emailed(self):
        db = FakeDb()
        with self.use(db):
            out = self.ws.request_code(TENANT, ADMIN, "admin", WS)
        self.assertTrue(out["sent"])
        [stored] = db.wrote(r"^INSERT INTO workspace_deletion")
        to, subject, body = self.ws.mail.send.call_args.args
        self.assertEqual(to, ADMIN)
        code = re.search(r"The code is: (\d{6})", body).group(1)
        self.assertEqual(stored["h"], self.ws._hash(TENANT, WS, code))
        self.assertNotIn(code, stored["h"])

    def test_one_code_a_minute(self):
        db = FakeDb(recent=1)
        with self.use(db):
            with self.assertRaises(self.ws.Refused):
                self.ws.request_code(TENANT, ADMIN, "admin", WS)
        self.assertEqual(db.wrote(r"^INSERT"), [])
        self.ws.mail.send.assert_not_called()

    # --- deleting ---------------------------------------------------------

    def test_the_name_must_be_typed_exactly(self):
        db = FakeDb(code_row=self.good_code())
        with self.assertRaises(ValueError):
            self.delete(db, name="real estate")
        self.assertEqual(db.wrote(r"^UPDATE workspace SET"), [])

    def test_no_code_asked_for(self):
        db = FakeDb()
        with self.assertRaises(ValueError):
            self.delete(db)

    def test_a_wrong_code_is_counted_and_deletes_nothing(self):
        db = FakeDb(code_row=self.good_code())
        with self.assertRaises(ValueError):
            self.delete(db, code="000000")
        self.assertEqual(len(db.wrote(r"SET tries = tries \+ 1")), 1)
        self.assertEqual(db.wrote(r"^UPDATE workspace SET"), [])
        self.share.suspend_workspace.assert_not_called()

    def test_an_expired_or_overtried_code_is_refused(self):
        for row in (self.good_code(valid=False), self.good_code(tries=5)):
            db = FakeDb(code_row=row)
            with self.subTest(row=row[2:]):
                with self.assertRaises(ValueError):
                    self.delete(db)
                self.assertEqual(db.wrote(r"^UPDATE workspace SET"), [])

    def test_deleting_suspends_then_hides_and_spends_the_code(self):
        db = FakeDb(code_row=self.good_code())
        order = []
        self.share.suspend_workspace.side_effect = \
            lambda *a: order.append("suspend") or 2
        real = db.sql

        def sql(statement, params=None):
            if statement.lstrip().startswith("UPDATE workspace SET"):
                order.append("hide")
            return real(statement, params)
        with mock.patch.object(self.ws, "_sql", sql):
            out = self.ws.delete(TENANT, ADMIN, "admin", WS,
                                 {"name": "Real Estate", "code": "123456"})
        self.assertEqual(order, ["suspend", "hide"])
        [hidden] = db.wrote(r"^UPDATE workspace SET deleted_at = NOW\(\)")
        self.assertEqual((hidden["by"], hidden["w"]), (ADMIN, WS))
        self.assertTrue(db.wrote(r"^UPDATE workspace_deletion SET deleted_at"))
        self.assertEqual(out["shares_suspended"], 2)
        self.assertIsNone(out["members_moved_to"])

    def test_six_months_is_written_when_it_is_deleted(self):
        db = FakeDb(code_row=self.good_code())
        self.delete(db)
        [s] = [s for s, _ in db.done
               if s.startswith("UPDATE workspace SET deleted_at")]
        self.assertIn("INTERVAL 6 MONTH", s)

    # --- members ----------------------------------------------------------

    def test_members_seeing_only_this_must_be_given_somewhere(self):
        db = FakeDb(code_row=self.good_code(), seats=[(8, "m@firm.com")])
        with self.assertRaises(self.ws.Refused) as raised:
            self.delete(db)
        self.assertIn("m@firm.com sees only this workspace",
                      str(raised.exception))
        self.assertEqual(db.wrote(r"^UPDATE workspace SET"), [])
        self.share.suspend_workspace.assert_not_called()

    def test_they_move_where_the_administrator_says(self):
        db = FakeDb(code_row=self.good_code(), seats=[(8, "m@firm.com")],
                    invitations=[(5, "new@firm.com")])
        out = self.delete(db, move_members_to=OTHER)
        [seat] = db.wrote(r"^INSERT IGNORE INTO seat_workspace")
        self.assertEqual((seat["s"], seat["w"]), (8, OTHER))
        [inv] = db.wrote(r"^INSERT IGNORE INTO seat_invitation_workspace")
        self.assertEqual((inv["i"], inv["w"]), (5, OTHER))
        self.assertEqual(out["members_moved"], ["m@firm.com"])
        self.assertEqual(out["members_moved_to"], OTHER)

    def test_not_to_the_workspace_being_deleted(self):
        db = FakeDb(code_row=self.good_code(), seats=[(8, "m@firm.com")])
        with self.assertRaises(ValueError):
            self.delete(db, move_members_to=WS)
        self.assertEqual(db.wrote(r"^INSERT IGNORE"), [])

    def test_an_already_deleted_workspace_is_not_deleted_again(self):
        db = FakeDb(deleted=True, code_row=self.good_code())
        with self.assertRaises(self.ws.Refused):
            self.delete(db)

    # --- restoring --------------------------------------------------------

    def test_restoring_lifts_then_unhides(self):
        db = FakeDb(deleted=True)
        with self.use(db):
            out = self.ws.restore(TENANT, ADMIN, "admin", WS)
        self.share.lift_workspace.assert_called_once_with(TENANT, WS)
        [shown] = db.wrote(r"^UPDATE workspace SET deleted_at = NULL")
        self.assertEqual(shown["w"], WS)
        [recorded] = db.wrote(r"^UPDATE workspace_deletion SET restored_at")
        self.assertEqual(recorded["by"], ADMIN)
        self.assertEqual(out["shares_restored"], 2)

    def test_not_after_its_date(self):
        db = FakeDb(deleted=True, restorable=False)
        with self.use(db):
            with self.assertRaises(self.ws.Refused):
                self.ws.restore(TENANT, ADMIN, "admin", WS)
        self.share.lift_workspace.assert_not_called()

    def test_not_without_room_on_the_plan(self):
        self.ws.billing.require_workspace_room.side_effect = \
            self.ws.billing.Refused("full")
        db = FakeDb(deleted=True)
        with self.use(db):
            with self.assertRaises(self.ws.Refused) as raised:
                self.ws.restore(TENANT, ADMIN, "admin", WS)
        self.assertIn("no room", str(raised.exception))
        self.share.lift_workspace.assert_not_called()

    def test_a_live_workspace_is_not_restored(self):
        with self.use(FakeDb()):
            with self.assertRaises(self.ws.Refused):
                self.ws.restore(TENANT, ADMIN, "admin", WS)


class RouteTest(unittest.TestCase):
    """The four routes reach workspaces.py with the token's tenant, and its
    refusals come back as the API's."""

    def setUp(self):
        self.app = load_api()

    def dispatch(self, route, path=None, body=None, role="admin"):
        import json
        ev = {"routeKey": route, "pathParameters": path,
              "queryStringParameters": None,
              "body": json.dumps(body) if body is not None else None,
              "requestContext": {"authorizer": {"jwt": {"claims": {
                  "custom:tenant_id": str(TENANT), "custom:role": role,
                  "email": ADMIN}}}}}
        reply = self.app._dispatch(ev, None)
        return reply["statusCode"], json.loads(reply["body"])

    def test_delete_takes_the_body_and_the_path(self):
        with mock.patch.object(self.app.workspaces, "delete",
                               return_value={"workspace_id": WS}) as d:
            status, _ = self.dispatch(
                "POST /workspaces/{workspace_id}/delete",
                path={"workspace_id": str(WS)},
                body={"name": "Real Estate", "code": "1"})
        self.assertEqual(status, 200)
        d.assert_called_once_with(TENANT, ADMIN, "admin", str(WS),
                                  {"name": "Real Estate", "code": "1"})

    def test_not_found_is_404_and_refused_is_409(self):
        with mock.patch.object(self.app.workspaces, "restore",
                               return_value=None):
            status, _ = self.dispatch(
                "POST /workspaces/{workspace_id}/restore",
                path={"workspace_id": "55"})
        self.assertEqual(status, 404)
        with mock.patch.object(self.app.workspaces, "restore",
                               side_effect=self.app.workspaces.Refused("no")):
            status, body = self.dispatch(
                "POST /workspaces/{workspace_id}/restore",
                path={"workspace_id": str(WS)})
        self.assertEqual((status, body["error"]), (409, "no"))

    def test_a_member_is_refused(self):
        status, _ = self.dispatch("GET /workspaces", role="member")
        self.assertEqual(status, 403)

    def test_the_routes_are_in_terraform(self):
        from api_modules import ROOT
        tf = (ROOT / "api.tf").read_text(encoding="utf-8")
        for route in ("GET /workspaces",
                      "POST /workspaces/{workspace_id}/delete/code",
                      "POST /workspaces/{workspace_id}/delete",
                      "POST /workspaces/{workspace_id}/restore"):
            self.assertIn('"%s"' % route, tf)


class HiddenTest(unittest.TestCase):
    """Where a deleted workspace is hidden: every list and lookup (config),
    the plan's count (billing), and which workspaces a member works in or may
    be given (seats). The rows that assign it are kept, so a restore gives
    back the access there was."""

    def setUp(self):
        self.app = load_api()

    def statements(self, module, call):
        seen = []

        def sql(statement, params=None, tx=None):
            seen.append(" ".join(statement.split()))
            return rows()
        with mock.patch.object(module, "_sql", sql):
            try:
                call()
            except ValueError:
                pass
        return seen

    def test_config_lists_live_workspaces_only(self):
        [s] = self.statements(self.app.config,
                              lambda: self.app.config.workspaces(TENANT))
        self.assertIn("deleted_at IS NULL", s)

    def test_the_plan_counts_live_workspaces_only(self):
        [s] = self.statements(self.app.billing,
                              lambda: self.app.billing.workspaces_held(TENANT))
        self.assertIn("deleted_at IS NULL", s)

    def test_a_member_works_in_live_workspaces_only(self):
        [s] = self.statements(self.app.seats,
                              lambda: self.app.seats.allowed_workspaces(
                                  TENANT, "m@firm.com", "member"))
        self.assertIn("deleted_at IS NULL", s)

    def test_changing_a_members_workspaces_keeps_a_hidden_ones_row(self):
        seats = self.app.seats
        seen = []

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            seen.append(s)
            if s.startswith("SELECT role FROM seat"):
                return rows(("member",))
            if s.startswith("SELECT workspace_id FROM workspace"):
                return rows((OTHER,))
            return rows()
        with mock.patch.object(seats, "_sql", sql):
            seats.set_workspaces(TENANT, ADMIN, 8, [OTHER])
        [delete] = [s for s in seen if s.startswith("DELETE")]
        self.assertIn("deleted_at IS NULL", delete)


class SuspendedShareTest(unittest.TestCase):
    """The viewer refuses a suspended grant, as it refuses a revoked one."""

    def test_a_suspended_grant_is_refused(self):
        from api_modules import SHARED
        sys.path.insert(0, str(SHARED))
        try:
            sys.modules.pop("share_rules", None)
            import share_rules as rules
        finally:
            sys.path.remove(str(SHARED))
        grant = {"link_token": "t", "status": rules.ACTIVE,
                 "expires_at": "2099-01-01T00:00:00Z"}
        self.assertIsNone(rules.refusal(grant, rules.now(), token="t"))
        self.assertEqual(rules.refusal(dict(grant, suspended=True),
                                       rules.now(), token="t"), "suspended")


if __name__ == "__main__":
    unittest.main()
