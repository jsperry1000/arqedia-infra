"""
The proposer finds each section's own text by its heading. Run from the
repository root:

    python -m unittest discover -s tests

WHY. A PDF's text layer puts a tab, a line break or two spaces where the page
shows one space, and the model answers with one space. Matched character for
character, the Real Estate sample walked on 23 October 2026 had none of its
eight headings found, so every section was read against the whole report and
proposed twenty facts, most of them another section's. Whitespace and case
are now not part of the match; the words still are.

Nothing reaches AWS: boto3 is replaced, and config and extractors - which the
proposer imports from the layer - are stand-ins.
"""

import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
PROPOSER = ROOT / "lambda" / "proposer"


def load_proposer():
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    fakes = {"boto3": boto3, "botocore": botocore,
             "botocore.exceptions": exceptions,
             "config": types.ModuleType("config"),
             "extractors": types.ModuleType("extractors")}
    env = {"REVIEW_BUCKET": "review", "CLUSTER_ARN": "c", "SECRET_ARN": "s",
           "DATABASE": "d", "MODEL_ID": "m"}
    saved = list(sys.path)
    with mock.patch.dict(sys.modules, fakes), mock.patch.dict(os.environ, env):
        sys.modules.pop("app", None)
        sys.path.insert(0, str(PROPOSER))
        try:
            return importlib.import_module("app")
        finally:
            sys.path[:] = saved
            sys.modules.pop("app", None)


# The shape pypdf gave for the Real Estate sample: tabs between words.
TEXT = ("Mock Real Estate Investment Summary\n"
        "Executive\tSummary\nThe property is a 120-unit building.\n"
        "Investment\tHighlights\nStrong rent growth.\n"
        "Risk\tFactors\nExit\tcap\trate\trisk: returns are sensitive.\n"
        "Exit\tStrategy\nSale in year five.\n")

SECTIONS = [{"heading": h} for h in (
    "Executive Summary", "Investment Highlights", "Risk Factors",
    "Exit Strategy")]


class SlicingTest(unittest.TestCase):
    def setUp(self):
        self.p = load_proposer()

    def test_every_heading_is_found_whatever_the_whitespace(self):
        out = self.p._slice_sections(TEXT, SECTIONS)
        self.assertEqual([located for _, located in out], [True] * 4)

    def test_each_section_gets_its_own_text_only(self):
        out = self.p._slice_sections(TEXT, SECTIONS)
        self.assertIn("120-unit", out[0][0])
        self.assertNotIn("rent growth", out[0][0])
        self.assertIn("Exit\tcap\trate", out[2][0])
        self.assertNotIn("year five", out[2][0])
        self.assertIn("year five", out[3][0])

    def test_case_is_not_the_heading(self):
        at, _ = self.p._find("RISK  FACTORS\nx", "Risk Factors")
        self.assertEqual(at, 0)

    def test_the_words_still_must_all_be_there(self):
        self.assertEqual(self.p._find(TEXT, "Risk Summary"), (-1, -1))
        out = self.p._slice_sections(TEXT, [{"heading": "Rent Roll"}])
        self.assertEqual(out[0][1], False)

    def test_a_heading_found_earlier_is_not_found_again_before_it(self):
        """A later section's heading is looked for after the one before it,
        so a phrase repeated in the body does not pull it back."""
        text = "Risk Factors appear below.\nSummary\nA\nRisk\tFactors\nB\n"
        out = self.p._slice_sections(
            text, [{"heading": "Summary"}, {"heading": "Risk Factors"}])
        self.assertTrue(out[1][0].startswith("Risk\tFactors"))

    def test_regex_characters_in_a_heading_are_taken_literally(self):
        at, _ = self.p._find("Pro Forma (5-Year) NOI\n", "Pro Forma (5-Year) NOI")
        self.assertEqual(at, 0)


if __name__ == "__main__":
    unittest.main()
