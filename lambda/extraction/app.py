"""
app.py - document extraction.

Fires on a normalized envelope landing in the review bucket. Runs each schema
mapped to the document's type, and writes one row per extracted value.

The span join (EV-01) is the point of this function. The model is asked to
return, alongside each value, the UNIT it read the value from. That unit is
validated against the envelope's unit list and resolved to a character range.
A unit outside the document's range is discarded rather than trusted: a
citation pointing at the wrong page still reads as authoritative, and that is
the failure that costs trust.
"""

import json
import os
import re
import time
import urllib.parse

import boto3
from botocore.exceptions import ClientError

import config

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")
_bedrock = boto3.client("bedrock-runtime")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
MODEL_ID = os.environ["MODEL_ID"]

# Bounded input for Stage 1. Long documents get chunking later; the truncation
# is recorded on the envelope so a short extraction is explainable.
MAX_CHARS = 50000

_ENVELOPE_SUFFIX = ".normalized.json"


def _sql(statement, params=None):
    """Data API call, retrying while the cluster wakes from zero capacity."""
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
    if isinstance(value, bool):
        return {"name": name, "value": {"booleanValue": value}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    if isinstance(value, float):
        return {"name": name, "value": {"doubleValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _unit_word(units):
    """What to call a unit in the prompt: page, sheet or section."""
    return units[0]["kind"] if units else "section"


def _build_prompt(schema, envelope):
    units = envelope["units"]
    word = _unit_word(units)
    count = len(units)

    lines = []
    for field in schema["fields"]:
        field_id, label, ftype, card, desc = field[0], field[1], field[2], field[3], field[4]
        if card == "group":
            cols = ", ".join('"' + c[0].split(".", 1)[1] + '": string | null' for c in field[5])
            lines.append('  "' + field_id + '": { "rows": [ { ' + cols +
                         ' } ], "unit": integer | null },  // ' + label + " - " + desc)
            continue
        hint = "[string] | null" if card == "many" else "string | null"
        lines.append(
            '  "' + field_id + '": { "value": ' + hint + ', "unit": integer | null },'
            + "  // " + label + " (" + ftype + ") - " + desc
        )

    # Built by concatenation, not .format(): the text contains literal JSON
    # braces and every one of them would be read as a placeholder.
    instruction = (
        "Extract the following from the document below. Return JSON with "
        "exactly these keys:\n\n"
        "{\n" + "\n".join(lines) + "\n}\n\n"
        'For each field, "value" is what the document states, or null if it '
        "is not present. Do not infer, do not use outside knowledge.\n\n"
        '"unit" is the ' + word + " number the value was read from. "
        "The document has " + str(count) + " " + word + "s, numbered 1 to "
        + str(count) + ", marked in the text below.\n"
        "If you cannot tell which " + word + " a value came from, return null "
        'for "unit". A wrong ' + word + " number is worse than none.\n\n"
        "Return only the JSON object."
    )

    raw = envelope.get("raw_text") or ""
    marked, cursor = [], 0
    for u in units:
        start = min(u["char_start"], len(raw))
        end = min(u["char_end"], len(raw))
        if start > cursor:
            marked.append(raw[cursor:start])
        label = " (" + u["label"] + ")" if u.get("label") else ""
        marked.append("\n--- " + word.upper() + " " + str(u["index"]) + label + " ---\n")
        marked.append(raw[start:end])
        cursor = end
    if cursor < len(raw):
        marked.append(raw[cursor:])

    body = "".join(marked)[:MAX_CHARS]

    prompt = (
        instruction
        + "\n\n--- DOCUMENT START ---\n"
        + body
        + "\n--- DOCUMENT END ---"
    )
    return prompt, len(raw) > MAX_CHARS

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
        block.get("text", "") for block in payload.get("content", [])
        if block.get("type") == "text"
    )
    usage = payload.get("usage", {})

    # Strip code fences if the model wrapped the JSON.
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()

    try:
        return json.loads(cleaned), usage
    except json.JSONDecodeError:
        return None, usage


def _resolve_locator(unit_value, units):
    """Turn a model-returned unit number into a real location.

    Returns (kind, index, char_start, char_end, cell_range). An unusable unit
    resolves to kind 'none' rather than a guess."""
    if unit_value is None:
        return "none", None, None, None, None

    try:
        index = int(unit_value)
    except (TypeError, ValueError):
        return "none", None, None, None, None

    for u in units:
        if u["index"] == index:
            return u["kind"], index, u["char_start"], u["char_end"], None

    # Out of range: the model invented it. Discard.
    return "none", None, None, None, None


def _write_value(envelope, field_id, value, row_ordinal,
                 kind, index, char_start, char_end, cell_range):
    """One row in extracted_value. Every row carries a locator or 'none'."""
    _sql(
        """
        INSERT INTO extracted_value
          (tenant_id, document_id, field_id, value, row_ordinal,
           config_revision, locator_kind, locator_index,
           char_start, char_end, cell_range)
        VALUES
          (:tenant_id, :document_id, :field_id, :value, :row_ordinal,
           :config_revision, :locator_kind, :locator_index,
           :char_start, :char_end, :cell_range)
        """,
        [
            _p("tenant_id", envelope["tenant_id"]),
            _p("document_id", envelope["document_id"]),
            _p("field_id", field_id),
            _p("value", str(value)),
            _p("row_ordinal", row_ordinal),
            _p("config_revision", envelope.get("config_revision") or 1),
            _p("locator_kind", kind),
            _p("locator_index", index),
            _p("char_start", char_start),
            _p("char_end", char_end),
            _p("cell_range", cell_range),
        ],
    )


def _persist(envelope, registry, schema_key, extracted):
    """Write one row per field. Every row carries a locator or 'none'."""
    schema = registry.get_schema(schema_key)
    units = envelope["units"]
    written = 0

    for field in schema["fields"]:
        field_id, card = field[0], field[3]
        item = extracted.get(field_id) or {}
        unit = item.get("unit") if isinstance(item, dict) else None
        kind, index, start, end, cell = _resolve_locator(unit, units)

        # Repeating rows. Each record is written under its own row number so
        # a person's nationality stays attached to that person's name.
        if card == "group":
            rows = item.get("rows") if isinstance(item, dict) else None
            if not isinstance(rows, list):
                continue
            for ordinal, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                for col in field[5]:
                    col_id = col[0]
                    cell_value = row.get(col_id.split(".", 1)[1])
                    if cell_value is None or cell_value == "":
                        continue
                    _write_value(envelope, col_id, cell_value, ordinal,
                                 kind, index, start, end, cell)
                    written += 1
            continue

        value = item.get("value") if isinstance(item, dict) else item

        if value is None or value == "" or value == []:
            continue

        # A multi-value field arrives as a list. Store it readably rather
        # than as Python list syntax, which would render into a memo verbatim.
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value if v not in (None, ""))
            if not value:
                continue

        _write_value(envelope, field_id, value, 0,
                     kind, index, start, end, cell)
        written += 1

    return written


def _source_from_event(event):
    records = event.get("Records")
    if records and records[0].get("s3"):
        s3 = records[0]["s3"]
        return s3["bucket"]["name"], urllib.parse.unquote_plus(s3["object"]["key"])

    detail = event.get("detail")
    if detail and "bucket" in detail:
        return detail["bucket"]["name"], urllib.parse.unquote_plus(detail["object"]["key"])

    raise ValueError("unrecognised event shape")


def lambda_handler(event, context):
    bucket, key = _source_from_event(event)

    if not key.endswith(_ENVELOPE_SUFFIX):
        return {"status": "skipped", "reason": "not-an-envelope"}

    envelope = json.loads(
        _s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    )

    # Our own write re-fires the trigger. Exit rather than loop.
    if envelope.get("extraction_complete"):
        return {"status": "skipped", "reason": "already-extracted"}

    # The revision the document was FILED under, not the tenant's current
    # one. A document filed under revision 11 resolves against revision 11 for
    # ever - that is what a snapshot is for, and it is why a memo written in
    # March still reproduces in September.
    registry = config.load(envelope["tenant_id"],
                           envelope.get("config_revision") or 1)

    schema_keys = registry.schemas_for(envelope.get("document_type"))
    results, total_written = {}, 0
    tokens_in = tokens_out = 0

    for schema_key in schema_keys:
        schema = registry.get_schema(schema_key)
        if not schema:
            results[schema_key] = {"status": "no-schema"}
            continue

        prompt, truncated = _build_prompt(schema, envelope)
        extracted, usage = _invoke(prompt)

        tokens_in += usage.get("input_tokens", 0)
        tokens_out += usage.get("output_tokens", 0)

        if extracted is None:
            results[schema_key] = {"status": "invalid-json"}
            continue

        written = _persist(envelope, registry, schema_key, extracted)
        total_written += written

        results[schema_key] = {
            "status": "extracted",
            "fields_written": written,
            "truncated": truncated,
        }

    envelope["extraction_complete"] = True
    envelope["extraction_results"] = results
    envelope["extraction_tokens"] = {"input": tokens_in, "output": tokens_out}
    envelope["model_id"] = MODEL_ID

    _s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )

    # Mark the document extracted. Without this the list cannot tell a
    # document still being read from one that yielded nothing - both show as
    # zero values, and they mean very different things to a reader.
    document_id = envelope.get("document_id")
    if document_id:
        _sql(
            "UPDATE document SET extracted_at = UTC_TIMESTAMP() "
            "WHERE tenant_id = :t AND document_id = :d",
            [_p("t", envelope["tenant_id"]), _p("d", int(document_id))],
        )

    print("[extracted] doc={} schemas={} values={} tokens_in={} tokens_out={}".format(
        envelope.get("document_id"), list(results.keys()),
        total_written, tokens_in, tokens_out))

    return {
        "status": "ok",
        "document_id": envelope.get("document_id"),
        "values_written": total_written,
        "results": results,
    }





