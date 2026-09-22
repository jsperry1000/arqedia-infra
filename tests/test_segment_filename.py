"""
The file name is a hint the classifier reads; the folder is not (18.7, 18.13).

    python -m unittest discover -s tests

TWO THINGS, AND THEY PULL OPPOSITE WAYS.

The first is that segment.segment now carries the filename into the prompt.
Until 18.13 it was forbidden to - rightly, when the alternative was typing FROM
the name, and wrongly once the name sits beside four thousand characters of the
document's own text. What these assert is not that the model behaves: it is
that the prompt SAYS the name, says plainly that it may mislead, and says the
content decides. That is the whole of what this code controls.

The second is that the scan path still does not classify at all. A scan has no
text, so a type would be a guess from the name and nothing else - which is the
thing 18.13 did not license. test_normalizer_refusal.ScanTest already asserts
segment is not called; the case here is narrower and is the one that would
break first if somebody "helpfully" passed the name along: that a scan's row
carries no type even though the filename is now a hint everywhere else.

Nothing reaches AWS: bedrock is a stub and the scan path never gets that far.
"""

import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

FILENAME = "Cocoa-Empire-Articles-of-Association.pdf"
FOLDER = "2024 statutory"
KEY = "tenants/9/docs/Test-Engagement-One/" + FILENAME


def load_segment():
    """segment.py with boto3 replaced, and MODEL_ID set.

    MODEL_ID is read at import, and segment() returns the one-part answer
    without building a prompt at all where it is unset - so a test that forgot
    this would pass while asserting nothing."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    with mock.patch.dict(sys.modules, {"boto3": boto3}), \
         mock.patch.dict(os.environ, {"CLASSIFIER_MODEL_ID": "a-model"}):
        spec = importlib.util.spec_from_file_location(
            "normalizer_segment", ROOT / "lambda/normalizer/segment.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class FakeRegistry:
    DOCUMENT_TYPES = {"articles": {}}

    def document_type_list(self):
        return [{"key": "articles", "category": "constitutional",
                 "label": "Articles of association",
                 "description": "The company's constitution."}]


UNITS = [{"index": 1, "kind": "page", "char_start": 0, "char_end": 20},
         {"index": 2, "kind": "page", "char_start": 20, "char_end": 40}]
TEXT = "A" * 20 + "B" * 20


class PromptTest(unittest.TestCase):
    """What the model is actually sent."""

    def setUp(self):
        self.segment = load_segment()
        answer = {"parts": [{"page_from": 1, "page_to": 2,
                             "document_type": "articles",
                             "confidence": "high", "contents": "the articles",
                             "boundary": "the whole file"}]}
        body = mock.MagicMock()
        body.read.return_value = json.dumps({
            "content": [{"type": "text", "text": json.dumps(answer)}],
            "usage": {"input_tokens": 11, "output_tokens": 7},
        }).encode("utf-8")
        self.segment._bedrock.invoke_model.return_value = {"body": body}

    def prompt(self, filename=None):
        self.segment.segment(TEXT, UNITS, FakeRegistry(), filename)
        sent = json.loads(
            self.segment._bedrock.invoke_model.call_args.kwargs["body"])
        return sent["messages"][0]["content"]

    # --- the name is there, and it is qualified ---------------------------

    def test_the_prompt_names_the_file(self):
        said = self.prompt(FILENAME)
        self.assertIn('The file is named "%s".' % FILENAME, said)

    def test_the_prompt_says_the_name_may_mislead(self):
        """The whole of 18.13 is 'a hint, weighed against the content'. A
        prompt carrying the name without that is a different decision."""
        said = self.prompt(FILENAME)
        self.assertIn("IT IS A HINT AND NOT AN ANSWER", said)
        self.assertIn("THE CONTENT WINS", said)
        self.assertIn("stale", said)

    def test_the_prompt_says_one_name_cannot_describe_several_documents(self):
        """A file holding four documents has one name. Left unsaid, the name
        is an argument against every boundary but the first."""
        said = self.prompt(FILENAME)
        self.assertIn("ONE NAME CANNOT DESCRIBE SEVERAL DOCUMENTS", said)
        self.assertIn("NEVER let it argue against a boundary", said)

    def test_the_name_cannot_invent_a_type(self):
        said = self.prompt(FILENAME)
        self.assertIn("IT NEVER CREATES A TYPE", said)

    def test_the_document_text_is_still_there(self):
        """The name is added beside the excerpts, never instead of them."""
        said = self.prompt(FILENAME)
        self.assertIn("--- FILE START ---", said)
        self.assertIn("A" * 20, said)
        self.assertIn("B" * 20, said)

    # --- and it is optional -----------------------------------------------

    def test_without_a_filename_the_prompt_is_what_it_was(self):
        """Not merely 'works without one'. A caller that cannot say must get
        the prompt as it stood before 18.13, or the change is not optional -
        it is a second prompt nobody reviewed."""
        said = self.prompt(None)
        self.assertNotIn("The file is named", said)
        self.assertNotIn("The file name:", said)
        self.assertNotIn("IT IS A HINT AND NOT AN ANSWER", said)

    def test_an_empty_filename_counts_as_none(self):
        self.assertNotIn("The file is named", self.prompt(""))
        self.assertNotIn("The file is named", self.prompt("   "))

    def test_the_folder_is_not_in_the_signature_at_all(self):
        """The strongest form of 'the classifier never reads the folder':
        there is nowhere to put one. A future caller cannot pass it by
        accident, because the parameter does not exist."""
        import inspect
        names = list(inspect.signature(self.segment.segment).parameters)
        self.assertEqual(names, ["raw_text", "units", "registry", "filename"])

    def test_the_answer_is_still_read(self):
        """The prompt changed; what comes back is parsed as before."""
        parts, usage = self.segment.segment(TEXT, UNITS, FakeRegistry(),
                                            FILENAME)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["document_type"], "articles")
        self.assertEqual(usage["input_tokens"], 11)


# --- the scan path ---------------------------------------------------------


def load_normalizer():
    """The normalizer, with everything below it replaced.

    extractors is a real module because the handler catches
    UnreadableDocument by identity - a mock would give a different class each
    time and the except clause would never fire."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions

    extractors = types.ModuleType("extractors")

    class UnreadableDocument(Exception):
        def __init__(self, reason, pages=None, chars=None):
            super().__init__(reason)
            self.reason = reason
            self.pages = pages
            self.chars = chars

    extractors.UnreadableDocument = UnreadableDocument
    extractors.extract = mock.MagicMock()

    config = types.ModuleType("config")
    config.active_revision = mock.MagicMock(return_value=7)
    config.load = mock.MagicMock()

    segment = types.ModuleType("segment")
    segment.segment = mock.MagicMock(return_value=([], {}))

    env = {"REVIEW_BUCKET": "review", "CLUSTER_ARN": "arn:cluster",
           "SECRET_ARN": "arn:secret", "DATABASE": "arqedia"}
    modules = {"boto3": boto3, "botocore": botocore,
               "botocore.exceptions": exceptions, "extractors": extractors,
               "config": config, "segment": segment}
    with mock.patch.dict(sys.modules, modules), \
         mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "normalizer_app_18_7", ROOT / "lambda/normalizer/app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, extractors


def plain(value):
    return None if "isNull" in value else next(iter(value.values()))


class FakeDb:
    def __init__(self):
        self.statements = []

    def sql(self, statement, params=None):
        self.statements.append((" ".join(statement.split()),
                                {p["name"]: plain(p["value"])
                                 for p in params or []}))
        return {"records": []}

    def inserts(self):
        return [(s, v) for s, v in self.statements
                if s.startswith("INSERT INTO document")]


class ScanKeepsItsSilenceTest(unittest.TestCase):
    """A scan is not classified, and the filename does not change that.

    The name is now a hint EVERYWHERE THERE IS TEXT TO WEIGH IT AGAINST. A
    scan has none, so a type taken from it would rest on the name alone -
    which is exactly what CLAUDE.md's "a type guessed from a filename would
    put a guess where a reading belongs" refuses, and what 18.13 did not
    license."""

    def setUp(self):
        self.app, self.extractors = load_normalizer()
        self.db = FakeDb()
        body = mock.MagicMock()
        body.read.return_value = b"%PDF-1.4 a scan"
        self.app._s3.get_object.return_value = {
            "Body": body, "VersionId": "v1",
            "Metadata": {"uploaded-by": "walk1@deus-ex.co",
                         "source-folder": FOLDER},
        }
        self.extractors.extract.side_effect = \
            self.extractors.UnreadableDocument("no_text_layer", pages=12,
                                               chars=340)

    def run_handler(self):
        with mock.patch.object(self.app, "_sql", self.db.sql):
            return self.app.lambda_handler(
                {"detail": {"bucket": {"name": "docs"},
                            "object": {"key": KEY}}}, None)

    def row(self):
        inserts = self.db.inserts()
        self.assertEqual(len(inserts), 1, "expected exactly one row")
        return inserts[0][1]

    def test_segment_is_not_called_even_with_a_telling_name(self):
        """The filename here names its own type outright. The scan path must
        still not ask."""
        self.run_handler()
        self.app.segment.segment.assert_not_called()

    def test_no_type_is_proposed_from_the_name(self):
        self.run_handler()
        values = self.row()
        self.assertIsNone(values["document_type"])
        self.assertIsNone(values["type_confidence"])

    def test_the_row_says_why_it_has_no_type(self):
        self.run_handler()
        self.assertEqual(self.row()["type_reason"], self.app.SCAN_REASON)

    def test_the_folder_is_recorded_on_a_scan_too(self):
        """Provenance does not depend on whether anything could be read."""
        self.run_handler()
        self.assertEqual(self.row()["source_folder"], FOLDER)


class TextPathTest(unittest.TestCase):
    """What the normalizer hands segment, and what it does not."""

    def setUp(self):
        self.app, self.extractors = load_normalizer()
        self.db = FakeDb()
        body = mock.MagicMock()
        body.read.return_value = b"%PDF-1.4 real text"
        self.app._s3.get_object.return_value = {
            "Body": body, "VersionId": "v1",
            "Metadata": {"uploaded-by": "walk1@deus-ex.co",
                         "source-folder": FOLDER},
        }
        self.extractors.extract.return_value = (TEXT, UNITS, "pdf")
        self.app.segment.segment.return_value = ([{
            "part_index": 1, "page_from": None, "page_to": None,
            "document_type": "articles", "confidence": "high",
            "why": "the articles", "boundary": "the whole file"}], {})

    def run_handler(self):
        with mock.patch.object(self.app, "_sql", self.db.sql):
            return self.app.lambda_handler(
                {"detail": {"bucket": {"name": "docs"},
                            "object": {"key": KEY}}}, None)

    def test_the_filename_is_passed_to_segment(self):
        self.run_handler()
        args = self.app.segment.segment.call_args.args
        self.assertEqual(args[3], FILENAME)

    def test_the_folder_is_not_passed_to_segment(self):
        """The decision that has stood since the product was described:
        letting a folder hint would put a counterparty's filing habits into
        our classification, and two tenants would get different answers from
        the same document."""
        self.run_handler()
        call = self.app.segment.segment.call_args
        self.assertNotIn(FOLDER, [str(a) for a in call.args])
        self.assertNotIn(FOLDER, [str(v) for v in call.kwargs.values()])

    def test_the_folder_reaches_the_row(self):
        self.run_handler()
        inserts = self.db.inserts()
        self.assertEqual(len(inserts), 1)
        self.assertEqual(inserts[0][1]["source_folder"], FOLDER)

    def test_no_folder_is_null_rather_than_empty(self):
        """Absent means 'not a directory upload'. An empty string in the
        column would mean 'the root'."""
        self.app._s3.get_object.return_value["Metadata"] = {
            "uploaded-by": "walk1@deus-ex.co"}
        self.run_handler()
        self.assertIsNone(self.db.inserts()[0][1]["source_folder"])


if __name__ == "__main__":
    unittest.main()
