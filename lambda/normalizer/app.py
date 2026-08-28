"""
app.py - document normalizer.

Fires on an object landing in the docs bucket. Reads it, extracts text and unit
boundaries, proposes what the document is, and records a row in `document`. It
does NOT start extraction: filing does that, once a person has confirmed the
proposal.

Key layout in the docs bucket:
    tenants/<tenant_id>/docs/<engagement_id>/<file_id>--<filename>

tenant_id is taken from the KEY PATH, never from a tag. Tags are eventually
consistent on a fresh object and were returned null intermittently in the eBL
build; the key path cannot race.

Who uploaded travels as object metadata, set by the browser when it PUTs the
file against a signed link the API issued. The API knows the caller; the
normalizer does not, so the answer has to arrive with the object.
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

import classify
import extractors

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")

REVIEW_BUCKET = os.environ["REVIEW_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

# Stage 1 runs a single hard-coded configuration.
CONFIG_REVISION = 1

# A page yielding less than this, in a file large enough to be an image, is a
# scan carrying only a stamp. Characters per page alone let 68 characters
# through as a readable certificate of incorporation.
_THIN_CHARS_PER_PAGE = 200
_IMAGE_BYTES_PER_PAGE = 100000

_KEY_RE = re.compile(
    r"^tenants/(?P<tenant>\d+)/docs/(?P<engagement>[^/]+)/(?P<file>.+)$")


def _is_thin(text, pages, byte_size):
    """True when the text is implausibly short for a file this size."""
    if pages < 1:
        return True
    thin = (len(text) / pages) < _THIN_CHARS_PER_PAGE
    heavy = (byte_size / pages) > _IMAGE_BYTES_PER_PAGE
    return thin and heavy


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _sql(statement, params=None):
    """Execute over the Data API, retrying while the cluster wakes.

    The cluster pauses at zero capacity and takes roughly fifteen seconds to
    resume. DatabaseResumingException is normal operation, not a fault."""
    for _ in range(12):
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
        raise ValueError("key does not match the expected layout: " + key)
    return int(m.group("tenant")), m.group("engagement"), m.group("file")


def _write_envelope(key, envelope):
    """.analysed.json, not .normalized.json. Extraction listens for the latter,
    so writing this does not start extraction - filing does, by renaming the
    envelope once a person has confirmed what the document is."""
    review_key = key + ".analysed.json"
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
           sha256, filename, page_count, extraction_method, document_type,
           state, thin_text, char_count, byte_size,
           type_confidence, type_reason, uploaded_by, config_revision)
        VALUES
          (:tenant_id, :engagement_id, :s3_bucket, :s3_key, :s3_version_id,
           :sha256, :filename, :page_count, :extraction_method, :document_type,
           :state, :thin_text, :char_count, :byte_size,
           :type_confidence, :type_reason, :uploaded_by, :config_revision)
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
            _p("document_type", envelope.get("document_type")),
            _p("state", "analysed"),
            _p("thin_text", 1 if envelope.get("thin_text") else 0),
            _p("char_count", len(envelope.get("raw_text") or "")),
            _p("byte_size", envelope.get("byte_size")),
            _p("type_confidence", envelope.get("document_type_confidence")),
            _p("type_reason", envelope.get("document_type_reason")),
            _p("uploaded_by", envelope.get("uploaded_by")),
            _p("config_revision", CONFIG_REVISION),
        ],
    )
    return result.get("generatedFields", [{}])[0].get("longValue")


def _source_from_event(event):
    """Accept either shape: S3 bucket notification or EventBridge."""
    records = event.get("Records")
    if records and records[0].get("s3"):
        s3 = records[0]["s3"]
        return s3["bucket"]["name"], urllib.parse.unquote_plus(
            s3["object"]["key"])

    detail = event.get("detail")
    if detail and "bucket" in detail:
        return detail["bucket"]["name"], urllib.parse.unquote_plus(
            detail["object"]["key"])

    raise ValueError("unrecognised event shape")


def lambda_handler(event, context):
    src_bucket, src_key = _source_from_event(event)

    if src_key.endswith(".analysed.json") or src_key.endswith(".normalized.json"):
        return {"status": "skipped", "reason": "already-processed"}

    tenant_id, engagement, filename = _parse_key(src_key)

    obj = _s3.get_object(Bucket=src_bucket, Key=src_key)
    body = obj["Body"].read()
    sha = hashlib.sha256(body).hexdigest()

    # Set by the browser against the signed link. The API knew who was asking;
    # this function does not, so the answer arrives with the object.
    uploaded_by = (obj.get("Metadata") or {}).get("uploaded-by")

    try:
        raw_text, units, method = extractors.extract(src_key, body)
    except extractors.UnreadableDocument as exc:
        print("[unreadable] key=%s reason=%s" % (src_key, exc.reason))
        return {"status": "unreadable", "reason": exc.reason, "key": src_key}

    document_type, confidence, why = classify.classify(raw_text)

    envelope = {
        "tenant_id": tenant_id,
        "document_type": document_type,
        "document_type_proposed": document_type,
        "document_type_confidence": confidence,
        "document_type_reason": why,
        "document_type_confirmed": False,
        "byte_size": len(body),
        "thin_text": _is_thin(raw_text, len(units), len(body)),
        "state": "analysed",
        "uploaded_by": uploaded_by,
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

    review_key = _write_envelope(src_key, envelope)

    print("[analysed] doc=%s method=%s units=%d type=%s by=%s key=%s" % (
        document_id, method, len(units), document_type, uploaded_by, src_key))

    return {
        "status": "ok",
        "document_id": document_id,
        "tenant_id": tenant_id,
        "review_key": review_key,
        "extraction_method": method,
        "document_type": document_type,
        "units": len(units),
    }
