"""
An engagement is a row, and everything written into one says so (13.3).

    python -m unittest discover -s tests

Stage 2 of the plan: four writers learn the new columns while every list goes
on matching the S3 key. So these tests are about what is WRITTEN, never about
what is read - switching the reads is stage 4 and is not built.

The rule under all of it is that one name is one row. It is written twice, in
lambda/api/app.py and lambda/normalizer/app.py, because a shared module would
reach both only through the docprocessing layer; the last two tests here are
what stop the copies drifting.

Nothing reaches AWS: boto3 is replaced at import and _sql is a stub.
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
from test_normalizer_refusal import load_normalizer

ROOT = Path(__file__).resolve().parents[1]

TENANT = 7
NAME = "Meridian-Trading"
ENGAGEMENT_ID = 42


def load_composition():
    """Composition, with everything it talks to replaced. Imported for one
    pure function, so nothing below the import is exercised."""
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    botocore = types.ModuleType("botocore")
    botocore_config = types.ModuleType("botocore.config")
    botocore_config.Config = mock.MagicMock()
    exceptions = types.ModuleType("botocore.exceptions")
    exceptions.ClientError = type("ClientError", (Exception,), {})
    botocore.exceptions = exceptions
    botocore.config = botocore_config

    cleanup = types.ModuleType("cleanup")
    config = types.ModuleType("config")

    env = {"CURATED_BUCKET": "curated", "CLUSTER_ARN": "arn:cluster",
           "SECRET_ARN": "arn:secret", "DATABASE": "arqedia",
           "MODEL_ID": "model", "RENDER_FUNCTION": "render"}
    modules = {"boto3": boto3, "botocore": botocore,
               "botocore.config": botocore_config,
               "botocore.exceptions": exceptions,
               "cleanup": cleanup, "config": config}
    with mock.patch.dict(sys.modules, modules), mock.patch.dict(os.environ, env):
        spec = importlib.util.spec_from_file_location(
            "composition_app", ROOT / "lambda/composition/app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def plain(value):
    """A Data API parameter as the value that went into it. isNull is None,
    not True - which is exactly the confusion these tests exist to catch."""
    return None if value.get("isNull") else next(iter(value.values()))


def sent(params):
    return {p["name"]: plain(p["value"]) for p in params or []}


class Db:
    """A stub that answers the two-step resolve: a SELECT that may find
    nothing, an INSERT, then a SELECT that finds it."""

    def __init__(self, exists=False):
        self.exists = exists
        self.statements = []

    def sql(self, statement, params=None, tx=None):
        s = " ".join(statement.split())
        self.statements.append((s, sent(params)))

        if s.startswith("SELECT engagement_id FROM engagement"):
            return rows((ENGAGEMENT_ID,)) if self.exists else rows()
        if s.startswith("INSERT INTO engagement"):
            # The row exists from here on, as it would in the database.
            self.exists = True
            return {"records": [], "numberOfRecordsUpdated": 1}
        return rows()

    def kinds(self):
        """Each statement as its first three words, which is enough to tell
        the four apart and short enough to assert on."""
        return [" ".join(s.split()[:3]) for s, _ in self.statements]


class ApiResolveTest(unittest.TestCase):
    """lambda/api/app.py: the copy that runs when somebody types the name."""

    def setUp(self):
        self.app = load_api()

    def resolve(self, exists, name=NAME, by="partner@firm.com"):
        db = Db(exists=exists)
        with mock.patch.object(self.app, "_sql", db.sql):
            return self.app.engagement_id(TENANT, name, by), db

    def test_a_name_never_seen_before_is_created(self):
        found, db = self.resolve(exists=False)
        self.assertEqual(found, ENGAGEMENT_ID)
        # Read, written, read back: not LAST_INSERT_ID, which is per
        # connection and which the Data API does not promise.
        self.assertEqual(db.kinds(),
                         ["SELECT engagement_id FROM",
                          "INSERT INTO engagement",
                          "SELECT engagement_id FROM"])
        _, wrote = db.statements[1]
        self.assertEqual((wrote["t"], wrote["n"], wrote["by"]),
                         (TENANT, NAME, "partner@firm.com"))

    def test_a_name_already_held_is_found_and_nothing_is_written(self):
        found, db = self.resolve(exists=True)
        self.assertEqual(found, ENGAGEMENT_ID)
        self.assertEqual(db.kinds(), ["SELECT engagement_id FROM"])

    def test_the_insert_cannot_mint_a_second_row_for_one_name(self):
        """Two uploads racing each other: the second insert is absorbed by the
        unique key and the read that follows is what answers."""
        _, db = self.resolve(exists=False)
        statement, _ = db.statements[1]
        self.assertIn("ON DUPLICATE KEY UPDATE engagement_id = engagement_id",
                      statement)

    def test_an_empty_name_is_no_engagement(self):
        found, db = self.resolve(exists=False, name="   ")
        self.assertIsNone(found)
        self.assertEqual(db.statements, [])


class ApiUploadTest(unittest.TestCase):
    """The engagement becomes a row at the moment its name is typed."""

    def setUp(self):
        self.app = load_api()

    def test_uploading_creates_the_engagement(self):
        db = Db(exists=False)
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_s3") as s3:
            s3.generate_presigned_url.return_value = "https://signed"
            out = self.app.upload_url(TENANT, "partner@firm.com",
                                      NAME, "Articles.pdf")

        self.assertEqual(out["key"],
                         "tenants/7/docs/Meridian-Trading/Articles.pdf")
        self.assertIn("INSERT INTO engagement", db.kinds())
        # created_by is recorded HERE or nowhere: the normalizer meets the
        # same name later with only an object and its metadata.
        _, wrote = db.statements[1]
        self.assertEqual(wrote["by"], "partner@firm.com")

    def test_a_name_already_held_is_not_written_again(self):
        db = Db(exists=True)
        with mock.patch.object(self.app, "_sql", db.sql), \
                mock.patch.object(self.app, "_s3") as s3:
            s3.generate_presigned_url.return_value = "https://signed"
            self.app.upload_url(TENANT, "partner@firm.com", NAME, "a.pdf")
        self.assertNotIn("INSERT INTO engagement", db.kinds())


class ReviseInheritsTest(unittest.TestCase):
    """A revision is the same matter as its parent, and in the same state."""

    def setUp(self):
        self.app = load_api()

    def revise(self, state="live", engagement=ENGAGEMENT_ID):
        written = {}

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            values = sent(params)
            if s.startswith("SELECT s3_key, template_key"):
                return rows(("tenants/7/memos/Meridian-Trading/credit.md",
                             "credit-memorandum", 11, None, 1,
                             engagement, state))
            if s.startswith("SELECT DISTINCT d.filename"):
                return rows()
            if s.startswith("SELECT COALESCE(MAX(revision), 0)"):
                return rows((1,))
            if s.startswith("INSERT INTO memo "):
                written.update(values)
                return {"generatedFields": [{"longValue": 99}]}
            return rows()

        with mock.patch.object(self.app, "_sql", sql), \
                mock.patch.object(self.app, "_s3") as s3, \
                mock.patch.object(self.app, "_lambda"), \
                mock.patch.object(self.app, "_put_working"):
            s3.put_object.return_value = {"VersionId": "v1"}
            out = self.app.revise_memo(TENANT, "author@firm.com", 11,
                                       "# A memorandum\n\nText.\n")
        return out, written

    def test_the_revision_lands_in_the_parents_engagement(self):
        out, written = self.revise()
        self.assertEqual(out["memo_id"], 99)
        self.assertEqual(written["engagement_id"], ENGAGEMENT_ID)

    def test_revising_something_archived_does_not_unarchive_it(self):
        """The state belongs to the line. A revision that came back 'live'
        would quietly put a tidied-away matter back in the list."""
        _, written = self.revise(state="archived")
        self.assertEqual(written["state"], "archived")

    def test_an_ordinary_revision_stays_live(self):
        _, written = self.revise(state="live")
        self.assertEqual(written["state"], "live")

    def test_a_parent_with_no_engagement_yields_none_rather_than_a_guess(self):
        """Before the backfill, or after a key that did not match the pattern.
        Recorded as it stands."""
        _, written = self.revise(engagement=None)
        self.assertIsNone(written["engagement_id"])


class CompositionTest(unittest.TestCase):
    """A memo belongs where the documents it was written from belong."""

    def setUp(self):
        self.app = load_composition()

    def test_it_takes_the_engagement_from_its_documents(self):
        values = [{"document_id": 1, "engagement_id": ENGAGEMENT_ID},
                  {"document_id": 2, "engagement_id": ENGAGEMENT_ID}]
        self.assertEqual(self.app._engagement_of(values), ENGAGEMENT_ID)

    def test_a_document_without_one_does_not_stop_the_memo(self):
        values = [{"document_id": 1, "engagement_id": None},
                  {"document_id": 2, "engagement_id": ENGAGEMENT_ID}]
        self.assertEqual(self.app._engagement_of(values), ENGAGEMENT_ID)

    def test_none_of_them_having_one_is_recorded_as_none(self):
        values = [{"document_id": 1, "engagement_id": None}]
        self.assertIsNone(self.app._engagement_of(values))

    def test_no_values_at_all(self):
        self.assertIsNone(self.app._engagement_of([]))


class NormalizerTest(unittest.TestCase):
    """lambda/normalizer/app.py: the copy that runs against an object."""

    def setUp(self):
        # load_normalizer hands back the module and its stand-in extractors;
        # only the module is wanted here.
        self.norm, _ = load_normalizer()

    def envelope(self, engagement=NAME):
        return {
            "tenant_id": TENANT, "engagement": engagement,
            "source_bucket": "docs", "source_key":
                "tenants/7/docs/%s/Articles.pdf" % engagement,
            "source_version_id": "v1", "sha256_source": "a" * 64,
            "filename": "Articles.pdf", "extraction_method": "pdf",
            "units": [], "raw_text": "", "uploaded_by": "partner@firm.com",
            "config_revision": 7,
        }

    def record(self, exists):
        db = Db(exists=exists)
        with mock.patch.object(self.norm, "_sql", db.sql):
            self.norm._record_document(self.envelope())
        return db

    def test_a_name_never_seen_before_is_created(self):
        db = self.record(exists=False)
        self.assertEqual(db.kinds()[:3],
                         ["SELECT engagement_id FROM",
                          "INSERT INTO engagement",
                          "SELECT engagement_id FROM"])
        _, wrote = db.statements[-1]
        self.assertEqual(wrote["engagement_id"], ENGAGEMENT_ID)

    def test_an_existing_name_is_resolved_without_writing(self):
        """The ordinary case: /uploads created the row seconds earlier."""
        db = self.record(exists=True)
        self.assertNotIn("INSERT INTO engagement", db.kinds())
        _, wrote = db.statements[-1]
        self.assertEqual(wrote["engagement_id"], ENGAGEMENT_ID)

    def test_a_refusal_is_recorded_even_if_the_engagement_cannot_be(self):
        """The row is the only record a person will ever see of a file nobody
        could read. A lookup that fails must not take it with it."""
        calls = []

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            calls.append((s, sent(params)))
            if s.startswith("SELECT engagement_id"):
                raise RuntimeError("cluster did not resume")
            return rows()

        with mock.patch.object(self.norm, "_sql", sql):
            self.norm._record_refusal(
                TENANT, NAME, "Articles.pdf", "docs",
                "tenants/7/docs/Meridian-Trading/Articles.pdf", "v1",
                "a" * 64, 1234, "partner@firm.com", "pdf_parse_failed")

        wrote = [c for c in calls if c[0].startswith("INSERT INTO document")]
        self.assertEqual(len(wrote), 1)
        self.assertIsNone(wrote[0][1]["engagement_id"])

    def test_the_two_copies_ask_the_database_the_same_thing(self):
        """The rule is written twice. These are the statements that must not
        drift: same lookup, same insert, same unique-key absorption."""
        api = load_api()

        api_db, norm_db = Db(exists=False), Db(exists=False)
        with mock.patch.object(api, "_sql", api_db.sql):
            api.engagement_id(TENANT, NAME, "partner@firm.com")
        with mock.patch.object(self.norm, "_sql", norm_db.sql):
            self.norm._engagement_id(TENANT, NAME, "partner@firm.com")

        self.assertEqual([s for s, _ in api_db.statements],
                         [s for s, _ in norm_db.statements])


if __name__ == "__main__":
    unittest.main()
