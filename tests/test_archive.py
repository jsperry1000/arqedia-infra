"""
Archiving puts something away. It never deletes anything (Group 14).

    python -m unittest discover -s tests

Four things are tested here, and the fourth is the one that matters:

  archiving sets a column, and records who and when;
  restoring clears the same three, so a restored row does not still read as
    archived to anybody looking at it;
  the lists leave archived items out until Show archived asks for them;
  NOTHING IS DELETED - no statement any of these issues is a DELETE, on any
    table, in any case.

Nothing reaches AWS: boto3 is replaced at import and _sql is a stub.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 7
NAME = "Meridian-Trading"
ENGAGEMENT_ID = 42
WHO = "a@firm.com"


def sent(params):
    def plain(value):
        return None if value.get("isNull") else next(iter(value.values()))
    return {p["name"]: plain(p["value"]) for p in params or []}


class Db:
    """Answers the resolve and the read-back, and keeps every statement."""

    def __init__(self, engagement=(ENGAGEMENT_ID, NAME, None, "open"),
                 memo_parent=(None,), updated=1):
        self.engagement = engagement
        self.memo_parent = memo_parent
        self.updated = updated
        self.statements = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        self.statements.append((s, sent(params)))
        if s.startswith("UPDATE"):
            return {"records": [], "numberOfRecordsUpdated": self.updated}
        if s.startswith("SELECT engagement_id, name, subject_name, status"):
            return rows(self.engagement) if self.engagement else rows()
        if s.startswith("SELECT parent_memo_id FROM memo"):
            return rows(self.memo_parent) if self.memo_parent else rows()
        return rows()

    def writes(self, prefix="UPDATE"):
        return [(s, p) for s, p in self.statements if s.startswith(prefix)]

    def all(self):
        return " | ".join(s for s, _ in self.statements)


def event(route, path=None, body=None, query=None):
    return {
        "routeKey": route,
        "pathParameters": path,
        "queryStringParameters": query,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "custom:tenant_id": str(TENANT),
            "custom:role": "member",
            "email": WHO,
        }}}},
    }


class NothingIsDeletedTest(unittest.TestCase):
    """The whole point of archiving rather than deleting."""

    def setUp(self):
        self.app = load_api()

    def every_statement(self, run):
        db = Db()
        with mock.patch.object(self.app, "_sql", db.sql):
            run(db)
        return db

    def test_archiving_an_engagement_deletes_nothing(self):
        db = self.every_statement(lambda db: self.app.set_engagement_state(
            TENANT, WHO, NAME, "archived"))
        self.assertNotIn("DELETE", db.all())
        self.assertNotIn("DROP", db.all())
        self.assertNotIn("TRUNCATE", db.all())

    def test_archiving_a_memo_deletes_nothing(self):
        db = self.every_statement(lambda db: self.app.set_memo_state(
            TENANT, WHO, 11, "archived"))
        self.assertNotIn("DELETE", db.all())

    def test_restoring_deletes_nothing(self):
        for run in (
            lambda db: self.app.set_engagement_state(TENANT, WHO, NAME, "open"),
            lambda db: self.app.set_memo_state(TENANT, WHO, 11, "live"),
        ):
            db = self.every_statement(run)
            self.assertNotIn("DELETE", db.all())

    def test_an_archived_engagement_keeps_its_documents(self):
        """Nothing touches the document table at all: the column that moves
        is on the engagement, and the documents are where they were."""
        db = self.every_statement(lambda db: self.app.set_engagement_state(
            TENANT, WHO, NAME, "archived"))
        self.assertNotIn("document", db.all())
        self.assertNotIn("extracted_value", db.all())

    def test_archiving_an_engagement_leaves_its_memoranda_alone(self):
        """13.3's decision. A memorandum may have been sent to a lender;
        tidying the matter it came out of must not withdraw it."""
        db = self.every_statement(lambda db: self.app.set_engagement_state(
            TENANT, WHO, NAME, "archived"))
        self.assertNotIn("memo", db.all())


class ArchiveEngagementTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def act(self, status, engagement=(ENGAGEMENT_ID, NAME, None, "open")):
        db = Db(engagement=engagement)
        with mock.patch.object(self.app, "_sql", db.sql):
            out = self.app.set_engagement_state(TENANT, WHO, NAME, status)
        return out, db

    def test_archiving_records_who_and_when(self):
        out, db = self.act("archived")
        self.assertEqual(out["status"], "archived")
        [(statement, params)] = db.writes()
        self.assertIn("status = 'archived'", statement)
        self.assertIn("archived_at = UTC_TIMESTAMP()", statement)
        self.assertEqual(params["who"], WHO)
        self.assertEqual(params["e"], ENGAGEMENT_ID)

    def test_restoring_clears_all_three(self):
        """A restored engagement that still said who archived it would read
        as archived to anybody looking at the row."""
        out, db = self.act(
            "open", engagement=(ENGAGEMENT_ID, NAME, None, "archived"))
        self.assertEqual(out["status"], "open")
        [(statement, _)] = db.writes()
        self.assertIn("status = 'open'", statement)
        self.assertIn("archived_by = NULL", statement)
        self.assertIn("archived_at = NULL", statement)

    def test_an_archived_one_can_still_be_found(self):
        """Resolved without regard to status, or archiving would be a
        one-way door."""
        _, db = self.act(
            "open", engagement=(ENGAGEMENT_ID, NAME, None, "archived"))
        [(resolve, _)] = [(s, p) for s, p in db.statements
                          if s.startswith("SELECT engagement_id, name")]
        self.assertNotIn("status =", resolve)

    def test_a_name_with_no_row_is_not_found(self):
        out, db = self.act("archived", engagement=None)
        self.assertIsNone(out)
        self.assertEqual(db.writes(), [])

    def test_only_two_states_are_accepted(self):
        for bad in ("deleted", "OPEN", "", None, "closed"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.act(bad)


class ArchiveMemoTest(unittest.TestCase):
    """The whole revision line moves."""

    def setUp(self):
        self.app = load_api()

    def act(self, state, memo_id=11, parent=(None,), updated=1):
        db = Db(memo_parent=parent, updated=updated)
        with mock.patch.object(self.app, "_sql", db.sql):
            out = self.app.set_memo_state(TENANT, WHO, memo_id, state)
        return out, db

    def test_archiving_a_root_takes_its_revisions(self):
        out, db = self.act("archived", memo_id=11, parent=(None,), updated=3)
        self.assertEqual(out["root_memo_id"], 11)
        self.assertEqual(out["revisions"], 3)
        [(statement, params)] = db.writes()
        self.assertIn("memo_id = :root OR parent_memo_id = :root", statement)
        self.assertEqual(params["root"], 11)

    def test_archiving_a_revision_takes_the_whole_line(self):
        """Archiving one revision and leaving its siblings would put half a
        line in the list and half out of it."""
        out, db = self.act("archived", memo_id=13, parent=(11,))
        self.assertEqual(out["root_memo_id"], 11)
        _, params = db.writes()[0]
        self.assertEqual(params["root"], 11)

    def test_restoring_clears_all_three(self):
        _, db = self.act("live")
        [(statement, _)] = db.writes()
        self.assertIn("state = 'live'", statement)
        self.assertIn("archived_by = NULL", statement)
        self.assertIn("archived_at = NULL", statement)

    def test_a_memo_that_does_not_exist_is_not_found(self):
        out, db = self.act("archived", parent=None)
        self.assertIsNone(out)
        self.assertEqual(db.writes(), [])

    def test_only_two_states_are_accepted(self):
        for bad in ("deleted", "LIVE", "", "open"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.act(bad)


class ListsLeaveArchivedOutTest(unittest.TestCase):
    """14.2, and 14.3's way back in."""

    def setUp(self):
        self.app = load_api()

    def engagements(self, include):
        db = Db()
        with mock.patch.object(self.app, "_sql", db.sql):
            self.app.list_engagements(TENANT, include)
        return db.statements[0]

    def memos(self, include):
        db = Db()
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app.config, "load",
                                  lambda t, r: mock.MagicMock()):
            self.app.list_memos(TENANT, ENGAGEMENT_ID, include)
        return db.statements[0]

    def test_the_engagement_list_asks_for_open_ones(self):
        statement, params = self.engagements(False)
        self.assertIn("(e.status = 'open' OR :include_archived)", statement)
        self.assertIs(params["include_archived"], False)

    def test_show_archived_asks_for_all_of_them(self):
        _, params = self.engagements(True)
        self.assertIs(params["include_archived"], True)

    def test_the_memo_list_asks_for_live_ones(self):
        statement, params = self.memos(False)
        self.assertIn("(state = 'live' OR :include_archived)", statement)
        self.assertIs(params["include_archived"], False)

    def test_show_archived_asks_the_memo_list_for_all(self):
        _, params = self.memos(True)
        self.assertIs(params["include_archived"], True)

    def test_the_status_travels_on_every_row(self):
        """An archived item shown unmarked is a lie, so the state has to
        reach the screen that shows it."""
        db = Db()
        with mock.patch.object(
                self.app, "_sql",
                lambda s, p=None, tx=None: rows(
                    (ENGAGEMENT_ID, NAME, None, 0, None,
                     "archived", WHO, "2026-09-22 10:00:00"))):
            [row] = self.app.list_engagements(TENANT, True)
        self.assertEqual(row["status"], "archived")
        self.assertEqual(row["archived_by"], WHO)
        self.assertEqual(row["archived_at"], "2026-09-22 10:00:00")
        del db


class AskedForArchivedTest(unittest.TestCase):
    """What the query string means. "false" is text, and all text is true in
    Python - so it is read positively rather than negatively."""

    def setUp(self):
        self.app = load_api()

    def test_the_values_a_screen_sends_when_it_is_on(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            self.assertIs(self.app._asked_for_archived({"archived": value}),
                          True, value)

    def test_everything_else_is_off(self):
        for query in ({}, None, {"archived": ""}, {"archived": "0"},
                      {"archived": "false"}, {"archived": "no"},
                      {"name": "Meridian"}):
            self.assertIs(self.app._asked_for_archived(query), False,
                          repr(query))


class RoutesTest(unittest.TestCase):
    """Both acts through the dispatcher, where a screen reaches them."""

    def setUp(self):
        self.app = load_api()

    def call(self, ev, db=None):
        db = db or Db()
        with mock.patch.object(self.app, "_sql", db.sql):
            reply = self.app._dispatch(ev, None)
        return reply, db

    def test_archiving_an_engagement(self):
        reply, db = self.call(event("PUT /engagements/{id}/state",
                                    path={"id": NAME},
                                    body={"status": "archived"}))
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(json.loads(reply["body"])["status"], "archived")
        self.assertEqual(len(db.writes()), 1)

    def test_archiving_an_engagement_that_does_not_exist_is_404(self):
        reply, db = self.call(event("PUT /engagements/{id}/state",
                                    path={"id": NAME},
                                    body={"status": "archived"}),
                              Db(engagement=None))
        self.assertEqual(reply["statusCode"], 404)
        self.assertEqual(db.writes(), [])

    def test_a_state_that_is_not_a_state_is_400(self):
        reply, _ = self.call(event("PUT /engagements/{id}/state",
                                   path={"id": NAME},
                                   body={"status": "deleted"}))
        self.assertEqual(reply["statusCode"], 400)

    def test_archiving_a_memo(self):
        reply, db = self.call(event("PUT /memos/{memo_id}/state",
                                    path={"memo_id": "11"},
                                    body={"state": "archived"}))
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(json.loads(reply["body"])["state"], "archived")
        self.assertEqual(len(db.writes()), 1)

    def test_archiving_a_memo_that_does_not_exist_is_404(self):
        reply, db = self.call(event("PUT /memos/{memo_id}/state",
                                    path={"memo_id": "99"},
                                    body={"state": "archived"}),
                              Db(memo_parent=None))
        self.assertEqual(reply["statusCode"], 404)
        self.assertEqual(db.writes(), [])

    def test_show_archived_reaches_the_engagement_list(self):
        _, db = self.call(event("GET /engagements", query={"archived": "1"}))
        [(_, params)] = [(s, p) for s, p in db.statements
                         if "FROM engagement e" in s]
        self.assertIs(params["include_archived"], True)

    def test_the_engagement_list_leaves_them_out_by_default(self):
        _, db = self.call(event("GET /engagements"))
        [(_, params)] = [(s, p) for s, p in db.statements
                         if "FROM engagement e" in s]
        self.assertIs(params["include_archived"], False)

    def test_show_archived_reaches_the_memo_list(self):
        with mock.patch.object(self.app.config, "load",
                               lambda t, r: mock.MagicMock()):
            _, db = self.call(event("GET /engagements/{id}/memos",
                                    path={"id": NAME},
                                    query={"archived": "1"}))
        [(_, params)] = [(s, p) for s, p in db.statements if "FROM memo" in s]
        self.assertIs(params["include_archived"], True)


class ArchivedMemoStillOpensTest(unittest.TestCase):
    """GET /memos/{id} ignores state, deliberately.

    A link to a memorandum is a link to a document somebody may have been
    sent. Archiving is about lists, not about access."""

    def setUp(self):
        self.app = load_api()

    def test_the_memo_read_does_not_filter_on_state(self):
        asked = {}

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            if "FROM memo WHERE" in s:
                asked["memo"] = s
                return rows(("curated", "k.md", "2026-03-04 10:00:00",
                             WHO, None, None, 1, None, None))
            return rows()

        with mock.patch.object(self.app, "_sql", sql), \
                mock.patch.object(self.app, "_s3") as s3:
            s3.get_object.return_value = {
                "Body": mock.MagicMock(read=lambda: b"# A memo\n")}
            out = self.app.get_memo(TENANT, 11)

        self.assertEqual(out["memo_id"], 11)
        self.assertNotIn("state", asked["memo"])


if __name__ == "__main__":
    unittest.main()
