"""
app.py - the API.

One handler, several routes. Deliberately one function: the tenant identifier
is read from the signed token in exactly one place, which is the whole of the
isolation model. Spread across five functions, one of them eventually reads a
tenant from a request parameter and the boundary is gone.

The token also carries the caller's email. That is recorded against every act -
upload, generate, deactivate, edit - because in a compliance record the author
of an act matters as much as the act.

Routes:
  GET  /engagements                      what this tenant has
  GET  /engagements/{id}/pending         analysed, awaiting confirmation
  POST /engagements/{id}/file            confirm types and file
  GET  /engagements/{id}/documents       filed documents
  POST /documents/{document_id}/active   include or exclude from future memos
  GET  /documents/{document_id}/values   what was extracted, and what was not
  GET  /documents/{document_id}/passage  the text of one page, for a citation
  GET  /engagements/{id}/memos           memos generated for it
  POST /engagements/{id}/generate        compose a memo (deliberate act)
  GET  /memos/{memo_id}                  a memo, its PDF link and its sources
  POST /uploads                          a signed link to upload one file
  GET  /document-types                   the type list, for the dropdown
"""

import json
import os
import re
import time
import urllib.parse

import boto3
from botocore.exceptions import ClientError

import pack
import textract

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")
_lambda = boto3.client("lambda")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
DOCS_BUCKET = os.environ["DOCS_BUCKET"]
REVIEW_BUCKET = os.environ["REVIEW_BUCKET"]
CURATED_BUCKET = os.environ["CURATED_BUCKET"]
COMPOSITION_FUNCTION = os.environ["COMPOSITION_FUNCTION"]
TEXTRACT_TOPIC_ARN = os.environ["TEXTRACT_TOPIC_ARN"]
TEXTRACT_ROLE_ARN = os.environ["TEXTRACT_ROLE_ARN"]


def _clean(name):
    """Make a name safe for a storage key while keeping it recognisable.

    Real documents are called things like "KCCA Trade Licence 2026.pdf".
    Rejecting them was a rule written for a machine rather than a person:
    whitespace becomes a dash, anything else unsafe is dropped."""
    name = re.sub(r"\s+", "-", (name or "").strip())
    name = re.sub(r"[^A-Za-z0-9._-]", "", name)
    name = re.sub(r"-{2,}", "-", name).strip("-.")
    return name[:120]


def _sql(statement, params=None):
    """Data API call, retrying while the cluster wakes from zero capacity."""
    for _ in range(12):
        try:
            return _rds.execute_statement(
                resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                database=DATABASE, sql=statement, parameters=params or [])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in (
                "DatabaseResumingException", "ThrottlingException"
            ):
                time.sleep(3)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _p(name, value):
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _col(record, i):
    cell = record[i]
    for kind in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if kind in cell:
            return cell[kind]
    return None


def caller(event):
    """THE isolation control, plus the author of whatever follows.

    The tenant comes from the claims API Gateway verified on the token, and
    from nowhere else. It is never read from the path, the query string or the
    body. A user cannot construct a request that reaches another tenant's data
    because the tenant is not something they supply.
    """
    claims = (event.get("requestContext", {})
                   .get("authorizer", {})
                   .get("jwt", {})
                   .get("claims", {}))
    raw = claims.get("custom:tenant_id")
    if raw is None:
        raise PermissionError("no tenant on token")
    email = claims.get("email") or claims.get("cognito:username") or "unknown"
    return int(raw), email


def _reply(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _label_for(field_id):
    if "." in field_id:
        group = field_id.split(".", 1)[0]
        for col in (pack.group_columns(group) or []):
            if col[0] == field_id:
                return col[1]
    return pack.label_for(field_id)


# --- engagements -----------------------------------------------------------

def list_engagements(tenant_id):
    result = _sql(
        """
        SELECT
          SUBSTRING_INDEX(SUBSTRING_INDEX(s3_key, '/docs/', -1), '/', 1) AS engagement,
          COUNT(*)      AS documents,
          MAX(filed_at) AS last_activity
        FROM document
        WHERE tenant_id = :tenant_id
        GROUP BY engagement
        ORDER BY last_activity DESC
        """,
        [_p("tenant_id", tenant_id)],
    )
    return [
        {"engagement": _col(r, 0),
         "documents": _col(r, 1),
         "last_activity": _col(r, 2)}
        for r in result.get("records", [])
    ]


def list_pending(tenant_id, engagement):
    """Analysed but not yet filed: the proposed type, how sure, and why."""
    result = _sql(
        """
        SELECT document_id, filename, document_type, page_count,
               thin_text, char_count, type_confidence, type_reason, state,
               uploaded_by
        FROM document
        WHERE tenant_id = :tenant_id
          AND state IN ('analysed', 'reading')
          AND s3_key LIKE :prefix
        ORDER BY document_id
        """,
        [_p("tenant_id", tenant_id),
         _p("prefix", "%/docs/" + engagement + "/%")],
    )
    return [
        {"document_id": _col(r, 0),
         "filename": _col(r, 1),
         "proposed_type": _col(r, 2),
         "pages": _col(r, 3),
         "thin_text": bool(_col(r, 4)),
         "chars": _col(r, 5),
         "confidence": _col(r, 6),
         "why": _col(r, 7),
         "state": _col(r, 8),
         "uploaded_by": _col(r, 9)}
        for r in result.get("records", [])
    ]


def _start_ocr(tenant_id, document_id, s3_key, document_type):
    """Send a scan to OCR rather than to extraction.

    The read mode comes from the confirmed type, which is why confirmation
    happens before filing. The job runs asynchronously; the collector picks it
    up on completion and releases the document to extraction then."""
    job_id, mode = textract.start(
        DOCS_BUCKET, s3_key, document_type,
        TEXTRACT_TOPIC_ARN, TEXTRACT_ROLE_ARN)
    _sql(
        """
        UPDATE document
        SET document_type = :ty, type_confirmed = 1, state = 'reading',
            textract_job_id = :job, textract_api = :mode
        WHERE tenant_id = :t AND document_id = :d
        """,
        [_p("ty", document_type), _p("job", job_id), _p("mode", mode),
         _p("t", tenant_id), _p("d", document_id)],
    )
    return job_id, mode


def file_documents(tenant_id, decisions):
    """Confirm types and file. The deliberate act that starts extraction -
    and, later, the point at which money changes hands.

    A document that could not be read goes to OCR instead, and reaches
    extraction when the OCR finishes. A rejected document is marked and kept,
    never deleted."""
    filed, rejected, reading = 0, 0, 0

    for d in decisions:
        document_id = int(d.get("document_id"))

        if not d.get("include", True):
            _sql("UPDATE document SET state = 'rejected' "
                 "WHERE tenant_id = :t AND document_id = :d",
                 [_p("t", tenant_id), _p("d", document_id)])
            rejected += 1
            continue

        document_type = d.get("document_type") or None

        row = _sql("SELECT s3_key, thin_text FROM document "
                   "WHERE tenant_id = :t AND document_id = :d",
                   [_p("t", tenant_id), _p("d", document_id)])
        records = row.get("records", [])
        if not records:
            continue
        s3_key = _col(records[0], 0)
        thin = bool(_col(records[0], 1))

        if thin or textract.always_ocr(document_type):
            _start_ocr(tenant_id, document_id, s3_key, document_type)
            reading += 1
            continue

        _sql("UPDATE document SET document_type = :ty, type_confirmed = 1, "
             "state = 'filed' WHERE tenant_id = :t AND document_id = :d",
             [_p("ty", document_type), _p("t", tenant_id),
              _p("d", document_id)])

        # Extraction listens for .normalized.json. Renaming the envelope is
        # what starts it - filing, not uploading.
        body = _s3.get_object(Bucket=REVIEW_BUCKET,
                              Key=s3_key + ".analysed.json")["Body"].read()
        envelope = json.loads(body.decode("utf-8"))
        envelope["document_type"] = document_type
        envelope["document_type_confirmed"] = True
        _s3.put_object(
            Bucket=REVIEW_BUCKET, Key=s3_key + ".normalized.json",
            Body=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json")
        filed += 1

    return {"filed": filed, "reading": reading, "rejected": rejected}


# --- documents -------------------------------------------------------------

def list_documents(tenant_id, engagement):
    """Filed documents. `reading` documents are included so the screen can see
    that something is in flight and hold the generate action."""
    result = _sql(
        """
        SELECT document_id, filename, document_type, page_count,
               extraction_method, filed_at, uploaded_by, active, state,
               deactivated_by, deactivated_at, extracted_at,
               (SELECT COUNT(*) FROM extracted_value v
                 WHERE v.document_id = d.document_id
                   AND v.tenant_id = d.tenant_id) AS values_found
        FROM document d
        WHERE tenant_id = :tenant_id
          AND state IN ('filed', 'reading')
          AND s3_key LIKE :prefix
        ORDER BY document_id
        """,
        [_p("tenant_id", tenant_id),
         _p("prefix", "%/docs/" + engagement + "/%")],
    )
    return [
        {"document_id": _col(r, 0),
         "filename": _col(r, 1),
         "document_type": _col(r, 2),
         "pages": _col(r, 3),
         "method": _col(r, 4),
         "filed_at": _col(r, 5),
         "uploaded_by": _col(r, 6),
         "active": bool(_col(r, 7)),
         "state": _col(r, 8),
         "deactivated_by": _col(r, 9),
         "deactivated_at": _col(r, 10),
         # Null means extraction has not run. Zero values with a null here is
         # "still working"; zero values with a timestamp is a finding.
         "extracted_at": _col(r, 11),
         "values": _col(r, 12)}
        for r in result.get("records", [])
    ]


def set_active(tenant_id, email, document_id, active):
    """Include or exclude a filed document from future memos.

    Deactivating never deletes: a diligence file keeps everything it was given
    and records what was set aside, by whom and when. Memos already generated
    are untouched - they cited what was current when they were written."""
    if active:
        _sql("UPDATE document SET active = 1, deactivated_by = NULL, "
             "deactivated_at = NULL WHERE tenant_id = :t AND document_id = :d",
             [_p("t", tenant_id), _p("d", int(document_id))])
    else:
        _sql("UPDATE document SET active = 0, deactivated_by = :who, "
             "deactivated_at = UTC_TIMESTAMP() "
             "WHERE tenant_id = :t AND document_id = :d",
             [_p("who", email), _p("t", tenant_id), _p("d", int(document_id))])
    return {"document_id": int(document_id), "active": bool(active)}


def document_values(tenant_id, document_id):
    """What was extracted from one document, and what its type called for but
    did not yield. An empty list of found values says less than a list of the
    fields that were looked for and missed."""
    head = _sql(
        """
        SELECT filename, document_type, page_count, extraction_method
        FROM document WHERE tenant_id = :t AND document_id = :d
        """,
        [_p("t", tenant_id), _p("d", int(document_id))],
    )
    records = head.get("records", [])
    if not records:
        return None

    result = _sql(
        """
        SELECT field_id, value, locator_kind, locator_index, row_ordinal
        FROM extracted_value
        WHERE tenant_id = :t AND document_id = :d
        ORDER BY field_id, row_ordinal
        """,
        [_p("t", tenant_id), _p("d", int(document_id))],
    )

    values, found = [], set()
    for r in result.get("records", []):
        field_id = _col(r, 0)
        found.add(field_id.split(".", 1)[0])
        values.append({
            "field_id": field_id,
            "label": _label_for(field_id),
            "value": _col(r, 1),
            "locator_kind": _col(r, 2),
            "locator_index": _col(r, 3),
            "row": _col(r, 4),
        })

    document_type = _col(records[0], 1)
    expected, missing = [], []
    for schema_key in pack.schemas_for(document_type):
        schema = pack.get_schema(schema_key)
        if not schema:
            continue
        for f in schema["fields"]:
            expected.append(f[0])
            if f[0] not in found:
                missing.append({"field_id": f[0], "label": f[1]})

    return {
        "document_id": int(document_id),
        "filename": _col(records[0], 0),
        "document_type": document_type,
        "pages": _col(records[0], 2),
        "method": _col(records[0], 3),
        "values": values,
        "missing": missing,
        "expected": len(expected),
    }


def document_passage(tenant_id, document_id, unit):
    """The text of one page, so a citation can be checked against what the
    system actually read.

    This is what was read, not the original image - which is arguably the more
    useful thing when checking an extraction, since a wrong value is usually a
    misreading rather than a misprint."""
    row = _sql(
        "SELECT s3_key, filename, page_count FROM document "
        "WHERE tenant_id = :t AND document_id = :d",
        [_p("t", tenant_id), _p("d", int(document_id))],
    )
    records = row.get("records", [])
    if not records:
        return None

    s3_key = _col(records[0], 0)
    envelope = json.loads(
        _s3.get_object(Bucket=REVIEW_BUCKET,
                       Key=s3_key + ".normalized.json")["Body"].read()
        .decode("utf-8"))

    raw = envelope.get("raw_text") or ""
    units = envelope.get("units") or []

    text, kind, label = raw, "document", None
    if unit:
        for u in units:
            if u.get("index") == int(unit):
                text = raw[u.get("char_start", 0):u.get("char_end", len(raw))]
                kind = u.get("kind") or "page"
                label = u.get("label")
                break

    source_url = _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": DOCS_BUCKET, "Key": s3_key},
        ExpiresIn=3600)

    return {
        "document_id": int(document_id),
        "filename": _col(records[0], 1),
        "unit": int(unit) if unit else None,
        "unit_kind": kind,
        "unit_label": label,
        "pages": _col(records[0], 2),
        "text": text[:20000],
        "source_url": source_url,
    }


# --- memos -----------------------------------------------------------------

def list_memos(tenant_id, engagement):
    result = _sql(
        """
        SELECT memo_id, template_key, generated_at, generated_by,
               parent_memo_id, revision, modified_by, modified_at, pdf_key
        FROM memo
        WHERE tenant_id = :tenant_id
          AND s3_key LIKE :prefix
        ORDER BY COALESCE(parent_memo_id, memo_id) DESC, revision DESC
        """,
        [_p("tenant_id", tenant_id),
         _p("prefix", "%/memos/" + engagement + "/%")],
    )
    return [
        {"memo_id": _col(r, 0),
         "template": _col(r, 1),
         "generated_at": _col(r, 2),
         "generated_by": _col(r, 3),
         "parent_memo_id": _col(r, 4),
         "revision": _col(r, 5),
         "modified_by": _col(r, 6),
         "modified_at": _col(r, 7),
         "label": "%s.%s" % (_col(r, 4) or _col(r, 0), _col(r, 5)),
         "has_pdf": bool(_col(r, 8))}
        for r in result.get("records", [])
    ]


def get_memo(tenant_id, memo_id):
    """A memo, a signed link to its PDF, and the documents behind it.

    The sources are returned so the reader can turn a citation - which names a
    filename - into something it can open. The memo text has no document
    identifiers in it; this is the map."""
    result = _sql(
        """
        SELECT s3_bucket, s3_key, generated_at, generated_by, pdf_key,
               parent_memo_id, revision, modified_by, modified_at
        FROM memo
        WHERE tenant_id = :tenant_id AND memo_id = :memo_id
        """,
        [_p("tenant_id", tenant_id), _p("memo_id", int(memo_id))],
    )
    records = result.get("records", [])
    if not records:
        return None
    r = records[0]

    markdown = _s3.get_object(
        Bucket=_col(r, 0), Key=_col(r, 1))["Body"].read().decode("utf-8")

    sources = _sql(
        """
        SELECT d.document_id, d.filename
        FROM memo_source ms
        JOIN document d ON d.document_id = ms.document_id
        WHERE ms.tenant_id = :t AND ms.memo_id = :m
        """,
        [_p("t", tenant_id), _p("m", int(memo_id))],
    )

    pdf_url = None
    pdf_key = _col(r, 4)
    if pdf_key:
        # A signed link, so the browser fetches the PDF straight from storage.
        # Short-lived, and shareable for as long as it lives.
        pdf_url = _s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": CURATED_BUCKET, "Key": pdf_key},
            ExpiresIn=3600)

    return {
        "memo_id": int(memo_id),
        "generated_at": _col(r, 2),
        "generated_by": _col(r, 3),
        "parent_memo_id": _col(r, 5),
        "revision": _col(r, 6),
        "label": "%s.%s" % (_col(r, 5) or int(memo_id), _col(r, 6)),
        "modified_by": _col(r, 7),
        "modified_at": _col(r, 8),
        "markdown": markdown,
        "pdf_url": pdf_url,
        "sources": [{"document_id": _col(s, 0), "filename": _col(s, 1)}
                    for s in sources.get("records", [])],
    }


# --- uploads and generation ------------------------------------------------

def upload_url(tenant_id, email, engagement, filename):
    """A short-lived signed link. The browser uploads straight to S3; the file
    never passes through here. The key is built from the token's tenant, so a
    caller cannot place a file in another tenant's space.

    The caller's email travels as object metadata: this function knows who is
    asking, the normalizer does not, so the answer has to arrive with the
    object. It also stays with the object permanently, which is better
    provenance than a lookup table."""
    engagement = _clean(engagement)
    filename = _clean(filename)
    if not engagement or not filename:
        raise ValueError("engagement and file name are required")

    key = "tenants/%d/docs/%s/%s" % (tenant_id, engagement, filename)
    url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": DOCS_BUCKET, "Key": key,
                "ServerSideEncryption": "aws:kms",
                "Metadata": {"uploaded-by": email}},
        ExpiresIn=900)
    return {"url": url, "key": key, "uploaded_by": email}


def generate(tenant_id, email, engagement):
    """Composition takes over a minute, so this starts it and returns. The
    caller polls the memo list."""
    _lambda.invoke(
        FunctionName=COMPOSITION_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps({"tenant_id": tenant_id, "engagement": engagement,
                            "generated_by": email}))
    return {"status": "started", "engagement": engagement}


def document_types():
    """The type list for the dropdown, with what filing each one will do - so
    the screen can say whether confirming a type triggers OCR."""
    return [
        {"key": t["key"], "label": t["label"], "category": t["category"],
         "description": t["description"],
         "read_mode": textract.read_mode_for(t["key"]),
         "always_ocr": textract.always_ocr(t["key"])}
        for t in pack.document_type_list()
    ]


# --- dispatch --------------------------------------------------------------

def lambda_handler(event, context):
    try:
        tenant_id, email = caller(event)
    except (PermissionError, ValueError, TypeError):
        return _reply(403, {"error": "no tenant on token"})

    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}
    engagement = urllib.parse.unquote(params.get("id", "")) \
        if params.get("id") else None

    try:
        if route == "GET /engagements":
            return _reply(200, {"engagements": list_engagements(tenant_id)})

        if route == "GET /engagements/{id}/pending":
            return _reply(200, {"pending": list_pending(tenant_id, engagement)})

        if route == "POST /engagements/{id}/file":
            body = json.loads(event.get("body") or "{}")
            return _reply(200, file_documents(tenant_id,
                                              body.get("decisions", [])))

        if route == "GET /engagements/{id}/documents":
            return _reply(200, {"documents": list_documents(tenant_id,
                                                            engagement)})

        if route == "POST /documents/{document_id}/active":
            body = json.loads(event.get("body") or "{}")
            return _reply(200, set_active(tenant_id, email,
                                          params.get("document_id"),
                                          bool(body.get("active", True))))

        if route == "GET /documents/{document_id}/values":
            detail = document_values(tenant_id, params.get("document_id"))
            if detail is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, detail)

        if route == "GET /documents/{document_id}/passage":
            passage = document_passage(tenant_id, params.get("document_id"),
                                       query.get("unit"))
            if passage is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, passage)

        if route == "GET /engagements/{id}/memos":
            return _reply(200, {"memos": list_memos(tenant_id, engagement)})

        if route == "POST /engagements/{id}/generate":
            return _reply(202, generate(tenant_id, email, engagement))

        if route == "GET /memos/{memo_id}":
            memo = get_memo(tenant_id, params.get("memo_id"))
            if memo is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, memo)

        if route == "POST /uploads":
            body = json.loads(event.get("body") or "{}")
            return _reply(200, upload_url(tenant_id, email,
                                          body.get("engagement", ""),
                                          body.get("filename", "")))

        if route == "GET /document-types":
            return _reply(200, {"types": document_types()})

        return _reply(404, {"error": "unknown route"})

    except ValueError as exc:
        return _reply(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - never leak internals to a client
        print("[api-error] route=%s tenant=%s %r" % (route, tenant_id, exc))
        return _reply(500, {"error": "internal error"})
