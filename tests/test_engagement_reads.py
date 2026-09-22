"""
The reads ask the engagement column, not the storage key (13.3 stage 4).

    python -m unittest discover -s tests

Stage 2 taught four writers the new columns while every list went on matching
s3_key. This is the other half: the five reads take an engagement_id, the
routes keep the name in the address, and one function turns one into the
other.

WHAT THESE ARE ABOUT. Not the SQL's prose - the statement each read issues and
the parameters it sends, because that is where the old behaviour lived. A test
asserting only the returned dictionary would have passed unchanged through
this entire switch.

Nothing reaches AWS: boto3 is replaced at import and _sql is a stub.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 7
NAME = "Meridian-Trading"
TYPED = "Meridian Trading"
ENGAGEMENT_ID = 42
SUBJECT = "Meridian Trading Ltd"


def sent(params):
    def plain(value):
        return None if value.get("isNull") else next(iter(value.values()))
    return {p["name"]: plain(p["value"]) for p in params or []}


class Recorder:
    """Answers whatever the statement asks for, and keeps every statement."""

    def __init__(self, engagement=(ENGAGEMENT_ID, NAME, SUBJECT, "open"),
                 listed=(), documents=(), memos=()):
        self.engagement = engagement
        self.listed = listed
        self.documents = documents
        self.memos = memos
        self.statements = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        self.statements.append((s, sent(params)))

        if s.startswith("SELECT engagement_id, name, subject_name, status"):
            return rows(self.engagement) if self.engagement else rows()
        if "FROM engagement e" in s:
            return rows(*self.listed)
        if "FROM memo" in s:
            return rows(*self.memos)
        return rows(*self.documents)

    def asked(self, fragment):
        """The one statement containing this fragment, and its parameters."""
        found = [(s, p) for s, p in self.statements if fragment in s]
        assert len(found) == 1, "%d statements match %r" % (len(found),
                                                            fragment)
        return found[0]

    def every_statement(self):
        return " | ".join(s for s, _ in self.statements)


def event(route, engagement=NAME):
    return {
        "routeKey": route,
        "pathParameters": {"id": engagement},
        "queryStringParameters": None,
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "custom:tenant_id": str(TENANT),
            "custom:role": "admin",
            "email": "a@firm.com",
        }}}},
    }


class ResolveTest(unittest.TestCase):
    """One place turns a name into a row."""

    def setUp(self):
        self.app = load_api()

    def resolve(self, db, name=NAME):
        with mock.patch.object(self.app, "_sql", db.sql):
            return self.app.engagement_named(TENANT, name)

    def test_it_finds_the_row(self):
        db = Recorder()
        found = self.resolve(db)
        self.assertEqual(found["engagement_id"], ENGAGEMENT_ID)
        self.assertEqual(found["engagement"], NAME)
        self.assertEqual(found["subject_name"], SUBJECT)

    def test_it_resolves_by_the_cleaned_name(self):
        """The row carries the cleaned name, because upload_url cleans before
        creating it. A lookup on the raw path parameter misses every name
        somebody typed with a space in it - which is 17.3 again."""
        db = Recorder()
        self.resolve(db, TYPED)
        _, params = db.asked("FROM engagement WHERE")
        self.assertEqual(params["n"], NAME)

    def test_a_name_with_no_row_is_none(self):
        self.assertIsNone(self.resolve(Recorder(engagement=None)))

    def test_it_never_creates(self):
        """engagement_id() creates, because uploading into a new name is how
        an engagement begins. A read must not, or every typo opens one."""
        db = Recorder(engagement=None)
        self.resolve(db)
        self.assertNotIn("INSERT", db.every_statement())

    def test_a_null_subject_is_no_subject(self):
        db = Recorder(engagement=(ENGAGEMENT_ID, NAME, None, "open"))
        self.assertIsNone(self.resolve(db)["subject_name"])


class ListEngagementsTest(unittest.TestCase):
    """From the engagement table, so an engagement exists whether or not a
    file does."""

    def setUp(self):
        self.app = load_api()

    def listing(self, *listed):
        db = Recorder(listed=listed)
        with mock.patch.object(self.app, "_sql", db.sql):
            return self.app.list_engagements(TENANT), db

    def test_an_engagement_with_no_documents_appears(self):
        """THE POINT OF STAGE 4 FOR THIS READ. The old list grouped document
        keys, so an engagement existed only as long as a file did: naming a
        subject and then thinking better of the first upload left a row
        nothing would ever show."""
        [row], _ = self.listing(
            (51, "Brand-New", None, 0, None, "open", None, None))
        self.assertEqual(row["engagement"], "Brand-New")
        self.assertEqual(row["documents"], 0)
        self.assertIsNone(row["last_activity"])

    def test_it_reads_the_engagement_table_and_not_the_keys(self):
        _, db = self.listing()
        statement, _ = db.asked("FROM engagement e")
        self.assertIn("LEFT JOIN document d", statement)
        self.assertIn("d.engagement_id = e.engagement_id", statement)
        self.assertNotIn("s3_key", statement)
        self.assertNotIn("SUBSTRING_INDEX", statement)

    def test_only_open_engagements_are_listed(self):
        """Archiving is a decision on the row, not a deletion."""
        _, db = self.listing()
        statement, _ = db.asked("FROM engagement e")
        self.assertIn("e.status = 'open'", statement)

    def test_the_count_is_of_documents_not_of_rows(self):
        """COUNT(*) over a LEFT JOIN counts the engagement's own row and
        reports one document where there are none."""
        _, db = self.listing()
        statement, _ = db.asked("FROM engagement e")
        self.assertIn("COUNT(d.document_id)", statement)
        self.assertNotIn("COUNT(*)", statement)

    def test_a_new_engagement_sorts_by_when_it_was_opened(self):
        """MAX() of no documents is NULL, which MySQL sorts last in DESC -
        so the engagement somebody just opened would appear at the bottom."""
        _, db = self.listing()
        statement, _ = db.asked("FROM engagement e")
        self.assertIn("ORDER BY COALESCE(MAX(d.filed_at), e.created_at) DESC",
                      statement)

    def test_every_field_the_screen_reads(self):
        [row], _ = self.listing(
            (ENGAGEMENT_ID, NAME, SUBJECT, 3, "2026-09-21 10:00:00",
             "open", None, None))
        self.assertEqual(row, {
            "engagement_id": ENGAGEMENT_ID,
            "engagement": NAME,
            "subject_name": SUBJECT,
            "documents": 3,
            "last_activity": "2026-09-21 10:00:00",
            # Group 14. Carried so the list can mark an archived one rather
            # than mixing it in unannounced.
            "status": "open",
            "archived_by": None,
            "archived_at": None,
        })


class ByEngagementIdTest(unittest.TestCase):
    """The three per-engagement reads, each asking the column."""

    def setUp(self):
        self.app = load_api()

    def run_read(self, which, *records):
        db = Recorder(documents=records, memos=records)
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app.config, "load",
                                  lambda t, r: mock.MagicMock()):
            out = which(TENANT, ENGAGEMENT_ID)
        return out, db

    def test_pending_asks_the_column(self):
        _, db = self.run_read(self.app.list_pending)
        statement, params = db.asked("FROM document")
        self.assertIn("engagement_id = :engagement_id", statement)
        self.assertNotIn("LIKE", statement)
        self.assertEqual(params["engagement_id"], ENGAGEMENT_ID)
        # Unchanged: what makes a document pending.
        self.assertIn("state IN ('analysed', 'reading', 'unreadable')",
                      statement)

    def test_documents_asks_the_column(self):
        _, db = self.run_read(self.app.list_documents)
        statement, params = db.asked("FROM document d")
        self.assertIn("engagement_id = :engagement_id", statement)
        self.assertNotIn("LIKE", statement)
        self.assertEqual(params["engagement_id"], ENGAGEMENT_ID)
        self.assertIn("state IN ('filed', 'reading')", statement)

    def test_memos_asks_the_column_and_only_live_ones(self):
        _, db = self.run_read(self.app.list_memos)
        statement, params = db.asked("FROM memo")
        self.assertIn("engagement_id = :engagement_id", statement)
        self.assertIn("state = 'live'", statement)
        self.assertNotIn("LIKE", statement)
        self.assertEqual(params["engagement_id"], ENGAGEMENT_ID)

    def test_an_engagement_with_no_documents_reads_as_empty(self):
        """Empty is a real answer for an engagement that exists. It is the
        answer for a name that does NOT exist that must be different, and
        the route is what makes it so - see NoSuchEngagementTest."""
        pending, _ = self.run_read(self.app.list_pending)
        self.assertEqual(pending, [])
        documents, _ = self.run_read(self.app.list_documents)
        self.assertEqual(documents, [])


class NoSuchEngagementTest(unittest.TestCase):
    """A name that resolves to no row is 404, never an empty list."""

    def setUp(self):
        self.app = load_api()

    def call(self, route, engagement=NAME):
        db = Recorder(engagement=None)
        with mock.patch.object(self.app, "_sql", db.sql):
            reply = self.app._dispatch(event(route, engagement), None)
        return reply, db

    def test_pending_is_404(self):
        reply, _ = self.call("GET /engagements/{id}/pending")
        self.assertEqual(reply["statusCode"], 404)
        self.assertIn(NAME, json.loads(reply["body"])["error"])

    def test_documents_is_404(self):
        reply, _ = self.call("GET /engagements/{id}/documents")
        self.assertEqual(reply["statusCode"], 404)

    def test_memos_is_404(self):
        reply, _ = self.call("GET /engagements/{id}/memos")
        self.assertEqual(reply["statusCode"], 404)

    def test_nothing_is_read_after_the_refusal(self):
        """The refusal comes before the list, so a 404 costs one query."""
        _, db = self.call("GET /engagements/{id}/documents")
        self.assertEqual(len(db.statements), 1)

    def test_an_engagement_that_exists_is_not_404(self):
        db = Recorder()
        with mock.patch.object(self.app, "_sql", db.sql):
            reply = self.app._dispatch(
                event("GET /engagements/{id}/documents"), None)
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(json.loads(reply["body"])["documents"], [])


class PendingCarriesTheSubjectTest(unittest.TestCase):
    """The subject comes off the row the route already resolved."""

    def setUp(self):
        self.app = load_api()

    def test_it_is_returned_with_the_pending_list(self):
        db = Recorder()
        with mock.patch.object(self.app, "_sql", db.sql):
            reply = self.app._dispatch(
                event("GET /engagements/{id}/pending"), None)
        body = json.loads(reply["body"])
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(body["subject_name"], SUBJECT)

    def test_it_costs_no_second_lookup(self):
        """It used to: engagement_subject ran its own SELECT beside the
        list. One resolve now answers both."""
        db = Recorder()
        with mock.patch.object(self.app, "_sql", db.sql):
            self.app._dispatch(event("GET /engagements/{id}/pending"), None)
        resolves = [s for s, _ in db.statements
                    if "FROM engagement WHERE" in s]
        self.assertEqual(len(resolves), 1)


class OpenEngagementTest(unittest.TestCase):
    """Opening one from the form creates its row.

    The reads answer 404 for a name with no row, which is right for an
    address typed wrongly and wrong for the form that opens a new
    engagement. Before stage 4 the reads grepped storage keys and answered
    an empty list for any name at all, so the form could navigate and the
    screen opened onto nothing."""

    def setUp(self):
        self.app = load_api()

    class Db:
        """The resolve, then engagement_id's find-insert-find."""

        def __init__(self, exists=False):
            self.exists = exists
            self.statements = []

        def sql(self, statement, params=None, tx=None):
            s = " ".join(statement.split())
            self.statements.append((s, sent(params)))
            if s.startswith("INSERT INTO engagement"):
                self.exists = True
                return {"records": []}
            if s.startswith("SELECT engagement_id, name, subject_name, status"):
                return rows((ENGAGEMENT_ID, NAME, None, "open")) \
                    if self.exists else rows()
            if s.startswith("SELECT engagement_id FROM engagement"):
                return rows((ENGAGEMENT_ID,)) if self.exists else rows()
            return rows()

        def kinds(self):
            return [s.split(" ", 2)[0] + " " + s.split(" ", 2)[1]
                    for s, _ in self.statements]

    def open(self, name=NAME, exists=False):
        db = self.Db(exists=exists)
        with mock.patch.object(self.app, "_sql", db.sql):
            out = self.app.open_engagement(TENANT, "a@firm.com", name)
        return out, db

    def test_a_new_name_is_created(self):
        out, db = self.open()
        self.assertTrue(out["created"])
        self.assertEqual(out["engagement"], NAME)
        self.assertEqual(out["engagement_id"], ENGAGEMENT_ID)
        self.assertIsNone(out["subject_name"])
        self.assertIn("INSERT INTO", db.kinds())

    def test_it_is_stored_under_the_cleaned_name(self):
        """The row carries the cleaned name, and the caller navigates to
        what comes back - so the address and the row agree from the first
        moment rather than from the first upload (17.3)."""
        out, db = self.open(TYPED)
        self.assertEqual(out["engagement"], NAME)
        inserted = [p for s, p in db.statements if s.startswith("INSERT")]
        self.assertEqual(inserted[0]["n"], NAME)

    def test_opening_one_that_exists_creates_nothing(self):
        """Idempotent, because one name is one row. Opening the same name
        twice must not mint a second."""
        out, db = self.open(exists=True)
        self.assertFalse(out["created"])
        self.assertEqual(out["engagement_id"], ENGAGEMENT_ID)
        self.assertNotIn("INSERT INTO", db.kinds())

    def test_it_reuses_the_rule_uploads_uses(self):
        """engagement_id() is the one place a name becomes a row when it has
        to exist. A second create here would be a second rule."""
        _, db = self.open()
        self.assertTrue(any(
            s.startswith("INSERT INTO engagement (tenant_id, name, created_by)")
            for s, _ in db.statements))

    def test_a_name_that_cleans_to_nothing_is_refused(self):
        for typed in ("", "   ", "...", "---"):
            with self.assertRaises(ValueError, msg=typed):
                self.open(typed)

    def test_the_route_answers_201_with_the_stored_name(self):
        db = self.Db()
        ev = event("POST /engagements")
        ev["pathParameters"] = None
        ev["body"] = json.dumps({"engagement": TYPED})
        with mock.patch.object(self.app, "_sql", db.sql):
            reply = self.app._dispatch(ev, None)
        self.assertEqual(reply["statusCode"], 201)
        self.assertEqual(json.loads(reply["body"])["engagement"], NAME)

    def test_a_typed_address_for_a_name_never_opened_is_still_404(self):
        """Creating on OPEN must not make every read create. A bookmark for
        an engagement that does not exist stays a 404."""
        db = Recorder(engagement=None)
        with mock.patch.object(self.app, "_sql", db.sql):
            reply = self.app._dispatch(
                event("GET /engagements/{id}/documents", "Never-Opened"), None)
        self.assertEqual(reply["statusCode"], 404)
        self.assertNotIn("INSERT", db.every_statement())


class GenerateTest(unittest.TestCase):
    """Composition is told which engagement by id, and is not charged for a
    name that does not exist."""

    def setUp(self):
        self.app = load_api()

    def generate(self, engagement_row):
        db = Recorder(engagement=engagement_row)
        registry = mock.MagicMock()
        registry.TEMPLATE_KEY = "credit-memo"
        registry.has_template.return_value = True
        registry.label_for_template.return_value = "Credit Memorandum"

        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app.config, "for_tenant",
                                  lambda t: registry), \
                mock.patch.object(self.app.wallet, "charge") as charge, \
                mock.patch.object(self.app, "_lambda") as invoked:
            try:
                out = self.app.generate(TENANT, "a@firm.com", NAME,
                                        "credit-memo", "key-1")
                error = None
            except ValueError as exc:
                out, error = None, str(exc)
        return out, error, charge, invoked

    def test_the_payload_carries_the_engagement_id(self):
        _, _, _, invoked = self.generate(
            (ENGAGEMENT_ID, NAME, SUBJECT, "open"))
        payload = json.loads(invoked.invoke.call_args.kwargs["Payload"])
        self.assertEqual(payload["engagement_id"], ENGAGEMENT_ID)
        # The name travels too: the memo's storage key is built from it.
        self.assertEqual(payload["engagement"], NAME)

    def test_a_name_with_no_row_is_refused_before_the_charge(self):
        """An engagement that does not exist must not take a dollar on its
        way to failing - the same rule the template check follows."""
        out, error, charge, invoked = self.generate(None)
        self.assertIsNone(out)
        self.assertIn(NAME, error)
        charge.assert_not_called()
        invoked.invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
