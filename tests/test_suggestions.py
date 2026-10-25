"""
A suggestion goes to info@arqedia.com, and the sender is thanked only once it
has.

    python -m unittest discover -s tests

Nothing here reaches AWS: boto3 is replaced at import, the tenant's name is
a stubbed read, and mail.send is a mock.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api

TENANT = 7
SENDER = "analyst@firm.com"


def event(body, role="member"):
    return {
        "routeKey": "POST /suggestions",
        "body": json.dumps(body),
        "requestContext": {"authorizer": {"jwt": {"claims": {
            "custom:tenant_id": str(TENANT),
            "email": SENDER,
            "custom:role": role,
        }}}},
    }


class SuggestionTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def suggest(self, body, send):
        named = {"records": [[{"stringValue": "Firm Ltd"}]]}
        with mock.patch.object(self.app, "_sql", return_value=named), \
                mock.patch.object(self.app.mail, "send", send):
            reply = self.app.lambda_handler(event(body), None)
        return reply, json.loads(reply["body"])

    def test_it_goes_to_us_and_the_sender_is_thanked(self):
        send = mock.Mock(return_value=True)
        reply, body = self.suggest({"text": "Export to Excel, please.",
                                    "page": "/engagements/X"}, send)
        self.assertEqual(reply["statusCode"], 201)
        self.assertEqual(body, {"sent": True, "thanked": True})

        (to, subject, note), first = send.call_args_list[0]
        self.assertEqual(to, "info@arqedia.com")
        # Answering it reaches the person who sent it.
        self.assertEqual(first["reply_to"], SENDER)
        self.assertIn("Export to Excel, please.", note)
        self.assertIn("Firm Ltd", subject)
        self.assertIn("/engagements/X", note)

        (to, subject, note), second = send.call_args_list[1]
        self.assertEqual(to, SENDER)
        self.assertEqual(second["reply_to"], "info@arqedia.com")
        self.assertIn("value your input", note)
        self.assertIn("Export to Excel, please.", note)

    def test_nobody_is_thanked_for_a_suggestion_that_did_not_go(self):
        send = mock.Mock(return_value=False)
        reply, body = self.suggest({"text": "Something."}, send)
        self.assertEqual(reply["statusCode"], 502)
        self.assertEqual(body["error"], self.app.SUGGESTION_NOT_SENT)
        self.assertEqual(send.call_count, 1)

    def test_a_failed_thank_you_still_reports_the_suggestion_sent(self):
        send = mock.Mock(side_effect=[True, False])
        reply, body = self.suggest({"text": "Something."}, send)
        self.assertEqual(reply["statusCode"], 201)
        self.assertEqual(body, {"sent": True, "thanked": False})

    def test_an_empty_suggestion_is_refused_and_nothing_is_sent(self):
        send = mock.Mock(return_value=True)
        reply, body = self.suggest({"text": "  \n "}, send)
        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(body["error"], self.app.SUGGESTION_EMPTY)
        send.assert_not_called()

    def test_a_long_suggestion_is_refused(self):
        send = mock.Mock(return_value=True)
        reply, _ = self.suggest({"text": "x" * 5001}, send)
        self.assertEqual(reply["statusCode"], 400)
        send.assert_not_called()

    def test_control_characters_are_dropped_and_line_breaks_kept(self):
        send = mock.Mock(return_value=True)
        self.suggest({"text": "one\x00\x07\nTwo\tthree"}, send)
        note = send.call_args_list[0].args[2]
        self.assertIn("one\nTwo\tthree", note)
        self.assertNotIn("\x00", note)


if __name__ == "__main__":
    unittest.main()
