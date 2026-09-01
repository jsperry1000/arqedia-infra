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
  DELETE /documents/{document_id}         discard one not yet filed
  GET  /documents/{document_id}/values   what was extracted, and what was not
  GET  /documents/{document_id}/passage  the text of one page, for a citation
  GET  /engagements/{id}/memos           memos generated for it
  POST /engagements/{id}/generate        compose a memo (deliberate act)
  GET  /memos/{memo_id}                  a memo, its PDF link and its sources
  POST /uploads                          a signed link to upload one file
  GET  /document-types                   the type list, for the dropdown
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
import editor
import registry
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
BRAND_BUCKET = os.environ["BRAND_BUCKET"]
COMPOSITION_FUNCTION = os.environ["COMPOSITION_FUNCTION"]
TEXTRACT_TOPIC_ARN = os.environ["TEXTRACT_TOPIC_ARN"]
TEXTRACT_ROLE_ARN = os.environ["TEXTRACT_ROLE_ARN"]
RENDER_FUNCTION = os.environ["RENDER_FUNCTION"]


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
    """THE isolation control, plus the author of whatever follows and what
    they are permitted to do.

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
    # Role is signed into the token and excluded from the client's writable
    # attributes, so a user cannot promote themselves. Every user is an admin
    # today; the check is here so Component 9's seat model can begin creating
    # members without any rule being rewritten.
    role = claims.get("custom:role") or "member"
    return int(raw), email, role


def _reply(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _label_for(registry, field_id):
    if "." in field_id:
        group = field_id.split(".", 1)[0]
        for col in (registry.group_columns(group) or []):
            if col[0] == field_id:
                return col[1]
    return registry.label_for(field_id)


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


def _start_ocr(registry, tenant_id, document_id, s3_key, document_type):
    """Send a scan to OCR rather than to extraction.

    The read mode comes from the confirmed type, which is why confirmation
    happens before filing. The job runs asynchronously; the collector picks it
    up on completion and releases the document to extraction then."""
    job_id, mode = textract.start(
        DOCS_BUCKET, s3_key, document_type,
        TEXTRACT_TOPIC_ARN, TEXTRACT_ROLE_ARN,
        read_mode=registry.read_mode_for(document_type))
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
    registry = config.for_tenant(tenant_id)
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

        if thin or registry.always_ocr(document_type):
            _start_ocr(registry, tenant_id, document_id, s3_key,
                       document_type)
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

def remove_document(tenant_id, document_id):
    """Discard a document that has not been filed.

    The only destructive action outside account deletion, and deliberately so.
    A file chosen by mistake may belong to another client or to nobody's
    business but the uploader's, and marking it rejected would leave it in this
    tenant's storage indefinitely. Both objects go - the upload and the
    analysed envelope holding its text - and then the row.

    Refused once filing has started. A document in `reading` has a Textract job
    in flight that would write back to a row no longer there, and a filed one
    has been extracted and paid for. Neither is a misclick.
    """
    row = _sql("SELECT s3_key, state FROM document "
               "WHERE tenant_id = :t AND document_id = :d",
               [_p("t", tenant_id), _p("d", document_id)])
    records = row.get("records", [])
    if not records:
        return None

    s3_key = _col(records[0], 0)
    state = _col(records[0], 1)
    if state != "analysed":
        return {"refused": state}

    # Storage first. A failure here leaves the row intact and the card on
    # screen, which is retryable. The reverse orphans an object nobody can see.
    # Deleting a key that is not there is not an error in S3, so the second
    # call is safe whether or not the normalizer got that far.
    _s3.delete_object(Bucket=DOCS_BUCKET, Key=s3_key)
    _s3.delete_object(Bucket=REVIEW_BUCKET, Key=s3_key + ".analysed.json")

    _sql("DELETE FROM document WHERE tenant_id = :t AND document_id = :d",
         [_p("t", tenant_id), _p("d", document_id)])
    return {"removed": document_id}


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
        SELECT filename, document_type, page_count, extraction_method,
               config_revision
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

    # The revision the document was filed under, so "looked for, not found"
    # names the fields that were actually looked for at the time.
    registry = config.load(tenant_id, _col(records[0], 4) or 1)

    values, found = [], set()
    for r in result.get("records", []):
        field_id = _col(r, 0)
        found.add(field_id.split(".", 1)[0])
        values.append({
            "field_id": field_id,
            "label": _label_for(registry, field_id),
            "value": _col(r, 1),
            "locator_kind": _col(r, 2),
            "locator_index": _col(r, 3),
            "row": _col(r, 4),
        })

    document_type = _col(records[0], 1)
    expected, missing = [], []
    for schema_key in registry.schemas_for(document_type):
        schema = registry.get_schema(schema_key)
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

    # No PDF link here. The PDF is a view of the memo, rendered on demand from
    # the markdown, so it is always current with whatever the renderer does
    # today. Serving a file rendered weeks ago meant a presentation
    # improvement never reached a memo already written.

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
        "sources": [{"document_id": _col(s, 0), "filename": _col(s, 1)}
                    for s in sources.get("records", [])],
    }


def revise_memo(tenant_id, email, memo_id, markdown):
    """Save an edited memo as a NEW row. The original and its PDF are never
    touched: a compliance record is not overwritten, and which version anyone
    read stays answerable.

    Sources carry forward - the revision rests on the same documents. Claims
    do not. A claim binds a generated sentence to the values behind it, and
    once a person has rewritten that sentence the binding describes text that
    no longer exists. The editor's review is the evidence for a revision; that
    is what signing off means, and it belongs to a person rather than to the
    machinery.
    """
    parent = _sql(
        """
        SELECT s3_key, template_key, config_revision, parent_memo_id, revision
        FROM memo WHERE tenant_id = :t AND memo_id = :m
        """,
        [_p("t", tenant_id), _p("m", int(memo_id))],
    )
    records = parent.get("records", [])
    if not records:
        return None

    parent_key = _col(records[0], 0)
    template_key = _col(records[0], 1)
    config_revision = _col(records[0], 2)
    root_id = _col(records[0], 3) or int(memo_id)

    # A citation naming a file that is not one of this memo's sources cannot
    # be checked against anything. Refuse the save rather than accept an
    # assertion nobody can verify.
    sources = _sql(
        """
        SELECT DISTINCT d.filename
        FROM memo_source ms
        JOIN document d ON d.document_id = ms.document_id
        WHERE ms.tenant_id = :t AND ms.memo_id = :m
        """,
        [_p("t", tenant_id), _p("m", root_id)],
    )
    known = {_col(r, 0) for r in sources.get("records", [])}

    # Anything of the form "<name>, page 3" is making a citation claim,
    # whether or not it looks like a filename. Requiring an extension let
    # "made-up-ref-1.0, page 1" through: it named no real document, cited a
    # page, and read as authoritative.
    cited = set()
    for m in re.finditer(
        r"([A-Za-z0-9._()\-]{3,})\s*,\s*(?:page|section|sheet)\s+\d+",
        markdown, re.I,
    ):
        cited.add(m.group(1).strip())
    for m in re.finditer(
        r"[A-Za-z0-9._()\-]+\.(?:pdf|docx|xlsx|txt|json|xml)", markdown
    ):
        cited.add(m.group(0))

    unknown = sorted(c for c in cited if c not in known)
    if unknown:
        raise ValueError(
            "these citations name documents that are not sources of this "
            "memo: " + ", ".join(unknown[:6]))

    # The next revision of this memo's line, not of this row.
    highest = _sql(
        """
        SELECT COALESCE(MAX(revision), 0) FROM memo
        WHERE tenant_id = :t
          AND (memo_id = :root OR parent_memo_id = :root)
        """,
        [_p("t", tenant_id), _p("root", root_id)],
    )
    next_revision = int(_col(highest.get("records", [[{}]])[0], 0) or 0) + 1

    encoded = markdown.encode("utf-8")
    sha = hashlib.sha256(encoded).hexdigest()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    new_key = "%s-r%d-%s.md" % (parent_key.rsplit(".", 1)[0],
                                next_revision, stamp)

    put = _s3.put_object(Bucket=CURATED_BUCKET, Key=new_key, Body=encoded,
                         ContentType="text/markdown")

    created = _sql(
        """
        INSERT INTO memo
          (tenant_id, template_key, config_revision, s3_bucket, s3_key,
           s3_version_id, sha256, parent_memo_id, revision,
           modified_by, modified_at)
        VALUES
          (:tenant_id, :template_key, :config_revision, :s3_bucket, :s3_key,
           :s3_version_id, :sha256, :parent_memo_id, :revision,
           :modified_by, UTC_TIMESTAMP())
        """,
        [
            _p("tenant_id", tenant_id),
            _p("template_key", template_key),
            _p("config_revision", config_revision),
            _p("s3_bucket", CURATED_BUCKET),
            _p("s3_key", new_key),
            _p("s3_version_id", put.get("VersionId")),
            _p("sha256", sha),
            _p("parent_memo_id", root_id),
            _p("revision", next_revision),
            _p("modified_by", email),
        ],
    )
    new_id = created.get("generatedFields", [{}])[0].get("longValue")

    # Sources carry forward: the revision rests on the same documents.
    _sql(
        """
        INSERT IGNORE INTO memo_source (memo_id, document_id, tenant_id)
        SELECT :new_id, document_id, tenant_id
        FROM memo_source WHERE tenant_id = :t AND memo_id = :root
        """,
        [_p("new_id", new_id), _p("t", tenant_id), _p("root", root_id)],
    )

    _lambda.invoke(
        FunctionName=RENDER_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps({"tenant_id": tenant_id, "memo_id": new_id}))

    print("[revised] memo=%s from=%s revision=%d by=%s" % (
        new_id, memo_id, next_revision, email))

    return {"memo_id": new_id, "parent_memo_id": root_id,
            "revision": next_revision,
            "label": "%s.%s" % (root_id, next_revision)}


# --- settings --------------------------------------------------------------

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg"}


def get_settings(tenant_id):
    """The tenant's name, plan and branding. Branding is returned whatever the
    plan, so a Base tenant can see what a paid plan would let them set rather
    than finding an empty screen."""
    result = _sql(
        """
        SELECT name, plan, brand_logo_key, brand_deep, brand_mid,
               brand_highlight
        FROM tenant WHERE tenant_id = :t
        """,
        [_p("t", tenant_id)],
    )
    records = result.get("records", [])
    if not records:
        return None
    r = records[0]

    plan = (_col(r, 1) or "base").lower()
    logo_key = _col(r, 2)

    logo_url = None
    if logo_key:
        try:
            logo_url = _s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BRAND_BUCKET, "Key": logo_key},
                ExpiresIn=3600)
        except Exception:  # noqa: BLE001 - a missing logo is not an error
            logo_url = None

    return {
        "name": _col(r, 0),
        "plan": plan,
        "may_brand": plan in ("business", "enterprise"),
        "may_remove_footer": plan == "enterprise",
        "logo_key": logo_key,
        "logo_url": logo_url,
        "deep": _col(r, 3),
        "mid": _col(r, 4),
        "highlight": _col(r, 5),
    }


def _require_branding(tenant_id, role):
    """Two gates, and they fail differently on purpose: one is about who you
    are, the other about what the tenant pays for."""
    if role != "admin":
        raise PermissionError("only an administrator may change branding")

    result = _sql("SELECT plan FROM tenant WHERE tenant_id = :t",
                  [_p("t", tenant_id)])
    records = result.get("records", [])
    plan = (_col(records[0], 0) if records else "base") or "base"
    if plan.lower() not in ("business", "enterprise"):
        raise ValueError("branding is available on Business and Enterprise")
    return plan.lower()


def update_settings(tenant_id, role, body):
    """Set the three colours, or clear them. Clearing returns the tenant to
    the platform palette rather than leaving a half-set page."""
    _require_branding(tenant_id, role)

    fields, params = [], [_p("t", tenant_id)]
    for key, column in (("deep", "brand_deep"),
                        ("mid", "brand_mid"),
                        ("highlight", "brand_highlight")):
        if key not in body:
            continue
        value = (body.get(key) or "").strip() or None
        if value and not _HEX.match(value):
            raise ValueError("%s must be a colour like #002561" % key)
        fields.append("%s = :%s" % (column, column))
        params.append(_p(column, value))

    if "logo_key" in body and not body.get("logo_key"):
        fields.append("brand_logo_key = :brand_logo_key")
        params.append(_p("brand_logo_key", None))

    if not fields:
        return get_settings(tenant_id)

    _sql("UPDATE tenant SET " + ", ".join(fields) + " WHERE tenant_id = :t",
         params)
    return get_settings(tenant_id)


def render_memo(tenant_id, memo_id):
    """Render the PDF now and return a link to it.

    The PDF is a presentation of the memo, not a second record of it. What was
    issued is the memo - its words, its number, its author - and a revision
    already produces a new memo when the content changes. So rendering on
    demand costs nothing that matters and means an improvement to the
    rendering reaches every memo rather than only the next one.

    Synchronous: a couple of seconds, and the person is waiting for a file."""
    response = _lambda.invoke(
        FunctionName=RENDER_FUNCTION,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tenant_id": tenant_id, "memo_id": int(memo_id)}))

    result = json.loads(response["Payload"].read())
    if result.get("status") != "ok":
        raise ValueError("the memorandum could not be rendered")

    url = _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": CURATED_BUCKET, "Key": result["pdf_key"]},
        ExpiresIn=3600)
    return {"url": url, "bytes": result.get("bytes")}


def preview_branding(tenant_id):
    """Render a sample memo against the tenant's current branding.

    A colour change never rewrites an existing PDF - that is a record of what
    was issued. So this is the only way to see a setting take effect before
    the next memo is generated, which is what the setting is for.

    Synchronous: it is one page, and the person is waiting."""
    response = _lambda.invoke(
        FunctionName=RENDER_FUNCTION,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tenant_id": tenant_id, "preview": True}))

    result = json.loads(response["Payload"].read())
    if result.get("status") != "ok":
        raise ValueError("the preview could not be rendered")
    return {"url": result["url"], "plan": result.get("plan")}


def logo_upload_url(tenant_id, role, content_type):
    """A signed link, as documents use. The browser sends the file straight to
    storage and the key is recorded only once the upload has succeeded, so a
    failed upload cannot leave the tenant pointing at a logo that is not
    there."""
    _require_branding(tenant_id, role)

    suffix = _LOGO_TYPES.get((content_type or "").lower())
    if not suffix:
        raise ValueError("a logo must be a PNG or a JPEG")

    key = "tenants/%d/logo%s" % (tenant_id, suffix)
    url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BRAND_BUCKET, "Key": key,
                "ContentType": content_type},
        ExpiresIn=900)
    return {"url": url, "key": key}


def confirm_logo(tenant_id, role, key):
    """Record the logo only after the browser reports the upload succeeded."""
    _require_branding(tenant_id, role)

    if not key or not key.startswith("tenants/%d/" % tenant_id):
        raise ValueError("that logo does not belong to this tenant")

    _sql("UPDATE tenant SET brand_logo_key = :k WHERE tenant_id = :t",
         [_p("k", key), _p("t", tenant_id)])
    return get_settings(tenant_id)


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


def document_types(tenant_id):
    """The tenant's own type list, with what filing each one will do - so the
    screen can say whether confirming a type triggers OCR.

    Read mode and always-OCR are properties of the TYPE now, not of a
    hard-coded table, because the type is what a person confirms."""
    return config.for_tenant(tenant_id).document_type_list()


# --- configuration ---------------------------------------------------------
#
# Authoring is an admin act. It changes what every future memo says, which is
# a heavier thing than uploading a document.

def _require_admin(role):
    if role != "admin":
        raise PermissionError("only an administrator may change the "
                              "configuration")


def config_state(tenant_id):
    """Where this tenant stands: what is published, whether a draft is open,
    and what publishing it would flag."""
    revisions = registry.revisions(tenant_id)
    draft = next((r for r in revisions if r["is_draft"]), None)

    state = {
        "active_revision": config.active_revision(tenant_id),
        "revisions": [r for r in revisions if not r["is_draft"]],
        "draft": draft,
    }
    if draft:
        state["validation"] = registry.validate(tenant_id, registry.DRAFT)
    return state


def config_read(tenant_id, revision):
    """A whole revision, for an editor to work on or a reader to inspect.

    Loaded through the same path the pipeline uses, so what an editor sees is
    what extraction will do."""
    reg = config.load(tenant_id, int(revision))
    return {
        "revision": int(revision),
        "categories": [{"key": k, "label": v}
                       for k, v in reg.CATEGORIES.items()],
        "document_types": [
            {"key": k, "label": v["label"], "category": v["category"],
             "description": v["description"], "read_mode": v["read_mode"],
             "always_ocr": v["always_ocr"], "schemas": v["schemas"]}
            for k, v in reg.DOCUMENT_TYPES.items()],
        "schemas": [
            {"key": k, "label": v["label"], "instruction": v["handler"],
             "fields": [
                 {"key": f[0], "label": f[1], "type": f[2],
                  "cardinality": f[3], "description": f[4],
                  "columns": [{"key": c[0], "label": c[1], "type": c[2],
                               "description": c[3]}
                              for c in (f[5] if len(f) > 5 else [])]}
                 for f in v["fields"]]}
            for k, v in reg.SCHEMAS.items()],
        "template_key": reg.TEMPLATE_KEY,
        "sections": reg.MEMO_SECTIONS,
    }


# --- dispatch --------------------------------------------------------------

def lambda_handler(event, context):
    try:
        tenant_id, email, role = caller(event)
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

        if route == "DELETE /documents/{document_id}":
            removing = int((event.get("pathParameters") or {})
                           .get("document_id"))
            outcome = remove_document(tenant_id, removing)
            if outcome is None:
                return _reply(404, {"error": "no such document"})
            if "refused" in outcome:
                return _reply(409, {"error": outcome["refused"]})
            return _reply(200, outcome)

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

        if route == "POST /memos/{memo_id}/revise":
            body = json.loads(event.get("body") or "{}")
            revised = revise_memo(tenant_id, email, params.get("memo_id"),
                                  body.get("markdown", ""))
            if revised is None:
                return _reply(404, {"error": "not found"})
            return _reply(201, revised)

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

        if route == "GET /settings":
            settings = get_settings(tenant_id)
            if settings is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, settings)

        if route == "POST /settings":
            body = json.loads(event.get("body") or "{}")
            return _reply(200, update_settings(tenant_id, role, body))

        if route == "GET /memos/{memo_id}/pdf":
            return _reply(200, render_memo(tenant_id, params.get("memo_id")))

        if route == "GET /settings/preview":
            return _reply(200, preview_branding(tenant_id))

        if route == "POST /settings/logo":
            body = json.loads(event.get("body") or "{}")
            return _reply(200, logo_upload_url(tenant_id, role,
                                               body.get("content_type", "")))

        if route == "POST /settings/logo/confirm":
            body = json.loads(event.get("body") or "{}")
            return _reply(200, confirm_logo(tenant_id, role,
                                            body.get("key", "")))

        if route == "GET /config":
            return _reply(200, config_state(tenant_id))

        if route == "GET /config/{revision}":
            return _reply(200, config_read(tenant_id,
                                           params.get("revision")))

        if route == "POST /config/draft":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(201, registry.open_draft(
                tenant_id, email, body.get("from_revision")))

        if route == "DELETE /config/draft":
            _require_admin(role)
            return _reply(200, registry.discard_draft(tenant_id))

        if route == "GET /config/draft/validate":
            return _reply(200, registry.validate(tenant_id, registry.DRAFT))

        if route == "POST /config/publish":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            result = registry.publish(tenant_id, email, body.get("note"))
            # A refused publish is not an error: the person is told what to
            # fix and the draft is untouched.
            return _reply(200 if result["published"] else 409, result)

        if route == "GET /config/packs":
            return _reply(200, {"packs": registry.packs()})

        if route == "POST /config/fork":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(201, registry.fork(
                tenant_id, email, int(body.get("revision", 1))))

        # --- editing the draft -----------------------------------------
        if route == "GET /config/draft":
            return _reply(200, editor.draft(tenant_id))

        if route == "POST /config/draft/sections":
            _require_admin(role)
            return _reply(200, editor.save_section(
                tenant_id, json.loads(event.get("body") or "{}")))

        if route == "DELETE /config/draft/sections/{key}":
            _require_admin(role)
            return _reply(200, editor.delete_section(tenant_id,
                                                     params.get("key")))

        if route == "PUT /config/draft/sections/{key}/fields":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(200, editor.set_section_fields(
                tenant_id, params.get("key"), body.get("fields") or []))

        if route == "POST /config/draft/fields":
            _require_admin(role)
            return _reply(200, editor.save_field(
                tenant_id, json.loads(event.get("body") or "{}")))

        if route == "DELETE /config/draft/fields/{key}":
            _require_admin(role)
            return _reply(200, editor.delete_field(tenant_id,
                                                   params.get("key")))

        if route == "PUT /config/draft/fields/{key}/documents":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(200, editor.set_field_documents(
                tenant_id, params.get("key"), body.get("documents") or []))

        if route == "PUT /config/draft/types/{key}/fields":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(200, editor.set_document_fields(
                tenant_id, params.get("key"), body.get("fields") or []))

        if route == "POST /config/draft/types":
            _require_admin(role)
            return _reply(200, editor.save_document_type(
                tenant_id, json.loads(event.get("body") or "{}")))

        if route == "DELETE /config/draft/types/{key}":
            _require_admin(role)
            return _reply(200, editor.delete_document_type(
                tenant_id, params.get("key")))

        if route == "POST /config/draft/categories":
            _require_admin(role)
            return _reply(200, editor.save_category(
                tenant_id, json.loads(event.get("body") or "{}")))

        if route == "DELETE /config/draft/categories/{key}":
            _require_admin(role)
            return _reply(200, editor.delete_category(
                tenant_id, params.get("key")))

        if route == "GET /document-types":
            return _reply(200, {"types": document_types(tenant_id)})

        return _reply(404, {"error": "unknown route"})

    except PermissionError as exc:
        return _reply(403, {"error": str(exc)})
    except ValueError as exc:
        return _reply(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - never leak internals to a client
        print("[api-error] route=%s tenant=%s %r" % (route, tenant_id, exc))
        return _reply(500, {"error": "internal error"})
