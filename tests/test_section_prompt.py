"""
A section's own instruction decides its form (16 October 2026).

    python -m unittest discover -s tests

The defect being closed: memo 191's Suppliers section was configured as "one
short paragraph ... then a table" and came back as three paragraphs, a region
table and a closing Note. The instruction reached the model, but appended to
the user message, while CLEANUP_PREAMBLE's own shape rules sat in the system
prompt and won. The section prompt replaced SECTION_PRESENTATION and nothing
else.

Nothing reaches AWS: boto3 is replaced at import and _invoke is a stub.
"""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / "lambda" / "composition"
SHARED = ROOT / "lambda" / "shared"

ENV = {
    "CLUSTER_ARN": "arn:cluster", "SECRET_ARN": "arn:secret",
    "DATABASE": "arqedia", "CURATED_BUCKET": "curated",
    "MODEL_ID": "model", "RENDER_FUNCTION": "render",
}

SUPPLIERS_PROMPT = (
    "Write one short paragraph describing the types of entities from which "
    "the SUBJECT buys its goods (f_suppliers). Then display a table of all "
    "identified suppliers using the data in f_suppliers.")

ASSEMBLED = (
    "**Source: schedule.pdf**\n\n"
    "- **Trade Flows (f_trade_flows):** pecans  \n  *schedule.pdf, page 1*\n")


def load_composition():
    """composition's app.py, with cleanup and config as it imported them."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    config = types.ModuleType("botocore.config")
    config.Config = mock.MagicMock()
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.config = config
    botocore.exceptions = exceptions
    fakes = {"boto3": boto3, "botocore": botocore,
             "botocore.config": config, "botocore.exceptions": exceptions}
    saved = list(sys.path)
    with mock.patch.dict(sys.modules, fakes), mock.patch.dict(os.environ, ENV):
        sys.path[:0] = [str(COMPOSITION), str(SHARED)]
        try:
            for name in ("cleanup", "config"):
                sys.modules.pop(name, None)
            spec = importlib.util.spec_from_file_location(
                "composition_app", COMPOSITION / "app.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            sys.path[:] = saved
    return module


def section(kind="extract", prompt=None, key="suppliers"):
    return {"key": key, "num": "IV", "title": "Suppliers", "kind": kind,
            "prompt": prompt, "fields": ["f_trade_flows"]}


class Consolidation(unittest.TestCase):

    def setUp(self):
        self.app = load_composition()
        self.cleanup = self.app.cleanup
        self.calls = []

        def invoke(prompt, system=None, **_):
            self.calls.append({"prompt": prompt, "system": system})
            return "## IV. Suppliers\n\ntext", {}

        patcher = mock.patch.object(self.app, "_invoke", side_effect=invoke)
        patcher.start()
        self.addCleanup(patcher.stop)

    def consolidate(self, sec):
        self.app._consolidate(sec, ASSEMBLED)
        return self.calls[-1]

    # --- no instruction: exactly what it was -------------------------------

    def test_without_an_instruction_the_prompt_is_unchanged(self):
        """The formula as it stood before, written out, so any drift in the
        unprompted path fails here rather than in a memo."""
        sec = section(key="business")
        call = self.consolidate(sec)
        masked, _ = self.app._mask_citations(ASSEMBLED)
        before = (
            self.cleanup.CLEANUP_PROMPT
            + self.cleanup.presentation_for("business")
            + self.cleanup.CITATION_TOKENS
            + "\n\n--- SECTION START ---\n"
            + "## IV. Suppliers\n\n"
            + masked
            + "\n--- SECTION END ---"
        )
        self.assertEqual(call["prompt"], before)
        self.assertEqual(call["system"], self.cleanup.CLEANUP_PREAMBLE)

    def test_a_whitespace_prompt_is_no_instruction(self):
        call = self.consolidate(section(prompt="   "))
        self.assertEqual(call["system"], self.cleanup.CLEANUP_PREAMBLE)

    # --- an instruction decides the form ------------------------------------

    def test_an_instruction_is_given_as_the_instruction(self):
        call = self.consolidate(section(prompt=SUPPLIERS_PROMPT))
        self.assertIn("INSTRUCTION\n" + SUPPLIERS_PROMPT + "\n", call["prompt"])
        self.assertTrue(call["prompt"].startswith(
            self.cleanup.INSTRUCTED_PROMPT))
        self.assertEqual(call["system"], self.cleanup.INSTRUCTED_PREAMBLE)

    def test_the_shape_rules_that_outranked_it_are_gone(self):
        call = self.consolidate(section(prompt=SUPPLIERS_PROMPT))
        for rule in ("Open the section with one sentence",
                     "grouped on a meaningful axis",
                     "beginning '**Note.**'",
                     "Merge the repeated extracts into one account"):
            self.assertNotIn(rule, call["system"] + call["prompt"])

    def test_a_disagreement_is_still_stated(self):
        self.assertIn("say the sources disagree, naming each, in whatever "
                      "form the instruction allows",
                      self.cleanup.INSTRUCTED_PREAMBLE)

    def test_a_gap_is_kept_even_where_not_asked_for(self):
        self.assertIn("even where the instruction does not ask for one",
                      self.cleanup.INSTRUCTED_PREAMBLE)
        self.assertIn("'> **Gap.**'", self.cleanup.INSTRUCTED_PREAMBLE)

    def test_citations_are_still_protected(self):
        call = self.consolidate(section(prompt=SUPPLIERS_PROMPT))
        self.assertIn(self.cleanup.CITATION_TOKENS, call["prompt"])
        self.assertNotIn("schedule.pdf", call["prompt"])

    # --- a composed section keeps the form it was drafted in ----------------

    def test_a_composed_section_is_consolidated_under_the_rules_alone(self):
        call = self.consolidate(section(kind="composed",
                                        prompt=SUPPLIERS_PROMPT))
        self.assertEqual(call["system"], self.cleanup.INSTRUCTED_PREAMBLE)
        self.assertIn(self.cleanup.COMPOSED_INSTRUCTION, call["prompt"])
        self.assertNotIn(SUPPLIERS_PROMPT, call["prompt"])

    def test_a_composed_section_without_a_prompt_gets_the_same(self):
        call = self.consolidate(section(kind="composed"))
        self.assertEqual(call["system"], self.cleanup.INSTRUCTED_PREAMBLE)


class Keys(unittest.TestCase):
    """The instruction names keys; the context now carries them."""

    def setUp(self):
        self.app = load_composition()
        registry = mock.MagicMock()
        registry.label_for.side_effect = {
            "f_trade_flows": "Trade Flows", "f_suppliers": "Suppliers"}.get
        registry.group_columns.side_effect = {
            "f_suppliers": [("f_suppliers.name", "Name", "text", "")]}.get
        self.registry = registry

    def value(self, field_id, value, ordinal=None):
        return {"value_id": 1, "field_id": field_id, "value": value,
                "locator_kind": "page", "locator_index": 1,
                "row_ordinal": ordinal, "document_id": 9,
                "filename": "schedule.pdf"}

    def test_a_single_field_carries_its_key(self):
        markdown, _ = self.app._assemble_extract(
            self.registry, {"fields": ["f_trade_flows"]},
            [self.value("f_trade_flows", "pecans")])
        self.assertIn("- **Trade Flows (f_trade_flows):** pecans", markdown)

    def test_a_group_table_carries_its_key(self):
        markdown, _ = self.app._assemble_extract(
            self.registry, {"fields": ["f_suppliers"]},
            [self.value("f_suppliers.name", "Supplier 1", ordinal=1)])
        self.assertIn("**Suppliers (f_suppliers)**", markdown)
        self.assertIn("| Name |", markdown)


if __name__ == "__main__":
    unittest.main()
