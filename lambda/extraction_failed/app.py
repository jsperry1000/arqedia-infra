"""
app.py - what extraction could not finish, finished (EXT-02 case 3).

Extraction catches each schema's failure, marks the document and refunds a
document that read nothing (EXT-02, #341). That holds only while the code
RUNS. A timeout at 300 seconds, an out-of-memory kill, a crash at start-up -
a stale layer, a bad import - leave the row with neither extracted_at nor
extraction_error: the screen says "extracting..." for ever and the $0.25
stays taken.

Lambda retries the invocation twice, then sends an on-failure INVOCATION
RECORD to the extraction-failed queue. Its requestPayload is the EventBridge
event that started extraction, which names the envelope. This function reads
the envelope for the document, and does what extraction would have done had
it lived (decided 5 November 2026):

  mark it     extracted_at now, extraction_error 'extraction_died' - so the
              screen says "extraction failed" instead of waiting
  refund it   if it holds no values, by wallet.refund() keyed
              'refund:<document_id>' - the same key extraction and the
              collector use, so a document is refunded once whichever came
              first

A SEPARATE FUNCTION, as composition-failed is (decided 19 October 2026): an
extraction that dies at start-up would break the thing meant to clean up
after it.

ONLY A ROW STILL UNMARKED. A document already marked - its run finished
after all, or this record arrived twice - is left exactly as it is. The
refund is keyed, so a second one is refused by the ledger whatever this
function believes.

A MESSAGE THAT CANNOT BE HANDLED IS LEFT ON THE QUEUE, reported back as a
batch item failure, so it is tried again and stays visible. The queue keeps
it fourteen days.
"""

import json
import os
import time
import urllib.parse

import boto3
from botocore.exceptions import ClientError

import wallet

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

# What goes in document.extraction_error. A code, as extraction's own are:
# the screen branches on nothing but "is it set".
ERROR_DIED = "extraction_died"

_ENVELOPE_SUFFIX = ".normalized.json"


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
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _envelope_key(payload):
    """The bucket and key extraction was started on, from the EventBridge
    event it was given - the shape extraction's _source_from_event reads."""
    detail = payload.get("detail") or {}
    bucket = (detail.get("bucket") or {}).get("name")
    key = (detail.get("object") or {}).get("key")
    if not bucket or not key:
        return None, None
    return bucket, urllib.parse.unquote_plus(key)


def _document(bucket, key):
    """The tenant and document the envelope names, or (None, None)."""
    if not key.endswith(_ENVELOPE_SUFFIX):
        return None, None
    envelope = json.loads(
        _s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8"))
    tenant_id = envelope.get("tenant_id")
    document_id = envelope.get("document_id")
    if tenant_id is None or not document_id:
        return None, None
    return int(tenant_id), int(document_id)


def _mark(tenant_id, document_id):
    """Mark the row failed, only where nothing has marked it. Answers whether
    this call was the one that did."""
    done = _sql(
        """
        UPDATE document
        SET extracted_at = UTC_TIMESTAMP(), extraction_error = :error
        WHERE tenant_id = :t AND document_id = :d
          AND extracted_at IS NULL AND extraction_error IS NULL
        """,
        [_p("error", ERROR_DIED), _p("t", tenant_id), _p("d", document_id)])
    return bool(done.get("numberOfRecordsUpdated"))


def _refund_if_nothing_read(tenant_id, document_id):
    """Extraction's own rule (lambda/extraction/app.py, same name): refunded
    only where the document holds no values, counted in the table. RAISES on
    a refund that could not be made, unlike extraction's: here that is a
    message to try again, not a line in a log.

    ONLY A ROW THIS FUNCTION MARKED. Asked of the row, not of whether this
    call marked it: a refund that threw sends the message round again, and
    the second delivery finds the row already marked - by us - and must
    still refund. A row extraction marked itself is extraction's to settle.
    The key makes a second refund a repeat, not a second payment."""
    found = _sql(
        "SELECT d.charge_entry_id, "
        "(SELECT COUNT(*) FROM extracted_value v "
        " WHERE v.tenant_id = d.tenant_id AND v.document_id = d.document_id), "
        "d.extraction_error "
        "FROM document d WHERE d.tenant_id = :t AND d.document_id = :d",
        [_p("t", tenant_id), _p("d", document_id)]).get("records", [])
    if not found:
        return {"refunded": False, "reason": "no document row"}
    entry = found[0][0].get("longValue")
    held = found[0][1].get("longValue") or 0
    error = found[0][2].get("stringValue")
    if error != ERROR_DIED:
        return {"refunded": False, "reason": "settled by extraction itself"}
    if held:
        return {"refunded": False, "reason": "holds %d values" % held}
    return wallet.refund(tenant_id, document_id, entry)


def _handle(record):
    """One invocation record. Returns what was done, for the log line."""
    payload = record.get("requestPayload") or {}
    response = record.get("responsePayload") or {}
    context = record.get("requestContext") or {}
    why = (response.get("errorMessage") or response.get("errorType")
           or context.get("condition") or "unknown")[:300]

    bucket, key = _envelope_key(payload)
    tenant_id = document_id = None
    if bucket:
        tenant_id, document_id = _document(bucket, key)

    if document_id is None:
        # Not an envelope, or one that names no document: nothing was charged
        # that this can find, so nothing is touched.
        outcome = "no document named: nothing done"
    else:
        marked = _mark(tenant_id, document_id)
        given = _refund_if_nothing_read(tenant_id, document_id)
        outcome = "marked=%s refunded=%s repeated=%s %s" % (
            marked, given.get("refunded"), given.get("repeated"),
            given.get("reason") or "")

    print("[extraction-died] tenant=%s doc=%s why=%s outcome=%s" % (
        tenant_id, document_id, why, outcome.strip()))
    return outcome


def lambda_handler(event, context):
    """SQS, a batch at a time. A message that could not be handled is named
    back to SQS (ReportBatchItemFailures) and comes round again; the rest
    are deleted."""
    failures = []
    for message in event.get("Records", []):
        try:
            _handle(json.loads(message["body"]))
        except Exception as exc:  # noqa: BLE001 - left on the queue, named
            print("[extraction-died-unhandled] message=%s %r" % (
                message.get("messageId"), exc))
            failures.append({"itemIdentifier": message.get("messageId")})
    return {"batchItemFailures": failures}
