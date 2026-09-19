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
import traceback
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


def _has_thin_page(text, units, byte_size=None):  # noqa: ARG001
    """True when any single page is a scan.

    Distinct from _is_thin, which averages across the file and decides whether
    the DOCUMENT goes to OCR. This asks a narrower question: does the file
    contain a page that cannot be read? A file averaging well can still hold
    three scanned pages in the middle, and those pages are why the file must
    not be split - see the guard in lambda_handler."""
    if not units:
        return False

    # NO FILE-LEVEL WEIGHT TEST. This asked whether the whole file averaged
    # over 100 KB a page before it would look at any page, so a five-page PDF
    # with four text pages and one scan was never examined - the loop below
    # did not run, the file was split, and the scanned part became a document
    # nothing could read and nobody could clear.
    #
    # Characters alone are a blunt test, and _is_thin needs the weight check
    # because sending a readable document to OCR wastes money. Here the costs
    # are the other way round: refusing to split a file that could have been
    # split costs a little tidiness, and splitting one that holds an
    # unreadable page strands a document.
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


# What a person is told, per reason. The remedy is the same sentence in three
# of the four, because the remedy IS the same - only the diagnosis differs, and
# the diagnosis is the part that matters. A scan is an ordinary document with a
# fixable problem; a corrupt file may be junk.
#
# no_text_layer is INTERIM. Stage 4 converts it from a refusal into the OCR
# route, and this entry goes with it (decision record, 18 September, item 3).
_REFUSAL_TEXT = {
    "pdf_parse_failed":
        "This file carries nothing readable. Put it through an OCR process "
        "on your side and upload the result.",
    "no_pages":
        "This file carries nothing readable. Put it through an OCR process "
        "on your side and upload the result.",
    "error":
        "This file could not be processed. Nothing was charged. Remove it "
        "and try again, or send it to us if it keeps happening.",
}

# The reasons extractors raises, mapped to ours. Theirs carry a colon and a
# hyphen; a code that reaches a database column and a log filter should carry
# neither. An unrecognised reason becomes 'error' rather than inventing a code.
#
# no_text_layer IS NOT HERE. It was an interim refusal and Stage 4 made it a
# route: a scan gets a row and goes to OCR, and the wording that told a person
# to OCR it themselves went with it (decision record, 18 September, item 3).
_REFUSAL_CODES = {
    "no-pages": "no_pages",
}

# What a scan's row says about why it has no proposed type. It goes in
# type_reason - which means exactly "why the classifier proposed what it did",
# and here the answer is that there was nothing to classify from. NOT in
# refusal_reason: a scan is not a refusal, and refusal_* stays for the three
# that are.
SCAN_REASON = ("A scan, no readable text. Choose a type and file it to read "
               "it.")


def _refusal_code(reason):
    reason = str(reason or "")
    if reason in _REFUSAL_CODES:
        return _REFUSAL_CODES[reason]
    if reason.startswith("pdf-parse-failed"):
        return "pdf_parse_failed"
    return "error"


def _record_refusal(tenant_id, engagement, filename, src_bucket, src_key,
                    version_id, sha, byte_size, uploaded_by, code):
    """A document nobody could read, recorded so somebody can see it.

    THE POINT OF STAGE 1. Every exit below the fetch used to return a dict to
    EventBridge, which discards it - no row, no message, and a review screen
    waiting ten minutes for something no process would ever create. A refusal
    is now a row like any other, in a state of its own.

    NO ENVELOPE. There is no text to put in one, and nothing downstream reads
    it: extraction listens for .normalized.json, which only filing writes.
    remove_document deletes a key that is not there without complaint, so
    Remove works on these rows unchanged.

    page_count, char_count and extraction_method stay NULL. The gate knows the
    page count when it refuses a scan and throws it away; carrying it out means
    editing extractors, which ships in the layer, and Stage 4 is where the OCR
    route actually needs it. Until then the screen says "? pages", which is
    true.

    config_revision is NOT NULL and active_revision falls back to 1 for a
    tenant that has none, so this cannot fail for want of a configuration."""
    _sql(
        """
        INSERT INTO document
          (tenant_id, engagement_id, s3_bucket, s3_key, s3_version_id,
           sha256, filename, byte_size, state, refusal_code, refusal_reason,
           uploaded_by, config_revision)
        VALUES
          (:tenant_id, NULL, :s3_bucket, :s3_key, :s3_version_id,
           :sha256, :filename, :byte_size, 'unreadable', :code, :reason,
           :uploaded_by, :config_revision)
        """,
        [
            _p("tenant_id", tenant_id),
            _p("s3_bucket", src_bucket),
            _p("s3_key", src_key),
            _p("s3_version_id", version_id),
            _p("sha256", sha),
            _p("filename", filename),
            _p("byte_size", byte_size),
            _p("code", code),
            _p("reason", _REFUSAL_TEXT.get(code, _REFUSAL_TEXT["error"])),
            _p("uploaded_by", uploaded_by),
            _p("config_revision", config.active_revision(tenant_id)),
        ],
    )


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
            # Measured where the caller measured them. A scan has real pages
            # and a real (tiny) character count, and its envelope is empty -
            # deriving these from the envelope would say 0 pages about a file
            # the gate had just counted.
            _p("page_count", envelope.get(
                "page_count", len(envelope["units"]))),
            _p("part_index", envelope.get("part_index")),
            _p("page_from", envelope.get("page_from")),
            _p("page_to", envelope.get("page_to")),
            _p("extraction_method", envelope["extraction_method"]),
            _p("document_type", envelope.get("document_type")),
            _p("state", "analysed"),
            _p("thin_text", 1 if envelope.get("thin_text") else 0),
            _p("char_count", envelope.get(
                "char_count", len(envelope.get("raw_text") or ""))),
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

    def refuse(code, log_reason):
        _record_refusal(tenant_id, engagement, filename, src_bucket, src_key,
                        obj.get("VersionId"), sha, len(body), uploaded_by,
                        code)
        print("[unreadable] key=%s reason=%s code=%s" % (
            src_key, log_reason, code))
        return {"status": "unreadable", "reason": log_reason, "code": code,
                "key": src_key}

    def scan(exc):
        """A file whose pages are images. Not a refusal - a document with no
        type yet, bound for OCR at filing.

        ONE PART, NO CLASSIFICATION. segment.segment is not called: there is
        no text to classify from, and a type guessed from a filename would put
        a guess where a reading belongs. The person chooses it, which is the
        price item 3 accepted.

        THE ENVELOPE MUST EXIST. It is empty - raw_text "" and no units -
        because nothing has been read yet. The collector READS this object
        when OCR finishes and overwrites those fields; without it the job
        completes and has nowhere to put the result."""
        envelope = {
            "tenant_id": tenant_id,
            "document_type": None,
            "document_type_proposed": None,
            "document_type_confidence": None,
            "document_type_reason": SCAN_REASON,
            "document_type_confirmed": False,
            "part_index": 1,
            "page_from": None,
            "page_to": None,
            "byte_size": len(body),
            "thin_text": True,
            "state": "analysed",
            "uploaded_by": uploaded_by,
            "engagement": engagement,
            "filename": filename,
            "source_bucket": src_bucket,
            "source_key": src_key,
            "source_version_id": obj.get("VersionId"),
            "sha256_source": sha,
            "extraction_method": None,
            "extracted_at": _now(),
            "config_revision": config.active_revision(tenant_id),
            "page_count": exc.pages,
            "char_count": exc.chars,
            "raw_text": "",
            "units": [],
            "extracted_values": [],
            "extraction_complete": False,
        }
        document_id = _record_document(envelope)
        envelope["document_id"] = document_id
        review_key = _write_envelope(src_key, envelope)
        print("[scan] doc=%s pages=%s chars=%s by=%s key=%s" % (
            document_id, exc.pages, exc.chars, uploaded_by, src_key))
        return {"status": "scan", "document_id": document_id,
                "pages": exc.pages, "chars": exc.chars,
                "review_key": review_key, "key": src_key}

    try:
        return _analyse(src_bucket, src_key, tenant_id, engagement, filename,
                        obj, body, sha, uploaded_by)
    except extractors.UnreadableDocument as exc:
        if exc.reason == "no_text_layer":
            return scan(exc)
        return refuse(_refusal_code(exc.reason), exc.reason)
    except Exception as exc:  # noqa: BLE001 - the row is the record, not a raise
        # NOT RE-RAISED, deliberately. Re-raising would have EventBridge retry
        # twice and write three refusal rows for one file. The row and this
        # line are the durable record; a crash BEFORE the row is written is
        # what Stage 2's on-failure destination is for.
        #
        # [normalizer-error] is the prefix Stage 5 puts a metric filter on. It
        # is the only place it appears, so a filter on it counts exactly this.
        print("[normalizer-error] key=%s %r" % (src_key, exc))
        traceback.print_exc()
        try:
            return refuse("error", type(exc).__name__)
        except Exception:  # noqa: BLE001 - nothing left to do but say so
            print("[normalizer-error] key=%s could not record the refusal"
                  % src_key)
            raise


def _analyse(src_bucket, src_key, tenant_id, engagement, filename, obj, body,
             sha, uploaded_by):
    """Read the document and record what it is. Everything below the fetch.

    Split out so lambda_handler can wrap the whole of it in one try: an exit
    that writes nothing is the defect Stage 1 closes, and the only way to be
    sure there is not a fifth one is to catch the lot."""
    raw_text, units, method = extractors.extract(src_key, body)

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
