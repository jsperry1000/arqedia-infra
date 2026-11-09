"""
The organization profile (9 November 2026, migration 056).

    python -m unittest discover -s tests -p "test_organization_profile.py"

An administrator keeps the organization's name, address, contact email and
contact phone. Only the name is required. A member is refused, reading and
writing.

Nothing reaches AWS: boto3 is replaced at import and _sql is a stub.
"""

import unittest
from unittest import mock

from api_modules import load_api, rows
from test_memo_update import value

TENANT = 5


class OrganizationProfile(unittest.TestCase):

    def setUp(self):
        self.app = load_api()
        self.stored = ("eBL", None, None, None)
        self.writes = []

        def sql(statement, params=None):
            if statement.startswith("SELECT name, address"):
                return rows(self.stored)
            if statement.startswith("UPDATE tenant SET name"):
                got = {p["name"]: value(p) for p in params}
                self.writes.append(got)
                self.stored = (got["n"], got["a"], got["e"], got["p"])
                return {}
            raise AssertionError("unexpected SQL: " + statement)

        p = mock.patch.object(self.app, "_sql", side_effect=sql)
        p.start()
        self.addCleanup(p.stop)

    def put(self, role="admin", **body):
        full = {"name": "eBL Finance Inc.", "address": "", "contact_email": "",
                "contact_phone": ""}
        full.update(body)
        return self.app.update_organization(TENANT, "admin@ebl.com", role, full)

    def test_reads_with_the_signed_in_address_beside_it(self):
        out = self.app.get_organization(TENANT, "admin@ebl.com", "admin")
        self.assertEqual(out["name"], "eBL")
        self.assertIsNone(out["contact_email"])
        self.assertEqual(out["signed_in_email"], "admin@ebl.com")

    def test_saves_the_name_and_nothing_else_as_empty(self):
        out = self.put()
        self.assertEqual(out["name"], "eBL Finance Inc.")
        self.assertEqual(self.writes[0],
                         {"n": "eBL Finance Inc.", "a": None, "e": None,
                          "p": None, "t": TENANT})

    def test_keeps_the_address_lines(self):
        self.put(address="  1 Main  St \n\n Suite 2 \nNew York")
        self.assertEqual(self.writes[0]["a"], "1 Main St\nSuite 2\nNew York")

    def test_the_name_is_required(self):
        with self.assertRaises(ValueError):
            self.put(name="   ")
        self.assertEqual(self.writes, [])

    def test_a_bad_email_or_phone_is_refused(self):
        with self.assertRaises(ValueError):
            self.put(contact_email="not an address")
        with self.assertRaises(ValueError):
            self.put(contact_phone="call me")
        self.assertEqual(self.writes, [])

    def test_contact_details_are_kept(self):
        self.put(contact_email="ops@ebl-finance.com",
                 contact_phone="+1 (212) 555-0100")
        self.assertEqual(self.writes[0]["e"], "ops@ebl-finance.com")
        self.assertEqual(self.writes[0]["p"], "+1 (212) 555-0100")

    def test_a_member_is_refused_both_ways(self):
        with self.assertRaises(PermissionError):
            self.app.get_organization(TENANT, "m@ebl.com", "member")
        with self.assertRaises(PermissionError):
            self.put(role="member")
        self.assertEqual(self.writes, [])


if __name__ == "__main__":
    unittest.main()
