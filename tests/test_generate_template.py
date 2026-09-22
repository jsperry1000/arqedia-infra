"""
Generating with no published memorandum (18.12).

    python -m unittest discover -s tests

A tenant reaches this state by signing up and leaving Get started without
ticking anything: fork_base brings the facts and the document types and
deliberately brings no memorandum, so TEMPLATE_KEY is None and the default
that every older caller relies on does not exist.

WHAT THESE ARE ABOUT. That the two refusals stay two refusals. "Nothing is
published" and "that key does not exist" are different faults, and before this
they were one - the None default flowed into has_template and answered "no
such template: None". The wrong-key message is as valuable as it ever was and
is asserted here so that fixing the first did not quietly swallow the second.

AND THAT NEITHER COSTS ANYTHING. Both refusals are above the charge. A test
that only read the message would pass with wallet.charge called first.

Nothing reaches AWS: boto3 is replaced at import and every collaborator is a
stub.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api

TENANT = 7
EMAIL = "susan@vantage.test"
NAME = "Meridian-Trading"
ENGAGEMENT_ID = 42


class FakeRegistry:
    """A tenant's active configuration, holding whatever templates it is
    given. TEMPLATE_KEY is the real rule - sorted keys, first one, None where
    there are none - because that is the value under test."""

    def __init__(self, templates=()):
        self.TEMPLATES = {k: {"key": k, "label": k.title(), "sections": []}
                          for k in templates}

    @property
    def TEMPLATE_KEY(self):
        keys = sorted(self.TEMPLATES)
        return keys[0] if keys else None

    def has_template(self, template_key):
        return template_key in self.TEMPLATES

    def label_for_template(self, template_key):
        found = self.TEMPLATES.get(template_key)
        return (found["label"] if found else template_key)


class GenerateTemplateTest(unittest.TestCase):

    def setUp(self):
        self.app = load_api()

        self.charges = []
        self.invocations = []

        self.registry = FakeRegistry()

        patches = [
            mock.patch.object(self.app.config, "for_tenant",
                              side_effect=lambda t: self.registry),
            mock.patch.object(self.app, "engagement_named",
                              side_effect=lambda t, n: {
                                  "engagement_id": ENGAGEMENT_ID,
                                  "engagement": NAME,
                                  "subject_name": "Meridian Trading Ltd",
                                  "status": "open"}),
            mock.patch.object(self.app.wallet, "charge",
                              side_effect=lambda *a, **k:
                                  self.charges.append((a, k))),
            mock.patch.object(self.app._lambda, "invoke",
                              side_effect=lambda **k:
                                  self.invocations.append(k)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def generate(self, template_key=None):
        return self.app.generate(TENANT, EMAIL, NAME, template_key,
                                 "idem-key-1")

    # --- nothing published -------------------------------------------------

    def test_no_template_published_is_its_own_sentence(self):
        """The refusal names what to do, and never the word None."""
        with self.assertRaises(ValueError) as caught:
            self.generate()

        said = str(caught.exception)
        self.assertEqual(said, self.app.NO_TEMPLATE_PUBLISHED)
        self.assertIn("Template Catalogue", said)
        self.assertNotIn("None", said)
        self.assertNotIn("no such template", said)

    def test_no_template_published_charges_nothing(self):
        """Above the charge, and above the invocation."""
        with self.assertRaises(ValueError):
            self.generate()

        self.assertEqual(self.charges, [])
        self.assertEqual(self.invocations, [])

    def test_an_empty_key_counts_as_asking_for_nothing(self):
        """"" is what a screen sends for "no choice made", and `or` reads it
        as absent - so the sentence has to cover it too, or the empty string
        falls through to has_template("") and answers 'no such template: '."""
        with self.assertRaises(ValueError) as caught:
            self.generate("")

        self.assertEqual(str(caught.exception),
                         self.app.NO_TEMPLATE_PUBLISHED)

    def test_a_named_key_with_nothing_published_is_still_a_wrong_key(self):
        """Asking for a memorandum by name is a request about that name. The
        workspace being empty does not make it the other fault."""
        with self.assertRaises(ValueError) as caught:
            self.generate("ghost")

        self.assertEqual(str(caught.exception), "no such template: ghost")

    # --- something published ----------------------------------------------

    def test_a_wrong_key_keeps_its_own_message(self):
        self.registry = FakeRegistry(["credit"])

        with self.assertRaises(ValueError) as caught:
            self.generate("ghost")

        self.assertEqual(str(caught.exception), "no such template: ghost")
        self.assertEqual(self.charges, [])
        self.assertEqual(self.invocations, [])

    def test_the_default_still_works(self):
        """Every caller that predates several templates asks without naming
        one. Nothing about that changed."""
        self.registry = FakeRegistry(["credit", "kyc"])

        answer = self.generate()

        self.assertEqual(answer["template_key"], "credit")
        self.assertEqual(answer["status"], "started")
        self.assertEqual(len(self.charges), 1)
        self.assertEqual(len(self.invocations), 1)

        payload = json.loads(self.invocations[0]["Payload"])
        self.assertEqual(payload["template_key"], "credit")
        self.assertEqual(payload["engagement_id"], ENGAGEMENT_ID)

    def test_a_named_key_that_exists_is_used(self):
        self.registry = FakeRegistry(["credit", "kyc"])

        answer = self.generate("kyc")

        self.assertEqual(answer["template_key"], "kyc")
        payload = json.loads(self.invocations[0]["Payload"])
        self.assertEqual(payload["template_key"], "kyc")

    # --- through the dispatcher -------------------------------------------

    def test_the_route_answers_400_with_the_sentence(self):
        """What the screen actually receives. charged() in Review.tsx unwraps
        `error`, so this string is what a person reads."""
        event = {
            "routeKey": "POST /engagements/{id}/generate",
            "pathParameters": {"id": NAME},
            "body": json.dumps({}),
            "requestContext": {"authorizer": {"jwt": {"claims": {
                "custom:tenant_id": str(TENANT),
                "email": EMAIL,
                "custom:role": "admin"}}}},
        }

        reply = self.app._dispatch(event, None)

        self.assertEqual(reply["statusCode"], 400)
        self.assertEqual(json.loads(reply["body"])["error"],
                         self.app.NO_TEMPLATE_PUBLISHED)
        self.assertEqual(self.charges, [])


if __name__ == "__main__":
    unittest.main()
