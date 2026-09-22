"""
The name an upload was stored under goes back to the screen (17.3).

    python -m unittest discover -s tests

THE BUG THIS CLOSES. upload_url cleans the engagement name for the storage
key - "TEST - 2" becomes "TEST-2" - and the screen kept what was typed. It
then polled /engagements/TEST%20-%202/pending, which matches on the S3 key
and found nothing, so two documents that had been read in two seconds sat on
"analysing" for ever under a name nobody was looking at.

There is one cleaning rule and it is _clean. These tests pin the two places
it now reaches the browser: the name returned by POST /uploads, and the
answer to "what would this become" that the new-engagement field asks while
somebody types.

Nothing reaches AWS: boto3 is replaced at import and _sql is a stub.
"""

import json
import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 2
EMAIL = "partner@firm.com"

# Typed, and what _clean makes of it. Spaces to dashes, runs of dashes
# collapsed, anything a key cannot carry dropped, edges trimmed.
NAMES = [
    ("TEST - 2", "TEST-2"),
    ("Meridian Trading", "Meridian-Trading"),
    ("  padded  ", "padded"),
    # "Smith & Co." -> "Smith-&-Co." -> "Smith--Co." -> "Smith-Co." ->
    # "Smith-Co". I wrote "SmithCo" here first, from memory of a rule I had
    # read an hour earlier, and the test caught it. That is the argument for
    # the browser asking rather than carrying a copy, in four characters.
    ("Smith & Co.", "Smith-Co"),
    ("a/b", "ab"),
    ("--leading", "leading"),
    ("Café Noir", "Caf-Noir"),
]


class UploadNameTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def upload(self, engagement, filename="Articles.pdf"):
        with mock.patch.object(self.app, "_sql",
                               lambda s, p=None, tx=None: rows((7,))), \
                mock.patch.object(self.app, "_s3") as s3:
            s3.generate_presigned_url.return_value = "https://signed"
            return self.app.upload_url(TENANT, EMAIL, engagement, filename)

    def test_the_cleaned_name_comes_back(self):
        out = self.upload("TEST - 2")
        self.assertEqual(out["engagement"], "TEST-2")

    def test_it_is_the_name_in_the_key(self):
        """The whole point: what the caller is told and where the file goes
        are the same string, read from the same variable."""
        for typed, expected in NAMES:
            out = self.upload(typed)
            self.assertEqual(out["engagement"], expected, typed)
            self.assertEqual(
                out["key"],
                "tenants/%d/docs/%s/Articles.pdf" % (TENANT, expected), typed)

    def test_a_name_that_needed_no_cleaning_comes_back_unchanged(self):
        out = self.upload("MERIDIAN")
        self.assertEqual(out["engagement"], "MERIDIAN")

    def test_a_name_that_cleans_away_to_nothing_is_refused(self):
        """"///" is not a quiet empty engagement at the root of the bucket."""
        with self.assertRaises(ValueError):
            self.upload("///")

    def test_the_rest_of_the_answer_is_unchanged(self):
        out = self.upload("TEST - 2")
        self.assertEqual(out["url"], "https://signed")
        self.assertEqual(out["uploaded_by"], EMAIL)


class UploadFilenameTest(unittest.TestCase):
    """The FILE's cleaned name goes back too (17.4).

    Review.tsx carried its own copy of _clean in TypeScript so that a file it
    was waiting for matched the row that arrived. Two implementations of the
    rule that decides where a file is kept, agreeing character for character
    and one edit away from not - which is 17.3, in the other half of the
    key. The screen is told instead."""

    def setUp(self):
        self.app = load_api()

    def upload(self, filename, engagement="Meridian"):
        with mock.patch.object(self.app, "_sql",
                               lambda s, p=None, tx=None: rows((7,))), \
                mock.patch.object(self.app, "_s3") as s3:
            s3.generate_presigned_url.return_value = "https://signed"
            return self.app.upload_url(TENANT, EMAIL, engagement, filename)

    def test_the_cleaned_filename_comes_back(self):
        out = self.upload("KCCA Trade Licence 2026.pdf")
        self.assertEqual(out["filename"], "KCCA-Trade-Licence-2026.pdf")

    # Real names, and what _clean makes of them. Written out rather than
    # composed from the engagement table above: "  padded  " + ".pdf" cleans
    # to "padded-.pdf", because the space before the extension becomes a dash
    # like any other. I composed it first and this caught me - which is the
    # same argument as the "Smith & Co." note above, one row lower down.
    FILENAMES = [
        ("KCCA Trade Licence 2026.pdf", "KCCA-Trade-Licence-2026.pdf"),
        ("Articles.pdf", "Articles.pdf"),
        ("Board Minutes (2026).pdf", "Board-Minutes-2026.pdf"),
        ("  padded  .pdf", "padded-.pdf"),
        ("Café Noir.pdf", "Caf-Noir.pdf"),
        ("a/b.pdf", "ab.pdf"),
    ]

    def test_it_is_the_name_in_the_key(self):
        """What the caller is told and where the file goes are the same
        string, read from the same variable - as for the engagement."""
        for typed, expected in self.FILENAMES:
            out = self.upload(typed)
            self.assertEqual(out["filename"], expected, typed)
            self.assertTrue(out["key"].endswith("/" + expected), out["key"])

    def test_it_is_clean_itself_and_not_a_second_rule(self):
        """If _clean changes, this answer changes with it. Asserted by
        calling both rather than by restating the rule."""
        for typed, _ in self.FILENAMES:
            out = self.upload(typed)
            self.assertEqual(out["filename"], self.app._clean(typed), typed)

    def test_a_filename_needing_no_cleaning_comes_back_unchanged(self):
        out = self.upload("Articles.pdf")
        self.assertEqual(out["filename"], "Articles.pdf")

    def test_a_filename_that_cleans_away_to_nothing_is_refused(self):
        with self.assertRaises(ValueError):
            self.upload("///")

    def test_this_is_the_name_the_row_will_carry(self):
        """The screen matches the returned name against document.filename,
        and the normalizer reads that off the key. So the two agree by
        construction: both are the last segment of this key."""
        out = self.upload("Board Minutes (2026).pdf")
        self.assertEqual(out["key"].rsplit("/", 1)[1], out["filename"])


class CleanedNameRouteTest(unittest.TestCase):
    """GET /engagements?name= - what the field asks while somebody types.

    It exists so the browser holds no copy of _clean. A copy would be a
    second implementation of the rule that decides where a file is stored,
    and there is no test runner in ui/ that could ever prove the two still
    agreed."""

    def setUp(self):
        self.app = load_api()

    def get(self, query=None):
        event = {
            "routeKey": "GET /engagements",
            "queryStringParameters": query,
            "requestContext": {"authorizer": {"jwt": {"claims": {
                "custom:tenant_id": str(TENANT), "email": EMAIL,
                "custom:role": "admin"}}}},
        }
        with mock.patch.object(self.app, "_sql",
                               lambda s, p=None, tx=None: rows()):
            reply = self.app.lambda_handler(event, None)
        return reply, json.loads(reply["body"])

    def test_it_answers_what_a_typed_name_becomes(self):
        for typed, expected in NAMES:
            _, body = self.get({"name": typed})
            self.assertEqual(body["cleaned"], expected, typed)

    def test_the_list_still_comes_with_it(self):
        reply, body = self.get({"name": "TEST - 2"})
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(body["engagements"], [])

    def test_without_a_name_it_is_the_list_it_always_was(self):
        """Every caller that predates this asks for no name and must see the
        answer it has always seen."""
        reply, body = self.get(None)
        self.assertEqual(reply["statusCode"], 200)
        self.assertEqual(list(body), ["engagements"])

    def test_an_empty_name_answers_nothing_rather_than_an_empty_string(self):
        _, body = self.get({"name": "   "})
        self.assertNotIn("cleaned", body)

    def test_the_answer_is_clean_itself_and_not_a_second_rule(self):
        """If _clean changes, this route changes with it. Asserted by calling
        both rather than by restating the rule a third time."""
        for typed, _ in NAMES:
            _, body = self.get({"name": typed})
            self.assertEqual(body["cleaned"], self.app._clean(typed), typed)


if __name__ == "__main__":
    unittest.main()
