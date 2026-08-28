"""
app.py - memo composition.

Invoked with a tenant and engagement. Three stages:

  1. Assemble    one block per source document, nothing merged. A fact stated
                 by eight documents appears eight times.
  2. Draft       model-written sections from that assembled context.
  3. Consolidate a second pass, once per section, turning the assembled
                 repetition into the version a reader receives.

Stage 1 must not merge: merging silently loses a contradiction between sources,
and a contradiction the reader cannot see is worse than one they can. Stage 3 is
where agreement collapses to one statement and disagreement is stated as
disagreement.

Evidence binding is DETERMINISTIC. We record the values we fed into a section as
that section's evidence rather than asking the model which ones it used.
Broader, but it cannot be wrong - and the product rests on citations being
trustworthy.

Invoke with:
    {"tenant_id": 1, "engagement": "eng-001"}
"""

import datetime
import hashlib
import json
import os
import time

import boto3
from botocore.exceptions import ClientError

import cleanup
import pack
import template

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")
_bedrock = boto3.client("bedrock-runtime")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
MODEL_ID = os.environ["MODEL_ID"]

# A single section's assembled draft. Long enough for fifty documents' worth of
# one section, short enough that the consolidation stays sharp.
_SECTION_INPUT_CHARS = 40000


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
               v.locator_index, v.row_ordinal, v.document_id, d.filename
        FROM extracted_value v
        JOIN document d ON d.document_id = v.document_id
        WHERE v.tenant_id = :tenant_id
          AND d.state = 'filed'
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
            "row_ordinal": _col(r, 5),
            "document_id": _col(r, 6),
            "filename": _col(r, 7),
        }
        for r in result.get("records", [])
    ]


def _label_for(field_id):
    """Label from the pack. Group columns resolve to their own column label."""
    if "." in field_id:
        group = field_id.split(".", 1)[0]
        for col in (pack.group_columns(group) or []):
            if col[0] == field_id:
                return col[1]
    return pack.label_for(field_id)


def _citation(v):
    """A readable source reference. Filename plus location where known."""
    if v["locator_kind"] and v["locator_kind"] != "none" and v["locator_index"]:
        return "{}, {} {}".format(
            v["filename"], v["locator_kind"], v["locator_index"])
    return v["filename"]


# --- stage 1: assemble -----------------------------------------------------

def _render_group(field_id, columns, rows):
    """A repeating-row field as a markdown table. Only columns that carry a
    value are shown - an empty column tells the reader nothing."""
    records = {}
    for v in rows:
        if v["field_id"].split(".", 1)[0] != field_id:
            continue
        records.setdefault(v["row_ordinal"], {})[v["field_id"]] = v

    if not records:
        return []

    live = [c for c in columns if any(c[0] in r for r in records.values())]
    if not live:
        return []

    out = ["**" + pack.label_for(field_id) + "**", ""]
    out.append("| " + " | ".join(c[1] for c in live) + " |")
    out.append("|" + "|".join(["---"] * len(live)) + "|")
    for ordinal in sorted(records):
        record = records[ordinal]
        cells = []
        for c in live:
            got = record.get(c[0])
            cells.append(str(got["value"]).replace("|", "\\|") if got else "")
        out.append("| " + " | ".join(cells) + " |")

    any_value = next(iter(next(iter(records.values())).values()))
    out.append("")
    out.append("_" + _citation(any_value) + "_")
    out.append("")
    return out


def _assemble_extract(section, values):
    """One block per source document. Nothing is merged here - consolidation
    does that, and only after it has seen everything."""
    wanted = set(section["fields"])
    used = []
    for v in values:
        fid = v["field_id"]
        if fid in wanted or fid.split(".", 1)[0] in wanted:
            used.append(v)
    if not used:
        return "", []

    by_document = {}
    for v in used:
        by_document.setdefault(v["document_id"], []).append(v)

    blocks = []
    for document_id in sorted(by_document):
        rows = by_document[document_id]
        blocks.append("**Source: " + rows[0]["filename"] + "**\n")

        for field_id in section["fields"]:
            columns = pack.group_columns(field_id)
            if columns:
                blocks.extend(_render_group(field_id, columns, rows))
                continue
            for v in rows:
                if v["field_id"] == field_id:
                    blocks.append("- **" + _label_for(field_id) + ":** "
                                  + str(v["value"]) + "  \n  _" + _citation(v) + "_")
        blocks.append("")

    return "\n".join(blocks) + "\n", used


# --- model -----------------------------------------------------------------

def _invoke(prompt, system=None):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    response = _bedrock.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    payload = json.loads(response["body"].read())
    text = "".join(
        b.get("text", "") for b in payload.get("content", [])
        if b.get("type") == "text"
    )
    return text.strip(), payload.get("usage", {})


# --- stage 2: draft --------------------------------------------------------

def _compose(section, assembled):
    """Model-drafted section. Evidence is every value fed into its context."""
    context_parts, used = [], []

    for key in section.get("context_sections", []):
        block = assembled.get(key)
        if not block or not block["markdown"].strip():
            continue
        context_parts.append("## {}\n\n{}".format(block["title"], block["markdown"]))
        used.extend(block["values"])

    if not context_parts:
        return "", [], {}

    prompt = (
        section["prompt"]
        + "\n\n--- CONTEXT START ---\n"
        + "\n\n".join(context_parts)[:_SECTION_INPUT_CHARS]
        + "\n--- CONTEXT END ---"
    )

    text, usage = _invoke(prompt)
    return text + "\n", used, usage


# --- stage 3: consolidate --------------------------------------------------

def _consolidate(section, markdown):
    """Turn one assembled section into the version a reader receives.

    Runs per section, not per memo: a single prompt over fifty documents
    produces mush, and per-section lets one section carry its own shape."""
    if not markdown.strip():
        return markdown, {}

    prompt = (
        cleanup.CLEANUP_PROMPT
        + cleanup.presentation_for(section["key"])
        + "\n\n--- SECTION START ---\n"
        + "## {}. {}\n\n".format(section["num"], section["title"])
        + markdown[:_SECTION_INPUT_CHARS]
        + "\n--- SECTION END ---"
    )

    text, usage = _invoke(prompt, system=cleanup.CLEANUP_PREAMBLE)
    return text + "\n", usage


# --- claims ----------------------------------------------------------------

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


# --- handler ---------------------------------------------------------------

def lambda_handler(event, context):
    tenant_id = int(event["tenant_id"])
    engagement = event["engagement"]

    values = _load_values(tenant_id, engagement)
    if not values:
        return {"status": "no-values", "engagement": engagement}

    document_ids = sorted({v["document_id"] for v in values})
    generated_at = datetime.datetime.now(datetime.timezone.utc)
    tokens_in = tokens_out = 0

    # 1. Assemble the deterministic sections. They are the context for the rest.
    assembled = {}
    for section in template.sections_of_kind("extract"):
        markdown, used = _assemble_extract(section, values)
        assembled[section["key"]] = {
            "title": section["title"],
            "num": section["num"],
            "markdown": markdown,
            "values": used,
        }

    # 2. Draft the composed sections from that context.
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

    # 3. Consolidate each section into what a reader receives.
    empty_sections = []
    for section in template.MEMO_SECTIONS:
        block = assembled[section["key"]]
        if not block["markdown"].strip():
            empty_sections.append(section["title"])
            continue
        clean, usage = _consolidate(section, block["markdown"])
        tokens_in += usage.get("input_tokens", 0)
        tokens_out += usage.get("output_tokens", 0)
        block["markdown"] = clean

    # 4. Render. Front matter and the coverage banner are built, not written.
    subject = cleanup.subject_from(values)
    parts = [
        cleanup.front_matter(
            subject, engagement,
            generated_at.strftime("%d %B %Y, %H:%M UTC"),
            len(document_ids), len({v["filename"] for v in values}),
        ),
        cleanup.coverage_callout(empty_sections),
    ]

    for section in template.MEMO_SECTIONS:
        block = assembled[section["key"]]
        body = block["markdown"].strip()

        if not body:
            parts.append("## {}. {}".format(block["num"], block["title"]))
            parts.append("")
            parts.append("> **Gap.** No material addressing this section was "
                         "provided.")
            parts.append("")
            continue

        # The consolidation keeps the heading, so do not add a second one.
        if not body.lstrip().startswith("#"):
            parts.append("## {}. {}".format(block["num"], block["title"]))
            parts.append("")
        parts.append(body)
        parts.append("")

        sources = sorted({_citation(v) for v in block["values"]})
        if sources:
            parts.append("_Sources: " + "; ".join(sources) + "._")
            parts.append("")

    memo_body = "\n".join(parts)
    encoded = memo_body.encode("utf-8")
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

    # 5. Record the memo, its sources, and its claims.
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
        if not block["values"]:
            continue
        _record_claim(tenant_id, memo_id, section["key"], ordinal,
                      block["markdown"], block["values"])
        claims += 1

    print("[composed] memo={} docs={} values={} claims={} empty={} "
          "tokens_in={} tokens_out={}".format(
              memo_id, len(document_ids), len(values), claims,
              len(empty_sections), tokens_in, tokens_out))

    return {
        "status": "ok",
        "memo_id": memo_id,
        "memo_key": memo_key,
        "subject": subject,
        "documents": len(document_ids),
        "values": len(values),
        "claims": claims,
        "empty_sections": empty_sections,
        "tokens": {"input": tokens_in, "output": tokens_out},
    }
