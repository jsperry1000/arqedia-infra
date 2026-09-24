"""
The type chosen for a document while it waits, and filing with it (21.1).
Run from the repository root:

    python -m unittest discover -s tests

THE BUG. The types a person chose while categorising lived in the browser
until File was pressed. Leaving to top up threw every one away, and on dev a
batch of 57 took a quarter of an hour to categorise.

THE CONTRACT.
  - PUT /documents/{document_id}/type writes document.chosen_type, and never
    document_type, which holds the proposal.
  - "" is a choice of "Not classified"; NULL is nobody has chosen.
  - Only a document waiting to be filed can be given a type, and only one of
    the workspace's own types.
  - The pending list carries chosen_type.
  - Filing uses the decision's type where it names one, else the chosen
    type, else the proposal - and files only the decisions it is sent.

Nothing reaches AWS: _sql is patched and config is replaced. This tests what
the handler decides; the SQL itself is unverified until it runs against dev
with migration 034 applied.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 7
DOC = 41
ENGAGEMENT = "Meridian"


def event(route, doc=DOC, body=None):
    return {
        "routeKey": route,
        "pathParameters": {"document_id": str(doc)},
        "body": json.dumps(body or {}),
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "custom:tenant_id": str(TENANT), "email": "clerk@firm.com",
            "custom:role": "member"}}}},
    }


def plain(value):
    return None if value.get("isNull") else next(iter(value.values()))


class Db:
    """Documents by id: state, chosen_type, proposal (document_type)."""

    def __init__(self, docs=None, subject="Meridian Holdings Ltd"):
        self.docs = dict({DOC: ("analysed", None, "invoice")}
                         if docs is None else docs)
        self.subject = subject
        self.ran = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        values = {p["name"]: plain(p["value"]) for p in params or []}
        self.ran.append((s, values))

        if s.startswith("SELECT state FROM document"):
            doc = self.docs.get(values["d"])
            return rows((doc[0],)) if doc else rows()
        if s.startswith("SELECT subject_name FROM engagement"):
            return rows((self.subject,))
        if s.startswith("SELECT document_id, filename, state, chosen_type"):
            return rows(*[(d, "file-%d.pdf" % d, st, chosen, proposal)
                          for d, (st, chosen, proposal) in self.docs.items()])
        if s.startswith("SELECT s3_key, thin_text, page_from, part_index"):
            return rows(("tenants/7/docs/Meridian/file.pdf", False, None, None))
        return rows()

    def writes(self, prefix):
        return [(s, v) for s, v in self.ran if s.startswith(prefix)]


def registry_with(*type_keys):
    reg = mock.MagicMock()
    reg.DOCUMENT_TYPES = {k: {} for k in type_keys}
    reg.always_ocr.return_value = False
    return reg


class ChooseTypeTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def choose(self, type_key, db=None, types=("invoice", "bank_statement")):
        db = db or Db()
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "config") as config:
            config.for_tenant.return_value = registry_with(*types)
            reply = self.app._dispatch(
                event("PUT /documents/{document_id}/type",
                      body={"type": type_key}), None)
        return reply, db

    def test_a_type_is_saved_as_the_choice(self):
        reply, db = self.choose("bank_statement")
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(json.loads(reply["body"]),
                         {"document_id": DOC, "chosen_type": "bank_statement"})
        [(statement, values)] = db.writes("UPDATE document")
        self.assertIn("SET chosen_type = :c", statement)
        self.assertEqual(values["c"], "bank_statement")

    def test_the_proposal_is_never_written(self):
        """document_type holds what the classifier proposed. Choosing writes
        beside it, not over it."""
        _, db = self.choose("bank_statement")
        [(statement, _)] = db.writes("UPDATE document")
        self.assertNotIn("document_type", statement)

    def test_the_write_is_held_to_a_document_still_waiting(self):
        """A filing landing between the read and the write must not have a
        choice written under it."""
        _, db = self.choose("bank_statement")
        [(statement, _)] = db.writes("UPDATE document")
        self.assertIn("state = 'analysed'", statement)
        self.assertIn("tenant_id = :t", statement)

    def test_not_classified_is_kept_as_a_choice(self):
        """"" rather than NULL, so it is told apart from nobody choosing and
        survives leaving the screen like any other choice."""
        reply, db = self.choose("")
        self.assertEqual(reply["statusCode"], 200)
        [(_, values)] = db.writes("UPDATE document")
        self.assertEqual(values["c"], "")

    def test_a_type_the_workspace_does_not_hold_is_refused(self):
        reply, db = self.choose("made_up")
        self.assertEqual(reply["statusCode"], 400)
        self.assertIn("made_up", json.loads(reply["body"])["error"])
        self.assertEqual(db.writes("UPDATE"), [])

    def test_a_document_no_longer_waiting_is_refused(self):
        for state in ("filed", "reading", "unreadable", "rejected"):
            with self.subTest(state=state):
                reply, db = self.choose(
                    "invoice", Db({DOC: (state, None, "invoice")}))
                self.assertEqual(reply["statusCode"], 400)
                self.assertEqual(db.writes("UPDATE"), [])

    def test_a_document_that_does_not_exist_is_404(self):
        reply, db = self.choose("invoice", Db({}))
        self.assertEqual(reply["statusCode"], 404)
        self.assertEqual(db.writes("UPDATE"), [])

    def test_the_route_is_in_the_terraform(self):
        """A route the dispatcher answers and API Gateway does not carry is
        a 404 at the gateway, before any of this runs."""
        from api_modules import ROOT
        terraform = (ROOT / "api.tf").read_text(encoding="utf-8")
        self.assertIn('"PUT /documents/{document_id}/type"', terraform)


class PendingCarriesTheChoiceTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def test_chosen_type_travels_beside_the_proposal(self):
        record = (DOC, "a.pdf", "invoice", 3, False, 900, "high", "why",
                  "analysed", "clerk@firm.com", None, None, None, None, None,
                  None, "bank_statement")
        with mock.patch.object(self.app, "_sql",
                               return_value=rows(record)) as sql:
            [row] = self.app.list_pending(TENANT, 3)
        self.assertIn("chosen_type", " ".join(sql.call_args[0][0].split()))
        self.assertEqual(row["proposed_type"], "invoice")
        self.assertEqual(row["chosen_type"], "bank_statement")


class FilingUsesTheChoiceTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def file(self, decisions, db):
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "wallet") as wallet, \
                mock.patch.object(self.app, "config") as config, \
                mock.patch.object(self.app, "_s3") as s3:
            config.for_tenant.return_value = registry_with("invoice",
                                                           "bank_statement")
            wallet.charge.return_value = {"entry_id": 5}
            s3.get_object.return_value = {
                "Body": mock.MagicMock(read=lambda: b"{}")}
            try:
                out = self.app.file_documents(
                    TENANT, "clerk@firm.com", ENGAGEMENT, decisions, "key-1")
                return out, None, wallet, db
            except ValueError as exc:
                return None, exc, wallet, db

    def filed_as(self, db):
        return [v["ty"] for s, v in db.writes(
            "UPDATE document SET document_type = :ty")]

    def test_a_decision_without_a_type_files_as_the_chosen_type(self):
        db = Db({DOC: ("analysed", "bank_statement", "invoice")})
        out, refused, _, _ = self.file([{"document_id": DOC}], db)
        self.assertIsNone(refused)
        self.assertEqual(self.filed_as(db), ["bank_statement"])

    def test_with_nothing_chosen_the_proposal_is_filed(self):
        db = Db({DOC: ("analysed", None, "invoice")})
        self.file([{"document_id": DOC}], db)
        self.assertEqual(self.filed_as(db), ["invoice"])

    def test_the_decisions_own_type_wins(self):
        """What the person pressed File on is the last word."""
        db = Db({DOC: ("analysed", "bank_statement", "invoice")})
        self.file([{"document_id": DOC, "document_type": "invoice"}], db)
        self.assertEqual(self.filed_as(db), ["invoice"])

    def test_not_classified_is_refused_before_the_charge(self):
        """"" is a choice, not an absence: it does not fall back to the
        proposal, and nothing is charged for trying."""
        db = Db({DOC: ("analysed", "", "invoice")})
        out, refused, wallet, _ = self.file([{"document_id": DOC}], db)
        self.assertIsNone(out)
        self.assertIn("Choose a type", str(refused))
        wallet.charge.assert_not_called()

    def test_only_the_decisions_sent_are_charged_and_filed(self):
        """Part of a batch: two of three sent. The third is not charged, not
        touched, and not rejected - it simply stays waiting."""
        db = Db({41: ("analysed", "invoice", "invoice"),
                 42: ("analysed", "invoice", "invoice"),
                 43: ("analysed", "invoice", "invoice")})
        out, refused, wallet, _ = self.file(
            [{"document_id": 41}, {"document_id": 42}], db)
        self.assertIsNone(refused)
        self.assertEqual(wallet.charge.call_args[0][3], 2)
        touched = {v.get("d") for s, v in db.ran
                   if s.startswith("UPDATE document")}
        self.assertEqual(touched, {41, 42})
        self.assertEqual(db.writes("UPDATE document SET state = 'rejected'"),
                         [])
        self.assertEqual(out["rejected"], 0)


if __name__ == "__main__":
    unittest.main()
