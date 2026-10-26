"""
The image sweep (graphics-insert, feature/graphics-sweep). Run from the
repository root:

    python -m unittest discover -s tests

Nothing reaches AWS: boto3 is replaced at import and S3 is a dictionary of
keys, ages and working copies. What is tested is what the sweep decides - an
old file no working copy names goes, every version of it; one named in a text
or in an undo step stays; one inside the grace stays; an unreadable copy keeps
its memo's images; and a revision's own images are never looked at.
"""

import datetime
import importlib.util
import io
import json
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.datetime.now(datetime.timezone.utc)
A, B, C = ("%s.png" % (ch * 32) for ch in "abc")


def load_sweep():
    boto3 = types.ModuleType("boto3")
    boto3.client = mock.MagicMock()
    with mock.patch.dict(sys.modules, {"boto3": boto3}), \
            mock.patch.dict(os.environ, {"CURATED_BUCKET": "curated"}):
        spec = importlib.util.spec_from_file_location(
            "image_sweep_app", ROOT / "lambda" / "image_sweep" / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def line(image):
    return "![x](image:%s)" % image


class FakeS3:
    """Objects as key -> (age in hours, body). Versions are the object plus
    one older version and one delete marker, so 'every version' is tested."""

    def __init__(self, objects):
        self.objects = dict(objects)
        self.deleted = []

    def list_objects_v2(self, Bucket, Prefix, Delimiter=None,  # noqa: N803
                        ContinuationToken=None):
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        if Delimiter:
            folders = sorted({Prefix + k[len(Prefix):].split("/", 1)[0] + "/"
                              for k in keys if "/" in k[len(Prefix):]})
            return {"CommonPrefixes": [{"Prefix": f} for f in folders]}
        return {"Contents": [
            {"Key": k, "Size": 10,
             "LastModified": NOW - datetime.timedelta(hours=self.objects[k][0])}
            for k in keys]}

    def get_object(self, Bucket, Key):                         # noqa: N803
        return {"Body": io.BytesIO(self.objects[Key][1])}

    def list_object_versions(self, Bucket, Prefix):            # noqa: N803
        return {"Versions": [{"Key": Prefix, "VersionId": "v2"},
                             {"Key": Prefix, "VersionId": "v1"}],
                "DeleteMarkers": [{"Key": Prefix, "VersionId": "m1"}]}

    def delete_objects(self, Bucket, Delete):                  # noqa: N803
        self.deleted += [(o["Key"], o["VersionId"]) for o in Delete["Objects"]]


def image(memo, name, tenant=5):
    return "tenants/%d/working/images/memos/%d/%s" % (tenant, memo, name)


def copy(memo, working, who="p1", tenant=5):
    key = "tenants/%d/working/memos/%d/%s.json" % (tenant, memo, who)
    return key, (1, json.dumps({"working": working}).encode("utf-8"))


class ImageSweepTest(unittest.TestCase):
    def setUp(self):
        self.app = load_sweep()

    def run_with(self, objects, event=None):
        s3 = FakeS3(objects)
        self.app._s3 = s3
        return s3, self.app.lambda_handler(event or {}, None)

    def removed(self, s3):
        return sorted({k for k, _ in s3.deleted})

    def test_an_old_file_nothing_names_goes_every_version(self):
        s3, out = self.run_with({image(212, A): (30, b"")})
        self.assertEqual(self.removed(s3), [image(212, A)])
        self.assertEqual(sorted(v for _, v in s3.deleted), ["m1", "v1", "v2"])
        self.assertEqual(out["removed"], 1)

    def test_a_file_the_text_names_stays(self):
        s3, out = self.run_with(dict([
            (image(212, A), (30, b"")),
            copy(212, {"text": "# M\n\n" + line(A) + "\n"})]))
        self.assertEqual(s3.deleted, [])
        self.assertEqual(out["kept_named"], 1)

    def test_a_file_only_an_undo_step_names_stays(self):
        s3, _ = self.run_with(dict([
            (image(212, A), (30, b"")), (image(212, B), (30, b"")),
            copy(212, {"text": "# M\n", "history": [
                {"act": "delete", "at": 1, "before": [line(A) + "\n"], "after": []},
                {"act": "image", "at": 1, "before": [], "after": [line(B) + "\n"]}]})]))
        self.assertEqual(s3.deleted, [])

    def test_any_persons_copy_counts(self):
        s3, _ = self.run_with(dict([
            (image(212, A), (30, b"")),
            copy(212, {"text": "nothing"}, who="p1"),
            copy(212, {"text": line(A)}, who="p2")]))
        self.assertEqual(s3.deleted, [])

    def test_a_file_inside_the_grace_stays(self):
        s3, out = self.run_with({image(212, A): (23, b"")})
        self.assertEqual(s3.deleted, [])
        self.assertEqual(out["younger_than_grace"], 1)

    def test_an_unreadable_copy_keeps_the_memos_images(self):
        s3, out = self.run_with({
            image(212, A): (30, b""),
            "tenants/5/working/memos/212/p1.json": (1, b"{not json")})
        self.assertEqual(s3.deleted, [])
        self.assertEqual(out["kept_unread"], 1)

    def test_a_cleared_copy_names_nothing(self):
        # After a save the copy is {"working": null}: its images are in the
        # revision's own prefix now, and the uploads can go.
        s3, _ = self.run_with(dict([(image(212, A), (30, b"")),
                                    copy(212, None)]))
        self.assertEqual(self.removed(s3), [image(212, A)])

    def test_a_name_inside_a_sentence_does_not_keep_it(self):
        s3, _ = self.run_with(dict([
            (image(212, A), (30, b"")),
            copy(212, {"text": "See %s here." % line(A)})]))
        self.assertEqual(self.removed(s3), [image(212, A)])

    def test_a_revisions_own_images_are_never_looked_at(self):
        s3, out = self.run_with({
            "tenants/5/images/memos/212/" + A: (300, b""),
            image(211, B): (30, b"")})
        self.assertEqual(self.removed(s3), [image(211, B)])
        self.assertEqual(out["scanned"], 1)

    def test_every_tenant_and_memo_is_swept(self):
        s3, out = self.run_with({image(212, A): (30, b""),
                                 image(9, B, tenant=7): (30, b"")})
        self.assertEqual(out["tenants"], 2)
        self.assertEqual(len(self.removed(s3)), 2)

    def test_a_dry_run_removes_nothing_and_says_what_it_would(self):
        s3, out = self.run_with({image(212, A): (30, b"")}, {"dry_run": True})
        self.assertEqual(s3.deleted, [])
        self.assertEqual(out["keys"], [image(212, A)])

    def test_a_check_by_hand_can_narrow_it_and_shorten_the_grace(self):
        s3, out = self.run_with({image(212, A): (1, b""),
                                 image(211, B): (1, b"")},
                                {"tenant_id": 5, "memo_id": 212,
                                 "grace_hours": 0})
        self.assertEqual(self.removed(s3), [image(212, A)])


if __name__ == "__main__":
    unittest.main()
