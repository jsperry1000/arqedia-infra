"""
A person's own image in a memo (graphics-insert, feature/graphics-storage).
Run from the repository root:

    python -m unittest discover -s tests

Nothing reaches AWS: boto3 is replaced at import, _sql is patched, and S3 is
a dictionary of keys and sizes. What is tested is what the API decides - the
policy an upload is signed with, where an image is looked for, and what a
save copies. That S3 refuses a file outside the policy was checked against
the dev bucket on 26 October 2026 (EntityTooLarge), not here.
"""

import io
import unittest
from unittest import mock

from api_modules import load_api, rows

TENANT = 7
MEMO = 208
PNG = "a" * 32 + ".png"
JPG = "b" * 32 + ".jpg"
MB = 1024 * 1024


SIGNATURE = {".png": b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR",
             ".jpg": b"\xff\xd8\xff\xe0\0\x10JFIF\0"}


class FakeS3:
    """Keys and sizes, and what was copied where. An object given as a size
    is a real image of the type its key says; given as bytes, it is those
    bytes."""

    def __init__(self, app, objects=None):
        self.app = app
        self.objects = {k: len(v) if isinstance(v, bytes) else v
                        for k, v in (objects or {}).items()}
        self.content = {k: v for k, v in (objects or {}).items()
                        if isinstance(v, bytes)}
        self.copied = []
        self.signed = []
        self.ranges = []

    def get_object(self, Bucket, Key, Range=None):         # noqa: N803
        self.ranges.append((Key, Range))
        body = self.content.get(Key, SIGNATURE[Key[Key.rindex("."):]])
        end = int(Range.split("-")[1]) + 1 if Range else len(body)
        return {"Body": io.BytesIO(body[:end])}

    def list_objects_v2(self, Bucket, Prefix, **_):        # noqa: N803
        return {"Contents": [{"Key": k, "Size": s}
                             for k, s in self.objects.items()
                             if k.startswith(Prefix)]}

    def head_object(self, Bucket, Key):                    # noqa: N803
        if Key not in self.objects:
            missing = self.app.ClientError("404")
            missing.response = {"Error": {"Code": "404"}}
            raise missing
        return {"ContentLength": self.objects[Key]}

    def generate_presigned_post(self, Bucket, Key, Fields, Conditions,
                                ExpiresIn):                # noqa: N803
        self.signed.append({"Key": Key, "Fields": Fields,
                            "Conditions": Conditions, "ExpiresIn": ExpiresIn})
        return {"url": "https://curated.s3/", "fields": dict(Fields, key=Key)}

    def generate_presigned_url(self, op, Params, ExpiresIn):  # noqa: N803
        return "https://signed/" + Params["Key"]

    def copy_object(self, Bucket, Key, CopySource):        # noqa: N803
        self.copied.append((CopySource["Key"], Key))

    def put_object(self, **kwargs):
        return {"VersionId": "v1"}


def own(*_args, **_kw):
    return rows((MEMO,))


class ImagesTest(unittest.TestCase):
    def setUp(self):
        self.app = load_api()

    def s3(self, objects=None):
        fake = FakeS3(self.app, objects)
        self.app._s3 = fake
        return fake

    def working(self, image):
        return self.app._image_working_key(TENANT, MEMO, image)

    def saved(self, image, memo=MEMO):
        return self.app._image_key(TENANT, memo, image)

    # --- the upload -----------------------------------------------------

    def upload(self, content_type="image/png"):
        with mock.patch.object(self.app, "_sql", own):
            return self.app.image_upload(TENANT, "sp@ebl.test", MEMO,
                                         content_type)

    def test_an_upload_is_one_key_in_this_memos_working_prefix(self):
        s3 = self.s3()
        out = self.upload()
        self.assertRegex(out["image"], r"^[0-9a-f]{32}\.png$")
        self.assertEqual(s3.signed[0]["Key"], self.working(out["image"]))
        self.assertEqual(s3.signed[0]["ExpiresIn"], 900)

    def test_the_policy_holds_the_size_the_type_and_every_field(self):
        s3 = self.s3()
        self.upload("image/jpeg")
        signed = s3.signed[0]
        self.assertIn(["content-length-range", 1, 10 * MB],
                      signed["Conditions"])
        self.assertIn({"Content-Type": "image/jpeg"}, signed["Conditions"])
        # Every field sent has its condition, or S3 refuses the form.
        for name, value in signed["Fields"].items():
            self.assertIn({name: value}, signed["Conditions"])

    def test_the_ceiling_is_what_is_left_of_the_memos_fifty(self):
        s3 = self.s3({self.saved(PNG): 30 * MB, self.working(JPG): 15 * MB})
        out = self.upload()
        self.assertEqual(out["max_bytes"], 5 * MB)
        self.assertIn(["content-length-range", 1, 5 * MB],
                      s3.signed[0]["Conditions"])

    def test_a_full_memo_signs_nothing(self):
        s3 = self.s3({self.saved(PNG): 50 * MB})
        with self.assertRaises(ValueError) as refused:
            self.upload()
        self.assertEqual(str(refused.exception), self.app.IMAGES_FULL)
        self.assertEqual(s3.signed, [])

    def test_only_png_and_jpeg(self):
        self.s3()
        for refused in ("image/gif", "image/svg+xml", "application/pdf", ""):
            with self.assertRaises(ValueError):
                self.upload(refused)

    def test_another_tenants_memo_is_not_found(self):
        self.s3()
        with mock.patch.object(self.app, "_sql", lambda *a, **k: rows()):
            self.assertIsNone(self.app.image_upload(
                TENANT, "sp@ebl.test", MEMO, "image/png"))

    # --- reading --------------------------------------------------------

    def urls(self, ids):
        with mock.patch.object(self.app, "_sql", own):
            return self.app.image_urls(TENANT, MEMO, ids)["images"]

    def test_the_memos_own_copy_first_then_its_working_one(self):
        self.s3({self.saved(PNG): 1, self.working(PNG): 1,
                 self.working(JPG): 1})
        urls = self.urls(PNG + "," + JPG)
        self.assertEqual(urls[PNG], "https://signed/" + self.saved(PNG))
        self.assertEqual(urls[JPG], "https://signed/" + self.working(JPG))

    def test_an_image_the_memo_does_not_hold_is_null(self):
        self.s3()
        self.assertEqual(self.urls(PNG), {PNG: None})

    def test_a_file_that_is_not_the_image_its_name_says_is_refused(self):
        # Posted as image/png, so stored as one: the bytes say otherwise.
        s3 = self.s3({self.working(PNG): b"<html><script>x</script></html>",
                      self.working(JPG): SIGNATURE[".png"],
                      self.working("c" * 32 + ".jpg"): SIGNATURE[".jpg"]})
        with mock.patch.object(self.app, "_sql", own):
            out = self.app.image_urls(TENANT, MEMO, ",".join(
                [PNG, JPG, "c" * 32 + ".jpg"]))
        self.assertEqual(out["refused"], [PNG, JPG])
        self.assertIsNone(out["images"][PNG])
        self.assertIsNone(out["images"][JPG])
        self.assertIsNotNone(out["images"]["c" * 32 + ".jpg"])
        # Eight bytes read, never the file.
        self.assertTrue(all(r == "bytes=0-7" for _, r in s3.ranges))

    def test_a_name_that_is_not_an_image_is_refused(self):
        self.s3()
        for bad in ("../x.png", "a.gif", "tenants/7/x.png"):
            with self.assertRaises(ValueError):
                self.urls(bad)

    # --- saving a revision ----------------------------------------------

    def text(self, *images):
        return "# Memo\n\nIntro.\n\n" + "".join(
            "![A diagram](image:%s)\n\n" % i for i in images) + "## I. One\n"

    def test_a_save_carries_the_images_its_text_names(self):
        self.s3({self.saved(PNG): 1, self.working(JPG): 1,
                 self.working("c" * 32 + ".png"): 1})
        found = self.app._images_to_carry(TENANT, MEMO, self.text(PNG, JPG))
        self.assertEqual(found, {PNG: self.saved(PNG),
                                 JPG: self.working(JPG)})

    def test_an_image_that_cannot_be_found_refuses_the_save(self):
        self.s3()
        with self.assertRaises(ValueError):
            self.app._images_to_carry(TENANT, MEMO, self.text(PNG))

    def test_a_file_that_is_not_an_image_refuses_the_save(self):
        self.s3({self.working(PNG): b"%PDF-1.7 not a picture"})
        with self.assertRaises(ValueError) as refused:
            self.app._images_to_carry(TENANT, MEMO, self.text(PNG))
        self.assertIn("not a PNG or a JPEG", str(refused.exception))

    def test_more_than_fifty_mb_shown_refuses_the_save(self):
        self.s3({self.saved(PNG): 30 * MB, self.working(JPG): 25 * MB})
        with self.assertRaises(ValueError):
            self.app._images_to_carry(TENANT, MEMO, self.text(PNG, JPG))

    def test_an_image_written_inside_a_sentence_is_not_carried(self):
        self.s3()
        text = "See ![x](image:%s) here.\n" % PNG
        self.assertEqual(self.app._images_to_carry(TENANT, MEMO, text), {})

    def test_revise_copies_them_into_the_new_revision(self):
        s3 = self.s3({self.working(PNG): 1})

        def sql(statement, params=None, tx=None):
            s = " ".join(statement.split())
            if s.startswith("SELECT s3_key, template_key"):
                return rows(("tenants/7/memos/208.md", "lender", 3, None, 1,
                             11, "live", 2))
            if s.startswith("SELECT COALESCE(MAX(revision)"):
                return rows((1,))
            if s.startswith("INSERT INTO memo "):
                return {"generatedFields": [{"longValue": 209}]}
            return rows()

        self.app._lambda = mock.MagicMock()
        with mock.patch.object(self.app, "_sql", sql), \
                mock.patch.object(self.app.config, "workspace_of",
                                  lambda t, w: w):
            out = self.app.revise_memo(TENANT, "sp@ebl.test", MEMO,
                                       self.text(PNG))
        self.assertEqual(out["memo_id"], 209)
        self.assertEqual(s3.copied, [(self.working(PNG),
                                      self.saved(PNG, memo=209))])


if __name__ == "__main__":
    unittest.main()
