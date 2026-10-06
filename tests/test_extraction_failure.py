"""
One schema's failure is one schema's. Run from the repository root:

    python -m unittest discover -s tests

The defect being closed: a document routed to twenty-one schemas lost the
twenty that worked because the first one raised, and then said
"extracting..." for ever because the UPDATE at the end of the handler never
ran. On 5 September that cost 102 documents in tenant 2.

So the tests that matter are the ones proving the OTHER schemas still wrote,
and that the row says what happened rather than staying silent.
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

KEY = "tenants/2/docs/COCOA-EMPIRE/Deck.pdf.normalized.json"

# A field's tuple is five parts; a group's is six, the sixth being its
# columns. This is the shape config.py hands over for a config_field row
# whose cardinality says 'group' and whose group_key is NULL - five parts,
# calling itself a group. field[5] on it is the IndexError.
MALFORMED_GROUP = ("f_ownership_and_control", "Ownership And Control",
                   "group", "group", "who owns it")

GOOD_GROUP = ("f_directors", "Directors", "group", "group", "who runs it",
              [("f_directors.name", "Name", "string", "their name")])

SINGLE = ("f_company_name", "Company Name", "string", "one",
          "the registered name")


def load_extraction():
    """The extractor, with boto3, botocore and config replaced."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions

    config = types.ModuleType("config")
    config.load = mock.MagicMock()

    env = {"CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
           "DATABASE": "arqedia", "MODEL_ID": "anthropic.haiku-test"}
    modules = {"boto3": boto3, "botocore": botocore,
               "botocore.exceptions": exceptions, "config": config}
    with mock.patch.dict(sys.modules, modules), \
            mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "extraction_app", ROOT / "lambda/extraction/app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, config


def plain(value):
    return None if "isNull" in value else next(iter(value.values()))


class FakeRegistry:
    """What config.load returns: the schemas a document type routes to."""

    def __init__(self, schemas):
        self._schemas = schemas

    def schemas_for(self, document_type):
        return list(self._schemas.keys())

    def get_schema(self, schema_key):
        return self._schemas.get(schema_key)


class FakeDb:
    """Every statement, and the one answer any of them needs.

    `subject` is what the engagement holds (migration 031). Extraction reads
    it before anything else and refuses where there is none, so a fake that
    answered every SELECT with no rows would send every test below down the
    refusal path. None is that path, asked for deliberately."""

    def __init__(self, subject="Cocoa Empire"):
        self.statements = []
        self.subject = subject

    def sql(self, statement, params=None):
        s = " ".join(statement.split())
        self.statements.append((s, {p["name"]: plain(p["value"])
                                    for p in params or []}))
        if s.startswith("SELECT e.subject_name"):
            if self.subject is None:
                return {"records": []}
            return {"records": [[{"stringValue": self.subject}]]}
        return {"records": []}

    def matching(self, start):
        return [(s, v) for s, v in self.statements if s.startswith(start)]


ENVELOPE = {
    "tenant_id": 2,
    "document_id": 753,
    "config_revision": 2,
    "document_type": "corporate-legal-deck",
    "units": [{"index": 1, "kind": "page", "char_start": 0, "char_end": 24,
               "label": None}],
    "raw_text": "Cocoa Empire Uganda Ltd.",
}

EVENT = {"detail": {"bucket": {"name": "review"}, "object": {"key": KEY}}}


class ExtractionFailureTest(unittest.TestCase):
    def setUp(self):
        self.app, self.config = load_extraction()
        self.db = FakeDb()

        body = mock.MagicMock()
        body.read.return_value = json.dumps(ENVELOPE).encode("utf-8")
        self.app._s3.get_object.return_value = {"Body": body}

    def run_handler(self, schemas, reply=None):
        """Run the handler over these schemas, in this order.

        The model is stubbed rather than Bedrock, because what is under test
        is what the handler does with a schema that raises before the model
        is ever reached."""
        self.config.load.return_value = FakeRegistry(schemas)
        answer = reply if reply is not None else {
            "f_company_name": {"value": "Cocoa Empire Uganda Ltd.", "unit": 1},
            "f_directors": {"rows": [{"name": "I. Arrigazzi", "unit": 1}],
                            "unit": 1},
        }
        usage = {"input_tokens": 11, "output_tokens": 7}
        with mock.patch.object(self.app, "_sql", self.db.sql), \
                mock.patch.object(self.app, "_invoke",
                                  return_value=(answer, usage)):
            return self.app.lambda_handler(EVENT, None)

    def marked(self):
        updates = self.db.matching("UPDATE document SET extracted_at")
        self.assertEqual(len(updates), 1, "expected exactly one UPDATE")
        return updates[0][1]

    def values(self):
        return [v["field_id"]
                for _, v in self.db.matching("INSERT INTO extracted_value")]

    # --- the guard itself --------------------------------------------------

    def test_a_five_part_group_is_refused_by_name(self):
        with self.assertRaises(self.app.MalformedGroup) as caught:
            self.app._group_columns(MALFORMED_GROUP)
        self.assertIn("f_ownership_and_control", str(caught.exception))

    def test_a_proper_group_gives_its_columns(self):
        self.assertEqual(self.app._group_columns(GOOD_GROUP), GOOD_GROUP[5])

    # --- the whole document ------------------------------------------------

    def test_a_malformed_group_does_not_stop_the_other_schemas(self):
        """The one that matters. The bad schema runs FIRST, which is the
        order that used to lose everything behind it."""
        result = self.run_handler({
            "bad": {"fields": [MALFORMED_GROUP]},
            "good": {"fields": [SINGLE, GOOD_GROUP]},
        })

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["results"]["bad"]["status"], "failed")
        self.assertEqual(result["results"]["bad"]["error"], "MalformedGroup")
        self.assertEqual(result["results"]["good"]["status"], "extracted")

        # The good schema's values are written, both shapes of them.
        self.assertIn("f_company_name", self.values())
        self.assertIn("f_directors.name", self.values())
        self.assertEqual(result["values_written"], 2)

    def test_a_malformed_group_marks_the_row(self):
        self.run_handler({
            "bad": {"fields": [MALFORMED_GROUP]},
            "good": {"fields": [SINGLE]},
        })
        row = self.marked()
        self.assertEqual(row["error"], "group_key_missing")
        self.assertEqual(row["d"], 753)
        self.assertEqual(row["t"], 2)

    def test_nothing_is_written_for_the_schema_that_failed(self):
        self.run_handler({"bad": {"fields": [MALFORMED_GROUP]}})
        self.assertEqual(self.values(), [])
        self.assertEqual(self.marked()["error"], "group_key_missing")

    def test_any_other_exception_is_recorded_and_carried_past(self):
        """A schema that fails for a reason nobody anticipated is still one
        schema's failure, and still says so on the row."""
        self.config.load.return_value = FakeRegistry({
            "boom": {"fields": [SINGLE]},
            "good": {"fields": [SINGLE]},
        })
        answers = [
            RuntimeError("bedrock said no"),
            ({"f_company_name": {"value": "Cocoa Empire Uganda Ltd.",
                                 "unit": 1}},
             {"input_tokens": 11, "output_tokens": 7}),
        ]

        def invoke(_prompt):
            outcome = answers.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch.object(self.app, "_sql", self.db.sql), \
                mock.patch.object(self.app, "_invoke", invoke):
            result = self.app.lambda_handler(EVENT, None)

        self.assertEqual(result["results"]["boom"]["status"], "failed")
        self.assertEqual(result["results"]["good"]["status"], "extracted")
        self.assertEqual(self.marked()["error"], "schema_failed")
        self.assertIn("f_company_name", self.values())

    # --- and the clean case, which must stay clean -------------------------

    def test_a_clean_run_writes_a_null_error(self):
        """Written NULL rather than left alone: a document re-extracted after
        its configuration was fixed must not keep yesterday's fault."""
        result = self.run_handler({"good": {"fields": [SINGLE, GOOD_GROUP]}})
        self.assertIsNone(result["extraction_error"])
        self.assertIsNone(self.marked()["error"])
        self.assertEqual(result["results"]["good"]["status"], "extracted")


class SubjectTest(unittest.TestCase):
    """Whose facts this document holds (SUBJ-01).

    The defect being closed: memo 120 described GoodFlow - a BUYER - as the
    specialist originator, under a citation to a page that says Cocoa Empire
    Uganda Limited. The description and the citation were both right. Nothing
    in the pipeline had ever been told which company the memorandum was for.
    """

    def setUp(self):
        self.app, self.config = load_extraction()
        body = mock.MagicMock()
        body.read.return_value = json.dumps(ENVELOPE).encode("utf-8")
        self.app._s3.get_object.return_value = {"Body": body}

    def run_with(self, subject):
        """The handler over one ordinary schema, with this subject."""
        db = FakeDb(subject=subject)
        self.config.load.return_value = FakeRegistry(
            {"good": {"fields": [SINGLE]}})
        invoke = mock.MagicMock(return_value=(
            {"f_company_name": {"value": "Cocoa Empire Uganda Ltd.",
                                "unit": 1}},
            {"input_tokens": 11, "output_tokens": 7}))
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_invoke", invoke):
            return self.app.lambda_handler(EVENT, None), db, invoke

    def test_no_subject_refuses_before_the_model_is_called(self):
        """Refused, not read and hoped over. A model call here would cost
        money and produce values nobody can trust."""
        result, db, invoke = self.run_with(None)

        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["extraction_error"], "subject_missing")
        self.assertEqual(result["values_written"], 0)
        invoke.assert_not_called()
        self.assertEqual(
            [v["field_id"]
             for _, v in db.matching("INSERT INTO extracted_value")], [])

    def test_the_refusal_is_on_the_row(self):
        """In the column migration 029 added, which the screen already reads
        - one code, one place to look."""
        _, db, _ = self.run_with(None)
        updates = db.matching("UPDATE document SET extracted_at")
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][1]["error"], "subject_missing")
        self.assertEqual(updates[0][1]["d"], 753)
        self.assertEqual(updates[0][1]["t"], 2)

    def test_the_envelope_is_marked_complete_on_a_refusal(self):
        """Our own write re-fires the trigger. Without this the refusal
        loops for ever, refusing the same document every few seconds."""
        _, _, _ = self.run_with(None)
        written = json.loads(
            self.app._s3.put_object.call_args.kwargs["Body"].decode("utf-8"))
        self.assertTrue(written["extraction_complete"])
        self.assertEqual(written["extraction_error"], "subject_missing")
        self.assertIsNone(written["subject_name"])

    def test_whitespace_is_no_subject(self):
        """A column holding three spaces is a column holding nothing."""
        result, _, invoke = self.run_with("   ")
        self.assertEqual(result["extraction_error"], "subject_missing")
        invoke.assert_not_called()

    def test_the_subject_opens_the_prompt(self):
        """Before the field list, because the descriptions are read in its
        light: "description of the SUBJECT" means nothing until the model
        has been told which company that is."""
        result, _, invoke = self.run_with("Cocoa Empire")

        self.assertEqual(result["status"], "ok")
        prompt = invoke.call_args.args[0]
        self.assertTrue(prompt.startswith(
            "The subject of this file is **Cocoa Empire**."), prompt[:120])
        self.assertIn("Treat any name that refers to the same company",
                      prompt)
        self.assertIn("is not the subject", prompt)
        # The field list still follows it, unchanged.
        self.assertIn("f_company_name", prompt)

    def test_the_subject_is_recorded_on_the_envelope(self):
        """Beside model_id, for the same reason: a value should be traceable
        to the subject it was read under. The engagement's subject is
        editable, so this is the only record of what it was at the time."""
        self.run_with("Cocoa Empire")
        written = json.loads(
            self.app._s3.put_object.call_args.kwargs["Body"].decode("utf-8"))
        self.assertEqual(written["subject_name"], "Cocoa Empire")

    def test_a_document_with_no_engagement_has_no_subject(self):
        """The join is inner: a document whose engagement_id is NULL returns
        no row, and that is the honest answer rather than a default."""
        with mock.patch.object(self.app, "_sql",
                               lambda s, p=None: {"records": []}):
            self.assertIsNone(self.app._subject_for(2, 753))


if __name__ == "__main__":
    unittest.main()
