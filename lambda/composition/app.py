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
    {"tenant_id": 1, "engagement": "eng-001", "engagement_id": 3,
     "template_key": "credit", "generated_by": "a@b.test",
     "entry_id": 50, "run": "<hex>"}

entry_id is the ledger entry that paid for it and run is where its progress
is kept; both come from the API, and a run that writes no memo gives the
charge back (see _generate).

or, to rewrite one section of a memo already written, with the id of the
memo_rewrite row the API has written for it:
    {"action": "rewrite", "tenant_id": 1, "rewrite_id": 42}

or, to update a memo a person has saved, against the configuration in use
and the documents now on file (see _update):
    {"action": "update", "tenant_id": 1, "memo_id": 7, "engagement_id": 3,
     "template_key": "credit", "config_revision": 9, "run": "<hex>",
     "requested_by": "a@b.test"}

with "section": "## II. Business", a saved heading, to update that section
alone.
"""

import datetime
import hashlib
import json
import os
import re
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import cleanup
import config
import wallet

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")
# botocore defaults to a 60-second read timeout and legacy retries of up to 5
# attempts, each re-sending and re-billing the call. On 18 September a memo
# produced nothing for five minutes after its last logged section and died at
# the 600-second function limit with nothing in the log.
_bedrock = boto3.client(
    "bedrock-runtime",
    config=Config(read_timeout=300,
                  retries={"mode": "standard", "max_attempts": 2}),
)
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


def _load_values(tenant_id, workspace_id, engagement_id):
    """Every extracted value for the engagement, with its source document.

    ONE WORKSPACE'S DOCUMENTS (PACK-01). A document is uploaded into one
    workspace and read under its vocabulary; a memo is written under one
    workspace's configuration. A Trade Finance memo must not bind values read
    under Real Estate's field definitions, however the field keys happen to
    coincide, so the documents are those of the memo's own workspace.

    BY d.engagement_id (13.3 stage 4), not by a LIKE on the storage key. The
    id arrives in the payload, resolved by the API from the name in the
    address - so this function holds no copy of the naming rule and cannot
    drift from it. The LIKE it replaces matched on where a file was stored,
    which is a different question from which engagement it belongs to, and
    answered it wrongly for any name that was a prefix of another."""
    result = _sql(
        """
        SELECT v.value_id, v.field_id, v.value, v.locator_kind,
               v.locator_index, v.row_ordinal, v.document_id, d.filename,
               d.engagement_id
        FROM extracted_value v
        JOIN document d ON d.document_id = v.document_id
        WHERE v.tenant_id = :tenant_id
          AND d.state = 'filed'
          AND d.active = 1
          AND d.engagement_id = :engagement_id
          AND d.workspace_id = :workspace_id
        ORDER BY v.document_id, v.value_id
        """,
        [
            _p("tenant_id", tenant_id),
            _p("engagement_id", int(engagement_id)),
            _p("workspace_id", int(workspace_id)),
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
            # The engagement these documents belong to (migration 030). Taken
            # from the documents rather than looked up by name: they ARE the
            # engagement, and a memo that binds their values belongs wherever
            # they do.
            "engagement_id": _col(r, 8),
        }
        for r in result.get("records", [])
    ]


# _engagement_of is gone with the LIKE it existed for (13.3 stage 4).
#
# It read the engagement back OFF the values, because the query that fetched
# them knew only a folder name and the id had to be recovered from somewhere.
# The id is now what the query was given, so recovering it from the rows would
# be asking the documents to confirm the question they were selected by.


def _subject_of(tenant_id, engagement_id):
    """The engagement's subject, or None (migration 031).

    THE CURRENT ONE, not the one in force when the documents were filed. A
    subject is editable, and a change is meant to reach every memorandum
    generated afterwards - which is the same rule composition already
    follows for the template: the memo is written now, against the
    configuration in force now. What a value was READ under is recorded on
    the extraction envelope and is a separate question."""
    if engagement_id is None:
        return None
    found = _sql(
        "SELECT subject_name FROM engagement "
        "WHERE tenant_id = :t AND engagement_id = :e",
        [_p("t", tenant_id), _p("e", int(engagement_id))]).get("records", [])
    if not found:
        return None
    return (_col(found[0], 0) or "").strip() or None


def _shown_as(tenant_id, engagement_id, name):
    """What the engagement is shown as now, for the Engagement row of the
    memorandum (migration 051): its display name where one is set, `name`
    where none is or the row cannot be read.

    THE CURRENT ONE, as the subject is. A rename reaches every memorandum
    generated afterwards; one already generated keeps what its text says."""
    found = _sql(
        "SELECT display_name FROM engagement "
        "WHERE tenant_id = :t AND engagement_id = :e",
        [_p("t", tenant_id), _p("e", int(engagement_id))]).get("records", [])
    shown = (_col(found[0], 0) or "").strip() if found else ""
    return shown or name


def _subject_of_memo(tenant_id, memo_id):
    """The subject of the engagement a memo belongs to, for a rewrite.

    Through memo.engagement_id (migration 030). A rewrite is handed nothing
    but a memo_rewrite row, so the engagement is reached from the memo
    rather than passed in.

    NULL where the memo predates 030's backfill and was never given an
    engagement. The rewrite then runs exactly as it does today - see
    cleanup.subject_rule, which is empty rather than guessing."""
    found = _sql(
        "SELECT engagement_id FROM memo "
        "WHERE tenant_id = :t AND memo_id = :m",
        [_p("t", tenant_id), _p("m", int(memo_id))]).get("records", [])
    if not found:
        return None
    return _subject_of(tenant_id, _col(found[0], 0))


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

    # The key beside the label, so an instruction that names f_suppliers can
    # find the table it means. The model is told never to write it out.
    out = ["**" + registry.label_for(field_id) + " (" + field_id + ")**", ""]
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
                    blocks.append("- **" + _label_for(registry, field_id)
                                  + " (" + field_id + "):** "
                                  + str(v["value"]) + "  \n  *" + _citation(v) + "*")
        blocks.append("")

    return "\n".join(blocks) + "\n", used


# --- model -----------------------------------------------------------------

# The most a single model call may return. Named because a rewrite needs to
# know it: a reply that uses every token was cut off, and a section missing its
# end reads as finished.
_MAX_TOKENS = 4096


def _invoke(prompt, system=None, stage="?", section="?", chars_in=0):
    """One model call, and a line about it either side.

    The log said nothing about a model call except dropped citations, so when
    a section produced nothing for five minutes the cause could not be read
    from the log at all.

    TWO LINES, NOT ONE. A call that never returns cannot log what it did, so
    the section is named BEFORE the call as well as after it. Without the
    first line a timeout is anonymous: the run simply stops, and nothing says
    which section it stopped in.

    A FAILURE IS LOGGED AND RE-RAISED, not swallowed. The line says what went
    wrong and how long it took; the exception travels on unchanged, so
    everything above this behaves exactly as it did.

    chars_in is the caller's, measured BEFORE the slice: only the caller knows
    what it cut. retries is read defensively - botocore sets
    ResponseMetadata.RetryAttempts on a successful response (endpoint.py), but
    this runs on the runtime's bundled botocore rather than one we ship, so an
    absent field prints 0 rather than raising."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": _MAX_TOKENS,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    # A rewrite refuses rather than truncates, so the 40,000-character cap is
    # not its rule and reporting it as one would be a lie either way round.
    truncated = "n/a" if stage == "rewrite" else (
        "yes" if chars_in > _SECTION_INPUT_CHARS else "no")

    print("[model-call-start] stage=%s section=%s chars_in=%d" % (
        stage, section, chars_in))

    started = time.time()
    try:
        response = _bedrock.invoke_model(
            modelId=MODEL_ID, body=json.dumps(body))
        payload = json.loads(response["body"].read())
    except Exception as exc:  # noqa: BLE001 - logged, then re-raised unchanged
        print("[model-call] stage=%s section=%s chars_in=%d seconds=%.1f "
              "outcome=error error=%s" % (
                  stage, section, chars_in, time.time() - started,
                  type(exc).__name__))
        raise
    seconds = time.time() - started

    usage = payload.get("usage", {})
    tokens_out = usage.get("output_tokens", 0)
    print("[model-call] stage=%s section=%s chars_in=%d truncated=%s "
          "seconds=%.1f tokens_in=%s tokens_out=%s hit_max=%s retries=%s "
          "outcome=ok" % (
              stage, section, chars_in, truncated, seconds,
              usage.get("input_tokens", 0), tokens_out,
              "yes" if tokens_out >= _MAX_TOKENS else "no",
              response.get("ResponseMetadata", {}).get("RetryAttempts", 0)))

    text = "".join(
        b.get("text", "") for b in payload.get("content", [])
        if b.get("type") == "text"
    )
    return text.strip(), usage


# --- stage 2: draft --------------------------------------------------------

def _compose(section, assembled, subject_name=None):
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

    context = "\n\n".join(context_parts)
    masked, tokens = _mask_citations(context[:_SECTION_INPUT_CHARS])

    # The draft has no system prompt, so the subject goes in the prompt
    # itself - after the section's own instruction, which is what the
    # section is FOR, and before the citation rules. Empty where the
    # engagement has no subject, and the prompt is then what it was.
    prompt = (
        section["prompt"]
        + cleanup.subject_rule(subject_name)
        + cleanup.CITATION_TOKENS
        + "\n\n--- CONTEXT START ---\n"
        + masked
        + "\n--- CONTEXT END ---"
    )

    text, usage = _invoke(prompt, stage="draft", section=section["key"],
                          chars_in=len(context))
    text, dropped = _restore_citations(text, tokens)

    if dropped:
        print("[citations-dropped] stage=draft section=%s count=%d of %d" % (
            section["key"], len(dropped), len(tokens)))

    return text + "\n", used, usage


# --- stage 3: consolidate --------------------------------------------------

_CITATION = re.compile(r"\*([^*\n]+?\.(?:pdf|docx|xlsx|txt|json|xml)[^*\n]*?)\*")


def _mask_citations(markdown, tokens=None):
    """Replace every citation with an opaque token before consolidation.

    Asking the model to preserve citations does not work: told to write for a
    reader, it turns "01.-Certificate-of-Incorporation-Cocoa-Empire-Uganda-Ltd
    .pdf, page 1" into "Certificate of Incorporation". That reads well and
    proves nothing - it names no file and no page, so it cannot be checked
    against anything.

    A token has nothing to paraphrase. The model moves it around; the text is
    restored afterwards, character for character.

    Returns (masked_text, {token: original}).

    `tokens` carries a numbering on from an earlier call, so two texts masked
    one after the other give the same citation the same token. Update needs
    that: the model is shown the saved section and the fresh one, and a
    source cited by both must read as one source.
    """
    tokens = {} if tokens is None else tokens
    seen = {original: token for token, original in tokens.items()}

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


def _section_heading(num, title):
    """A section's heading without its hashes: "I. Introduction", or the
    title alone where the section has no numeral. Written "{}. {}" until 26
    October 2026, which gave an unnumbered section ". Executive Summary"."""
    num = (num or "").strip()
    return "{}. {}".format(num, title) if num else title


def _consolidate(section, markdown, subject_name=None):
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
    remains the fallback, so the pack's tables keep working untouched.

    REPLACING MEANS THE PREAMBLE'S SHAPE TOO. Until 16 October 2026 only
    SECTION_PRESENTATION was replaced: the section prompt was appended to the
    user message while CLEANUP_PREAMBLE's own shape rules - opening sentence,
    grouped tables, a closing Note - sat in the system prompt and won. A
    section with an instruction is now consolidated under INSTRUCTED_PREAMBLE,
    where the instruction decides the form and the rules decide only what may
    be said.

    A COMPOSED section is consolidated under the rules alone. It was drafted
    to its own instruction already, and is told to keep the form it has."""
    if not markdown.strip():
        return markdown, {}

    masked, tokens = _mask_citations(markdown[:_SECTION_INPUT_CHARS])

    instruction = (section.get("prompt") or "").strip()
    if section.get("kind") == "composed":
        shaped_by = "rules only"
        instruction = cleanup.COMPOSED_INSTRUCTION
    elif instruction:
        shaped_by = "section prompt"
    else:
        shaped_by = "built-in"

    body = (
        cleanup.CITATION_TOKENS
        + "\n\n--- SECTION START ---\n"
        + "## " + _section_heading(section["num"], section["title"]) + "\n\n"
        + masked
        + "\n--- SECTION END ---"
    )

    # Without an instruction, exactly what it was: the full preamble and the
    # built-in shape for the pack's own section keys.
    if shaped_by == "built-in":
        preamble = cleanup.CLEANUP_PREAMBLE
        prompt = (cleanup.CLEANUP_PROMPT
                  + cleanup.presentation_for(section["key"])
                  + body)
    else:
        preamble = cleanup.INSTRUCTED_PREAMBLE
        prompt = (cleanup.INSTRUCTED_PROMPT
                  + "\n\nINSTRUCTION\n" + instruction + "\n"
                  + body)

    # The subject joins the PREAMBLE, not the instruction. cleanup.py's own
    # rule: anything about what may be SAID belongs in the preamble, so a
    # tenant's instruction, which decides the form, cannot displace it.
    text, usage = _invoke(prompt,
                          system=preamble
                          + cleanup.subject_rule(subject_name),
                          stage="consolidate", section=section["key"],
                          chars_in=len(markdown))
    text, dropped = _restore_citations(text, tokens)

    if dropped:
        print("[citations-dropped] section=%s count=%d of %d" % (
            section["key"], len(dropped), len(tokens)))

    print("[consolidated] section=%s shaped_by=%s" % (
        section["key"], shaped_by))

    return text + "\n", usage


# --- rewrite ---------------------------------------------------------------

# What a person is told when a rewrite or an Update stops on an exception.
# The exception itself is logged; its text is never shown.
REWRITE_FAULT = ("The rewrite stopped because of a fault on our side. "
                 "Try it again.")
UPDATE_FAULT = ("The update stopped because of a fault on our side. "
                "Try it again.")
# One section of an Update that could not be compared (ERR-01). The rest of
# the run is offered as usual.
UPDATE_SECTION_FAULT = ("This section could not be compared because of a "
                        "fault on our side. Run the update again.")
# An Update of one section whose heading the configuration in use does not
# write - retyped in the memo, or gone from the template. Refunded.
UPDATE_SECTION_UNKNOWN = ("This section is not one the configuration in use "
                          "writes, so it cannot be updated on its own. Its "
                          "heading may have been changed in the memo.")

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

        # A rewrite may reorder, shorten and retable a section, and every
        # one of those is a chance to attach a counterparty's fact to the
        # subject. It gets the same rule the other two passes get, reached
        # through memo.engagement_id because a rewrite is handed nothing
        # but its own row.
        text, usage = _invoke(prompt,
                              system=cleanup.REWRITE_PREAMBLE
                              + cleanup.subject_rule(
                                  _subject_of_memo(tenant_id, memo_id)),
                              stage="rewrite", section=str(rewrite_id),
                              chars_in=len(body))
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
        # The row's error is shown to the person as written, so the
        # exception goes to the log and the row carries the sentence.
        print("[rewrite-error] tenant=%s memo=%s rewrite=%s %r" % (
            tenant_id, memo_id, rewrite_id, exc))
        return fail(REWRITE_FAULT, tokens_in, tokens_out)


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


# --- writing the sections --------------------------------------------------

def _reads(registry, template_key, only):
    """The section `only` and every composed section it reads, however
    indirectly. A composed section is drafted from those, so an Update of it
    alone still has to draft them; assembled ones are always built."""
    composed = {s["key"]: s
                for s in registry.sections_of_kind("composed", template_key)}
    need, stack = set(), [only]
    while stack:
        key = stack.pop()
        if key in need:
            continue
        need.add(key)
        stack.extend(k for k in composed.get(key, {}).get(
            "context_sections", []) if k in composed)
    return need


def _write_sections(registry, template_key, values, subject_name, only=None):
    """Stages 1 to 3 for one template: assemble, draft, consolidate.

    Generation and Update both write through here, so a section Update puts
    beside a person's text is written exactly as a generated one would be.

    `only` is one section's key, for an Update of that section alone (31
    October 2026). Every assembled section is still built - that is no model
    call, and it is what a composed section reads - but only the composed
    sections it needs are drafted, and only it is consolidated. The rest are
    returned as assembled and must not be offered.

    Returns (sections, assembled, empty_sections, tokens_in, tokens_out)."""
    tokens_in = tokens_out = 0
    drafting = _reads(registry, template_key, only) if only else None

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
        if drafting is not None and section["key"] not in drafting:
            assembled[section["key"]] = {
                "title": section["title"], "num": section["num"],
                "markdown": "", "values": []}
            continue
        markdown, used, usage = _compose(section, assembled, subject_name)
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
        if only and section["key"] != only:
            continue
        block = assembled[section["key"]]
        if not block["markdown"].strip():
            empty_sections.append(section["title"])
            continue
        clean, usage = _consolidate(section, block["markdown"], subject_name)
        tokens_in += usage.get("input_tokens", 0)
        tokens_out += usage.get("output_tokens", 0)
        block["markdown"] = clean

    return sections, assembled, empty_sections, tokens_in, tokens_out


def _section_lines(block):
    """One section as the memo writes it. A section with nothing in it says
    so as a gap rather than vanishing from the page."""
    body = block["markdown"].strip()
    heading = "## " + _section_heading(block["num"], block["title"])

    if not body:
        return [heading, "",
                "> **Gap.** No material addressing this section was "
                "provided.", ""]

    lines = []
    # The consolidation keeps the heading, so do not add a second one.
    if not body.lstrip().startswith("#"):
        lines += [heading, ""]
    return lines + [body, ""]


# --- update ----------------------------------------------------------------
#
# A person has saved their own text of a memo, and the configuration or the
# documents have moved on since. Update writes every section again, exactly
# as generation would, and sets what is new beside the saved text for the
# person to accept or discard. NOTHING IS SAVED HERE: an accepted section
# reaches the memo only through revise, as a prompted rewrite's does, and
# each changed section is one memo_rewrite row marked source = 'update'.
#
# THE SAVED TEXT IS THE BASE AND IS NEVER RETURNED BY THE MODEL. The model
# says what to add and after which block; the code puts it there. A saved
# character cannot be changed by this pass, whatever the model answers.
#
# SECTIONS ARE MATCHED BY section_key, WORKED OUT, NOT STORED. The memo names
# the revision it was written under, and a revision never changes, so a saved
# heading looked up in that revision gives its key and a fresh section carries
# its own. A section renamed in the configuration since still matches. A
# heading a person retyped inside the memo resolves to nothing and is kept as
# it stands, as is a section the template no longer has.
#
# The run's progress is an object in the curated bucket, as a proposal's is:
# the screen polls it through the API, and it is what says an Update finished
# with nothing to change - which no row can say, because there is no row.

# A section heading as the memo screen splits on it: level two, at the start
# of the line. The screen's rule rather than _SECTION_HEADING's, so the
# sections Update reports are the sections the screen shows.
_SAVED_HEADING = re.compile(r"^##(?!#)\s+\S")

# Merges run side by side. Generation has already taken most of the
# function's time by the point they start.
_UPDATE_WORKERS = 4

# A citation token, as _mask_citations writes one.
_TOKEN = re.compile(r"\[\[C\d+\]\]")


def _update_key(tenant_id, memo_id, run):
    """Where a run's progress is kept. MIRRORED in lambda/api/app.py, which
    writes it first and reads it for the screen; the two must not drift."""
    return "tenants/%d/updates/memos/%d/%s.json" % (
        int(tenant_id), int(memo_id), run)


def _get_update(tenant_id, memo_id, run):
    try:
        body = _s3.get_object(Bucket=CURATED_BUCKET,
                              Key=_update_key(tenant_id, memo_id, run)
                              )["Body"].read()
    except ClientError:
        return None
    return json.loads(body.decode("utf-8"))


def _put_update(tenant_id, memo_id, run, state):
    _s3.put_object(Bucket=CURATED_BUCKET,
                   Key=_update_key(tenant_id, memo_id, run),
                   Body=json.dumps(state).encode("utf-8"),
                   ContentType="application/json")


def _split_saved(markdown):
    """The memo's sections as the screen splits them: [{heading, text}].

    Each text runs from its heading to the line before the next one, so it is
    the same text the screen holds under that section."""
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    starts = [i for i, line in enumerate(lines) if _SAVED_HEADING.match(line)]
    out = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        out.append({"heading": lines[start].strip(),
                    "text": "\n".join(lines[start:end])})
    return out


def _heading_norm(text):
    """A heading reduced to what identifies it: no hashes, no case, single
    spaces. Composition writes "## II. Business"; the model consolidating it
    occasionally doubles a space.

    No stray full stop either. An unnumbered section was written
    "## . Business" before 26 October 2026 and "## Business" since, and a
    memo saved from before must still match its section."""
    text = " ".join((text or "").lstrip("#").split())
    return re.sub(r"^\.\s+", "", text).lower()


def _keys_by_heading(registry, template_key):
    """{normalised heading: section_key} for one template at one revision."""
    if not registry.has_template(template_key):
        return {}
    keys = {}
    for s in registry.sections_for(template_key):
        keys.setdefault(
            _heading_norm(_section_heading(s["num"], s["title"])), s["key"])
    return keys


def _saved_blocks(text):
    """(lines, [(first, last)]) - a section's lines, and each block of it as
    the line range it occupies. A block is a run of lines with no blank one
    in it: a paragraph, a list, a table, a callout. The heading is line 0
    and belongs to no block."""
    lines = text.split("\n")
    blocks, start = [], None
    for i in range(1, len(lines)):
        if lines[i].strip():
            if start is None:
                start = i
        elif start is not None:
            blocks.append((start, i - 1))
            start = None
    if start is not None:
        blocks.append((start, len(lines) - 1))
    return lines, blocks


def _insert(text, placements):
    """The saved section with additions put in after the blocks named.

    Every saved line is written back in its place, unchanged. An addition is
    a new block of its own, set off by a blank line, so it can never run into
    the sentence before it. `after` 0 is before the first block; a number past
    the last block is after it."""
    lines, blocks = _saved_blocks(text)
    at = {}
    for after, addition in placements:
        n = max(0, min(int(after), len(blocks)))
        line = 0 if n == 0 else blocks[n - 1][1]
        at.setdefault(line, []).append(addition.strip())

    out = []
    for i, line in enumerate(lines):
        out.append(line)
        for addition in at.get(i, []):
            out.extend(["", addition])
    return "\n".join(out)


def _parse_update(text):
    """(additions, open_items) from the model's answer, each [(after, text)].

    Anything that is not the shape asked for is dropped rather than guessed
    at; an answer with no JSON in it at all is a failure."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("the model did not answer in the form asked for")
    found = json.loads(text[start:end + 1])

    def items(name):
        out = []
        for item in (found.get(name) or []):
            if not isinstance(item, dict):
                continue
            words = str(item.get("text") or "").strip()
            if not words:
                continue
            try:
                after = int(item.get("after") or 0)
            except (TypeError, ValueError):
                after = 0
            out.append((after, words))
        return out

    return items("additions"), items("open_items")


def _merge(saved_text, fresh_text, subject_name, label):
    """What the fresh section says that the saved one does not.

    Returns (additions, open_items, usage, discarded): additions and open
    items as [(after, text)] with their citations restored, and a count of
    those thrown away for carrying no citation. Raises on a reply that was
    cut off or not in the form asked for; the caller records it on a row.

    THE SAVED TEXT AND THE FRESH ONE SHARE ONE SET OF TOKENS, so a source
    cited by both reads as the same source and the model can tell a fact
    already stated from a new one by where it came from as well as by what
    it says."""
    lines, blocks = _saved_blocks(saved_text)
    tokens = {}
    numbered = []
    for n, (first, last) in enumerate(blocks, start=1):
        masked, tokens = _mask_citations("\n".join(lines[first:last + 1]),
                                         tokens)
        numbered.append("[B%d]\n%s" % (n, masked))

    _, fresh_body = _split_heading(fresh_text)
    fresh_masked, tokens = _mask_citations(
        fresh_body[:_SECTION_INPUT_CHARS], tokens)

    prompt = (
        cleanup.UPDATE_PROMPT
        + cleanup.CITATION_TOKENS
        + "\n\n--- SAVED START ---\n"
        + ("\n\n".join(numbered) or "(the saved section has no text)")
        + "\n--- SAVED END ---"
        + "\n\n--- FRESH START ---\n"
        + fresh_masked
        + "\n--- FRESH END ---"
    )

    text, usage = _invoke(prompt,
                          system=cleanup.UPDATE_PREAMBLE
                          + cleanup.subject_rule(subject_name),
                          stage="update", section=label,
                          chars_in=len(saved_text) + len(fresh_body))

    if usage.get("output_tokens", 0) >= _MAX_TOKENS:
        raise ValueError("the comparison ran past the length limit and was "
                         "cut off")

    additions, open_items = _parse_update(text)

    # A statement with no source behind it is an assertion nobody can check.
    # The model is told every one must carry a token; one that does not is
    # discarded here rather than trusted.
    discarded = 0

    def cited(items):
        nonlocal discarded
        kept = []
        for after, words in items:
            if not any(t in tokens for t in _TOKEN.findall(words)):
                discarded += 1
                continue
            kept.append((after, _restore_citations(words, tokens)[0]))
        return kept

    return cited(additions), cited(open_items), usage, discarded


def _update(event):
    """Update one saved memo. See the note above _SAVED_HEADING.

    The API has charged, written the run's progress as running, and invoked
    this asynchronously. Each changed section becomes a memo_rewrite row,
    status done, source 'update'; the run's progress object names them and
    says what was left alone.

    THE REVISION COMES IN THE EVENT. The API read the revision in use when it
    charged, and the job runs under that one (config registry spec, section
    8): a selection landing mid-run must not change the rules under a job
    already paid for.

    Never raises, for _rewrite's reason: Lambda retries an asynchronous
    invocation that raises, and the retry would spend the model again on a
    run already failed. The failure is written to the progress object.

    A FAILED RUN IS REFUNDED (UX02 20.1): it offered nothing, so the charge
    bought nothing. A run that finishes with some sections failed is done,
    not failed - it offered the rest - and is not refunded."""
    tenant_id = int(event["tenant_id"])
    memo_id = int(event["memo_id"])
    run = str(event["run"])
    revision = int(event["config_revision"])
    requested_by = event.get("requested_by") or "unknown"
    entry_id = event.get("entry_id")

    state = _get_update(tenant_id, memo_id, run) or {}
    # Finished already. A second delivery must not run the model twice.
    if state.get("status") not in (None, "running"):
        return {"status": "already-" + str(state.get("status")), "run": run}
    state.update({"status": "running", "run": run, "memo_id": memo_id,
                  "config_revision": revision})

    def finish(status, **fields):
        state.update(fields)
        state["status"] = status
        state["completed_at"] = datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if status == "failed":
            given = _refund_generation(tenant_id, entry_id, requested_by,
                                       "update: %s" % state.get("error"))
            state["refunded"] = bool(given.get("refunded"))
            state["amount_cents"] = given.get("amount_cents") or 0
        try:
            _put_update(tenant_id, memo_id, run, state)
        except Exception as exc:  # noqa: BLE001 - logged; nothing else to do
            print("[update-state-not-written] memo=%s run=%s %r" % (
                memo_id, run, exc))
        print("[update] tenant=%s memo=%s run=%s status=%s revision=%s "
              "changed=%s unchanged=%s kept=%s failed=%s" % (
                  tenant_id, memo_id, run, status, revision,
                  state.get("changed"), state.get("unchanged"),
                  len(state.get("kept") or []), state.get("failed_sections")))
        return {"status": status, "run": run}

    try:
        found = _sql(
            """
            SELECT s3_bucket, s3_key, config_revision, template_key,
                   engagement_id, workspace_id
            FROM memo WHERE tenant_id = :t AND memo_id = :m
            """,
            [_p("t", tenant_id), _p("m", memo_id)]).get("records", [])
        if not found:
            return finish("failed", error="the memorandum was not found")

        saved = _s3.get_object(Bucket=_col(found[0], 0),
                               Key=_col(found[0], 1))["Body"].read() \
                   .decode("utf-8")
        from_revision = int(_col(found[0], 2) or 1)
        template_key = event.get("template_key") or _col(found[0], 3)
        engagement_id = event.get("engagement_id") or _col(found[0], 4)
        # The memo's own workspace, from its row: the revision the API sent
        # is one of that workspace's series.
        workspace_id = config.workspace_of(tenant_id, _col(found[0], 5))
        state["from_revision"] = from_revision

        if engagement_id is None:
            return finish("failed", error="this memorandum belongs to no "
                          "engagement, so there is nothing to update it from")

        registry = config.load(tenant_id, workspace_id, revision)
        if not registry.has_template(template_key):
            return finish("failed", error="this memorandum is not in the "
                          "configuration in use")
        earlier = config.load(tenant_id, workspace_id, from_revision)

        # ONE SECTION (31 October 2026): the saved heading the person chose,
        # resolved to its key as every saved heading is below. One that
        # resolves to nothing the configuration in use writes is refused
        # before any model call, and the charge goes back.
        only = None
        chosen = str(event.get("section") or "").strip()
        if chosen:
            state["section"] = chosen
            only = _keys_by_heading(earlier, template_key).get(
                _heading_norm(chosen))
            if only is None or only not in {
                    s["key"] for s in registry.sections_for(template_key)}:
                return finish("failed", error=UPDATE_SECTION_UNKNOWN)

        values = _load_values(tenant_id, workspace_id, engagement_id)
        if not values:
            return finish("failed", error="no document filed in this "
                          "engagement has anything read from it")

        subject_name = _subject_of(tenant_id, engagement_id)

        sections, assembled, _empty, tokens_in, tokens_out = _write_sections(
            registry, template_key, values, subject_name, only=only)

        # Which saved section is which, by section_key.
        now_keys = {s["key"] for s in sections}
        was = _keys_by_heading(earlier, template_key)
        had_keys = set(was.values())
        matched, kept = {}, []
        for s in _split_saved(saved):
            key = was.get(_heading_norm(s["heading"]))
            if key is None or key in matched or key not in now_keys:
                kept.append(s["heading"])
                continue
            matched[key] = s

        fresh = {s["key"]: "\n".join(_section_lines(assembled[s["key"]]))
                 for s in sections}

        # The comparisons. Only where the fresh section says anything: one
        # that came back empty has nothing to add to what a person wrote.
        jobs = [s for s in sections
                if s["key"] in matched
                and (only is None or s["key"] == only)
                and assembled[s["key"]]["markdown"].strip()]
        # The other sections were not written this time, so nothing is said
        # about them either.
        if only:
            kept = []

        def compare(section):
            try:
                return section["key"], _merge(
                    matched[section["key"]]["text"], fresh[section["key"]],
                    subject_name, section["key"]), None
            except Exception as exc:  # noqa: BLE001 - recorded on a row
                # The row's error is shown to the person as written, so the
                # exception goes to the log and the row carries the sentence
                # (ERR-01).
                print("[update-section-error] tenant=%s memo=%s run=%s "
                      "section=%s %r" % (tenant_id, memo_id, run,
                                         section["key"], exc))
                return section["key"], None, UPDATE_SECTION_FAULT

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=_UPDATE_WORKERS) as pool:
            results = {key: (merged, error)
                       for key, merged, error in pool.map(compare, jobs)}

        # Open Items go to the memo's own Open Items section where it has
        # one; otherwise each sits in the section it came from. Not to one
        # whose own comparison failed: that section is offered as a failure,
        # and an Open Item put in it would be offered nowhere.
        # Not on an Update of one other section: Open Items is not offered
        # then, and an item sent there would be offered nowhere.
        target = ("open_items" if "open_items" in matched
                  and only in (None, "open_items")
                  and not results.get("open_items", (None, None))[1]
                  else None)
        placements = {key: [] for key in matched}
        collected = []
        usage_of = {}
        discarded = 0
        for key, (merged, error) in results.items():
            if error:
                continue
            additions, open_items, usage, dropped = merged
            usage_of[key] = usage
            discarded += dropped
            tokens_in += usage.get("input_tokens", 0)
            tokens_out += usage.get("output_tokens", 0)
            placements[key].extend(additions)
            for after, words in open_items:
                if target and key != target:
                    collected.append(cleanup.open_item(words))
                else:
                    placements[key].append((after, cleanup.open_item(words)))
        if target:
            # After the section's last block, in the order they were found.
            placements[target].extend(
                (len(_saved_blocks(matched[target]["text"])[1]), item)
                for item in collected)

        rewrite_ids, added_sections = [], []
        changed = unchanged = failed = 0
        for section in sections:
            key = section["key"]
            if only and key != only:
                continue
            if key in matched:
                heading = matched[key]["heading"]
                saved_text = matched[key]["text"]
                error = results.get(key, (None, None))[1]
                if error:
                    failed += 1
                    rewrite_ids.append(_update_row(
                        tenant_id, workspace_id, memo_id, heading,
                        requested_by, saved_text,
                        None, None, revision, error=error))
                elif placements[key]:
                    changed += 1
                    rewrite_ids.append(_update_row(
                        tenant_id, workspace_id, memo_id, heading,
                        requested_by, saved_text,
                        _insert(saved_text, placements[key]),
                        usage_of.get(key), revision))
                else:
                    unchanged += 1
            elif key not in had_keys:
                # New in the template since this memo was written: written
                # and offered whole, to go at the end.
                text = fresh[key]
                heading = text.split("\n", 1)[0].strip()
                added_sections.append(heading)
                rewrite_ids.append(_update_row(
                    tenant_id, workspace_id, memo_id, heading, requested_by,
                    "", text,
                    None, revision))
            # Otherwise the template had it when this memo was written and
            # the memo no longer does under that heading: a person removed
            # it or retyped its heading. Offering it again would put back
            # what somebody took out, so it is left alone.

        if discarded:
            print("[update-uncited-discarded] memo=%s run=%s count=%d" % (
                memo_id, run, discarded))

        return finish("done", rewrite_ids=rewrite_ids, changed=changed,
                      unchanged=unchanged, kept=kept[:50],
                      added_sections=added_sections, failed_sections=failed,
                      uncited_discarded=discarded,
                      tokens_in=tokens_in, tokens_out=tokens_out)

    except Exception as exc:  # noqa: BLE001 - written to the run, not raised
        # The run's error is shown to the person as written; the exception
        # goes to the log.
        print("[update-error] tenant=%s memo=%s run=%s %r" % (
            tenant_id, memo_id, run, exc))
        return finish("failed", error=UPDATE_FAULT)


def _update_row(tenant_id, workspace_id, memo_id, heading, requested_by,
                input_text, output_text, usage, revision, error=None):
    """One section of an Update as a memo_rewrite row, finished. Returns its
    id. Done where there is text to offer, failed where the comparison could
    not be made - the screen shows the second as it shows a failed rewrite,
    and revise accepts only the first."""
    usage = usage or {}
    created = _sql(
        """
        INSERT INTO memo_rewrite
          (tenant_id, workspace_id, memo_id, section_heading, prompt,
           prompted_by, model_id, input_text, output_text, tokens_in,
           tokens_out, status, error, completed_at, source, config_revision)
        VALUES
          (:t, :w, :m, :heading, :prompt, :who, :model, :input, :output,
           :tokens_in, :tokens_out, :status, :error, UTC_TIMESTAMP(),
           'update', :revision)
        """,
        [_p("t", tenant_id), _p("w", workspace_id), _p("m", memo_id),
         _p("heading", heading[:512]),
         _p("prompt", cleanup.UPDATE_ROW_PROMPT),
         _p("who", requested_by), _p("model", MODEL_ID),
         _p("input", input_text),
         _p("output", None if output_text is None
            else output_text.rstrip() + "\n"),
         _p("tokens_in", usage.get("input_tokens")),
         _p("tokens_out", usage.get("output_tokens")),
         _p("status", "failed" if error else "done"),
         _p("error", (error or "")[:1024] or None),
         _p("revision", revision)],
    )
    return created.get("generatedFields", [{}])[0].get("longValue")


# --- handler ---------------------------------------------------------------

def lambda_handler(event, context):
    # A section rewrite shares the model call and the citation masking with
    # generation, and nothing else. Routed first, so everything below runs
    # exactly as it did.
    if event.get("action") == "rewrite":
        return _rewrite(event)

    # Update shares generation's three stages through _write_sections, and
    # writes no memo of its own.
    if event.get("action") == "update":
        return _update(event)

    return _generate(event)


# --- a generation's run, and its money (UX02 20.1) --------------------------
#
# The API charged on the click and wrote the run as running. This writes how
# it ended, and where no memo was written, gives the charge back.
#
# NEVER RAISES, for _rewrite's reason: Lambda retries an asynchronous
# invocation that raises, and each retry ran every model call again on a run
# already failed. On 24 September one failure cost the dollar and three runs
# of Bedrock, and the event was then dropped with nothing on screen.
#
# A MEMO THAT EXISTS IS NOT REFUNDED. A failure after the memo row is written
# - recording its sources or claims - leaves a memorandum that opens, and the
# charge bought it (decided 19 October 2026).

GENERATE_FAULT = ("The memorandum could not be written because of a fault on "
                  "our side. Try it again.")
GENERATE_REFUSED = {
    "no-such-template": "This memorandum is not in the configuration in use.",
    "no-engagement-id": "The request did not name an engagement.",
    "no-values": ("No document filed in this engagement has anything read "
                  "from it, so there was nothing to write from."),
}


def _generate_key(tenant_id, engagement_id, run):
    """Where a generation's progress is kept. MIRRORED in lambda/api/app.py,
    which writes it first and reads it for the screen; the two must not
    drift."""
    return "tenants/%d/runs/generate/%d/%s.json" % (
        int(tenant_id), int(engagement_id), run)


def _generate(event):
    tenant_id = int(event["tenant_id"])
    run = event.get("run")
    engagement_id = event.get("engagement_id")
    entry_id = event.get("entry_id")
    by = event.get("generated_by")
    # Somewhere to keep the run only when the API named one. An invocation
    # made by hand, or queued before this was deployed, carries neither, and
    # runs exactly as it did.
    key = (_generate_key(tenant_id, engagement_id, run)
           if run and engagement_id is not None else None)

    state = {}
    if key:
        try:
            state = json.loads(_s3.get_object(
                Bucket=CURATED_BUCKET, Key=key)["Body"].read().decode("utf-8"))
        except (ClientError, ValueError):
            state = {}
        # Finished already. A second delivery must not run the model twice,
        # nor refund twice - though the refund's own key would refuse that.
        if state.get("status") not in (None, "running"):
            return {"status": "already-" + str(state.get("status")),
                    "run": run}
    state.update({"run": run, "engagement_id": engagement_id,
                  "entry_id": entry_id})

    def finish(status, **fields):
        state.update(fields)
        state["status"] = status
        state["completed_at"] = datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if key:
            try:
                _s3.put_object(Bucket=CURATED_BUCKET, Key=key,
                               Body=json.dumps(state).encode("utf-8"),
                               ContentType="application/json")
            except Exception as exc:  # noqa: BLE001 - logged; nothing else
                print("[generate-state-not-written] run=%s %r" % (run, exc))
        print("[generate] tenant=%s engagement=%s run=%s status=%s memo=%s "
              "refunded=%s" % (tenant_id, engagement_id, run, status,
                               state.get("memo_id"), state.get("refunded")))

    def fail(error, why):
        given = _refund_generation(tenant_id, entry_id, by, why)
        finish("failed", error=error,
               refunded=bool(given.get("refunded")),
               amount_cents=given.get("amount_cents") or 0)

    def row_written(memo_id):
        """The memo row exists. Said on the run AT ONCE, still running, so
        that if this function is then killed - a timeout recording claims -
        the failure handler finds a memo and refunds nothing (20.2). Never
        raises: the memo is written either way, and this is a record of it."""
        state["memo_id"] = memo_id
        if not key:
            return
        try:
            _s3.put_object(Bucket=CURATED_BUCKET, Key=key,
                           Body=json.dumps(dict(state, status="running"))
                           .encode("utf-8"),
                           ContentType="application/json")
        except Exception as exc:  # noqa: BLE001 - logged; nothing else
            print("[generate-state-not-written] run=%s %r" % (run, exc))

    written = {"row": False, "memo_id": None, "on_row": row_written}
    try:
        result = _compose_memo(event, written)
    except Exception as exc:  # noqa: BLE001 - written to the run, not raised
        print("[generate-error] tenant=%s engagement=%s run=%s memo=%s %r" % (
            tenant_id, engagement_id, run, written["memo_id"], exc))
        if not written["row"]:
            fail(GENERATE_FAULT, type(exc).__name__)
            return {"status": "failed", "run": run}
        # The memo is there and opens. What failed was a record about it.
        finish("done", memo_id=written["memo_id"], incomplete=True)
        return {"status": "ok", "memo_id": written["memo_id"],
                "incomplete": True}

    if result.get("status") != "ok":
        fail(GENERATE_REFUSED.get(result.get("status"), GENERATE_FAULT),
             result.get("status"))
        return result

    finish("done", memo_id=result.get("memo_id"))
    return result


def _refund_generation(tenant_id, entry_id, by, why):
    """wallet.refund_generation, never raising. A refund that throws is
    logged and reported on the run as not refunded, where somebody can see
    it - the alternative is an exception that loses the run's record too."""
    try:
        given = wallet.refund_generation(tenant_id, entry_id, by)
    except Exception as exc:  # noqa: BLE001 - reported on the run instead
        print("[refund-failed] tenant=%s entry=%s %r" % (
            tenant_id, entry_id, exc))
        return {"refunded": False, "amount_cents": 0}
    print("[generation-refunded] tenant=%s entry=%s why=%s refunded=%s "
          "repeated=%s cents=%s reason=%s" % (
              tenant_id, entry_id, why, given.get("refunded"),
              given.get("repeated"), given.get("amount_cents"),
              given.get("reason")))
    return given


def _compose_memo(event, written):
    """Generation itself: assemble, draft, consolidate, render, record.
    `written` is told the memo's id the moment its row exists, so the caller
    knows whether a failure came before or after there was a memo."""
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
    #
    # IN ONE WORKSPACE (PACK-01): the one the API resolved and charged in.
    # An event without one was queued before workspaces, by a tenant that
    # then held exactly one, and config.workspace answers that one.
    workspace_id = config.workspace(tenant_id, event.get("workspace_id"))
    revision = config.active_revision(tenant_id, workspace_id)
    registry = config.load(tenant_id, workspace_id, revision)

    # Which memorandum is being written. A tenant may hold a credit, a KYC and
    # a lender template over the same documents; the caller says which, and an
    # absent one means the tenant has only ever had the one - which is every
    # caller that predates this.
    template_key = requested_template or registry.TEMPLATE_KEY
    if not registry.has_template(template_key):
        return {"status": "no-such-template",
                "template_key": template_key,
                "available": [t["key"] for t in registry.template_list()]}

    # WHICH ENGAGEMENT, AS AN ID (13.3 stage 4). The API resolves the name in
    # the address to a row and sends the id; this function no longer derives
    # it from anything. An event without one is refused rather than guessed
    # at - it can only be an invocation made by hand, or one queued before
    # this was deployed, and quietly composing over a LIKE would be worse
    # than saying so.
    engagement_id = event.get("engagement_id")
    if engagement_id is None:
        return {"status": "no-engagement-id", "engagement": engagement}

    values = _load_values(tenant_id, workspace_id, engagement_id)
    if not values:
        return {"status": "no-values", "engagement": engagement}

    document_ids = sorted({v["document_id"] for v in values})
    generated_at = datetime.datetime.now(datetime.timezone.utc)
    tokens_in = tokens_out = 0

    # Whose memorandum this is (SUBJ-01). Read once and carried into the
    # draft, the consolidation and the front matter, so all three say the
    # same thing. None where the engagement never named one, and every
    # prompt is then exactly what it was.
    subject_name = _subject_of(tenant_id, engagement_id)

    # 1-3. Assemble, draft and consolidate.
    sections, assembled, empty_sections, used_in, used_out = _write_sections(
        registry, template_key, values, subject_name)
    tokens_in += used_in
    tokens_out += used_out

    # 4. Render. Front matter and the coverage banner are built, not written.
    #
    # THE ENTERED SUBJECT FIRST, then the counted one, then the engagement
    # name (SUBJ-01). subject_from() counts f_legal_name across the whole
    # engagement, and the same counting that put a buyer's business in
    # section II can put a buyer's name at the head of the page. It stays
    # as the fallback for every engagement that has no subject_name, and
    # front_matter falls back again to the engagement name below that.
    subject = subject_name or cleanup.subject_from(values)
    parts = [
        cleanup.front_matter(
            subject, _shown_as(tenant_id, engagement_id, engagement),
            generated_at.strftime("%d %B %Y, %H:%M UTC"),
            len(document_ids), len({v["filename"] for v in values}),
            registry.label_for_template(template_key),
        ),
        cleanup.coverage_callout(empty_sections),
    ]

    for section in sections:
        parts.extend(_section_lines(assembled[section["key"]]))

    memo_body = "\n".join(parts)
    encoded = memo_body.encode("utf-8")
    sha = hashlib.sha256(encoded).hexdigest()

    # Under its workspace (PACK-01), as its documents are: two workspaces may
    # each hold an engagement of one name, and a memo of one template written
    # in both in the same second must not land on one object. Every memo
    # written before workspaces keeps the key it has.
    memo_key = "tenants/{}/w/{}/memos/{}/{}-{}.md".format(
        tenant_id, workspace_id, engagement, template_key,
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
          (tenant_id, workspace_id, engagement_id, template_key,
           config_revision, s3_bucket, s3_key, s3_version_id, sha256,
           generated_by)
        VALUES
          (:tenant_id, :workspace_id, :engagement_id, :template_key,
           :config_revision, :s3_bucket, :s3_key, :s3_version_id, :sha256,
           :generated_by)
        """,
        [
            _p("tenant_id", tenant_id),
            _p("workspace_id", workspace_id),
            _p("engagement_id", engagement_id),
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
    # The row exists from here, whether or not its id came back with it.
    written["row"] = True
    written["memo_id"] = memo_id
    if written.get("on_row"):
        written["on_row"](memo_id)

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

    # subject_named says whether the prompts carried a subject at all, which
    # is the difference between a memo written under SUBJ-01's rule and one
    # written as they were before it. The name itself is on the memo.
    print("[composed] memo={} template={} revision={} docs={} values={} "
          "claims={} empty={} subject_named={} tokens_in={} tokens_out={}"
          .format(
              memo_id, template_key, revision, len(document_ids), len(values),
              claims, len(empty_sections), bool(subject_name),
              tokens_in, tokens_out))

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
