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

# What goes in document.extraction_error (migration 029). Short, machine-read
# codes: an operator counts them and the screen branches on nothing but
# "is it set". The sentence a person reads is written by the screen, not here.
ERROR_MALFORMED_GROUP = "group_key_missing"
ERROR_SCHEMA_FAILED = "schema_failed"
# The engagement never got a subject, so there is no telling whose facts
# this document holds. The API refuses to file into an engagement with none,
# which is the gate a person meets; this is the second line, for a document
# that reached here by some other route - a file placed in the docs bucket
# without passing through /uploads, or an engagement row minted by the
# normalizer (SUBJ-01).
ERROR_SUBJECT_MISSING = "subject_missing"


class MalformedGroup(Exception):
    """A field calling itself a table that does not carry its columns."""


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


def _column_name(column_key):
    """What a column is called inside its row.

    A column's identity is the group's key and a suffix - f_vessel_carriers.
    role - and the name is the part after the dot. A key without one was
    written by a caller that supplied its own, and splitting blindly raised
    IndexError inside the prompt builder, which stopped extraction on every
    document carrying a table rather than on the one field at fault."""
    return column_key.split(".", 1)[1] if "." in column_key else column_key


def _group_columns(field):
    """The columns of a group field, or a refusal that names the field.

    A field's tuple is five parts, and a group's is six - the sixth being its
    columns. config.py reads a config_field row with no group_key as a single
    value, so a row whose cardinality says 'group' while its group_key is
    NULL arrives here as a FIVE-part tuple calling itself a group. Asking it
    for field[5] raises IndexError, and that is how three malformed fields in
    revisions 2 and 3 stopped extraction on 102 documents on 5 September.

    registry.validate refuses that shape at publish now (cc0f141), so no
    revision published since carries it. This is the second line: a revision
    published BEFORE that guard existed is still readable, is still what
    documents filed under it resolve against for ever, and still reaches this
    code. Raised rather than skipped - a table asked for and not read is a
    finding, not a silence."""
    if len(field) < 6 or not isinstance(field[5], (list, tuple)):
        raise MalformedGroup(
            "'%s' says it is a table but carries no columns" % field[0])
    return field[5]


def _unit_word(units):
    """What to call a unit in the prompt: page, sheet or section."""
    return units[0]["kind"] if units else "section"


def _subject_for(tenant_id, document_id):
    """The subject of the engagement this document belongs to, or None.

    Through document.engagement_id (migration 030) to engagement.subject_name
    (migration 031). The envelope does not carry the engagement, so this is a
    read rather than a lookup in what we already hold.

    AN INNER JOIN, deliberately. A document whose engagement_id is NULL -
    one filed before 030's backfill, or written by a path that could not
    resolve the engagement - returns no row and is treated as having no
    subject. That is the truthful answer: there is no engagement to ask.
    """
    if not document_id:
        return None
    found = _sql(
        """
        SELECT e.subject_name
        FROM document d
        JOIN engagement e ON e.engagement_id = d.engagement_id
                         AND e.tenant_id = d.tenant_id
        WHERE d.tenant_id = :t AND d.document_id = :d
        """,
        [_p("t", tenant_id), _p("d", int(document_id))]).get("records", [])
    if not found:
        return None
    cell = found[0][0]
    return (cell.get("stringValue") or "").strip() or None


# Opens every extraction prompt. The name entered is INDICATIVE, not
# dispositive: "Cocoa Empire" has to reach "Cocoa Empire Uganda Limited",
# "Cocoa Empire Uganda Ltd" and "CE", and no normalisation we could write
# would do that honestly. The model is told the name and told what counts as
# the same company; the second sentence is the one that matters, because the
# failure this exists to stop is a BUYER's business description filed as the
# subject's under a citation that is perfectly correct (SUBJ-01).
def _subject_preamble(subject):
    return (
        "The subject of this file is **" + subject + "**. Documents may "
        "write the name differently - with or without a legal suffix such "
        "as Limited or Ltd, in another capitalisation, abbreviated, or in "
        "full. Treat any name that refers to the same company as the "
        "subject. Every other company - a buyer, supplier, lender, "
        "inspector or other counterparty - is not the subject.\n\n"
    )


def _build_prompt(schema, envelope):
    units = envelope["units"]
    word = _unit_word(units)
    count = len(units)

    # A part of a larger file keeps that file's own page numbers, so what the
    # model is told must come from the units rather than from how many there
    # are. Telling it "1 to 10" while the markers below read PAGE 21 is how a
    # citation ends up pointing at a page the value was never on.
    first_index = units[0]["index"] if units else 1
    last_index = units[-1]["index"] if units else 1

    lines = []
    for field in schema["fields"]:
        field_id, label, ftype, card, desc = field[0], field[1], field[2], field[3], field[4]
        if card == "group":
            # A UNIT ON EVERY ROW, not one for the whole table. A table's
            # rows are rarely all on one page - a list of related entities is
            # gathered from wherever each is mentioned - so asking for one
            # number for the table asks a question with no honest answer, and
            # the model correctly returned null. That null was then stamped on
            # every cell: of 483 values with no citation in one tenant, 474
            # were table columns and 9 were single values.
            cols = ", ".join('"' + _column_name(c[0]) + '": string | null'
                             for c in _group_columns(field))
            lines.append(
                '  "' + field_id + '": { "rows": [ { ' + cols
                + ', "unit": integer | null } ], "unit": integer | null },'
                + "  // " + label + " - " + desc)
            continue
        hint = "[string] | null" if card == "many" else "string | null"
        lines.append(
            '  "' + field_id + '": { "value": ' + hint + ', "unit": integer | null },'
            + "  // " + label + " (" + ftype + ") - " + desc
        )

    # Built by concatenation, not .format(): the text contains literal JSON
    # braces and every one of them would be read as a placeholder.
    #
    # THE SUBJECT COMES FIRST, before the field list, because the field
    # descriptions are read in its light: "one-paragraph description of the
    # SUBJECT" means nothing until the model has been told which company
    # that is. Absent only where the handler has already refused, so this is
    # never silently omitted.
    instruction = (
        _subject_preamble(envelope["subject_name"])
        if envelope.get("subject_name") else ""
    ) + (
        "Extract the following from the document below. Return JSON with "
        "exactly these keys:\n\n"
        "{\n" + "\n".join(lines) + "\n}\n\n"
        'For each field, "value" is what the document states, or null if it '
        "is not present. Do not infer, do not use outside knowledge.\n\n"
        '"unit" is the ' + word + " number the value was read from. "
        "For a table, give a unit on EACH ROW - the " + word + " that row "
        "was read from - and give the table's own unit only if every row "
        "came from the same one.\n"
        "The document has " + str(count) + " " + word + "s, numbered "
        + str(first_index) + " to " + str(last_index)
        + ", marked in the text below.\n"
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

                # The row's own unit, falling back to the table's. A row
                # knows where it was read from even when the table does not,
                # and stamping the table's null on every cell was how a
                # citation was lost from a value that had one.
                r_kind, r_index, r_start, r_end, r_cell = kind, index, start, end, cell
                if row.get("unit") is not None:
                    r_kind, r_index, r_start, r_end, r_cell = _resolve_locator(
                        row.get("unit"), units)

                for col in _group_columns(field):
                    col_id = col[0]
                    cell_value = row.get(_column_name(col_id))
                    if cell_value is None or cell_value == "":
                        continue
                    _write_value(envelope, col_id, cell_value, ordinal,
                                 r_kind, r_index, r_start, r_end, r_cell)
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


def _refuse_no_subject(bucket, key, envelope):
    """A document in an engagement that never named its subject.

    Terminal and recorded, in the same two columns a schema failure uses -
    one code, one place the screen looks. Nothing is read, nothing is
    written to extracted_value, and no model call is made.

    NOT A REFUND. The charge bought filing, and the API refuses to file
    into an engagement with no subject - so a document reaching here has
    not come through the paid path. Money is not moved from a function that
    cannot tell whether any was taken."""
    envelope["subject_name"] = None
    envelope["extraction_error"] = ERROR_SUBJECT_MISSING
    envelope["extraction_complete"] = True
    envelope["extraction_results"] = {}
    envelope["extraction_tokens"] = {"input": 0, "output": 0}
    envelope["model_id"] = MODEL_ID

    _s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )

    document_id = envelope.get("document_id")
    if document_id:
        _sql(
            "UPDATE document SET extracted_at = UTC_TIMESTAMP(), "
            "extraction_error = :error "
            "WHERE tenant_id = :t AND document_id = :d",
            [_p("error", ERROR_SUBJECT_MISSING),
             _p("t", envelope["tenant_id"]), _p("d", int(document_id))],
        )

    print("[extraction-refused] doc={} reason={}".format(
        document_id, ERROR_SUBJECT_MISSING))

    return {"status": "refused", "document_id": document_id,
            "values_written": 0,
            "extraction_error": ERROR_SUBJECT_MISSING,
            "results": {}}


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

    # WHOSE FACTS THIS DOCUMENT HOLDS, before anything is read from it
    # (SUBJ-01). Without it, a document describing a counterparty in detail
    # and the subject not at all fills the subject's fields with the
    # counterparty's - under citations that are entirely correct, which is
    # what makes it dangerous rather than merely wrong.
    #
    # REFUSED, NOT EXTRACTED. Reading it anyway and hoping would cost a
    # model call and produce values nobody can trust; the row says so
    # instead, in the column migration 029 added and the screen already
    # reads. extraction_complete is written so our own put_object does not
    # re-fire the trigger into the same refusal for ever.
    subject = _subject_for(envelope["tenant_id"], envelope.get("document_id"))
    if not subject:
        return _refuse_no_subject(bucket, key, envelope)

    envelope["subject_name"] = subject

    # The revision the document was FILED under, not the tenant's current
    # one. A document filed under revision 11 resolves against revision 11 for
    # ever - that is what a snapshot is for, and it is why a memo written in
    # March still reproduces in September.
    registry = config.load(envelope["tenant_id"],
                           envelope.get("config_revision") or 1)

    schema_keys = registry.schemas_for(envelope.get("document_type"))
    results, total_written = {}, 0
    tokens_in = tokens_out = 0
    failures = []

    for schema_key in schema_keys:
        schema = registry.get_schema(schema_key)
        if not schema:
            results[schema_key] = {"status": "no-schema"}
            continue

        # ONE SCHEMA'S FAILURE IS ONE SCHEMA'S (pipeline spec, per-schema
        # failure). This loop used to let an exception leave the handler: a
        # document routed to twenty-one schemas lost the twenty that worked
        # because the first one did not, and - because the UPDATE below never
        # ran - said "extracting..." for ever afterwards.
        #
        # The whole schema is inside the try, the persist included. A failure
        # in the writing rather than the reading is rarer and is not rolled
        # back: what was written for this schema stays, because unpicking it
        # would mean a transaction per schema and losing the values would be
        # the worse answer. The failure is recorded either way.
        try:
            prompt, truncated = _build_prompt(schema, envelope)
            extracted, usage = _invoke(prompt)

            tokens_in += usage.get("input_tokens", 0)
            tokens_out += usage.get("output_tokens", 0)

            if extracted is None:
                results[schema_key] = {"status": "invalid-json"}
                continue

            written = _persist(envelope, registry, schema_key, extracted)
        except Exception as exc:  # noqa: BLE001 - recorded, then carried on
            code = (ERROR_MALFORMED_GROUP if isinstance(exc, MalformedGroup)
                    else ERROR_SCHEMA_FAILED)
            failures.append(code)
            results[schema_key] = {
                "status": "failed",
                "error": type(exc).__name__,
                "detail": str(exc),
            }
            print("[extraction-failed] doc={} schema={} error={} detail={}"
                  .format(envelope.get("document_id"), schema_key,
                          type(exc).__name__, exc))
            continue

        total_written += written

        results[schema_key] = {
            "status": "extracted",
            "fields_written": written,
            "truncated": truncated,
        }

    # The one code the row carries, where several schemas failed differently.
    # The malformed group wins: it names a fault in the CONFIGURATION, which
    # somebody can go and fix, over a generic failure that says only that
    # something went wrong.
    extraction_error = None
    if failures:
        extraction_error = (ERROR_MALFORMED_GROUP
                            if ERROR_MALFORMED_GROUP in failures
                            else failures[0])

    envelope["extraction_error"] = extraction_error
    envelope["extraction_complete"] = True
    envelope["extraction_results"] = results
    envelope["extraction_tokens"] = {"input": tokens_in, "output": tokens_out}
    envelope["model_id"] = MODEL_ID
    # envelope["subject_name"] was set above, before the prompts were built.
    # It sits here beside model_id for the same reason: a value should be
    # traceable to the subject it was read under, as it is to the model that
    # read it. The engagement's subject is editable, so the name on this
    # envelope is the only record of what it was at the moment of reading.
    # ENVELOPE ONLY - no column, and nothing reads it yet (SUBJ-01, item 5).

    _s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )

    # Mark the document extracted, and say whether anything failed on the way.
    # Without the timestamp the list cannot tell a document still being read
    # from one that yielded nothing - both show as zero values, and they mean
    # very different things to a reader. Without the code it cannot tell one
    # that yielded nothing from one that was never asked properly.
    #
    # BOTH COLUMNS, EVERY TIME, and extraction_error is written NULL on a
    # clean run: a document re-extracted after its configuration was fixed
    # must not keep yesterday's fault. Nothing else on the row is named, so
    # nothing else is touched.
    document_id = envelope.get("document_id")
    if document_id:
        _sql(
            "UPDATE document SET extracted_at = UTC_TIMESTAMP(), "
            "extraction_error = :error "
            "WHERE tenant_id = :t AND document_id = :d",
            [_p("error", extraction_error),
             _p("t", envelope["tenant_id"]), _p("d", int(document_id))],
        )

    print("[extracted] doc={} schemas={} values={} failed={} error={} "
          "tokens_in={} tokens_out={}".format(
              envelope.get("document_id"), list(results.keys()),
              total_written, len(failures), extraction_error,
              tokens_in, tokens_out))

    return {
        "status": "ok",
        "document_id": envelope.get("document_id"),
        "values_written": total_written,
        "extraction_error": extraction_error,
        "results": results,
    }





