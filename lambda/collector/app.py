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


def _document_for_job(job_id):
    result = _sql(
        """
        SELECT document_id, tenant_id, s3_key, document_type, textract_api
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
    }


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
            # A failed read is recorded rather than retried. The document keeps
            # whatever text it had, and the person can see it produced nothing.
            _sql("UPDATE document SET state = 'filed' WHERE document_id = :d",
                 [_p("d", document_id)])
            print("[collector] doc={} job={} status={}".format(
                document_id, job_id, status))
            results.append({"document_id": document_id, "status": status})
            continue

        text, units, tables = textract.fetch(job_id, document["mode"])

        # Rewrite the envelope with what OCR read, then write it under the name
        # extraction listens for. Same as filing a readable document.
        analysed_key = document["s3_key"] + ".analysed.json"
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
            Key=document["s3_key"] + ".normalized.json",
            Body=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )

        _sql(
            """
            UPDATE document
            SET state = 'filed',
                thin_text = 0,
                char_count = :chars,
                page_count = :pages,
                extraction_method = :method
            WHERE document_id = :d
            """,
            [
                _p("chars", len(text)),
                _p("pages", len(units)),
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
