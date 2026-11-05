"""
The hourly limits count codes sent, and a free-mail address by itself.

    python -m unittest discover -s tests

On 5 November 2026 testers were locked out across addresses and connections:
every refusal counted toward the limit, including the rate_limited row each
refusal writes, and all of gmail.com shared one domain's allowance of three.

The database here is a list of signup_attempt rows. The stub answers the
counting queries by reading the WHERE the handler sends, so a query that counts
the wrong rows answers the wrong number.
"""

import re
import unittest
from unittest import mock

from api_modules import rows
from test_signup import EVENT, FakeSignupDb, load_signup


class AttemptsDb(FakeSignupDb):
    def __init__(self, attempts, **kw):
        super().__init__(**kw)
        self.attempts = attempts  # dicts: domain, hash, ip, outcome

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        if "COUNT(*) FROM signup_attempt" not in s:
            return super().sql(statement, params, tx)
        values = {p["name"]: next(iter(p["value"].values())) for p in params or []}
        found = self.attempts
        if "email_domain = :d" in s:
            found = [a for a in found if a["domain"] == values["d"]]
        if "email_hash = :h" in s:
            found = [a for a in found if a["hash"] == values["h"]]
        if "ip = :ip" in s:
            found = [a for a in found if a["ip"] == values["ip"]]
        only = re.search(r"outcome = '(\w+)'", s)
        if only:
            found = [a for a in found if a["outcome"] == only.group(1)]
        excluded = re.search(r"outcome NOT IN \(([^)]*)\)", s)
        if excluded:
            out = re.findall(r"'(\w+)'", excluded.group(1))
            found = [a for a in found if a["outcome"] not in out]
        self.statements.append((s, values))
        return rows((len(found),))


class RateLimitTest(unittest.TestCase):
    def setUp(self):
        self.signup = load_signup()
        self.signup._ses = mock.MagicMock()
        self.signup._idp = mock.MagicMock()
        not_found = type("UserNotFoundException", (Exception,), {})
        self.signup._idp.exceptions.UserNotFoundException = not_found
        self.signup._idp.admin_get_user.side_effect = not_found()

    def row(self, email, outcome, ip="203.0.113.9"):
        return {"domain": email.split("@")[1], "hash": self.signup._sha(email),
                "ip": ip, "outcome": outcome}

    def begin(self, attempts, email="a@firm.com"):
        db = AttemptsDb(attempts, allow=(email,))
        with mock.patch.object(self.signup, "_sql", db.sql):
            reply = self.signup.begin(EVENT, {"email": email, "org_name": "Firm"})
        return reply

    def test_refusals_do_not_count(self):
        """What locked a tester out: two failures, a refusal for the limit
        itself, and an uninvited try - none of them a code sent."""
        attempts = [self.row("a@firm.com", o) for o in
                    ("failed", "failed", "rate_limited", "not_invited",
                     "code_expired", "exists")]
        self.assertEqual(self.begin(attempts)["statusCode"], 200)

    def test_three_codes_to_one_firm_still_stop_the_fourth(self):
        attempts = [self.row(e, "code_sent", ip=ip) for e, ip in
                    (("a@firm.com", "198.51.100.1"),
                     ("b@firm.com", "198.51.100.2"),
                     ("c@firm.com", "198.51.100.3"))]
        reply = self.begin(attempts)
        self.assertEqual(reply["statusCode"], 400)
        self.assertIn("Too many attempts", reply["body"])

    def test_strangers_on_gmail_do_not_share_an_allowance(self):
        attempts = [self.row(e, "code_sent", ip=ip) for e, ip in
                    (("x@gmail.com", "198.51.100.1"),
                     ("y@gmail.com", "198.51.100.2"),
                     ("z@gmail.com", "198.51.100.3"))]
        self.assertEqual(self.begin(attempts, "a@gmail.com")["statusCode"], 200)

    def test_one_gmail_address_still_has_its_own_limit(self):
        attempts = [self.row("a@gmail.com", "code_sent", ip=ip) for ip in
                    ("198.51.100.1", "198.51.100.2", "198.51.100.3")]
        reply = self.begin(attempts, "a@gmail.com")
        self.assertEqual(reply["statusCode"], 400)
        self.assertIn("Too many attempts", reply["body"])

    def test_five_codes_from_one_connection_stop_the_sixth(self):
        attempts = [self.row("%s@other%d.com" % (c, i), "code_sent")
                    for i, c in enumerate("vwxyz")]
        reply = self.begin(attempts)
        self.assertEqual(reply["statusCode"], 400)
        self.assertIn("Too many attempts", reply["body"])

    def test_refusals_from_one_connection_do_not_count(self):
        attempts = [self.row("%s@other%d.com" % (c, i), "not_invited")
                    for i, c in enumerate("vwxyzq")]
        self.assertEqual(self.begin(attempts)["statusCode"], 200)

    def test_an_uninvited_address_is_still_refused_first(self):
        """The limits moved; the gate did not."""
        db = AttemptsDb([], allow=())
        with mock.patch.object(self.signup, "_sql", db.sql):
            reply = self.signup.begin(EVENT, {"email": "a@firm.com",
                                              "org_name": "Firm"})
        self.assertEqual(reply["statusCode"], 400)
        self.assertIn("not open for signup", reply["body"])


if __name__ == "__main__":
    unittest.main()
