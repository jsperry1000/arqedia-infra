"""
A split file is read once, and each part reads only its own pages, numbered
as the file numbers them (ocr-split-parts, 5 October 2026). Run from the
repository root:

    python -m unittest discover -s tests

The defects: every part started its own Textract job on the whole file (the
Manty accounts: 56 pages billed for 14), and the collector cut nothing, so
the first part of a set of accounts was extracted against pages 5-14 and
cited them - doc 1058, 17 values, every one outside pages 1-4.
"""

import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from api_modules import load_api, rows

ROOT = Path(__file__).resolve().parents[1]


def load_textract():
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    with mock.patch.dict(sys.modules, {"boto3": boto3}):
        spec = importlib.util.spec_from_file_location(
            "textract_split", ROOT / "lambda/shared/textract.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def line(page, text):
    return {"BlockType": "LINE", "Page": page, "Text": text}


# A 14-page file, a line per page, read in one job.
BLOCKS = [line(p, "page %d text" % p) for p in range(1, 15)]


class AssembleTest(unittest.TestCase):
    """What one part is given out of its file's blocks."""

    def setUp(self):
        self.t = load_textract()

    def test_a_part_gets_only_its_own_pages(self):
        text, units, _ = self.t.assemble(BLOCKS, 1, 4)
        self.assertEqual([u["index"] for u in units], [1, 2, 3, 4])
        self.assertNotIn("page 5 text", text)

    def test_pages_keep_the_files_numbers(self):
        """As the digital path keeps them (normalizer _slice): the part
        covering 5-14 cites page 5 for its first page, not page 1."""
        text, units, _ = self.t.assemble(BLOCKS, 5, 14)
        self.assertEqual(units[0]["index"], 5)
        self.assertEqual(units[-1]["index"], 14)
        self.assertNotIn("page 4 text", text)

    def test_offsets_are_relative_to_the_parts_own_text(self):
        text, units, _ = self.t.assemble(BLOCKS, 5, 14)
        self.assertEqual(units[0]["char_start"], 0)
        for u in units:
            self.assertEqual(text[u["char_start"]:u["char_end"]],
                             "page %d text" % u["index"])

    def test_a_whole_file_is_unchanged_in_shape(self):
        text, units, _ = self.t.assemble(BLOCKS)
        self.assertEqual([u["index"] for u in units], list(range(1, 15)))

    def test_an_empty_part_names_its_own_first_page(self):
        _, units, _ = self.t.assemble([], 5, 14)
        self.assertEqual(units[0]["index"], 5)


def load_collector():
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    textract = types.ModuleType("textract")
    wallet = types.ModuleType("wallet")
    env = {"REVIEW_BUCKET": "review", "CLUSTER_ARN": "c", "SECRET_ARN": "s",
           "DATABASE": "d"}
    with mock.patch.dict(sys.modules, {"boto3": boto3, "botocore": botocore,
                                       "botocore.exceptions": exceptions,
                                       "textract": textract,
                                       "wallet": wallet}), \
            mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "collector_app", ROOT / "lambda/collector/app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    module.textract = load_textract()
    return module


KEY = "tenants/5/docs/MANTY/accounts.pdf"
PARTS = [
    # document_id, tenant_id, s3_key, type, mode, page_from, part_index,
    # charge_entry_id, page_to
    (1058, 5, KEY, "audited-statements", "text", 1, 1, 9, 4),
    (1059, 5, KEY, "audited-statements", "text", 5, 2, 9, 14),
]


def event(status="SUCCEEDED"):
    return {"Records": [{"Sns": {"Message": json.dumps(
        {"JobId": "job-1", "Status": status})}}]}


class CollectorTest(unittest.TestCase):
    def setUp(self):
        self.app = load_collector()
        self.written = {}

        def put(Bucket, Key, Body, ContentType):
            self.written[Key] = json.loads(Body.decode("utf-8"))

        self.app._s3.put_object.side_effect = put
        self.app._s3.get_object.return_value = {
            "Body": mock.MagicMock(read=lambda: b"{}")}

    def run_with(self, status="SUCCEEDED"):
        def sql(statement, params=None):
            if "FROM document" in statement and "textract_job_id" in statement:
                return rows(*PARTS)
            return {"records": []}

        with mock.patch.object(self.app, "_sql", side_effect=sql), \
                mock.patch.object(self.app.textract, "fetch_blocks",
                                  return_value=BLOCKS) as fetch, \
                mock.patch.object(self.app, "wallet") as wallet:
            wallet.refund.return_value = {"refunded": True}
            out = self.app.lambda_handler(event(status), None)
        return out, fetch, wallet

    def test_every_part_on_the_job_is_collected_from_one_fetch(self):
        out, fetch, _ = self.run_with()
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual([r["document_id"] for r in out["collected"]],
                         [1058, 1059])

    def test_each_part_reads_only_its_own_pages(self):
        self.run_with()
        first = self.written[KEY + ".p1.normalized.json"]
        second = self.written[KEY + ".p2.normalized.json"]
        self.assertEqual([u["index"] for u in first["units"]], [1, 2, 3, 4])
        self.assertEqual([u["index"] for u in second["units"]],
                         list(range(5, 15)))
        self.assertNotIn("page 6 text", first["raw_text"])

    def test_a_failed_job_refunds_every_part(self):
        out, fetch, wallet = self.run_with(status="FAILED")
        fetch.assert_not_called()
        self.assertEqual(wallet.refund.call_count, 2)
        self.assertEqual([r["document_id"] for r in out["collected"]],
                         [1058, 1059])


class OneJobPerFileTest(unittest.TestCase):
    """Filing two thin parts of one file starts one job, not two."""

    def setUp(self):
        self.app = load_api()

    def test_two_parts_of_one_file_share_one_job(self):
        class Registry:
            DOCUMENT_TYPES = {"audited-statements": {}}

            def read_mode_for(self, t):
                return "text"

            def always_ocr(self, t):
                return False

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            if s.startswith("SELECT subject_name"):
                return rows(("Manty SA",))
            if s.startswith("SELECT document_id, filename, state"):
                return rows((1058, "a.pdf", "analysed", None,
                             "audited-statements"),
                            (1059, "a.pdf", "analysed", None,
                             "audited-statements"))
            if s.startswith("SELECT s3_key, thin_text"):
                d = [p["value"]["longValue"] for p in params
                     if p["name"] == "d"][0]
                return rows((KEY, True, 1 if d == 1058 else 5,
                             1 if d == 1058 else 2))
            return {"records": []}

        with mock.patch.object(self.app, "_sql", side_effect=sql), \
                mock.patch.object(self.app, "wallet") as wallet, \
                mock.patch.object(self.app, "config") as config, \
                mock.patch.object(self.app, "textract") as textract:
            config.for_tenant.return_value = Registry()
            wallet.charge.return_value = {"entry_id": 9}
            textract.start.return_value = ("job-1", "text")
            out = self.app.file_documents(
                5, "clerk@firm.com", "MANTY",
                [{"document_id": 1058}, {"document_id": 1059}], "key-1")

        self.assertEqual(textract.start.call_count, 1)
        self.assertEqual(out["reading"], 2)


if __name__ == "__main__":
    unittest.main()
