"""
app.py - the image sweep (graphics-insert, feature/graphics-sweep).

A person's image is uploaded into its memo's working prefix the moment it is
dropped or pasted, before anything in the memo names it:

    tenants/{t}/working/images/memos/{memo}/{image}

Most go on to be named in a working copy and carried into a revision at save
(decision N2): the revision keeps its own copy, under tenants/{t}/images/,
which this never touches. What is left behind is the upload nobody kept - put
in and undone past the ten steps undo holds, put in and discarded, refused
for its bytes, or carried into a revision whose working copy has gone.

So, once a day: every file in a working image prefix older than the grace
period (24 hours, decided 26 October 2026) that NO working copy of that memo
names, in its text or in its undo history, is removed. Every person's copy
counts, not only the uploader's: a copy is per person and per memo, and an
image one person put in may be in a colleague's history.

THE HISTORY COUNTS. Undo can put back a step that held an image, and the
step holds the image's line, not the file; removing a file a step still
names would undo into a hole. Ten steps, under 4 MiB (UNDO-01).

REMOVED MEANS EVERY VERSION. The bucket is versioned, so a plain delete
would add a marker and keep every byte for ever, which is not what a
garbage collection is for. Each version and marker of the key goes.

WHEN IN DOUBT IT KEEPS. A working copy that cannot be read or parsed keeps
every image of that memo for this run, and says so. A sweep that removes a
picture somebody is relying on cannot be taken back.

Invoked by EventBridge daily with an empty event. For a check by hand:
    {"tenant_id": 5, "memo_id": 212, "grace_hours": 0, "dry_run": true}
narrows it to one memo, shortens the grace and removes nothing.
"""

import datetime
import json
import os
import re

import boto3

_s3 = boto3.client("s3")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]
GRACE_HOURS = float(os.environ.get("GRACE_HOURS", "24"))

# The API's _IMAGE_LINE, character for character: what counts as naming an
# image is what a save carries.
_IMAGE_LINE = re.compile(
    r"^!\[[^\]\n]*\]\(image:([0-9a-f]{32}\.(?:png|jpg))\)[ \t]*$", re.M)
_TENANT = re.compile(r"^tenants/(\d+)/$")
_MEMO = re.compile(r"^tenants/\d+/working/images/memos/(\d+)/$")

SUMMARY = "[image-sweep]"
REMOVED = "[image-removed]"
KEPT_UNREAD = "[image-sweep-unread]"


def _pages(**kwargs):
    """Every page of a listing. A silent truncation would keep files for
    ever on a full prefix, which is the quiet failure a sweep has."""
    token = None
    while True:
        if token:
            kwargs["ContinuationToken"] = token
        page = _s3.list_objects_v2(Bucket=CURATED_BUCKET, **kwargs)
        yield page
        if not page.get("IsTruncated"):
            return
        token = page.get("NextContinuationToken")


def _folders(prefix, pattern):
    """The ids of the folders directly under a prefix."""
    out = []
    for page in _pages(Prefix=prefix, Delimiter="/"):
        for common in page.get("CommonPrefixes", []):
            m = pattern.match(common["Prefix"])
            if m:
                out.append(int(m.group(1)))
    return out


def names_in(working):
    """Every image a stored working copy names: its text, and every step of
    its history, before and after."""
    texts = [working.get("text") or ""]
    for step in working.get("history") or []:
        texts += [s for s in (step.get("before") or []) + (step.get("after") or [])
                  if isinstance(s, str)]
    return {n for t in texts for n in _IMAGE_LINE.findall(t)}


def _named(tenant_id, memo_id):
    """The images any working copy of this memo names, or None where one of
    them could not be read - and then nothing of this memo is removed."""
    named = set()
    for page in _pages(Prefix="tenants/%d/working/memos/%d/" % (tenant_id, memo_id)):
        for obj in page.get("Contents", []):
            try:
                body = _s3.get_object(Bucket=CURATED_BUCKET,
                                      Key=obj["Key"])["Body"].read()
                working = json.loads(body.decode("utf-8")).get("working")
            except Exception as exc:  # noqa: BLE001
                print("%s key=%s %s" % (KEPT_UNREAD, obj["Key"], str(exc)[:200]))
                return None
            if isinstance(working, dict):
                named |= names_in(working)
    return named


def _remove(key):
    """Every version and delete marker of one key."""
    versions = _s3.list_object_versions(Bucket=CURATED_BUCKET, Prefix=key)
    objs = [{"Key": v["Key"], "VersionId": v["VersionId"]}
            for v in versions.get("Versions", []) + versions.get("DeleteMarkers", [])
            if v["Key"] == key]
    if objs:
        _s3.delete_objects(Bucket=CURATED_BUCKET,
                           Delete={"Objects": objs, "Quiet": True})


def lambda_handler(event, context):
    event = event or {}
    grace = float(event.get("grace_hours", GRACE_HOURS))
    dry_run = bool(event.get("dry_run"))
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=grace)

    tenants = ([int(event["tenant_id"])] if "tenant_id" in event
               else _folders("tenants/", _TENANT))

    scanned = young = kept = removed = unread = 0
    gone = []
    for tenant_id in tenants:
        root = "tenants/%d/working/images/memos/" % tenant_id
        memos = ([int(event["memo_id"])] if "memo_id" in event
                 else _folders(root, _MEMO))
        for memo_id in memos:
            files = [o for page in _pages(Prefix="%s%d/" % (root, memo_id))
                     for o in page.get("Contents", [])]
            if not files:
                continue
            scanned += len(files)
            old = [o for o in files if o["LastModified"] <= cutoff]
            young += len(files) - len(old)
            if not old:
                continue
            named = _named(tenant_id, memo_id)
            if named is None:
                unread += len(old)
                continue
            for obj in old:
                image = obj["Key"].rsplit("/", 1)[-1]
                if image in named:
                    kept += 1
                    continue
                removed += 1
                gone.append(obj["Key"])
                print("%s key=%s age_hours=%d bytes=%d dry_run=%s" % (
                    REMOVED, obj["Key"],
                    (now - obj["LastModified"]).total_seconds() // 3600,
                    obj["Size"], dry_run))
                if not dry_run:
                    _remove(obj["Key"])

    # ALWAYS PRINTED, as reconcile's is: a run that removed nothing and a run
    # that did not happen must not look the same.
    print("%s tenants=%d scanned=%d younger_than_grace=%d kept_named=%d "
          "kept_unread=%d removed=%d grace_hours=%g dry_run=%s" % (
              SUMMARY, len(tenants), scanned, young, kept, unread, removed,
              grace, dry_run))

    return {"tenants": len(tenants), "scanned": scanned,
            "younger_than_grace": young, "kept_named": kept,
            "kept_unread": unread, "removed": removed, "keys": gone[:100],
            "grace_hours": grace, "dry_run": dry_run}
