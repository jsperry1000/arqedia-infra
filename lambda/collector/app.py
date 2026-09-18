"""
app.py - Textract collector.

Runs when a Textract job finishes. Picks up the recognised text, rewrites the
document's envelope with it, and hands the document on to extraction exactly as
if the text had been readable all along.

Nothing downstream knows OCR happened. The envelope has the same shape - text,
page boundaries, tables - so locators, citations and extraction are unchanged.

Triggered by a notification, not by polling: a twelve-page scan takes minutes
and no function should sit waiting for it.
"""

import json
import os
import time

import boto3
from botocore.exceptions import ClientError

import textract
import wallet

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")

REVIEW_BUCKET = os.environ["REVIEW_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]


def _sql(statement, params=None):
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
            if exc.response.get("Error", {}).get("Code") in (
                "DatabaseResumingException", "ThrottlingException"
            ):
                time.sleep(5)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _p(name, value):
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _col(record, i):
    cell = record[i]
    for kind in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if kind in cell:
            return cell[kind]
    return None


def envelope_suffix(page_from, part_index):
    """Where a document's envelope lives, relative to the file's own key.

    THE THIRD COPY OF THIS RULE. The normalizer writes envelopes and the API
    renames them at filing; both carry it. This function did not, and asked
    for the unsuffixed name - so a part's OCR result was read from an object
    that does not exist and the document never left `reading`.

    The three must not drift. Parts of one file share an s3_key, so the part
    number is what tells their envelopes apart."""
    if page_from is None:
        return ".analysed.json"
    return ".p" + str(part_index) + ".analysed.json"


def _document_for_job(job_id):
    result = _sql(
        """
        SELECT document_id, tenant_id, s3_key, document_type, textract_api,
               page_from, part_index, charge_entry_id
        FROM document
        WHERE textract_job_id = :job_id
        """,
        [_p("job_id", job_id)],
    )
    records = result.get("records", [])
    if not records:
        return None
    r = records[0]
    return {
        "document_id": _col(r, 0),
        "tenant_id": _col(r, 1),
        "s3_key": _col(r, 2),
        "document_type": _col(r, 3),
        "mode": _col(r, 4),
        "page_from": _col(r, 5),
        "part_index": _col(r, 6),
        # Which ledger entry paid for it, so a failed read can give it back.
        "charge_entry_id": _col(r, 7),
    }


# The same sentence the API uses when a read fails at the other end. One
# wording for one thing, in one place per function - the two must not drift.
OCR_FAILED_REASON = (
    "This file could not be read, even with OCR. It can't be used in its "
    "current state. Please fix it on your side and upload it again. The "
    "charge for it has been refunded.")


def _failed_read(document, job_id, status):
    """Textract came back with something other than SUCCEEDED.

    Terminal, in the state Stage 1 uses for a document nobody could read, so
    it lands in the one block the screen already has for this. Then the charge
    comes back, keyed on the document so a redelivered notification cannot
    refund it twice.

    The refusal is written BEFORE the refund. If the refund throws, the person
    is still told the document failed - the worse failure is a document that
    looks fine and is not."""
    document_id = document["document_id"]
    tenant_id = document["tenant_id"]

    _sql(
        "UPDATE document SET state = 'unreadable', refusal_code = 'ocr_failed',"
        " refusal_reason = :r WHERE document_id = :d",
        [_p("r", OCR_FAILED_REASON), _p("d", document_id)])

    given = {"refunded": False}
    try:
        given = wallet.refund(tenant_id, document_id,
                              document.get("charge_entry_id"))
    except Exception as exc:  # noqa: BLE001 - the refusal stands regardless
        print("[refund-failed] tenant={} doc={} entry={} {!r}".format(
            tenant_id, document_id, document.get("charge_entry_id"), exc))

    print("[ocr-failed] doc={} job={} status={} refunded={} repeated={} "
          "cents={}".format(document_id, job_id, status,
                            given.get("refunded"), given.get("repeated"),
                            given.get("amount_cents")))
    return {"document_id": document_id, "status": status,
            "refunded": bool(given.get("refunded"))}


def lambda_handler(event, context):
    results = []

    for record in event.get("Records", []):
        message = json.loads(record["Sns"]["Message"])
        job_id = message.get("JobId")
        status = message.get("Status")

        document = _document_for_job(job_id)
        if not document:
            print("[collector] unknown job {}".format(job_id))
            results.append({"job_id": job_id, "status": "unknown-job"})
            continue

        document_id = document["document_id"]

        if status != "SUCCEEDED":
            # WAS THE QUIETEST POSSIBLE OUTCOME. It marked the document
            # 'filed', so it looked successfully filed and sat in the list with
            # no values - indistinguishable from a document that genuinely
            # contained nothing - while the charge stood. Nothing said why.
            #
            # Now it is terminal, it says so in words, and the money comes back
            # (decision record, 18 September, items 14 and 16).
            results.append(_failed_read(document, job_id, status))
            continue

        text, units, tables = textract.fetch(job_id, document["mode"])

        # Rewrite the envelope with what OCR read, then write it under the name
        # extraction listens for. Same as filing a readable document.
        suffix = envelope_suffix(document["page_from"],
                                 document["part_index"])
        analysed_key = document["s3_key"] + suffix
        envelope = json.loads(
            _s3.get_object(Bucket=REVIEW_BUCKET,
                           Key=analysed_key)["Body"].read().decode("utf-8"))

        envelope["raw_text"] = text
        envelope["units"] = units
        envelope["tables"] = tables
        envelope["extraction_method"] = "textract-" + (document["mode"] or "text")
        envelope["thin_text"] = False
        envelope["document_type"] = document["document_type"]
        envelope["document_type_confirmed"] = True

        _s3.put_object(
            Bucket=REVIEW_BUCKET,
            Key=document["s3_key"]
                + suffix.replace(".analysed.", ".normalized."),
            Body=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )

        _sql(
            """
            UPDATE document
            SET state = 'filed',
                thin_text = 0,
                char_count = :chars,
                page_count = COALESCE(:pages, page_count),
                extraction_method = :method
            WHERE document_id = :d
            """,
            [
                _p("chars", len(text)),
                # A part's page count stays its own. Textract reads the whole
                # file - its API takes an object, not a page range - so the
                # count it returns is the file's, and writing it here would
                # tell a reader that page 5 of a five-page file is five pages
                # long.
                _p("pages", len(units) if document["page_from"] is None
                   else None),
                _p("method", envelope["extraction_method"]),
                _p("d", document_id),
            ],
        )

        print("[collector] doc={} job={} chars={} pages={} tables={}".format(
            document_id, job_id, len(text), len(units), len(tables)))

        results.append({
            "document_id": document_id,
            "status": "ok",
            "chars": len(text),
            "pages": len(units),
            "tables": len(tables),
        })

    return {"collected": results}
