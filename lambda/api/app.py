"""
app.py - the API.

One handler, several routes. Deliberately one function: the tenant identifier
is read from the signed token in exactly one place, which is the whole of the
isolation model. Spread across five functions, one of them eventually reads a
tenant from a request parameter and the boundary is gone.

Routes:
  GET  /engagements                     what this tenant has
  GET  /engagements/{id}/documents      documents in one engagement
  GET  /engagements/{id}/memos          memos generated for it
  POST /engagements/{id}/generate       compose a memo (deliberate act)
  GET  /memos/{memo_id}                 a rendered memo
  POST /uploads                         a signed link to upload one file
"""

import json
import os
import re
import time
import urllib.parse

import boto3
from botocore.exceptions import ClientError

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")
_lambda = boto3.client("lambda")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
DOCS_BUCKET = os.environ["DOCS_BUCKET"]
CURATED_BUCKET = os.environ["CURATED_BUCKET"]
COMPOSITION_FUNCTION = os.environ["COMPOSITION_FUNCTION"]

# Engagement and file names appear in S3 keys. Constrain them rather than
# trusting what arrives.
_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


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
                time.sleep(3)
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


def tenant_of(event):
    """THE isolation control.

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
    return int(raw)


def _reply(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


# --- routes ----------------------------------------------------------------

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


def list_documents(tenant_id, engagement):
    result = _sql(
        """
        SELECT document_id, filename, document_type, page_count,
               extraction_method, filed_at,
               (SELECT COUNT(*) FROM extracted_value v
                 WHERE v.document_id = d.document_id
                   AND v.tenant_id = d.tenant_id) AS values_found
        FROM document d
        WHERE tenant_id = :tenant_id
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
         "values": _col(r, 6)}
        for r in result.get("records", [])
    ]


def list_memos(tenant_id, engagement):
    result = _sql(
        """
        SELECT memo_id, template_key, generated_at, s3_key
        FROM memo
        WHERE tenant_id = :tenant_id
          AND s3_key LIKE :prefix
        ORDER BY generated_at DESC
        """,
        [_p("tenant_id", tenant_id),
         _p("prefix", "%/memos/" + engagement + "/%")],
    )
    return [
        {"memo_id": _col(r, 0),
         "template": _col(r, 1),
         "generated_at": _col(r, 2)}
        for r in result.get("records", [])
    ]


def get_memo(tenant_id, memo_id):
    """The tenant is in the WHERE clause, so another tenant's memo id simply
    returns nothing rather than someone else's document."""
    result = _sql(
        """
        SELECT s3_bucket, s3_key, generated_at
        FROM memo
        WHERE tenant_id = :tenant_id AND memo_id = :memo_id
        """,
        [_p("tenant_id", tenant_id), _p("memo_id", int(memo_id))],
    )
    records = result.get("records", [])
    if not records:
        return None

    bucket, key, generated_at = (_col(records[0], 0),
                                 _col(records[0], 1),
                                 _col(records[0], 2))
    body = _s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    return {"memo_id": int(memo_id), "generated_at": generated_at,
            "markdown": body}


def upload_url(tenant_id, engagement, filename):
    """A short-lived signed link. The browser uploads straight to S3; the file
    never passes through here. The key is built from the token's tenant, so a
    caller cannot place a file in another tenant's space."""
    if not _SAFE.match(engagement) or not _SAFE.match(filename):
        raise ValueError("engagement and filename must be letters, digits, dot, dash or underscore")

    key = "tenants/%d/docs/%s/%s" % (tenant_id, engagement, filename)
    url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": DOCS_BUCKET, "Key": key,
                "ServerSideEncryption": "aws:kms"},
        ExpiresIn=900,
    )
    return {"url": url, "key": key}


def generate(tenant_id, engagement):
    """Composition takes over a minute, so this starts it and returns. The
    caller polls the memo list."""
    _lambda.invoke(
        FunctionName=COMPOSITION_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps({"tenant_id": tenant_id, "engagement": engagement}),
    )
    return {"status": "started", "engagement": engagement}


# --- dispatch --------------------------------------------------------------

def lambda_handler(event, context):
    try:
        tenant_id = tenant_of(event)
    except (PermissionError, ValueError, TypeError):
        return _reply(403, {"error": "no tenant on token"})

    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}
    engagement = urllib.parse.unquote(params.get("id", "")) if params.get("id") else None

    try:
        if route == "GET /engagements":
            return _reply(200, {"engagements": list_engagements(tenant_id)})

        if route == "GET /engagements/{id}/documents":
            return _reply(200, {"documents": list_documents(tenant_id, engagement)})

        if route == "GET /engagements/{id}/memos":
            return _reply(200, {"memos": list_memos(tenant_id, engagement)})

        if route == "POST /engagements/{id}/generate":
            return _reply(202, generate(tenant_id, engagement))

        if route == "GET /memos/{memo_id}":
            memo = get_memo(tenant_id, params.get("memo_id"))
            if memo is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, memo)

        if route == "POST /uploads":
            body = json.loads(event.get("body") or "{}")
            return _reply(200, upload_url(tenant_id,
                                          body.get("engagement", ""),
                                          body.get("filename", "")))

        return _reply(404, {"error": "unknown route"})

    except ValueError as exc:
        return _reply(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - never leak internals to a client
        print("[api-error] route=%s tenant=%s %r" % (route, tenant_id, exc))
        return _reply(500, {"error": "internal error"})
