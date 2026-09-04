"""
app.py - the proposer.

Reads a client's OWN memorandum and proposes a configuration from it: the
sections it carries, the facts each section reports, and the documents those
facts come from. Nothing is written to the draft. The person accepts.

THE FILE IS FORM, NOT SUBSTANCE. It is a sample of a report format, not
evidence about anybody's borrower. So it is not filed, not classified, not
extracted from, not cited, and not charged. It lands in the review bucket
under a prefix nothing watches, is read once, and is deleted here.

Invoked as an event, never in a request. Reading a memorandum is one model
call per section and takes minutes; API Gateway allows 29 seconds.

    {"tenant_id": 1, "key": "tenants/1/proposals/<id>/memo.pdf",
     "requested_by": "someone@example.com"}

PROGRESS IS THE OUTPUT, NOT A SIDE EFFECT. The proposal object is rewritten
after every section, carrying how far it has got. The screen polls it and
shows the person the sections appearing one at a time. A minute of silence
with a spinner is indistinguishable from a function that has died.

ONE CALL PER SECTION. Asking for the whole memorandum at once fits in no
answer: the model stops at its token limit and the last sections simply are
not there, with nothing to say they were lost. Slower and dearer, and it does
not throw away the end of somebody's document.

MATCHING IS SHOWN, NEVER APPLIED. Where a fact the memorandum reports looks
like a field the tenant already holds, that is offered as a suggestion with
both descriptions beside it. The person decides whether it is the same fact.
Deciding for them binds a section to a field that means something else, which
renders a number that is wrong and looks right.
"""

import datetime
import json
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

import extractors

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")
_bedrock = boto3.client("bedrock-runtime")

REVIEW_BUCKET = os.environ["REVIEW_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
MODEL_ID = os.environ["MODEL_ID"]

DRAFT = 0

# What one section's text is worth reading. A section longer than this is
# padding by then - tables of counterparties, appendices - and the facts it
# reports have already been named.
_SECTION_CHARS = 24000

# What the first call sees. Enough for a long memorandum's headings, which is
# all that call is asked for.
_OUTLINE_CHARS = 60000

# The proposal is dead once accepted or abandoned. Nothing polls forever.
_MAX_SECTIONS = 40


# --- plumbing --------------------------------------------------------------

def _sql(statement, params=None):
    for _ in range(12):
        try:
            return _rds.execute_statement(
                resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                database=DATABASE, sql=statement, parameters=params or [])
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


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


class ModelUnavailable(Exception):
    """Bedrock would not take the call. Nothing to do with the file."""


# Bedrock refuses under load, and boto's own retries are spent in seconds -
# four attempts inside a blip is four ways of asking at the same moment. These
# wait, so a minute of unavailability costs a minute rather than the read.
_BUSY = ("ServiceUnavailableException", "ThrottlingException",
         "ModelTimeoutException", "InternalServerException")
_WAITS = (5, 15, 30, 60)


def _invoke(prompt, system=None):
    """Bedrock, as composition calls it. Temperature zero: the same
    memorandum read twice should propose the same configuration."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system

    last = None
    for attempt, wait in enumerate((0,) + _WAITS):
        if wait:
            time.sleep(wait)
        try:
            response = _bedrock.invoke_model(
                modelId=MODEL_ID, body=json.dumps(body))
            payload = json.loads(response["body"].read())
            text = "".join(
                b.get("text", "") for b in payload.get("content", [])
                if b.get("type") == "text"
            )
            return text.strip(), payload.get("usage", {})
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in _BUSY:
                raise
            last = code
            print("[model-busy] attempt=%d code=%s" % (attempt + 1, code))

    raise ModelUnavailable(last or "the model would not take the call")


_FENCE = re.compile(r"^```(?:json)?|```$", re.M)


def _as_json(text, fallback):
    """The model's answer, parsed. A malformed answer costs one section rather
    than the whole read - the section is reported as yielding nothing, which
    the person can see and correct, instead of the function dying at section
    nine of thirteen with nothing written."""
    cleaned = _FENCE.sub("", text or "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        return fallback
    try:
        return json.loads(cleaned[start:end + 1])
    except ValueError:
        return fallback


# --- what the tenant already holds -----------------------------------------

def _existing(tenant_id):
    """The draft's own vocabulary, not the published one.

    The person is configuring: what matters is what their draft holds, since
    that is what the proposal will be accepted into. A group's columns are
    left out - a column is not a fact anybody names in a memorandum."""
    fields = []
    result = _sql(
        "SELECT field_key, label, description, cardinality "
        "FROM config_field WHERE tenant_id = :t AND revision = :r "
        "AND (group_key IS NULL OR group_key = field_key) "
        "ORDER BY label",
        [_p("t", tenant_id), _p("r", DRAFT)])
    for r in result.get("records", []):
        fields.append({"key": _col(r, 0), "label": _col(r, 1),
                       "description": _col(r, 2) or "",
                       "cardinality": _col(r, 3) or "one"})

    types = []
    result = _sql(
        "SELECT type_key, label, description, category_key "
        "FROM config_document_type WHERE tenant_id = :t AND revision = :r "
        "ORDER BY label",
        [_p("t", tenant_id), _p("r", DRAFT)])
    for r in result.get("records", []):
        types.append({"key": _col(r, 0), "label": _col(r, 1),
                      "description": _col(r, 2) or "",
                      "category": _col(r, 3)})

    groups = []
    result = _sql(
        "SELECT category_key, label FROM config_category "
        "WHERE tenant_id = :t AND revision = :r ORDER BY sort_order",
        [_p("t", tenant_id), _p("r", DRAFT)])
    for r in result.get("records", []):
        groups.append({"key": _col(r, 0), "label": _col(r, 1)})

    return fields, types, groups


# --- the proposal object ---------------------------------------------------

def _proposal_key(key):
    return key + ".proposal.json"


def _publish(key, proposal):
    """Rewrite the proposal. Called after every section, because the screen
    reads this object to show progress."""
    _s3.put_object(
        Bucket=REVIEW_BUCKET,
        Key=_proposal_key(key),
        Body=json.dumps(proposal, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )


# --- call one: the outline -------------------------------------------------

_OUTLINE_SYSTEM = (
    "You are reading a sample report to learn its FORMAT. You are not "
    "interested in the companies, people, figures or findings it contains. "
    "Report only its structure. Answer with JSON and nothing else - no "
    "preamble, no explanation, no code fences."
)


def _outline(text, existing_types, existing_groups):
    """The memorandum's headings, and the documents it appears to draw on.

    Headings come back VERBATIM so they can be found in the text again. A
    paraphrased heading cannot be located, and the section it names is then
    read against the whole document rather than its own part of it."""
    known_types = ", ".join(
        "%s (%s)" % (t["label"], t["key"]) for t in existing_types) or "none"
    known_groups = ", ".join(
        "%s (%s)" % (g["label"], g["key"]) for g in existing_groups) or "none"

    prompt = """Below is a sample report. Report its structure.

Return JSON of this shape:

{
  "memorandum_label": "what this kind of report is called, e.g. Credit Memorandum",
  "sections": [
    {"heading": "the heading EXACTLY as it appears, including any numeral",
     "title": "the heading with any numeral removed",
     "numeral": "the numeral alone, or an empty string",
     "purpose": "one sentence on what this section establishes"}
  ],
  "document_types": [
    {"label": "a kind of source document this report draws on",
     "description": "one or two sentences telling a classifier how to \
recognise this kind of document",
     "group": "which group it belongs in",
     "existing_key": "the key of a document type below that is the same \
kind, or null"}
  ]
}

Document types this tenant already holds: %s
Groups this tenant already holds: %s

Prefer an existing group. Propose a new group only where none of them fits.
List every section, in the order they appear. Do not invent sections that are
not there.

--- SAMPLE START ---
%s
--- SAMPLE END ---""" % (known_types, known_groups, text[:_OUTLINE_CHARS])

    answer, usage = _invoke(prompt, _OUTLINE_SYSTEM)
    return _as_json(answer, {"sections": [], "document_types": []}), usage


# --- slicing ---------------------------------------------------------------

def _slice_sections(text, sections):
    """Each section's own text, found by locating its heading.

    Returns (text, located) per section. The flag reaches the screen:
    a section read against the whole document rather than its own part
    of it is one whose proposal deserves a harder look.

    A heading that cannot be found gets the whole document, truncated. That is
    worse input, not a failure: the section is still read, and the person still
    sees a proposal for it."""
    marks = []
    cursor = 0
    for section in sections:
        heading = (section.get("heading") or "").strip()
        at = text.find(heading, cursor) if heading else -1
        if at == -1 and heading:
            at = text.find(heading)
        marks.append(at)
        if at != -1:
            cursor = at + len(heading)

    out = []
    for i, section in enumerate(sections):
        start = marks[i]
        if start == -1:
            out.append((text[:_SECTION_CHARS], False))
            continue
        end = next((m for m in marks[i + 1:] if m > start), len(text))
        out.append((text[start:end][:_SECTION_CHARS], True))
    return out


# --- call two: one section's facts -----------------------------------------

_FACTS_SYSTEM = (
    "You are reading one section of a sample report to learn WHICH FACTS it "
    "reports, not what those facts say. Name the kind of fact, never its "
    "value: 'Total Assets', not '166,683,106'. Answer with JSON and nothing "
    "else - no preamble, no explanation, no code fences."
)


def _facts(section, body, existing_fields, type_labels):
    """The facts one section reports, matched against what the tenant holds.

    The match is the model's, and is offered rather than applied. Its
    confidence is not asked for: a number would invite the screen to act on
    it above some threshold, and the whole point is that the person decides."""
    known = "\n".join(
        "- %s (%s): %s" % (f["label"], f["key"], f["description"][:200])
        for f in existing_fields) or "(this tenant holds no fields yet)"

    prompt = """Below is one section of a sample report, headed "%s".

List the kinds of fact this section reports. For each, say whether it matches
a field the tenant already holds.

Return JSON of this shape:

{
  "facts": [
    {"label": "what this fact is called",
     "description": "one or two sentences telling an extractor what to look \
for in a source document",
     "shape": "one" or "table",
     "columns": ["column names, for a table only"],
     "found_in": ["labels of the document types this fact would come from"],
     "matches_existing": "the key of an existing field that is the same fact, \
or null",
     "why_match": "one short sentence on why they look like the same fact, \
or null"}
  ]
}

Fields the tenant already holds:
%s

Document types available: %s

Name at most twenty facts. A table of repeated rows - counterparties,
suppliers, policies - is one fact with shape "table", not one fact per row.

--- SECTION START ---
%s
--- SECTION END ---""" % (section.get("title") or section.get("heading"),
                          known, ", ".join(type_labels) or "none", body)

    answer, usage = _invoke(prompt, _FACTS_SYSTEM)
    return _as_json(answer, {"facts": []}), usage


# --- the handler -----------------------------------------------------------

def _read(event):
    tenant_id = int(event["tenant_id"])
    key = event["key"]
    requested_by = event.get("requested_by")

    proposal = {
        "tenant_id": tenant_id,
        "source_key": key,
        "requested_by": requested_by,
        "started_at": _now(),
        "status": "reading",
        "sections_done": 0,
        "sections_total": None,
        "memorandum_label": None,
        "document_types": [],
        "sections": [],
        "tokens_in": 0,
        "tokens_out": 0,
    }
    _publish(key, proposal)

    # 1. Read the file. The reader is the one the normalizer uses; there is no
    #    second way of getting text out of a PDF in this system.
    try:
        obj = _s3.get_object(Bucket=REVIEW_BUCKET, Key=key)
        body = obj["Body"].read()
        text, _units, method = extractors.extract(key, body)
    except extractors.UnreadableDocument as exc:
        proposal["status"] = "unreadable"
        proposal["reason"] = exc.reason
        proposal["finished_at"] = _now()
        _publish(key, proposal)
        print("[proposal-unreadable] key=%s reason=%s" % (key, exc.reason))
        return {"status": "unreadable", "reason": exc.reason}

    proposal["read_method"] = method
    proposal["status"] = "outlining"
    _publish(key, proposal)

    fields, types, groups = _existing(tenant_id)

    # 2. The outline. One call, whatever the length.
    outline, usage = _outline(text, types, groups)
    proposal["tokens_in"] += usage.get("input_tokens", 0)
    proposal["tokens_out"] += usage.get("output_tokens", 0)

    sections = (outline.get("sections") or [])[:_MAX_SECTIONS]
    proposal["memorandum_label"] = outline.get("memorandum_label")
    proposal["document_types"] = outline.get("document_types") or []
    proposal["sections_total"] = len(sections)
    proposal["status"] = "working"
    _publish(key, proposal)

    if not sections:
        proposal["status"] = "nothing-found"
        proposal["finished_at"] = _now()
        _publish(key, proposal)
        print("[proposal-empty] key=%s method=%s chars=%d" % (
            key, method, len(text)))
        return {"status": "nothing-found"}

    # Every document type the person could bind a fact to: theirs, plus the
    # ones this memorandum implies.
    type_labels = [t["label"] for t in types]
    type_labels += [t.get("label") for t in proposal["document_types"]
                    if t.get("label") and not t.get("existing_key")]

    # 3. One call per section, publishing after each so the screen can show
    #    the sections arriving.
    bodies = _slice_sections(text, sections)

    for i, section in enumerate(sections):
        body, located = bodies[i]
        found, usage = _facts(section, body, fields, type_labels)
        proposal["tokens_in"] += usage.get("input_tokens", 0)
        proposal["tokens_out"] += usage.get("output_tokens", 0)

        proposal["sections"].append({
            "heading": section.get("heading"),
            "title": section.get("title") or section.get("heading"),
            "numeral": section.get("numeral") or "",
            "purpose": section.get("purpose"),
            "located": located,
            "facts": found.get("facts") or [],
        })
        proposal["sections_done"] = i + 1
        _publish(key, proposal)

        print("[proposal-section] key=%s %d/%d title=%s facts=%d" % (
            key, i + 1, len(sections), section.get("title"),
            len(found.get("facts") or [])))

    # 4. The sample has served its purpose. It was never a document and it
    #    does not become one by having been read.
    try:
        _s3.delete_object(Bucket=REVIEW_BUCKET, Key=key)
        proposal["sample_deleted"] = True
    except ClientError as exc:
        proposal["sample_deleted"] = False
        print("[proposal-sample-kept] key=%s error=%s" % (key, exc))

    proposal["status"] = "ready"
    proposal["finished_at"] = _now()
    _publish(key, proposal)

    print("[proposal-ready] key=%s tenant=%s sections=%d types=%d "
          "tokens_in=%d tokens_out=%d by=%s" % (
              key, tenant_id, len(proposal["sections"]),
              len(proposal["document_types"]), proposal["tokens_in"],
              proposal["tokens_out"], requested_by))

    return {"status": "ready", "sections": len(proposal["sections"])}


def lambda_handler(event, context):
    """The read, with its failures written down.

    An exception escaping here leaves the proposal object saying "outlining"
    for ever, and the screen learns nothing except by giving up. So whatever
    goes wrong is recorded in the object the screen is already polling.

    AND IT IS NOT RE-RAISED. An asynchronous invocation retries twice, so an
    exception here asks a model that is already refusing two more times, five
    minutes apart, long after the person has been told it failed."""
    key = event.get("key")
    try:
        return _read(event)
    except ModelUnavailable as exc:
        _failed(key, "model-unavailable",
                "The model would not take the request. Nothing to do with "
                "your report - try again in a few minutes.", exc)
        return {"status": "failed", "reason": "model-unavailable"}
    except Exception as exc:  # noqa: BLE001 - the screen must be told
        _failed(key, "failed", "Something went wrong while reading it. "
                               "Nothing was saved.", exc)
        return {"status": "failed"}


def _failed(key, status, reason, exc):
    """Amend whatever was last published rather than writing a fresh object,
    so the sections already read are still there to look at."""
    print("[proposal-failed] key=%s status=%s %r" % (key, status, exc))
    if not key:
        return
    try:
        body = _s3.get_object(Bucket=REVIEW_BUCKET,
                              Key=_proposal_key(key))["Body"].read()
        proposal = json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001 - nothing was published yet
        proposal = {"source_key": key, "sections_done": 0,
                    "sections_total": None, "memorandum_label": None,
                    "document_types": [], "sections": []}

    proposal["status"] = status
    proposal["reason"] = reason
    proposal["finished_at"] = _now()
    try:
        _publish(key, proposal)
    except Exception as write:  # noqa: BLE001 - the log is the last resort
        print("[proposal-failed-unwritable] key=%s %r" % (key, write))
