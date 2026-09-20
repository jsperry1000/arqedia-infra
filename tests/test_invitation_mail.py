"""
An invitation that could not be emailed is still an invitation (10.5).

    python -m unittest discover -s tests

The seat is reserved and the token minted before anything is sent, so a
refusal from SES must not raise, must not undo the reservation, and must not
hide the link the administrator can send by hand. Nothing here reaches AWS:
boto3 is replaced at import and the SES client is a mock.
"""

import unittest
from unittest import mock

from api_modules import load_api

TENANT = 7
ADMIN = "partner@firm.com"
INVITEE = "newcomer@firm.com"

# What seats.invite returns, which is the half that is already committed by
# the time the send is attempted.
RESERVED = {"token": "a-token-shown-once", "email": INVITEE,
            "role": "member", "expires_at": "2026-09-27 10:00:00"}


def event(role="admin"):
    return {
        "routeKey": "POST /seats/invitations",
        "body": '{"email": "%s", "role": "member"}' % INVITEE,
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "custom:tenant_id": str(TENANT),
            "email": ADMIN,
            "custom:role": role,
        }}}},
    }


class InvitationMailTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def invite(self, send):
        """Dispatch the invitation route with seats.invite standing in for the
        database and `send` standing in for SES."""
        with mock.patch.object(self.app.seats, "invite",
                               return_value=dict(RESERVED)) as invited, \
                mock.patch.object(self.app.mail, "send", send):
            reply = self.app.lambda_handler(event(), None)
        self.assertEqual(invited.call_count, 1)
        import json
        return reply, json.loads(reply["body"])

    def test_a_sent_invitation_says_so(self):
        send = mock.Mock(return_value=True)
        reply, body = self.invite(send)
        self.assertEqual(reply["statusCode"], 201)
        self.assertTrue(body["sent"])
        # The link comes back whether or not it was emailed: it is the
        # fallback, and it is shown once.
        self.assertIn("token=a-token-shown-once", body["accept_url"])
        self.assertEqual(body["token"], "a-token-shown-once")

    def test_a_failed_send_does_not_lose_the_seat(self):
        """The whole point of the ordering. SES refusing must leave a 201, the
        token, the link, and an honest flag."""
        send = mock.Mock(return_value=False)
        reply, body = self.invite(send)
        self.assertEqual(reply["statusCode"], 201)
        self.assertFalse(body["sent"])
        self.assertIn("token=a-token-shown-once", body["accept_url"])

    def test_the_invitation_goes_to_the_invitee_and_replies_to_the_inviter(self):
        send = mock.Mock(return_value=True)
        self.invite(send)
        to, subject, text = send.call_args.args
        self.assertEqual(to, INVITEE)
        self.assertEqual(send.call_args.kwargs["reply_to"], ADMIN)
        # The name of the person who sent it is what distinguishes an
        # invitation from a phishing email, so it is in both.
        self.assertIn(ADMIN, subject)
        self.assertIn(ADMIN, text)


class InvitationWordingTest(unittest.TestCase):
    """mail.invitation on its own: it composes, it does not send."""

    def setUp(self):
        self.mail = load_api().mail

    def test_it_names_the_role_in_words(self):
        _, member = self.mail.invitation(ADMIN, "https://app/x", "2026-09-27",
                                         "member")
        _, admin = self.mail.invitation(ADMIN, "https://app/x", "2026-09-27",
                                        "admin")
        self.assertIn("as a member", member)
        self.assertIn("as an administrator", admin)

    def test_it_carries_the_link_and_the_date_it_lapses(self):
        _, text = self.mail.invitation(ADMIN, "https://app/invitation?x=1",
                                       "2026-09-27 10:00:00", "member")
        self.assertIn("https://app/invitation?x=1", text)
        self.assertIn("2026-09-27", text)
        # The time of day is noise in a sentence about a week from now.
        self.assertNotIn("10:00:00", text)

    def test_it_says_nothing_about_the_workspace(self):
        """Nothing about a tenant is visible to somebody who has not accepted,
        and that includes its name in an email to an address that may not be
        theirs."""
        subject, text = self.mail.invitation(ADMIN, "https://app/x",
                                             "2026-09-27", "member")
        for word in ("tenant", "workspace called", "engagement"):
            self.assertNotIn(word, (subject + text).lower())


class SenderTest(unittest.TestCase):
    """SENDER is read at the send, not at import (mail.py's docstring)."""

    def setUp(self):
        self.mail = load_api().mail

    def test_no_sender_refuses_the_send_rather_than_the_import(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(self.mail.sender(), "")
            self.assertFalse(self.mail.send(INVITEE, "subject", "body"))

    def test_an_address_is_masked_in_the_log(self):
        self.assertEqual(self.mail._mask("newcomer@firm.com"), "n***@firm.com")
        self.assertEqual(self.mail._mask("not-an-address"), "?")


if __name__ == "__main__":
    unittest.main()
