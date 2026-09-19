"""
app.py - the backstop.

Stage 1 made every exit of the normalizer write a row, so a refused document
says so on screen instead of leaving a person waiting ten minutes. Stage 2's
dead-letter queue catches the invocations that FAIL. Neither covers the case
where the normalizer was never invoked at all - an EventBridge rule disabled
by mistake, a notification configuration removed, an event dropped - and in
that case there is no failure anywhere to catch, only an object nobody ever
read.

So this asks the only question that finds it: is there an object in the docs
bucket with no document row?

IT REPORTS AND DOES NOTHING ELSE. It does not re-invoke the normalizer, does
not delete, does not write a row. An orphan is either a bug worth
understanding or a file somebody put there by hand, and a process that
silently reprocesses would hide both. Filing costs money; nothing here may
start that.

Runs on a schedule. Every object older than ORPHAN_AFTER_MINUTES is a
candidate - younger ones may legitimately still be in flight, and the
arithmetic behind that number is in observability.tf beside the schedule.
"""

import datetime
import os
import time

import boto3
from botocore.exceptions import ClientError

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")

DOCS_BUCKET = os.environ["DOCS_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
ORPHAN_AFTER_MINUTES = int(os.environ.get("ORPHAN_AFTER_MINUTES", "30"))

# Objects older than this are known historical debris, not findings.
#
# Eighty-eight objects predate the Stage 1 apply of 18 September, when the
# normalizer began writing a row for every refusal. Before that a refused
# document left no trace at all - which is the hole Stage 1 closed - so every
# one of them is an orphan by construction. Every key is recorded, with its
# timestamp, in docs/ARQEDIA_orphans_before_stage1_2026-09-19.md.
#
# Reporting them every fifteen minutes would bury a real one. They are COUNTED
# AND NOT LISTED: the summary line carries historical=N on every run, so the
# number stays in front of whoever reads it and a change in it would show.
# Nothing is hidden; it is just not repeated eighty-eight times an hour.
#
# Empty disables the split and everything is reported, which is what a fresh
# environment wants.
HISTORICAL_BEFORE = os.environ.get("HISTORICAL_BEFORE", "").strip()

# How many keys go into one IN list. Bounded so a bucket with a hundred
# thousand objects asks a hundred reasonable questions rather than one
# impossible one.
_CHUNK = 200

# Named so the log can be filtered, the same way [normalizer-error] is. One
# line per orphan, and one summary line whether or not there were any - a
# silent run and a run that did not happen look identical otherwise.
ORPHAN = "[orphan]"
SUMMARY = "[reconcile]"


def _historical_cutoff():
    """The boundary, or None where it is not set or is unreadable.

    A malformed value reports EVERYTHING rather than nothing. The failure that
    matters is a backstop that goes quiet, and a typo here must not cause
    one."""
    if not HISTORICAL_BEFORE:
        return None
    try:
        return datetime.datetime.fromisoformat(
            HISTORICAL_BEFORE.replace("Z", "+00:00"))
    except ValueError:
        print("%s historical_before=%r is not a date; reporting everything"
              % (SUMMARY, HISTORICAL_BEFORE))
        return None


def _sql(statement, params=None):
    for _ in range(12):
        try:
            return _rds.execute_statement(
                resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                database=DATABASE, sql=statement, parameters=params or [])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in (
                "DatabaseResumingException", "ThrottlingException"
            ):
                time.sleep(5)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _p(name, value):
    return {"name": name, "value": {"stringValue": str(value)}}


def _known(keys):
    """Which of these keys already have a document row.

    Asked in chunks, and asked about the CANDIDATES rather than reading every
    s3_key in the table: the table grows without bound and the candidate list
    is what we actually need to answer for."""
    found = set()
    for i in range(0, len(keys), _CHUNK):
        chunk = keys[i:i + _CHUNK]
        names = ", ".join(":k%d" % n for n in range(len(chunk)))
        params = [_p("k%d" % n, k) for n, k in enumerate(chunk)]
        rows = _sql(
            "SELECT DISTINCT s3_key FROM document WHERE s3_key IN (%s)" % names,
            params).get("records", [])
        for r in rows:
            cell = r[0]
            if "stringValue" in cell:
                found.add(cell["stringValue"])
    return found


def _candidates(cutoff):
    """Every object under tenants/ older than the cutoff.

    Paginated, because list_objects_v2 returns a thousand at a time and a
    silent truncation would make this report "no orphans" on a full bucket -
    the worst possible lie for a backstop to tell."""
    out, token, scanned = [], None, 0
    while True:
        kwargs = {"Bucket": DOCS_BUCKET, "Prefix": "tenants/"}
        if token:
            kwargs["ContinuationToken"] = token
        page = _s3.list_objects_v2(**kwargs)
        for obj in page.get("Contents", []):
            scanned += 1
            if obj["LastModified"] <= cutoff:
                out.append((obj["Key"], obj["LastModified"], obj["Size"]))
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    return out, scanned


def lambda_handler(event, context):
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(minutes=ORPHAN_AFTER_MINUTES)

    candidates, scanned = _candidates(cutoff)
    known = _known([k for k, _, _ in candidates]) if candidates else set()

    historical_before = _historical_cutoff()
    orphans, historical = [], 0
    for key, modified, size in candidates:
        if key in known:
            continue
        if historical_before and modified < historical_before:
            historical += 1
            continue
        age = int((now - modified).total_seconds() // 60)
        orphans.append(key)
        print("%s key=%s age_minutes=%d bytes=%d" % (ORPHAN, key, age, size))

    # ALWAYS PRINTED. Zero orphans is a result; no line at all is a function
    # that did not run, and the two must not look the same. historical is on
    # every line for the same reason - a count that only appears when it is
    # non-zero is a count nobody notices changing.
    print("%s scanned=%d older_than=%dm candidates=%d orphans=%d historical=%d"
          % (SUMMARY, scanned, ORPHAN_AFTER_MINUTES, len(candidates),
             len(orphans), historical))

    return {"scanned": scanned, "candidates": len(candidates),
            "orphans": len(orphans), "keys": orphans[:100],
            "historical": historical,
            "older_than_minutes": ORPHAN_AFTER_MINUTES}
