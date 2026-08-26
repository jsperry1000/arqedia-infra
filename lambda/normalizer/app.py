"""
app.py - document normalizer.

Fires on an object landing in the docs bucket. Reads it, extracts text and
unit boundaries, writes an envelope to the review bucket, and records a row
in `document`.

Key layout in the docs bucket:
    tenants/<tenant_id>/docs/<engagement_id>/<file_id>--<filename>

tenant_id is taken from the KEY PATH, never from a tag. Tags are eventually
consistent on a fresh object and returned null intermittently in the eBL
build; the key path cannot race.
"""

import datetime
import hashlib
import json
import os
import re
import time
import urllib.parse

import boto3
from botocore.exceptions import ClientError

import extractors

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")

REVIEW_BUCKET = os.environ["REVIEW_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

# Stage 1 runs a single hard-coded configuration.
CONFIG_REVISION = 1

_KEY_RE = re.compile(r"^tenants/(?P<tenant>\d+)/docs/(?P<engagement>[^/]+)/(?P<file>.+)$")


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sql(statement, params=None):
    """Execute over the Data API, retrying while the cluster wakes.

    The cluster pauses at zero capacity and takes roughly fifteen seconds to
    resume. DatabaseResumingException is normal operation, not a fault.
    """
    for attempt in range(12):
        try:
            return _rds.execute_statement(
                resourceArn=CLUSTER_ARN,
                secretArn=SECRET_ARN,
                database=DATABASE,
                sql=statement,
                parameters=params or [],
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("DatabaseResumingException", "ThrottlingException"):
                time.sleep(5)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _p(name, value):
    """Build a Data API parameter, mapping Python types to field kinds."""
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _parse_key(key):
    m = _KEY_RE.match(key)
    if not m:
        raise ValueError("key does not match the expected layout: {}".format(key))
    return int(m.group("tenant")), m.group("engagement"), m.group("file")


def _write_envelope(tenant_id, key, envelope):
    review_key = "{}.normalized.json".format(key)
    _s3.put_object(
        Bucket=REVIEW_BUCKET,
        Key=review_key,
        Body=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    return review_key


def _record_document(envelope):
    result = _sql(
        """
        INSERT INTO document
          (tenant_id, engagement_id, s3_bucket, s3_key, s3_version_id,
           sha256, filename, page_count, extraction_method, config_revision)
        VALUES
          (:tenant_id, :engagement_id, :s3_bucket, :s3_key, :s3_version_id,
           :sha256, :filename, :page_count, :extraction_method, :config_revision)
        """,
        [
            _p("tenant_id", envelope["tenant_id"]),
            _p("engagement_id", None),
            _p("s3_bucket", envelope["source_bucket"]),
            _p("s3_key", envelope["source_key"]),
            _p("s3_version_id", envelope["source_version_id"]),
            _p("sha256", envelope["sha256_source"]),
            _p("filename", envelope["filename"]),
            _p("page_count", len(envelope["units"])),
            _p("extraction_method", envelope["extraction_method"]),
            _p("config_revision", CONFIG_REVISION),
        ],
    )
    return result.get("generatedFields", [{}])[0].get("longValue")


def lambda_handler(event, context):
    detail = event["detail"]
    src_bucket = detail["bucket"]["name"]
    src_key = urllib.parse.unquote_plus(detail["object"]["key"])

    if src_key.endswith(".normalized.json"):
        return {"status": "skipped", "reason": "already-normalized"}

    tenant_id, engagement, filename = _parse_key(src_key)

    obj = _s3.get_object(Bucket=src_bucket, Key=src_key)
    body = obj["Body"].read()
    sha = hashlib.sha256(body).hexdigest()

    try:
        raw_text, units, method = extractors.extract(src_key, body)
    except extractors.UnreadableDocument as exc:
        print("[unreadable] key={} reason={}".format(src_key, exc.reason))
        return {"status": "unreadable", "reason": exc.reason, "key": src_key}

    envelope = {
        "tenant_id": tenant_id,
        "engagement": engagement,
        "filename": filename,
        "source_bucket": src_bucket,
        "source_key": src_key,
        "source_version_id": obj.get("VersionId"),
        "sha256_source": sha,
        "extraction_method": method,
        "extracted_at": _now(),
        "config_revision": CONFIG_REVISION,
        "raw_text": raw_text,
        "units": units,
        "extracted_values": [],
        "extraction_complete": False,
    }

    document_id = _record_document(envelope)
    envelope["document_id"] = document_id

    review_key = _write_envelope(tenant_id, src_key, envelope)

    print("[normalized] doc={} method={} units={} key={}".format(
        document_id, method, len(units), src_key))

    return {
        "status": "ok",
        "document_id": document_id,
        "tenant_id": tenant_id,
        "review_key": review_key,
        "extraction_method": method,
        "units": len(units),
    }
