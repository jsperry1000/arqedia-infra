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

THE TEMPLATE COMES FROM THE TENANT'S CONFIGURATION. template.py was a
hard-coded stand-in and said so; while it was in use, everything authored in the
editor was inert here. A group field with four columns, a hundred extracted
values, bound to a section and published, rendered nothing - because this
function never opened config_section. Sections, field bindings, prompts and
group columns now come from config.Registry, which extraction already reads.

Invoke with:
    {"tenant_id": 1, "engagement": "eng-001"}

or, to rewrite one section of a memo already written, with the id of the
memo_rewrite row the API has written for it:
    {"action": "rewrite", "tenant_id": 1, "rewrite_id": 42}
"""

import datetime
import hashlib
import json
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

import cleanup
import config

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")
_bedrock = boto3.client("bedrock-runtime")
_lambda = boto3.client("lambda")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
MODEL_ID = os.environ["MODEL_ID"]
RENDER_FUNCTION = os.environ["RENDER_FUNCTION"]

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
          AND d.active = 1
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


def _label_for(registry, field_id):
    """Label from the configuration. Group columns resolve to their own column
    label."""
    if "." in field_id:
        group = field_id.split(".", 1)[0]
        for col in (registry.group_columns(group) or []):
            if col[0] == field_id:
                return col[1]
    return registry.label_for(field_id)


def _citation(v):
    """A readable source reference. Filename plus location where known."""
    if v["locator_kind"] and v["locator_kind"] != "none" and v["locator_index"]:
        return "{}, {} {}".format(
            v["filename"], v["locator_kind"], v["locator_index"])
    return v["filename"]


# --- stage 1: assemble -----------------------------------------------------

def _render_group(registry, field_id, columns, rows):
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

    out = ["**" + registry.label_for(field_id) + "**", ""]
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
    out.append("*" + _citation(any_value) + "*")
    out.append("")
    return out


def _assemble_extract(registry, section, values):
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
            columns = registry.group_columns(field_id)
            if columns:
                blocks.extend(_render_group(registry, field_id, columns, rows))
                continue
            for v in rows:
                if v["field_id"] == field_id:
                    blocks.append("- **" + _label_for(registry, field_id) + ":** "
                                  + str(v["value"]) + "  \n  *" + _citation(v) + "*")
        blocks.append("")

    return "\n".join(blocks) + "\n", used


# --- model -----------------------------------------------------------------

# The most a single model call may return. Named because a rewrite needs to
# know it: a reply that uses every token was cut off, and a section missing its
# end reads as finished.
_MAX_TOKENS = 4096


def _invoke(prompt, system=None):
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": _MAX_TOKENS,
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
    """Model-drafted section. Evidence is every value fed into its context.

    Citations are masked here as well as at consolidation. Drafting was the one
    place a real citation reached a model unprotected, and it did exactly what
    the masking exists to prevent: told to write for a reader, it dropped the
    filenames and left the Summary carrying no evidence at all - the section a
    credit officer reads first. Consolidation then masked text that was already
    gone, which is why the loss was invisible in its log."""
    context_parts, used = [], []

    for key in section.get("context_sections", []):
        block = assembled.get(key)
        if not block or not block["markdown"].strip():
            continue
        context_parts.append("## {}\n\n{}".format(block["title"], block["markdown"]))
        used.extend(block["values"])

    if not context_parts:
        return "", [], {}

    masked, tokens = _mask_citations(
        "\n\n".join(context_parts)[:_SECTION_INPUT_CHARS])

    prompt = (
        section["prompt"]
        + cleanup.CITATION_TOKENS
        + "\n\n--- CONTEXT START ---\n"
        + masked
        + "\n--- CONTEXT END ---"
    )

    text, usage = _invoke(prompt)
    text, dropped = _restore_citations(text, tokens)

    if dropped:
        print("[citations-dropped] stage=draft section=%s count=%d of %d" % (
            section["key"], len(dropped), len(tokens)))

    return text + "\n", used, usage


# --- stage 3: consolidate --------------------------------------------------

_CITATION = re.compile(r"\*([^*\n]+?\.(?:pdf|docx|xlsx|txt|json|xml)[^*\n]*?)\*")


def _mask_citations(markdown):
    """Replace every citation with an opaque token before consolidation.

    Asking the model to preserve citations does not work: told to write for a
    reader, it turns "01.-Certificate-of-Incorporation-Cocoa-Empire-Uganda-Ltd
    .pdf, page 1" into "Certificate of Incorporation". That reads well and
    proves nothing - it names no file and no page, so it cannot be checked
    against anything.

    A token has nothing to paraphrase. The model moves it around; the text is
    restored afterwards, character for character.

    Returns (masked_text, {token: original}).
    """
    seen, tokens = {}, {}

    def swap(m):
        original = m.group(0)
        if original not in seen:
            token = "[[C%d]]" % (len(seen) + 1)
            seen[original] = token
            tokens[token] = original
        return seen[original]

    return _CITATION.sub(swap, markdown), tokens


_ADDED_SOURCE = re.compile(
    r"\[?\s*Sources?\s*:?\s*\]?\s*(?=\[\[C\d+\]\])", re.I)


def _restore_citations(text, tokens):
    """Put the citations back. Returns (text, dropped) - dropped names the
    tokens the model did not return, which is a fact worth logging rather
    than a fault to hide."""
    # The model sometimes writes "[Source: " beside a token, which then reads
    # twice in the output. Told not to, and stripped anyway - it has shown it
    # will do it.
    text = _ADDED_SOURCE.sub("", text)

    # Measured BEFORE restoring. Asking whether a token survives AFTER every
    # token has been replaced always answers no, so this reported a total loss
    # on every section of every memo while the citations were in fact intact -
    # the one line that would warn of real evidence loss, crying wolf on every
    # run and therefore telling nobody anything.
    dropped = [original for token, original in tokens.items()
               if token not in text]

    for token, original in tokens.items():
        text = text.replace(token, original)

    # A token the model invented has no source and must not survive as text.
    text = re.sub(r"\[\[C\d+\]\]", "", text)
    return text, dropped


def _consolidate(section, markdown):
    """Turn one assembled section into the version a reader receives.

    Runs per section, not per memo: a single prompt over fifty documents
    produces mush, and per-section lets one section carry its own shape.

    Citations are masked before the call and restored after, so consolidation
    cannot rewrite them. That is deterministic on the TEXT of a citation. It
    is not deterministic on which statement a citation ends up attached to -
    the model still moves the tokens - and nothing here can verify that.

    THE SECTION'S OWN PROMPT DECIDES ITS SHAPE, where it has one. Before, the
    only shaping came from a dictionary in cleanup.py keyed on the pack's own
    section keys, so a tenant's own section got none at all - and a field
    description asking for three paragraphs shaped EXTRACTION, per document,
    and never reached the writer. A tenant wrote an instruction, saw it obeyed
    nowhere, and had no way to find out why.

    It replaces rather than adds: a tenant who has written what a section
    should look like meant that, not that on top of ours. The built-in shaping
    remains the fallback, so the pack's tables keep working untouched."""
    if not markdown.strip():
        return markdown, {}

    masked, tokens = _mask_citations(markdown[:_SECTION_INPUT_CHARS])

    shape = (section.get("prompt") or "").strip()
    shape = "\n" + shape + "\n" if shape else cleanup.presentation_for(
        section["key"])

    prompt = (
        cleanup.CLEANUP_PROMPT
        + shape
        + cleanup.CITATION_TOKENS
        + "\n\n--- SECTION START ---\n"
        + "## {}. {}\n\n".format(section["num"], section["title"])
        + masked
        + "\n--- SECTION END ---"
    )

    text, usage = _invoke(prompt, system=cleanup.CLEANUP_PREAMBLE)
    text, dropped = _restore_citations(text, tokens)

    if dropped:
        print("[citations-dropped] section=%s count=%d of %d" % (
            section["key"], len(dropped), len(tokens)))

    print("[consolidated] section=%s shaped_by=%s" % (
        section["key"],
        "section prompt" if (section.get("prompt") or "").strip()
        else "built-in"))

    return text + "\n", usage


# --- rewrite ---------------------------------------------------------------

# A section heading as composition writes it: "## I. Introduction". Level two
# only, so a subheading the section itself carries is never mistaken for it.
_SECTION_HEADING = re.compile(r"^\s*##(?!#)\s+\S")


def _split_heading(markdown):
    """(heading, body). The heading is the first line, where that line is one."""
    text = (markdown or "").replace("\r\n", "\n").strip("\n")
    lines = text.split("\n")
    if lines and _SECTION_HEADING.match(lines[0]):
        return lines[0].rstrip(), "\n".join(lines[1:]).strip("\n")
    return "", text


def _rewrite(event):
    """Rewrite one section of a memo at a person's prompt.

    The API writes the memo_rewrite row, status running, and invokes this
    asynchronously. The row is the whole request and the whole result, so the
    screen polls the table rather than waiting on a function.

    Citations are protected exactly as consolidation protects them: masked
    before the call, restored after. A rewrite can move a citation and cannot
    rewrite one. Any the model did not return are counted on the row.

    The heading is never the model's. It is taken off before the call and put
    back after, character for character, so no prompt can renumber or retitle
    a section.

    Refuses rather than truncates. Consolidation cuts its input at
    _SECTION_INPUT_CHARS; a rewrite doing the same would hand back a section
    missing its end, looking complete. A reply that used every output token is
    refused for the same reason.

    Never raises. Lambda retries an asynchronous invocation that raises, which
    would spend the model call again on a request already failed. The failure
    is written to the row instead, and the person presses Go again."""
    tenant_id = int(event["tenant_id"])
    rewrite_id = int(event["rewrite_id"])

    found = _sql(
        """
        SELECT memo_id, prompt, input_text, status
        FROM memo_rewrite
        WHERE tenant_id = :t AND rewrite_id = :r
        """,
        [_p("t", tenant_id), _p("r", rewrite_id)],
    ).get("records", [])
    if not found:
        return {"status": "not-found", "rewrite_id": rewrite_id}

    memo_id = _col(found[0], 0)
    instruction = (_col(found[0], 1) or "").strip()
    section = _col(found[0], 2) or ""
    status = _col(found[0], 3)

    # Finished already. A second delivery of the same event must not call the
    # model twice.
    if status != "running":
        return {"status": "already-" + str(status), "rewrite_id": rewrite_id}

    def fail(reason, tokens_in=None, tokens_out=None):
        _sql(
            """
            UPDATE memo_rewrite
            SET status = 'failed', error = :error, model_id = :model,
                tokens_in = :tokens_in, tokens_out = :tokens_out,
                completed_at = UTC_TIMESTAMP()
            WHERE tenant_id = :t AND rewrite_id = :r AND status = 'running'
            """,
            [_p("error", reason[:1024]), _p("model", MODEL_ID),
             _p("tokens_in", tokens_in), _p("tokens_out", tokens_out),
             _p("t", tenant_id), _p("r", rewrite_id)],
        )
        print("[rewrite] tenant=%s memo=%s rewrite=%s status=failed "
              "reason=%s" % (tenant_id, memo_id, rewrite_id, reason))
        return {"status": "failed", "rewrite_id": rewrite_id,
                "error": reason}

    tokens_in = tokens_out = None
    try:
        heading, body = _split_heading(section)
        if not instruction:
            return fail("no instruction was given")
        if not body.strip():
            return fail("the section has no text to rewrite")
        if len(body) > _SECTION_INPUT_CHARS:
            return fail("the section is too long to rewrite in one pass: "
                        "%d characters, limit %d"
                        % (len(body), _SECTION_INPUT_CHARS))

        masked, tokens = _mask_citations(body)

        prompt = (
            cleanup.REWRITE_PROMPT
            + "\n\nINSTRUCTION\n"
            + instruction
            + "\n"
            + cleanup.CITATION_TOKENS
            + "\n\n--- SECTION START ---\n"
            + (heading + "\n\n" if heading else "")
            + masked
            + "\n--- SECTION END ---"
        )

        text, usage = _invoke(prompt, system=cleanup.REWRITE_PREAMBLE)
        tokens_in = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)

        if tokens_out >= _MAX_TOKENS:
            return fail("the rewrite ran past the length limit and was cut "
                        "off", tokens_in, tokens_out)

        text, dropped = _restore_citations(text, tokens)

        # Written anyway, despite being told not to. Ours goes back instead.
        _, text = _split_heading(text)
        if not text.strip():
            return fail("the model returned no text", tokens_in, tokens_out)

        output = (heading + "\n\n" if heading else "") + text.strip() + "\n"

        _sql(
            """
            UPDATE memo_rewrite
            SET status = 'done', output_text = :output,
                citations_dropped = :dropped, model_id = :model,
                tokens_in = :tokens_in, tokens_out = :tokens_out,
                completed_at = UTC_TIMESTAMP()
            WHERE tenant_id = :t AND rewrite_id = :r AND status = 'running'
            """,
            [_p("output", output), _p("dropped", len(dropped)),
             _p("model", MODEL_ID), _p("tokens_in", tokens_in),
             _p("tokens_out", tokens_out),
             _p("t", tenant_id), _p("r", rewrite_id)],
        )

        print("[rewrite] tenant=%s memo=%s rewrite=%s status=done "
              "citations_dropped=%d of %d tokens_in=%s tokens_out=%s" % (
                  tenant_id, memo_id, rewrite_id, len(dropped), len(tokens),
                  tokens_in, tokens_out))

        return {"status": "done", "rewrite_id": rewrite_id,
                "citations_dropped": len(dropped),
                "tokens": {"input": tokens_in, "output": tokens_out}}

    except Exception as exc:  # noqa: BLE001 - written to the row, not raised
        return fail("%s: %s" % (type(exc).__name__, exc),
                    tokens_in, tokens_out)


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
    # A section rewrite shares the model call and the citation masking with
    # generation, and nothing else. Routed first, so everything below runs
    # exactly as it did.
    if event.get("action") == "rewrite":
        return _rewrite(event)

    tenant_id = int(event["tenant_id"])
    engagement = event["engagement"]
    generated_by = event.get("generated_by")
    requested_template = event.get("template_key")

    # The tenant's ACTIVE revision, not the revision each document was filed
    # under. Extraction pins the filing revision because a value belongs to the
    # schema that produced it; a memo is written now, against the template in
    # force now, and binds whatever values exist by field_id. Pipeline spec
    # v1.0 section 7: a document filed under revision 3 and composed under
    # revision 7 binds fine as long as the field IDs still exist.
    revision = config.active_revision(tenant_id)
    registry = config.load(tenant_id, revision)

    # Which memorandum is being written. A tenant may hold a credit, a KYC and
    # a lender template over the same documents; the caller says which, and an
    # absent one means the tenant has only ever had the one - which is every
    # caller that predates this.
    template_key = requested_template or registry.TEMPLATE_KEY
    if not registry.has_template(template_key):
        return {"status": "no-such-template",
                "template_key": template_key,
                "available": [t["key"] for t in registry.template_list()]}

    values = _load_values(tenant_id, engagement)
    if not values:
        return {"status": "no-values", "engagement": engagement}

    document_ids = sorted({v["document_id"] for v in values})
    generated_at = datetime.datetime.now(datetime.timezone.utc)
    tokens_in = tokens_out = 0

    # 1. Assemble the deterministic sections. They are the context for the rest.
    assembled = {}
    for section in registry.sections_of_kind("extract", template_key):
        markdown, used = _assemble_extract(registry, section, values)
        assembled[section["key"]] = {
            "title": section["title"],
            "num": section["num"],
            "markdown": markdown,
            "values": used,
        }

    # 2. Draft the composed sections from that context.
    for section in registry.sections_of_kind("composed", template_key):
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
    sections = registry.sections_for(template_key)

    empty_sections = []
    for section in sections:
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
            registry.label_for_template(template_key),
        ),
        cleanup.coverage_callout(empty_sections),
    ]

    for section in sections:
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

    memo_body = "\n".join(parts)
    encoded = memo_body.encode("utf-8")
    sha = hashlib.sha256(encoded).hexdigest()

    memo_key = "tenants/{}/memos/{}/{}-{}.md".format(
        tenant_id, engagement, template_key,
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
           s3_version_id, sha256, generated_by)
        VALUES
          (:tenant_id, :template_key, :config_revision, :s3_bucket, :s3_key,
           :s3_version_id, :sha256, :generated_by)
        """,
        [
            _p("tenant_id", tenant_id),
            _p("template_key", template_key),
            _p("config_revision", revision),
            _p("s3_bucket", CURATED_BUCKET),
            _p("s3_key", memo_key),
            _p("s3_version_id", put.get("VersionId")),
            _p("sha256", sha),
            _p("generated_by", generated_by),
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
    for ordinal, section in enumerate(sections, start=1):
        block = assembled[section["key"]]
        if not block["values"]:
            continue
        _record_claim(tenant_id, memo_id, section["key"], ordinal,
                      block["markdown"], block["values"])
        claims += 1

    # Composition no longer renders. The PDF is a view of the memo, produced
    # on demand when somebody asks for it, so there is no window in which a
    # memo exists without one and no stored file to go stale.

    print("[composed] memo={} template={} revision={} docs={} values={} "
          "claims={} empty={} tokens_in={} tokens_out={}".format(
              memo_id, template_key, revision, len(document_ids), len(values),
              claims, len(empty_sections), tokens_in, tokens_out))

    return {
        "status": "ok",
        "memo_id": memo_id,
        "memo_key": memo_key,
        "subject": subject,
        "template_key": template_key,
        "config_revision": revision,
        "documents": len(document_ids),
        "values": len(values),
        "claims": claims,
        "empty_sections": empty_sections,
        "tokens": {"input": tokens_in, "output": tokens_out},
    }
