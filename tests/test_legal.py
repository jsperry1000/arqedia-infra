"""
The Agreement: one version, stated once, accepted on record (27 October 2026).

    python -m unittest discover -s tests

config/legal.json states the version for the site and the screen. The signup
and share_viewer Lambdas bundle their own directory only and cannot read it,
so each holds AGREEMENT_VERSION; this fails if any of them disagree, or if a
published document's version line says something else - the same arrangement
TRIAL_DAYS has with config/plans.json (test_plans_source.py).

Then the two routes that make an account: neither makes one without the box
ticked and the current version named, and each records the acceptance beside
what it made. The SQL itself runs against nothing here and is unverified
until migration 049 is applied on dev.
"""

import json
import re
import unittest
from pathlib import Path
from unittest import mock

from api_modules import rows
from test_invitation_password import FakeDb as InvitationDb, POLICY, TOKEN, \
    INVITEE, EVENT
from test_signup import FakeSignupDb, load_signup

ROOT = Path(__file__).resolve().parents[1]
LEGAL = json.loads((ROOT / "config/legal.json").read_text(encoding="utf-8"))


def constant(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    found = re.findall(r"^AGREEMENT_VERSION = (\d+)$", text, re.M)
    assert len(found) == 1, f"{path}: AGREEMENT_VERSION stated {len(found)} times"
    return int(found[0])


class OneVersionTest(unittest.TestCase):
    def test_every_lambda_states_the_files_version(self):
        for path in ("lambda/signup/app.py", "lambda/share_viewer/app.py"):
            with self.subTest(path=path):
                self.assertEqual(constant(path), LEGAL["agreement_version"])

    def test_each_document_exists_and_says_the_same_version(self):
        expected = "Version %d · Effective" % LEGAL["agreement_version"]
        for key, doc in LEGAL["documents"].items():
            with self.subTest(document=key):
                lines = [l for l in (ROOT / doc["path"]).read_text(
                    encoding="utf-8").splitlines() if l.strip()]
                self.assertEqual(lines[0], "# " + doc["title"])
                self.assertTrue(lines[1].startswith(expected), lines[1])

    def test_the_three_published_documents_are_the_three_pages(self):
        self.assertEqual(sorted(LEGAL["documents"]),
                         ["privacy", "refunds", "terms"])
        for key in LEGAL["documents"]:
            with self.subTest(page=key):
                page = (ROOT / "site" / key / "index.html").read_text(
                    encoding="utf-8")
                self.assertIn("<!-- @legal:%s -->" % key, page)
                self.assertIn('<meta name="robots" content="noindex">', page)

    def test_no_other_site_page_links_to_them(self):
        # Decided 27 October 2026: public, but linked from no footer or menu.
        for page in ("index.html", "pricing/index.html", "guide/index.html"):
            with self.subTest(page=page):
                html = (ROOT / "site" / page).read_text(encoding="utf-8")
                self.assertNotRegex(html, r'href="/(terms|privacy|refunds)')


def pending():
    return (1, "firm.com", None, 0, "Firm", None, "us-east-2", None, None,
            "2999-01-01 00:00:00", None, None)


class SignupAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.signup = load_signup()
        self.signup._rds = mock.MagicMock()
        self.signup._rds.begin_transaction.return_value = {"transactionId": "tx"}
        self.signup._idp = mock.MagicMock()
        row = list(pending())
        row[2] = self.signup._sha("123456")
        self.db = FakeSignupDb(pending=tuple(row))

    def verify(self, **terms):
        body = {"email": "a@firm.com", "code": "123456", "password": "pw"}
        body.update(terms)
        with mock.patch.object(self.signup, "_sql", self.db.sql):
            return self.signup.verify(EVENT, body)

    def test_an_unticked_box_makes_nothing_and_spends_no_attempt(self):
        reply = self.verify(agreement_version=1)
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(json.loads(reply["body"])["error"],
                         self.signup.TERMS_REQUIRED)
        self.assertEqual(self.db.statements, [])
        self.signup._idp.admin_create_user.assert_not_called()

    def test_another_version_is_refused(self):
        for version in (None, 0, 2, "1", True):
            with self.subTest(version=version):
                reply = self.verify(accept_terms=True,
                                    agreement_version=version)
                self.assertEqual(reply["statusCode"], 400)
                self.assertEqual(json.loads(reply["body"])["error"],
                                 self.signup.TERMS_CHANGED)
        self.assertEqual(self.db.statements, [])

    def test_the_acceptance_is_written_with_the_tenant(self):
        reply = self.verify(accept_terms=True, agreement_version=1)
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(self.db.inserted("terms_acceptance"), [{
            "e": "a@firm.com", "t": 42, "c": "signup", "v": 1}])


class InvitationAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.app = load_signup()
        self.app._password_policy_cache = None

    def accept(self, db, set_password=None, **terms):
        idp = mock.MagicMock()
        idp.describe_user_pool.return_value = {
            "UserPool": {"Policies": {"PasswordPolicy": POLICY}}}
        if set_password is not None:
            idp.admin_set_user_password.side_effect = set_password
        body = {"email": INVITEE, "token": TOKEN, "password": "Zq7wTr4mPl9x"}
        body.update(terms)
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_idp", idp), \
                mock.patch.object(self.app, "_record", lambda *a, **k: None):
            return self.app.accept(EVENT, body)

    def test_an_unticked_box_writes_no_seat(self):
        db = InvitationDb(self.app._sha(TOKEN))
        reply = self.accept(db)
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(db.statements, [])

    def test_the_acceptance_is_written_beside_the_seat(self):
        db = InvitationDb(self.app._sha(TOKEN))
        reply = self.accept(db, accept_terms=True, agreement_version=1)
        self.assertEqual(reply["statusCode"], 200)
        written = [s for s in db.statements
                   if s.startswith("INSERT INTO terms_acceptance")]
        self.assertEqual(len(written), 1)
        seat = next(i for i, s in enumerate(db.statements)
                    if s.startswith("INSERT INTO seat ("))
        self.assertLess(seat, db.statements.index(written[0]))

    def test_an_account_that_cannot_be_made_takes_its_acceptance_back(self):
        class Db(InvitationDb):
            def sql(self, statement, params=None, tx=None):
                s = " ".join(statement.split())
                if s.startswith("INSERT INTO terms_acceptance"):
                    self.statements.append(s)
                    return {"generatedFields": [{"longValue": 77}]}
                return super().sql(statement, params, tx)

        db = Db(self.app._sha(TOKEN))
        reply = self.accept(db, set_password=RuntimeError("cognito down"),
                            accept_terms=True, agreement_version=1)
        self.assertEqual(reply["statusCode"], 500)
        self.assertIn("DELETE FROM terms_acceptance WHERE acceptance_id = :a",
                      db.statements)
        self.assertIn("DELETE FROM seat WHERE tenant_id = :t AND email = :e",
                      db.statements)


if __name__ == "__main__":
    unittest.main()
