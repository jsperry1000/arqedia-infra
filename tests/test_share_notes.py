"""
Telling a recipient a share was revoked, and that a share is an update
(5 November 2026).

    python -m unittest discover -s tests

Uses test_share_routes' setUp - moto for DynamoDB and S3, Aurora and the
wallet stubbed - without inheriting its tests, so they run once.

Decided: revoking asks "Tell them by email", ticked; unticked is silent. A
later revision of a memorandum the person was already sent says "This is an
updated version of ..."; the earlier share is left as it is.
"""

import unittest

# The module, not the class: a TestCase imported by name into this module is
# collected here too, and its tests would run twice.
import test_share_routes as routes

HAVE = routes.HAVE

# Memo 11 is 287.2 and memo 12 is 287.3, one series. Memo 13 is another
# memorandum altogether, 300.1.
MEMOS = {11: ("KYC 287.2", 287, 2), 12: ("KYC 287.3", 287, 3),
         13: ("KYC 300.1", 300, 1)}


@unittest.skipUnless(HAVE, "moto, boto3, pypdf or reportlab not installed")
class NotesTest(unittest.TestCase):
    setUp = routes.SendTest.setUp
    tearDown = routes.SendTest.tearDown
    send = routes.SendTest.send

    def series(self):
        s = self.share
        s._memo = lambda t, m: None if int(m) not in MEMOS else {
            "memo_id": int(m), "label": MEMOS[int(m)][0],
            "subject": "Meridian Trading Ltd",
            "root": MEMOS[int(m)][1], "revision": MEMOS[int(m)][2]}
        s._series = lambda t, ids: {int(i): MEMOS[int(i)][1:]
                                    for i in ids if int(i) in MEMOS}

    # --- revoking ------------------------------------------------------------

    def test_revoke_with_the_box_ticked_tells_the_recipient(self):
        first = self.send()
        out = self.share.revoke(1, "rv@ebl.test", first["grant_id"],
                                notify=True)
        self.assertTrue(out["revoked"])
        self.assertTrue(out["notified"])
        to, subject, body, reply_to, bcc = self.mails[-1]
        self.assertEqual(to, "j.ferrers@northbank.com")
        self.assertIn("rv@ebl.test has withdrawn", subject)
        self.assertIn("KYC 11.1", body)
        self.assertIn("cannot recall", body)
        self.assertNotIn("https://", body)
        self.assertEqual(reply_to, "rv@ebl.test")
        self.assertIsNone(bcc)

    def test_revoke_unticked_is_silent(self):
        first = self.send()
        before = len(self.mails)
        out = self.share.revoke(1, "rv@ebl.test", first["grant_id"])
        self.assertTrue(out["revoked"])
        self.assertIsNone(out["notified"])
        self.assertEqual(len(self.mails), before)

    def test_a_share_already_revoked_is_not_told_twice(self):
        first = self.send()
        self.share.revoke(1, "rv@ebl.test", first["grant_id"], notify=True)
        told = len(self.mails)
        again = self.share.revoke(1, "rv@ebl.test", first["grant_id"],
                                  notify=True)
        self.assertTrue(again["revoked"])
        self.assertIsNone(again["notified"])
        self.assertEqual(len(self.mails), told)

    def test_a_share_never_emailed_is_not_told(self):
        """A batch share whose one email has not gone: they never heard of
        it, so they are not told it is gone."""
        first = self.send(notify=False)
        before = len(self.mails)
        out = self.share.revoke(1, "rv@ebl.test", first["grant_id"],
                                notify=True)
        self.assertIsNone(out["notified"])
        self.assertEqual(len(self.mails), before)

    def test_a_failed_email_still_revokes(self):
        first = self.send()
        self.share.mail.send = lambda *a, **k: False
        out = self.share.revoke(1, "rv@ebl.test", first["grant_id"],
                                notify=True)
        self.assertTrue(out["revoked"])
        self.assertFalse(out["notified"])
        item = self.share._table("grant").get_item(
            Key={"grant_id": first["grant_id"]})["Item"]
        self.assertTrue(item["revoked"])

    # --- the update line -----------------------------------------------------

    def test_a_later_revision_says_which_it_updates(self):
        self.series()
        self.send(memo=11, key="k1")
        self.send(memo=12, key="k2")
        body = self.mails[-1][2]
        self.assertIn("This is an updated version of KYC 287.2, which was "
                      "shared with you on", body)

    def test_the_first_share_of_a_series_says_nothing(self):
        self.series()
        self.send(memo=12)
        self.assertNotIn("updated version", self.mails[-1][2])

    def test_another_memorandum_is_not_an_update(self):
        self.series()
        self.send(memo=11, key="k1")
        self.send(memo=13, key="k2")
        self.assertNotIn("updated version", self.mails[-1][2])

    def test_an_earlier_revision_sent_after_a_later_one_is_not_an_update(self):
        self.series()
        self.send(memo=12, key="k1")
        self.send(memo=11, key="k2")
        self.assertNotIn("updated version", self.mails[-1][2])

    def test_the_same_memorandum_sent_again_is_not_an_update(self):
        self.series()
        self.send(memo=11, key="k1")
        self.send(memo=12, key="k2")
        self.send(memo=12, key="k3")
        self.assertNotIn("updated version", self.mails[-1][2])

    def test_another_recipient_is_not_told_of_someone_elses_share(self):
        self.series()
        self.send(memo=11, key="k1", to="a@one.test")
        self.send(memo=12, key="k2", to="b@two.test")
        self.assertNotIn("updated version", self.mails[-1][2])

    def test_the_earlier_share_is_left_as_it_was(self):
        self.series()
        first = self.send(memo=11, key="k1")
        self.send(memo=12, key="k2")
        item = self.share._table("grant").get_item(
            Key={"grant_id": first["grant_id"]})["Item"]
        self.assertFalse(item["revoked"])

    def test_a_failed_lookup_sends_the_ordinary_email(self):
        self.series()
        self.send(memo=11, key="k1")

        def broken(t, ids):
            raise RuntimeError("Aurora is asleep")
        self.share._series = broken
        sent = self.send(memo=12, key="k2")
        self.assertTrue(sent["sent"])
        self.assertNotIn("updated version", self.mails[-1][2])

    def test_a_batch_email_carries_the_line_too(self):
        self.series()
        self.send(memo=11, key="k1")
        later = self.send(memo=12, key="k2", notify=False)
        self.share.notify(1, "sp@ebl.test", [later["grant_id"]])
        self.assertIn("This is an updated version of KYC 287.2",
                      self.mails[-1][2])


@unittest.skipUnless(HAVE, "moto, boto3, pypdf or reportlab not installed")
class SenderNameTest(unittest.TestCase):
    """The person's name, not their address, leads (5 November 2026)."""

    setUp = routes.SendTest.setUp
    tearDown = routes.SendTest.tearDown

    def send(self, shown_as=None, **extra):
        body = dict({"recipient": "j.ferrers@northbank.com",
                     "authority_affirmed": True, "idempotency_key": "k1"},
                    **extra)
        return self.share.send(1, "sp@ebl.test", 11, body, shown_as=shown_as)

    def test_the_share_email_leads_with_the_name(self):
        self.send(shown_as="Steve Perry")
        to, subject, body, reply_to, _ = self.mails[-1]
        self.assertEqual(subject, "Steve Perry has shared a memorandum with you")
        self.assertTrue(body.startswith("Steve Perry (sp@ebl.test) at TESTCO A "))
        # A reply still reaches the address, and says so.
        self.assertEqual(reply_to, "sp@ebl.test")
        self.assertIn("it will reach sp@ebl.test", body)

    def test_with_no_name_it_is_the_address_as_before(self):
        self.send()
        _, subject, body, _, _ = self.mails[-1]
        self.assertEqual(subject, "sp@ebl.test has shared a memorandum with you")
        self.assertTrue(body.startswith("sp@ebl.test at TESTCO A "))

    def test_a_name_that_is_the_address_is_not_said_twice(self):
        self.send(shown_as="SP@ebl.test")
        _, subject, body, _, _ = self.mails[-1]
        self.assertTrue(subject.startswith("sp@ebl.test has shared"))
        self.assertNotIn("(sp@ebl.test)", body)

    def test_the_batch_email_leads_with_the_name(self):
        sent = self.send(notify=False)
        self.share.notify(1, "sp@ebl.test", [sent["grant_id"]],
                          shown_as="Steve Perry")
        self.assertTrue(self.mails[-1][1].startswith("Steve Perry has shared"))

    def test_the_revoke_email_leads_with_the_name(self):
        sent = self.send()
        self.share.revoke(1, "sp@ebl.test", sent["grant_id"], notify=True,
                          shown_as="Steve Perry")
        _, subject, body, reply_to, _ = self.mails[-1]
        self.assertEqual(subject,
                         "Steve Perry has withdrawn a memorandum shared with you")
        self.assertTrue(body.startswith("Steve Perry (sp@ebl.test) at "))
        self.assertEqual(reply_to, "sp@ebl.test")


if __name__ == "__main__":
    unittest.main()
