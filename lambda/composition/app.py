"""
app.py - memo composition.

Invoked manually with a tenant and engagement. Reads the extracted values for
that engagement, assembles the deterministic sections, drafts the composed
sections with the model, and writes a markdown memo to the curated bucket.

Evidence binding is DETERMINISTIC. We record the values we fed into a section
as that section's evidence, rather than asking the model which ones it used.
Broader, but it cannot be wrong - and the product rests on citations being
trustworthy.

Invoke with:
    {"tenant_id": 1, "engagement": "eng-001"}
"""

import datetime
import hashlib
import json
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

import template

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")
_bedrock = boto3.client("bedrock-runtime")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
MODEL_ID = os.environ["MODEL_ID"]


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


def _load_values(tenant_id, engagement):
    """Every extracted value for the engagement, with its source document."""
    result = _sql(
        """
        SELECT v.value_id, v.field_id, v.value, v.locator_kind,
               v.locator_index, v.document_id, d.filename
        FROM extracted_value v
        JOIN document d ON d.document_id = v.document_id
        WHERE v.tenant_id = :tenant_id
          AND d.s3_key LIKE :engagement_prefix
        ORDER BY v.document_id, v.value_id
        """,
        [
            _p("tenant_id", tenant_id),
            _p("engagement_prefix", "%/docs/{}/%".format(engagement)),
        ],
    )

    return [
        {
            "value_id": _col(r, 0),
            "field_id": _col(r, 1),
            "value": _col(r, 2),
            "locator_kind": _col(r, 3),
            "locator_index": _col(r, 4),
            "document_id": _col(r, 5),
            "filename": _col(r, 6),
        }
        for r in result.get("records", [])
    ]


def _label_for(field_id):
    """Human label from the pack. Falls back to the identifier."""
    for schema in _PACK_FIELDS:
        if schema[0] == field_id:
            return schema[1]
    return field_id


# Field labels, mirrored from the extraction pack. Stage 2 reads these from
# the configuration registry instead.
_PACK_FIELDS = [
    ("f_registered_name", "Registered Name"),
    ("f_company_number", "Company Number"),
    ("f_jurisdiction", "Jurisdiction"),
    ("f_legal_form", "Legal Form"),
    ("f_incorporation_date", "Incorporation Date"),
    ("f_registered_office", "Registered Office"),
]


def _citation(v):
    """A readable source reference. Filename plus location where known."""
    if v["locator_kind"] and v["locator_kind"] != "none" and v["locator_index"]:
        return "{}, {} {}".format(
            v["filename"], v["locator_kind"], v["locator_index"])
    return v["filename"]


def _assemble_extract(section, values):
    """Deterministic section, rendered one block per source document.

    Values are NOT merged across documents. Three documents stating a company
    name produce three blocks. Where they disagree, the reader sees the
    disagreement and its source. Merging would hide it silently, and a
    contradiction the reader cannot see is worse than one they can.
    """
    used = [v for v in values if v["field_id"] in section["fields"]]
    if not used:
        return "_No information available._\n", []

    by_document = {}
    for v in used:
        by_document.setdefault(v["document_id"], []).append(v)

    blocks = []
    for document_id in sorted(by_document):
        rows = by_document[document_id]
        blocks.append("**Source: " + rows[0]["filename"] + "**\n")
        for field_id in section["fields"]:
            for v in rows:
                if v["field_id"] == field_id:
                    blocks.append("- **" + _label_for(field_id) + ":** "
                                  + str(v["value"]) + "  \n  _" + _citation(v) + "_")
        blocks.append("")

    return "\n".join(blocks) + "\n", used

def _invoke(prompt):
    response = _bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    payload = json.loads(response["body"].read())
    text = "".join(
        b.get("text", "") for b in payload.get("content", [])
        if b.get("type") == "text"
    )
    return text.strip(), payload.get("usage", {})


def _compose(section, assembled):
    """Model-drafted section. Evidence is every value fed into its context."""
    context_parts, used = [], []

    for key in section.get("context_sections", []):
        block = assembled.get(key)
        if not block:
            continue
        context_parts.append("## {}\n\n{}".format(block["title"], block["markdown"]))
        used.extend(block["values"])

    if not context_parts:
        return "_No context available._\n", [], {}

    prompt = (
        section["prompt"]
        + "\n\n--- CONTEXT START ---\n"
        + "\n\n".join(context_parts)
        + "\n--- CONTEXT END ---"
    )

    text, usage = _invoke(prompt)
    return text + "\n", used, usage


def _record_claim(tenant_id, memo_id, section_key, ordinal, text, values):
    result = _sql(
        """
        INSERT INTO claim
          (tenant_id, memo_id, section_key, statement_ordinal, statement_text)
        VALUES
          (:tenant_id, :memo_id, :section_key, :ordinal, :statement_text)
        """,
        [
            _p("tenant_id", tenant_id),
            _p("memo_id", memo_id),
            _p("section_key", section_key),
            _p("ordinal", ordinal),
            _p("statement_text", text[:4000]),
        ],
    )
    claim_id = result.get("generatedFields", [{}])[0].get("longValue")

    for v in values:
        _sql(
            """
            INSERT IGNORE INTO claim_evidence (claim_id, value_id, tenant_id)
            VALUES (:claim_id, :value_id, :tenant_id)
            """,
            [
                _p("claim_id", claim_id),
                _p("value_id", v["value_id"]),
                _p("tenant_id", tenant_id),
            ],
        )

    return claim_id


def lambda_handler(event, context):
    tenant_id = int(event["tenant_id"])
    engagement = event["engagement"]

    values = _load_values(tenant_id, engagement)
    if not values:
        return {"status": "no-values", "engagement": engagement}

    document_ids = sorted({v["document_id"] for v in values})
    generated_at = datetime.datetime.now(datetime.timezone.utc)

    # 1. Deterministic sections first - they are the context for the rest.
    assembled = {}
    for section in template.sections_of_kind("extract"):
        markdown, used = _assemble_extract(section, values)
        assembled[section["key"]] = {
            "title": section["title"],
            "num": section["num"],
            "markdown": markdown,
            "values": used,
        }

    # 2. Composed sections.
    tokens_in = tokens_out = 0
    for section in template.sections_of_kind("composed"):
        markdown, used, usage = _compose(section, assembled)
        tokens_in += usage.get("input_tokens", 0)
        tokens_out += usage.get("output_tokens", 0)
        assembled[section["key"]] = {
            "title": section["title"],
            "num": section["num"],
            "markdown": markdown,
            "values": used,
        }

    # 3. Render in template order.
    parts = [
        "# Due Diligence Memorandum",
        "",
        "Generated {} UTC".format(generated_at.strftime("%d %B %Y, %H:%M")),
        "",
        "---",
        "",
    ]
    for section in template.MEMO_SECTIONS:
        block = assembled[section["key"]]
        parts.append("## {}. {}".format(block["num"], block["title"]))
        parts.append("")
        parts.append(block["markdown"])
        parts.append("")

        sources = sorted({_citation(v) for v in block["values"]})
        if sources:
            parts.append("_Sources: {}._".format("; ".join(sources)))
            parts.append("")

    body = "\n".join(parts)
    encoded = body.encode("utf-8")
    sha = hashlib.sha256(encoded).hexdigest()

    memo_key = "tenants/{}/memos/{}/{}-{}.md".format(
        tenant_id, engagement, template.TEMPLATE_KEY,
        generated_at.strftime("%Y%m%dT%H%M%SZ"))

    put = _s3.put_object(
        Bucket=CURATED_BUCKET,
        Key=memo_key,
        Body=encoded,
        ContentType="text/markdown",
    )

    # 4. Record the memo, its sources, and its claims.
    memo_result = _sql(
        """
        INSERT INTO memo
          (tenant_id, template_key, config_revision, s3_bucket, s3_key,
           s3_version_id, sha256)
        VALUES
          (:tenant_id, :template_key, :config_revision, :s3_bucket, :s3_key,
           :s3_version_id, :sha256)
        """,
        [
            _p("tenant_id", tenant_id),
            _p("template_key", template.TEMPLATE_KEY),
            _p("config_revision", template.CONFIG_REVISION),
            _p("s3_bucket", CURATED_BUCKET),
            _p("s3_key", memo_key),
            _p("s3_version_id", put.get("VersionId")),
            _p("sha256", sha),
        ],
    )
    memo_id = memo_result.get("generatedFields", [{}])[0].get("longValue")

    for document_id in document_ids:
        _sql(
            """
            INSERT IGNORE INTO memo_source (memo_id, document_id, tenant_id)
            VALUES (:memo_id, :document_id, :tenant_id)
            """,
            [
                _p("memo_id", memo_id),
                _p("document_id", document_id),
                _p("tenant_id", tenant_id),
            ],
        )

    claims = 0
    for ordinal, section in enumerate(template.MEMO_SECTIONS, start=1):
        block = assembled[section["key"]]
        _record_claim(tenant_id, memo_id, section["key"], ordinal,
                      block["markdown"], block["values"])
        claims += 1

    print("[composed] memo={} docs={} values={} claims={} "
          "tokens_in={} tokens_out={}".format(
              memo_id, len(document_ids), len(values), claims,
              tokens_in, tokens_out))

    return {
        "status": "ok",
        "memo_id": memo_id,
        "memo_key": memo_key,
        "documents": len(document_ids),
        "values": len(values),
        "claims": claims,
        "tokens": {"input": tokens_in, "output": tokens_out},
    }

