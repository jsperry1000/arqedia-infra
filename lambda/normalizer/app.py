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

import config
import extractors
import segment

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")

REVIEW_BUCKET = os.environ["REVIEW_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

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


def _has_thin_page(text, units, byte_size):
    """True when any single page is a scan.

    Distinct from _is_thin, which averages across the file and decides whether
    the DOCUMENT goes to OCR. This asks a narrower question: does the file
    contain a page that cannot be read? A file averaging well can still hold
    three scanned pages in the middle, and those pages are why the file must
    not be split - see the guard in lambda_handler."""
    if not units:
        return False
    heavy = (byte_size / len(units)) > _IMAGE_BYTES_PER_PAGE
    if not heavy:
        return False
    for u in units:
        chars = min(u["char_end"], len(text)) - min(u["char_start"], len(text))
        if chars < _THIN_CHARS_PER_PAGE:
            return True
    return False


def _slice(raw_text, units, part):
    """The part's own text and units.

    Page numbers stay the FILE's own. A value read from the first page of a
    part covering pages 21 to 30 cites page 21, because that is where a reader
    opening the file will find it. Character offsets are re-based to the sliced
    text, because that is what the extractor will be reading."""
    if part["page_from"] is None:
        return units, raw_text

    kept = [u for u in units
            if part["page_from"] <= u["index"] <= part["page_to"]]
    if not kept:
        return units, raw_text

    origin = kept[0]["char_start"]
    text = raw_text[origin:kept[-1]["char_end"]]

    rebased = []
    for u in kept:
        v = dict(u)
        v["char_start"] = u["char_start"] - origin
        v["char_end"] = u["char_end"] - origin
        rebased.append(v)
    return rebased, text


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


def envelope_suffix(page_from, part_index):
    """Where a document's envelope lives, relative to the file's own key.

    Parts of one file share an s3_key, so the part number is what tells their
    envelopes apart. A file holding one document keeps the unsuffixed name it
    has always had, so nothing already filed moves."""
    if page_from is None:
        return ".analysed.json"
    return ".p" + str(part_index) + ".analysed.json"


def _write_envelope(key, envelope):
    """.analysed.json, not .normalized.json. Extraction listens for the latter,
    so writing this does not start extraction - filing does, by renaming the
    envelope once a person has confirmed what the document is."""
    review_key = key + envelope_suffix(envelope.get("page_from"),
                                       envelope.get("part_index"))
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
           sha256, filename, page_count, part_index, page_from, page_to,
           extraction_method, document_type,
           state, thin_text, char_count, byte_size,
           type_confidence, type_reason,
           classify_tokens_in, classify_tokens_out,
           uploaded_by, config_revision)
        VALUES
          (:tenant_id, :engagement_id, :s3_bucket, :s3_key, :s3_version_id,
           :sha256, :filename, :page_count, :part_index, :page_from, :page_to,
           :extraction_method, :document_type,
           :state, :thin_text, :char_count, :byte_size,
           :type_confidence, :type_reason,
           :classify_tokens_in, :classify_tokens_out,
           :uploaded_by, :config_revision)
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
            _p("part_index", envelope.get("part_index")),
            _p("page_from", envelope.get("page_from")),
            _p("page_to", envelope.get("page_to")),
            _p("extraction_method", envelope["extraction_method"]),
            _p("document_type", envelope.get("document_type")),
            _p("state", "analysed"),
            _p("thin_text", 1 if envelope.get("thin_text") else 0),
            _p("char_count", len(envelope.get("raw_text") or "")),
            _p("byte_size", envelope.get("byte_size")),
            _p("type_confidence", envelope.get("document_type_confidence")),
            _p("type_reason", envelope.get("document_type_reason")),
            _p("classify_tokens_in", envelope.get("classify_tokens_in")),
            _p("classify_tokens_out", envelope.get("classify_tokens_out")),
            _p("uploaded_by", envelope.get("uploaded_by")),
            _p("config_revision", envelope.get("config_revision") or 1),
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

    # The tenant's own type list, at whatever revision they are working
    # under. A firm doing shipping finance is offered shipping documents.
    revision = config.active_revision(tenant_id)
    registry = config.load(tenant_id, revision)

    parts, usage = segment.segment(raw_text, units, registry)

    # A scanned page cannot be sent to OCR on its own: Textract's asynchronous
    # API takes an object, not a page range. Splitting a file that holds one
    # would produce a part nothing can ever read. So a file with any thin page
    # is filed whole and follows today's OCR path untouched, keeping whatever
    # type segmentation proposed for its first part.
    if len(parts) > 1 and _has_thin_page(raw_text, units, len(body)):
        head = parts[0]
        parts = [{"part_index": 1, "page_from": None, "page_to": None,
                  "document_type": head["document_type"],
                  "confidence": head["confidence"],
                  "why": head["why"]}]
        print("[not-split] key=%s reason=thin-page pages=%d" % (
            src_key, len(units)))

    thin = _is_thin(raw_text, len(units), len(body))
    written = []

    for part in parts:
        part_units, part_text = _slice(raw_text, units, part)

        envelope = {
            "tenant_id": tenant_id,
            "document_type": part["document_type"],
            "document_type_proposed": part["document_type"],
            "document_type_confidence": part["confidence"],
            "document_type_reason": part["why"],
            "document_type_confirmed": False,
            "part_index": part["part_index"],
            "page_from": part["page_from"],
            "page_to": part["page_to"],
            "byte_size": len(body),
            "thin_text": thin,
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
            "config_revision": revision,
            "raw_text": part_text,
            "units": part_units,
            "extracted_values": [],
            "extraction_complete": False,
        }

        # One segmentation call covers the whole file, so its cost is recorded
        # once. Summing this column across a file's parts would count the same
        # call several times, and the point of the column is to price the
        # classification allowance from what it actually costs.
        if part["part_index"] == 1:
            envelope["classify_tokens_in"] = usage.get("input_tokens")
            envelope["classify_tokens_out"] = usage.get("output_tokens")

        document_id = _record_document(envelope)
        envelope["document_id"] = document_id
        review_key = _write_envelope(src_key, envelope)
        written.append({"document_id": document_id,
                        "review_key": review_key,
                        "document_type": part["document_type"],
                        "page_from": part["page_from"],
                        "page_to": part["page_to"],
                        "units": len(part_units)})

        print("[analysed] doc=%s part=%s of %s pages=%s-%s method=%s "
              "type=%s by=%s key=%s boundary=%s" % (
                  document_id, part["part_index"], len(parts),
                  part["page_from"] or 1, part["page_to"] or len(units),
                  method, part["document_type"], uploaded_by, src_key,
                  (part.get("boundary") or "-")[:120]))

    return {
        "status": "ok",
        "tenant_id": tenant_id,
        "extraction_method": method,
        "pages": len(units),
        "documents": written,
    }
