"""
app.py - the reviewer (REV-01).

Reads a tenant's open draft and says what it would change: field descriptions,
section prompts, document type descriptions, where each fact should be sought,
and the facts a memorandum asks for that nothing supplies. The person accepts
or declines each suggestion. Nothing is written to the draft without a click.

    {"action": "open",   "tenant_id": 1, "email": "...", "role": "admin"}
    {"action": "read",   "tenant_id": 1, "session_id": "..."}      (itself)
    {"action": "poll",   "tenant_id": 1, "session_id": "..."}
    {"action": "accept", "tenant_id": 1, "email": "...", "role": "admin",
                         "session_id": "...", "suggestion_id": "s-0007",
                         "value": <optional, the person's edit>,
                         "bind_to": <optional, new_field only:
                                     {"template_key", "section_key"}>}
    {"action": "close",  "tenant_id": 1, "email": "...", "role": "admin",
                         "session_id": "..."}
    {"action": "answer", "tenant_id": 1, "email": "...", "role": "admin",
                         "session_id": "...", "suggestion_id": "s-0024",
                         "answer": "<the administrator's reply>"}
    {"action": "answer_read", "tenant_id": 1, "session_id": "...",
                         "suggestion_id": "s-0024"}            (itself)

A QUESTION IS ANSWERED, NOT ACCEPTED (REV-01 S2). The answer is recorded and
read in the background, as the review itself is: one small model call turns
the question and the reply into one concrete suggestion, "<id>-a", which then
goes through accept like any other. Answering never writes the draft and is
never charged; only an accept is.

The tenant, email and role come from the API, which reads them from the
signed token. Nothing here takes a tenant from anywhere else.

THE PROPOSER'S SHAPE. Reading takes minutes and API Gateway allows 29
seconds, so open starts the read asynchronously and returns; the screen polls
an object in the review bucket that the read rewrites as each part finishes.

THE DRAFT, AND ONLY THE DRAFT. The pipeline never reads revision 0
(config.py), so a reviewer that writes only there cannot collide with
extraction or composition. Every write goes through editor.py, the same path
every other configuration edit takes.

ONE WRITER PER OBJECT. The read owns <session>.review.json and nothing else
writes it. An accept writes <session>/accepted/<id>.json, an answer
<session>/answers/<id>.json and a close <session>/closed.json. Two acts
landing together each write their own object, so neither can overwrite the
other's record - the rule the proposer's working.json follows.

MONEY (settled 30 September 2026). $1.00 a session, charged once, on the
first accepted suggestion, keyed review:<session_id>. The order is quote,
write, charge: a write that is refused or fails never takes the dollar. A
session nobody accepts anything from costs nothing, and a read that fails
offers nothing to accept, so there is nothing to refund.
"""

import datetime
import json
import os
import re
import time
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

import editor
import registry
import wallet

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")
# As composition's, and for composition's reason. botocore defaults to a
# 60-second read timeout and legacy retries of up to 5 attempts. A memorandum's
# section prompts take Sonnet longer than a minute to answer, so on 30
# September the first live review timed out five times over five minutes on
# its second call and failed with 25 suggestions already read.
_bedrock = boto3.client(
    "bedrock-runtime",
    config=Config(read_timeout=300,
                  retries={"mode": "standard", "max_attempts": 2}),
)
_lambda = boto3.client("lambda")

REVIEW_BUCKET = os.environ["REVIEW_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
MODEL_ID = os.environ["MODEL_ID"]

EVENT = "config_review"

# Business and Enterprise (REV-01, finding 8). The set may_brand uses, read
# from the subscription where there is one rather than from tenant.plan.
REVIEW_PLANS = ("business", "enterprise")

# A suggestion from a session older than this cannot be accepted (D7).
SESSION_HOURS = 24

_MAX_TOKENS = 8192

# Per call. Enough to be useful, few enough that an answer is not cut off at
# the token limit - and if one is, the part says so.
_MAX_SUGGESTIONS = 25

_SESSION = re.compile(r"^[0-9a-f]{32}$")

# An administrator's reply to a question. Long enough for a paragraph of
# explanation; a question is not where a whole prompt is written.
_MAX_ANSWER = 2000

# The suggestion an answer produced carries its question's id and this.
_ANSWERED = "-a"

KINDS = ("field_description", "section_prompt", "document_type_description",
         "field_found_in", "new_field", "question")


class Stale(Exception):
    """The draft no longer holds what the suggestion was made against."""


class ModelUnavailable(Exception):
    """Bedrock would not take the call. Nothing to do with the draft."""


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


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _stamp(moment=None):
    return (moment or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_stamp(text):
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc)


# --- where a session lives -------------------------------------------------

def _prefix(tenant_id):
    return "tenants/%d/reviews/" % int(tenant_id)


def _session(session_id):
    """A session id is ours - 32 hex characters - and is checked before it
    goes anywhere near a storage key."""
    if not isinstance(session_id, str) or not _SESSION.match(session_id):
        raise ValueError("that is not a review session")
    return session_id


def _review_key(tenant_id, session_id):
    return _prefix(tenant_id) + session_id + ".review.json"


def _accepted_key(tenant_id, session_id, suggestion_id):
    return "%s%s/accepted/%s.json" % (_prefix(tenant_id), session_id,
                                      suggestion_id)


def _closed_key(tenant_id, session_id):
    return "%s%s/closed.json" % (_prefix(tenant_id), session_id)


def _answer_key(tenant_id, session_id, suggestion_id):
    return "%s%s/answers/%s.json" % (_prefix(tenant_id), session_id,
                                     suggestion_id)


def _put(key, body):
    _s3.put_object(
        Bucket=REVIEW_BUCKET, Key=key,
        Body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json")


def _get(key):
    """The object, or None where there is none."""
    try:
        body = _s3.get_object(Bucket=REVIEW_BUCKET, Key=key)["Body"].read()
    except ClientError:
        return None
    return json.loads(body.decode("utf-8"))


# --- who may ---------------------------------------------------------------

def _require_admin(role):
    """Configuring is an administrator's act, and this is configuring."""
    if role != "admin":
        raise PermissionError("only an administrator may review the "
                              "configuration")


def _plan_key(tenant_id):
    """The tenant's plan, as seats.seats_bought resolves it.

    subscription.plan_id IS THE PLAN (CLAUDE.md, Money). tenant.plan is read
    only where there is no subscription, which is a trial - and a trial on
    business is allowed (D4)."""
    rows = _sql(
        "SELECT p.plan_key FROM subscription s "
        "JOIN plan p ON p.plan_id = s.plan_id WHERE s.tenant_id = :t",
        [_p("t", tenant_id)]).get("records", [])
    if rows:
        return (_col(rows[0], 0) or "").strip().lower()

    rows = _sql("SELECT plan FROM tenant WHERE tenant_id = :t",
                [_p("t", tenant_id)]).get("records", [])
    plan = (_col(rows[0], 0) if rows else "base") or "base"
    return plan.strip().lower().replace(" ", "_")


def _require_plan(tenant_id):
    if _plan_key(tenant_id) not in REVIEW_PLANS:
        raise PermissionError("AI Review is available on Business and "
                              "Enterprise")


def _charged(tenant_id, session_id):
    """Whether this session has been paid for. The ledger is the record, and
    its unique key is what makes the charge happen once."""
    rows = _sql(
        "SELECT entry_id FROM wallet_ledger "
        "WHERE tenant_id = :t AND idempotency_key = :k",
        [_p("t", tenant_id), _p("k", "review:" + session_id)]
    ).get("records", [])
    return _col(rows[0], 0) if rows else None


# --- open ------------------------------------------------------------------

def open_session(tenant_id, email, role):
    """Check everything that can be checked now, then start the read.

    Refused here rather than after a minute of reading: no draft, the wrong
    plan, no price, or not enough to pay for it. Charges nothing."""
    _require_admin(role)
    _require_plan(tenant_id)
    editor.draft(tenant_id)          # "no draft is open" is raised here

    quote = wallet.quote(tenant_id, EVENT)   # Unpriced is raised here
    if not quote["affordable"]:
        raise wallet.InsufficientFunds(quote["total_cents"],
                                       quote["available_cents"],
                                       quote["purchased_only"])

    session_id = uuid.uuid4().hex
    review = {
        "tenant_id": tenant_id,
        "session_id": session_id,
        "requested_by": email,
        "opened_at": _stamp(),
        "status": "starting",
        "price_cents": quote["unit_cents"],
        "parts_done": 0,
        "parts_total": None,
        "parts": [],
        "suggestions": [],
        "tokens_in": 0,
        "tokens_out": 0,
        "model_id": MODEL_ID,
    }
    _put(_review_key(tenant_id, session_id), review)

    _lambda.invoke(
        FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({"action": "read", "tenant_id": tenant_id,
                            "session_id": session_id}))

    print("[review-opened] tenant=%s session=%s by=%s" % (
        tenant_id, session_id, email))
    return {"session_id": session_id, "status": "starting",
            "price_cents": quote["unit_cents"]}


# --- the model -------------------------------------------------------------

_BUSY = ("ServiceUnavailableException", "ThrottlingException",
         "ModelTimeoutException", "InternalServerException")
_WAITS = (5, 15, 30, 60)


def _invoke(prompt, system):
    """Bedrock, as the proposer calls it. Temperature zero: the same draft
    reviewed twice should say the same things."""
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": _MAX_TOKENS,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
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
                if b.get("type") == "text")
            return text.strip(), payload.get("usage", {}), \
                payload.get("stop_reason")
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in _BUSY:
                raise
            last = code
            print("[model-busy] attempt=%d code=%s" % (attempt + 1, code))
    raise ModelUnavailable(last or "the model would not take the call")


_FENCE = re.compile(r"^```(?:json)?|```$", re.M)


def _as_json(text):
    """The model's answer, parsed, or an empty list of suggestions. A
    malformed answer costs one part of the review, which the part records."""
    cleaned = _FENCE.sub("", text or "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        return {"suggestions": []}
    try:
        return json.loads(cleaned[start:end + 1])
    except ValueError:
        return {"suggestions": []}


_SYSTEM = (
    "You review the configuration of a due-diligence product. A configuration "
    "has document types (a classifier recognises each from its description), "
    "fields (an extractor reads each from documents, guided by its "
    "description), and memoranda made of sections (each section is written "
    "from its prompt and the fields bound to it). You suggest improvements. "
    "You never suggest deleting anything. Refer to fields, sections and "
    "document types only by the keys given. Answer with JSON and nothing "
    "else - no preamble, no explanation, no code fences."
)

_SHAPE = """Return JSON of this shape:

{
  "suggestions": [
    {"kind": one of %s,
     "target": %s,
     "proposed": %s,
     "reason": "one or two sentences on why",
     "question": "for kind question only: what you need to know, else null"}
  ]
}

Suggest at most %d changes, the ones that matter most. Suggest nothing where
the configuration is already clear. Where you cannot tell what is intended,
ask with kind "question" rather than guessing."""


def _vocabulary(fields, types, findings):
    """Whether each field can be extracted and each type recognised."""
    listing = json.dumps({
        "fields": [{"key": f["key"], "label": f["label"], "type": f["type"],
                    "is_table": f["is_group"],
                    "columns": [c["label"] for c in f["columns"]],
                    "description": f["description"] or "",
                    "found_in": f["found_in"]} for f in fields],
        "document_types": [{"key": t["key"], "label": t["label"],
                            "description": t["description"] or ""}
                           for t in types],
        "known_faults": findings,
    }, ensure_ascii=False)

    kinds = '"field_description", "document_type_description", "question"'
    return """Review these fields and document types.

For a field: is its description specific enough for an extractor to find the
value in a document and to tell it apart from similar values? For a document
type: would its description let a classifier tell it apart from the other
types listed?

%s

For field_description, target is {"field_key": ...}. For
document_type_description, target is {"type_key": ...}. proposed is the whole
new description. For question, target names what the question is about.

The known faults are already reported to the person. Do not repeat them.

--- CONFIGURATION ---
%s""" % (_SHAPE % (kinds, "see below", "the new text, or null for question",
                   _MAX_SUGGESTIONS), listing)


def _memorandum(template, sections, fields_by_key):
    """Whether each section's prompt can be written from what it reads."""
    listing = json.dumps({
        "memorandum": template["label"] or template["key"],
        "sections": [{
            "section_key": s["key"], "title": s["title"], "kind": s["kind"],
            "prompt": s["prompt"] or "",
            "reads_sections": s["context_sections"],
            "bound_fields": [{"key": k,
                              "label": fields_by_key[k]["label"],
                              "description": fields_by_key[k]["description"]
                              or ""}
                             for k in s["fields"] if k in fields_by_key],
        } for s in sections],
    }, ensure_ascii=False)

    kinds = '"section_prompt", "question"'
    return """Review the prompts of this memorandum's sections.

A section is written from its prompt and from the fields bound to it (or, for
a composed section, from the sections it reads). Does each prompt ask only for
what those can supply? Is it clear about what to say and in what order? Does
it ask for a fact no bound field holds?

%s

For section_prompt, target is {"section_key": ...} and proposed is the whole
new prompt. For question, target names the section.

--- MEMORANDUM ---
%s""" % (_SHAPE % (kinds, "see below", "the new prompt, or null for question",
                   _MAX_SUGGESTIONS), listing)


def _coverage(templates, sections, fields, types):
    """The facts the memoranda ask for that nothing supplies, and where each
    fact should be sought."""
    listing = json.dumps({
        "memoranda": [{
            "template_key": t["key"], "label": t["label"],
            "sections": [{"section_key": s["key"], "title": s["title"],
                          "prompt": s["prompt"] or "",
                          "bound_fields": s["fields"]}
                         for s in sections if s["template_key"] == t["key"]],
        } for t in templates],
        "fields": [{"key": f["key"], "label": f["label"],
                    "description": f["description"] or "",
                    "found_in": f["found_in"]} for f in fields],
        "document_types": [{"key": t["key"], "label": t["label"],
                            "description": t["description"] or ""}
                           for t in types],
    }, ensure_ascii=False)

    kinds = '"new_field", "field_found_in", "question"'
    return """Review what the memoranda need against what is extracted.

1. new_field: a fact a section's prompt asks for that no field holds. target
   is {"template_key": ..., "section_key": ...}, the section that needs it.
   proposed is {"label": ..., "description": ..., "is_table": true|false,
   "columns": [{"label": ..., "description": ...}] for a table else [],
   "found_in": [document type keys]}.
2. field_found_in: a field sought in the wrong documents, or in too few.
   target is {"field_key": ...}; proposed is the WHOLE list of document type
   keys it should be sought in, not only the ones to add.
3. question: where you cannot tell what is intended.

Use only document type keys that are listed.

%s

--- CONFIGURATION ---
%s""" % (_SHAPE % (kinds, "see below", "see below", _MAX_SUGGESTIONS),
         listing)


# --- checking what the model said ------------------------------------------

def current_value(draft, kind, target):
    """What the draft holds now for a suggestion's target, or raises KeyError
    where the target is not there. The single definition of "current", used
    when a suggestion is made and again when it is accepted."""
    if kind == "field_description":
        f = _field(draft, target["field_key"])
        return f["description"] or ""
    if kind == "field_found_in":
        return sorted(_field(draft, target["field_key"])["found_in"])
    if kind == "section_prompt":
        return _section(draft, target["template_key"],
                        target["section_key"])["prompt"] or ""
    if kind == "document_type_description":
        return _type(draft, target["type_key"])["description"] or ""
    if kind == "new_field":
        _section(draft, target["template_key"], target["section_key"])
        return None
    raise KeyError(kind)


def _field(draft, key):
    for f in draft["fields"]:
        if f["key"] == key:
            return f
    raise KeyError(key)


def _section(draft, template_key, section_key):
    for s in draft["sections"]:
        if s["template_key"] == template_key and s["key"] == section_key:
            return s
    raise KeyError(section_key)


def _type(draft, key):
    for t in draft["document_types"]:
        if t["key"] == key:
            return t
    raise KeyError(key)


def clean(draft, answer, allowed, template_key=None):
    """The model's suggestions, kept only where they can be acted on.

    THE CURRENT VALUE COMES FROM THE DRAFT, NEVER FROM THE MODEL. It is what
    an accept is checked against, so it has to be what was actually held.
    Returns (kept, dropped) - dropped is a count, recorded on the part so a
    review that lost suggestions says so."""
    type_keys = {t["key"] for t in draft["document_types"]}
    labels = {(f["label"] or "").strip().lower() for f in draft["fields"]}
    kept, dropped = [], 0

    for s in (answer.get("suggestions") or [])[:_MAX_SUGGESTIONS]:
        if not isinstance(s, dict):
            dropped += 1
            continue
        kind = s.get("kind")
        target = s.get("target")
        if kind not in allowed or not isinstance(target, dict):
            dropped += 1
            continue

        # A section is named inside one memorandum; the per-memorandum call
        # is not asked for the key, so it is supplied from the call.
        if template_key and "section_key" in target:
            target = dict(target, template_key=template_key)

        if kind == "question":
            question = (s.get("question") or "").strip()
            if not question:
                dropped += 1
                continue
            kept.append({"kind": kind, "target": target, "current": None,
                         "proposed": None, "reason": s.get("reason") or "",
                         "question": question})
            continue

        try:
            current = current_value(draft, kind, target)
        except (KeyError, TypeError):
            dropped += 1
            continue

        proposed = s.get("proposed")
        if kind in ("field_description", "section_prompt",
                    "document_type_description"):
            if not isinstance(proposed, str) or not proposed.strip() \
                    or proposed.strip() == current.strip():
                dropped += 1
                continue
            proposed = proposed.strip()
        elif kind == "field_found_in":
            if not isinstance(proposed, list) \
                    or not all(isinstance(k, str) for k in proposed) \
                    or not set(proposed) <= type_keys:
                dropped += 1
                continue
            proposed = sorted(set(proposed))
            if proposed == current or not proposed:
                dropped += 1
                continue
        elif kind == "new_field":
            proposed = _new_field(proposed, type_keys, labels)
            if proposed is None:
                dropped += 1
                continue

        kept.append({"kind": kind, "target": target, "current": current,
                     "proposed": proposed, "reason": s.get("reason") or "",
                     "question": None})
    return kept, dropped


def _new_field(proposed, type_keys, labels):
    """A proposed fact, in the shape save_field takes, or None. A label the
    draft already holds is dropped: save_field would refuse the key it mints,
    and the model has probably missed the field that exists."""
    if not isinstance(proposed, dict):
        return None
    label = (proposed.get("label") or "").strip()
    if not label or label.lower() in labels:
        return None
    found_in = proposed.get("found_in") or []
    if not isinstance(found_in, list) or not set(found_in) <= type_keys:
        return None
    table = bool(proposed.get("is_table"))
    columns = []
    if table:
        for c in proposed.get("columns") or []:
            if isinstance(c, dict) and (c.get("label") or "").strip():
                columns.append({"label": c["label"].strip(),
                                "description": c.get("description") or ""})
        if not columns:
            return None   # a table with no columns will not publish
    return {"label": label,
            "description": (proposed.get("description") or "").strip(),
            "is_table": table, "columns": columns,
            "found_in": sorted(set(found_in))}


# --- read ------------------------------------------------------------------

def _read(tenant_id, session_id):
    key = _review_key(tenant_id, session_id)
    review = _get(key)
    if review is None:
        raise ValueError("no such review")

    draft = editor.draft(tenant_id)
    report = registry.validate(tenant_id, registry.DRAFT)
    findings = [f["detail"] for f in report["fatal"] + report["warnings"]]

    fields = draft["fields"]
    fields_by_key = {f["key"]: f for f in fields}

    # The parts, in the order the screen shows them.
    parts = [("vocabulary", _vocabulary(fields, draft["document_types"],
                                        findings),
              ("field_description", "document_type_description",
               "question"), None)]
    for t in draft["templates"]:
        sections = [s for s in draft["sections"]
                    if s["template_key"] == t["key"]]
        if sections:
            parts.append(("memorandum:" + t["key"],
                          _memorandum(t, sections, fields_by_key),
                          ("section_prompt", "question"), t["key"]))
    parts.append(("coverage", _coverage(draft["templates"], draft["sections"],
                                        fields, draft["document_types"]),
                  ("new_field", "field_found_in", "question"), None))

    review["status"] = "reading"
    review["parts_total"] = len(parts)
    review["validation"] = {"fatal": len(report["fatal"]),
                            "warnings": len(report["warnings"])}
    _put(key, review)

    for name, prompt, allowed, template_key in parts:
        text, usage, stop = _invoke(prompt, _SYSTEM)
        review["tokens_in"] += usage.get("input_tokens", 0)
        review["tokens_out"] += usage.get("output_tokens", 0)

        kept, dropped = clean(draft, _as_json(text), allowed, template_key)
        for s in kept:
            s["id"] = "s-%04d" % (len(review["suggestions"]) + 1)
            review["suggestions"].append(s)

        # A reply that used every token was cut off, and a list missing its
        # end reads as finished. Said here so the screen can say it.
        review["parts"].append({"name": name, "suggestions": len(kept),
                                "dropped": dropped,
                                "cut_off": stop == "max_tokens"})
        review["parts_done"] += 1
        _put(key, review)

        print("[review-part] tenant=%s session=%s part=%s kept=%d dropped=%d "
              "stop=%s" % (tenant_id, session_id, name, len(kept), dropped,
                           stop))

    review["status"] = "ready"
    review["finished_at"] = _stamp()
    _put(key, review)

    print("[review-ready] tenant=%s session=%s suggestions=%d tokens_in=%d "
          "tokens_out=%d" % (tenant_id, session_id, len(review["suggestions"]),
                             review["tokens_in"], review["tokens_out"]))
    return {"status": "ready"}


def _read_safely(tenant_id, session_id):
    """The read, with its failures written into the object the screen polls.

    NOT RE-RAISED. An asynchronous invocation retries twice, which would ask a
    model that is refusing two more times after the person has been told it
    failed (the proposer's rule)."""
    try:
        return _read(tenant_id, session_id)
    except ModelUnavailable as exc:
        _failed(tenant_id, session_id, "model-unavailable",
                "The model would not take the request. Nothing to do with "
                "your configuration - try again in a few minutes.", exc)
    except Exception as exc:  # noqa: BLE001 - the screen must be told
        _failed(tenant_id, session_id, "failed",
                "Something went wrong while reviewing. Nothing was changed "
                "and nothing was charged.", exc)
    return {"status": "failed"}


def _failed(tenant_id, session_id, status, reason, exc):
    """Amend what was last written, so the parts already read are kept."""
    print("[review-failed] tenant=%s session=%s status=%s %r" % (
        tenant_id, session_id, status, exc))
    key = _review_key(tenant_id, session_id)
    try:
        review = _get(key) or {"session_id": session_id, "suggestions": []}
        review["status"] = status
        review["reason"] = reason
        review["finished_at"] = _stamp()
        _put(key, review)
    except Exception as write:  # noqa: BLE001 - the log is the last resort
        print("[review-failed-unwritable] session=%s %r" % (session_id, write))


# --- poll ------------------------------------------------------------------

def _records(tenant_id, session_id, kind):
    """Every record of one kind in a session - accepted or answers - keyed by
    the suggestion it is about."""
    found = {}
    prefix = "%s%s/%s/" % (_prefix(tenant_id), session_id, kind)
    token = None
    while True:
        args = {"Bucket": REVIEW_BUCKET, "Prefix": prefix}
        if token:
            args["ContinuationToken"] = token
        page = _s3.list_objects_v2(**args)
        for obj in page.get("Contents", []):
            record = _get(obj["Key"])
            if record:
                found[record["suggestion_id"]] = record
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    return found


def poll(tenant_id, session_id):
    """The review, with what has been accepted, what has been answered and
    whether it is closed.

    A question's answer travels on the question, and the suggestion it
    produced follows it in the list, so the screen shows the two together."""
    review = _get(_review_key(tenant_id, session_id))
    if review is None:
        raise ValueError("no such review")

    outcomes = _records(tenant_id, session_id, "accepted")
    answers = _records(tenant_id, session_id, "answers")

    listed = []
    for s in review.get("suggestions", []):
        listed.append(s)
        answered = answers.get(s["id"])
        if s.get("kind") != "question" or not answered:
            continue
        s["answer"] = {k: answered.get(k) for k in (
            "status", "answer", "by", "at", "reason")}
        if answered.get("status") == "ready" and answered.get("suggestion"):
            listed.append(answered["suggestion"])

    for s in listed:
        outcome = outcomes.get(s["id"])
        s["status"] = outcome["status"] if outcome else "open"
        # What was actually written, which is the person's edit where they
        # made one. Without it the screen could show only the suggestion as
        # it came, and an edited accept read as though the edit was lost.
        if outcome and outcome.get("status") == "accepted" \
                and "value" in outcome:
            s["written"] = outcome["value"]
    review["suggestions"] = listed

    closed = _get(_closed_key(tenant_id, session_id))
    review["closed"] = bool(closed)
    review["expired"] = _expired(review)
    return review


def _expired(review):
    opened = review.get("opened_at")
    if not opened:
        return True
    return _now() - _parse_stamp(opened) > datetime.timedelta(
        hours=SESSION_HOURS)


# --- accept ----------------------------------------------------------------

def accept(tenant_id, email, role, session_id, suggestion_id, value=None,
           bind_to=None):
    """Write one suggestion into the draft, and pay for the session if this
    is its first.

    QUOTE, WRITE, CHARGE (D3). The charge and the write cannot share a
    transaction - wallet.charge opens its own and editor.py uses none - so the
    order decides what a failure costs. Writing first means a refused or
    failed write never takes the dollar. The price of that order is a narrow
    race: the write lands and the charge then finds the balance gone. That is
    one free session, logged, and nothing is undone."""
    _require_admin(role)
    _require_plan(tenant_id)
    review = _usable(tenant_id, session_id)

    suggestion = _find(tenant_id, session_id, review, suggestion_id)
    if suggestion is None:
        raise ValueError("no such suggestion")
    if suggestion["kind"] == "question":
        raise ValueError("a question has nothing to accept. Answer it, and "
                         "accept the change the answer produces.")

    done = _get(_accepted_key(tenant_id, session_id, suggestion_id))
    if done and done.get("status") == "accepted":
        return dict(done, repeated=True)

    draft = editor.draft(tenant_id)

    # STALE IS REFUSED, NOT OVERWRITTEN. Another administrator's edit since
    # the review read the draft is never undone by a suggestion made before
    # it.
    try:
        now = current_value(draft, suggestion["kind"], suggestion["target"])
    except KeyError:
        now = KeyError
    if now != suggestion["current"]:
        # A double click: the first accept wrote the draft, so this one reads
        # it as changed. Its record wins over a stale one.
        done = _get(_accepted_key(tenant_id, session_id, suggestion_id))
        if done and done.get("status") == "accepted":
            return dict(done, repeated=True)
        _put(_accepted_key(tenant_id, session_id, suggestion_id), {
            "suggestion_id": suggestion_id, "status": "stale",
            "at": _stamp(), "by": email})
        raise Stale("this has changed since the review read it, so the "
                    "suggestion no longer applies")

    proposed = _value(suggestion, value, draft)

    # The price, before anything is written - unless this session is already
    # paid for, in which case the balance no longer matters to it.
    entry_id = _charged(tenant_id, session_id)
    if entry_id is None:
        quote = wallet.quote(tenant_id, EVENT)
        if not quote["affordable"]:
            raise wallet.InsufficientFunds(quote["total_cents"],
                                           quote["available_cents"],
                                           quote["purchased_only"])

    written = _write(tenant_id, draft, suggestion, proposed, bind_to)

    charge = None
    if entry_id is None:
        try:
            charge = wallet.charge(
                tenant_id, email, EVENT, 1,
                reference="AI review " + session_id,
                idempotency_key="review:" + session_id)
            entry_id = charge["entry_id"]
        except wallet.InsufficientFunds as exc:
            print("[review-charge-lost] tenant=%s session=%s needed=%s "
                  "available=%s" % (tenant_id, session_id, exc.needed_cents,
                                    exc.available_cents))

    outcome = {"suggestion_id": suggestion_id, "status": "accepted",
               "at": _stamp(), "by": email, "written": written,
               "value": proposed, "entry_id": entry_id,
               "charged_cents": charge["amount_cents"]
               if charge and not charge.get("repeated") else 0}
    _put(_accepted_key(tenant_id, session_id, suggestion_id), outcome)

    print("[review-accepted] tenant=%s session=%s suggestion=%s kind=%s "
          "entry=%s by=%s" % (tenant_id, session_id, suggestion_id,
                              suggestion["kind"], entry_id, email))
    return outcome


def _usable(tenant_id, session_id):
    """The review, where it may still be acted on: read to the end, not
    closed, and not older than a day (D7)."""
    review = _get(_review_key(tenant_id, session_id))
    if review is None:
        raise ValueError("no such review")
    if review.get("status") != "ready":
        raise ValueError("this review has not finished reading")
    if _get(_closed_key(tenant_id, session_id)):
        raise ValueError("this review is closed. Open a new one.")
    if _expired(review):
        raise ValueError("this review is more than %d hours old. Open a new "
                         "one." % SESSION_HOURS)
    return review


def _question(review, suggestion_id):
    """A question in the review, by its id, or None."""
    return next((s for s in review.get("suggestions", [])
                 if s.get("id") == suggestion_id
                 and s.get("kind") == "question"), None)


def _find(tenant_id, session_id, review, suggestion_id):
    """A suggestion the read made, or one an answer made, or None.

    An answer's suggestion is found through its question, so an id from the
    request reaches a storage key only once the question it names exists."""
    found = next((s for s in review.get("suggestions", [])
                  if s.get("id") == suggestion_id), None)
    if found is not None:
        return found
    if not isinstance(suggestion_id, str) \
            or not suggestion_id.endswith(_ANSWERED):
        return None
    asked = suggestion_id[:-len(_ANSWERED)]
    if _question(review, asked) is None:
        return None
    record = _get(_answer_key(tenant_id, session_id, asked)) or {}
    if record.get("status") != "ready":
        return None
    made = record.get("suggestion")
    return made if made and made.get("id") == suggestion_id else None


def _value(suggestion, value, draft):
    """What will be written: the suggestion, or the person's edit of it in the
    same shape. The edit replaces the value and nothing else - the target
    always comes from the stored suggestion, never from the request."""
    kind = suggestion["kind"]
    if value is None:
        return suggestion["proposed"]

    if kind in ("field_description", "section_prompt",
                "document_type_description"):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("say what it should read")
        return value.strip()

    type_keys = {t["key"] for t in draft["document_types"]}
    if kind == "field_found_in":
        if not isinstance(value, list) or not value \
                or not set(value) <= type_keys:
            raise ValueError("choose document types this workspace holds")
        return sorted(set(value))

    if kind == "new_field":
        labels = {(f["label"] or "").strip().lower() for f in draft["fields"]}
        cleaned = _new_field(value, type_keys, labels)
        if cleaned is None:
            raise ValueError("a new fact needs a name nothing else has, and "
                             "a table needs at least one column")
        return cleaned

    raise ValueError("nothing to write")


def _write(tenant_id, draft, suggestion, proposed, bind_to):
    """One suggestion, through editor.py.

    WHOLE OBJECTS. No editor save is partial: save_field, save_section and
    save_document_type each overwrite what the body omits with a default
    (REV-01, finding 3). So each is read from the draft and sent back whole,
    with one value changed. Sent alone, a description would reset the rest."""
    kind, target = suggestion["kind"], suggestion["target"]

    if kind == "field_description":
        f = _field(draft, target["field_key"])
        editor.save_field(tenant_id, {
            "key": f["key"], "label": f["label"], "type": f["type"],
            "cardinality": f["cardinality"], "description": proposed,
            "columns": [{"key": c["key"], "label": c["label"],
                         "type": c["type"], "description": c["description"]}
                        for c in f["columns"]],
        })
        return {"field": f["key"]}

    if kind == "section_prompt":
        s = _section(draft, target["template_key"], target["section_key"])
        # context_sections and sort_order are left out, and the section keeps
        # both (editor.save_section).
        editor.save_section(tenant_id, {
            "key": s["key"], "template_key": s["template_key"],
            "numeral": s["numeral"], "title": s["title"], "kind": s["kind"],
            "prompt": proposed,
        })
        return {"template_key": s["template_key"], "section": s["key"]}

    if kind == "document_type_description":
        t = _type(draft, target["type_key"])
        editor.save_document_type(tenant_id, {
            "key": t["key"], "label": t["label"], "category": t["category"],
            "description": proposed, "read_mode": t["read_mode"],
            "always_ocr": t["always_ocr"],
        })
        return {"type": t["key"]}

    if kind == "field_found_in":
        editor.set_field_documents(tenant_id, target["field_key"], proposed)
        return {"field": target["field_key"], "found_in": proposed}

    if kind == "new_field":
        return _write_new_field(tenant_id, draft, target, proposed, bind_to)

    raise ValueError("nothing to write")


def _write_new_field(tenant_id, draft, target, proposed, bind_to):
    """A create, so no key is sent: save_field mints one and refuses a taken
    one. Then where it is found, and - where asked (D5) - the section that
    renders it, with that section's existing fields kept in their order."""
    created = editor.save_field(tenant_id, {
        "label": proposed["label"],
        "type": "text",
        "cardinality": "group" if proposed["is_table"] else "one",
        "description": proposed["description"],
        "columns": [{"label": c["label"], "type": "text",
                     "description": c["description"]}
                    for c in proposed["columns"]],
    })
    key = created["key"]
    if proposed["found_in"]:
        editor.set_field_documents(tenant_id, key, proposed["found_in"])

    bound = None
    if bind_to:
        if not isinstance(bind_to, dict):
            raise ValueError("say which section should render it")
        s = _section(draft, bind_to.get("template_key"),
                     bind_to.get("section_key"))
        editor.set_section_fields(tenant_id, s["template_key"], s["key"],
                                  list(s["fields"]) + [key])
        bound = {"template_key": s["template_key"], "section": s["key"]}

    return {"field": key, "found_in": proposed["found_in"], "bound": bound}


# --- answer ----------------------------------------------------------------

def answer(tenant_id, email, role, session_id, suggestion_id, text):
    """Record an administrator's reply to a question, and start turning it
    into a change (REV-01 S2).

    Returns at once: the conversion is a model call, which can outlast the
    gateway's 29 seconds, so it runs in the background and the screen polls,
    as it does for the read. Nothing is written to the draft and nothing is
    charged. The suggestion it produces is accepted - or not - like any other,
    and that accept is the session's charge if it is the first."""
    _require_admin(role)
    _require_plan(tenant_id)
    review = _usable(tenant_id, session_id)

    if _question(review, suggestion_id) is None:
        raise ValueError("only a question in this review can be answered")
    text = text.strip() if isinstance(text, str) else ""
    if not text:
        raise ValueError("write an answer first")
    if len(text) > _MAX_ANSWER:
        raise ValueError("an answer is at most %d characters" % _MAX_ANSWER)

    key = _answer_key(tenant_id, session_id, suggestion_id)
    held = _get(key) or {}
    # Once a change has been made from an answer, or is being made, that is
    # the answer. One that came to nothing or failed may be answered again.
    if held.get("status") in ("answering", "ready"):
        raise ValueError("this question has already been answered")

    _put(key, {"suggestion_id": suggestion_id, "status": "answering",
               "answer": text, "by": email, "at": _stamp()})
    _lambda.invoke(
        FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({"action": "answer_read", "tenant_id": tenant_id,
                            "session_id": session_id,
                            "suggestion_id": suggestion_id}))

    print("[review-answered] tenant=%s session=%s question=%s by=%s" % (
        tenant_id, session_id, suggestion_id, email))
    return {"suggestion_id": suggestion_id, "status": "answering"}


def _answering(draft, question, text):
    """The prompt that turns a question and its answer into one change.

    It carries what the question is about and the whole vocabulary by key,
    because the change may be a new fact, or a fact sought in other documents,
    as well as new wording."""
    target = question.get("target") or {}
    about = {}
    try:
        if "field_key" in target:
            f = _field(draft, target["field_key"])
            about["field"] = {"key": f["key"], "label": f["label"],
                              "description": f["description"] or "",
                              "found_in": f["found_in"]}
        if "type_key" in target:
            t = _type(draft, target["type_key"])
            about["document_type"] = {"key": t["key"], "label": t["label"],
                                      "description": t["description"] or ""}
        if "section_key" in target and "template_key" in target:
            s = _section(draft, target["template_key"], target["section_key"])
            about["section"] = {"template_key": s["template_key"],
                                "section_key": s["key"], "title": s["title"],
                                "prompt": s["prompt"] or "",
                                "bound_fields": s["fields"]}
    except KeyError:
        pass   # what it was about has gone; the vocabulary below still holds

    listing = json.dumps({
        "about": about,
        "fields": [{"key": f["key"], "label": f["label"]}
                   for f in draft["fields"]],
        "document_types": [{"key": t["key"], "label": t["label"]}
                           for t in draft["document_types"]],
    }, ensure_ascii=False)

    kinds = ('"field_description", "section_prompt", '
             '"document_type_description", "field_found_in", "new_field"')
    return """You asked a question about this configuration and the person who
configures it has answered. Turn the answer into exactly ONE concrete change.

Your question: %s
Why you asked: %s
Their answer: %s

Targets and proposed values take the same shapes as before:
- field_description:          {"field_key": ...}; proposed is the whole new description
- document_type_description:  {"type_key": ...}; proposed is the whole new description
- section_prompt:             {"template_key": ..., "section_key": ...}; proposed is the whole new prompt
- field_found_in:             {"field_key": ...}; proposed is the WHOLE list of document type keys
- new_field:                  {"template_key": ..., "section_key": ...}; proposed is
  {"label", "description", "is_table", "columns": [{"label", "description"}], "found_in"}

Where the answer means nothing should change, return no suggestions.

%s

--- CONFIGURATION ---
%s""" % (question.get("question") or "", question.get("reason") or "", text,
         _SHAPE % (kinds, "see above", "see above", 1), listing)


def _answer_read(tenant_id, session_id, suggestion_id):
    key = _answer_key(tenant_id, session_id, suggestion_id)
    record = _get(key)
    if not record or record.get("status") != "answering":
        return {"status": "nothing to do"}
    review = _get(_review_key(tenant_id, session_id)) or {}
    question = _question(review, suggestion_id)
    if question is None:
        raise ValueError("the question has gone")

    draft = editor.draft(tenant_id)
    text, usage, stop = _invoke(_answering(draft, question, record["answer"]),
                                _SYSTEM)
    allowed = tuple(k for k in KINDS if k != "question")
    kept, dropped = clean(draft, _as_json(text), allowed,
                          (question.get("target") or {}).get("template_key"))

    record.update(tokens_in=usage.get("input_tokens", 0),
                  tokens_out=usage.get("output_tokens", 0),
                  finished_at=_stamp())
    if kept:
        made = kept[0]
        made["id"] = suggestion_id + _ANSWERED
        made["from_question"] = suggestion_id
        record.update(status="ready", suggestion=made)
    else:
        record.update(status="no_change",
                      reason="The answer did not lead to a change that can be "
                             "written. Answer again, or make the change "
                             "yourself.")
    _put(key, record)

    print("[review-answer-read] tenant=%s session=%s question=%s status=%s "
          "dropped=%d stop=%s" % (tenant_id, session_id, suggestion_id,
                                  record["status"], dropped, stop))
    return {"status": record["status"]}


def _answer_read_safely(tenant_id, session_id, suggestion_id):
    """The conversion, with its failure written where the screen polls. Not
    re-raised, for the read's reason: an asynchronous retry asks a refusing
    model twice more after the person has been told."""
    try:
        return _answer_read(tenant_id, session_id, suggestion_id)
    except Exception as exc:  # noqa: BLE001 - the screen must be told
        print("[review-answer-failed] tenant=%s session=%s question=%s %r" % (
            tenant_id, session_id, suggestion_id, exc))
        key = _answer_key(tenant_id, session_id, suggestion_id)
        try:
            record = _get(key) or {"suggestion_id": suggestion_id}
            record.update(status="failed", finished_at=_stamp(),
                          reason="That answer could not be turned into a "
                                 "change just now. Try answering again.")
            _put(key, record)
        except Exception as write:  # noqa: BLE001 - the log is the last resort
            print("[review-answer-unwritable] %r" % write)
    return {"status": "failed"}


# --- close -----------------------------------------------------------------

def close(tenant_id, email, role, session_id):
    """End the session. Nothing more can be accepted from it; a new one is a
    new read and a new price."""
    _require_admin(role)
    if _get(_review_key(tenant_id, session_id)) is None:
        raise ValueError("no such review")
    _put(_closed_key(tenant_id, session_id),
         {"closed_at": _stamp(), "closed_by": email})
    return {"session_id": session_id, "closed": True}


# --- the handler -----------------------------------------------------------

def _reply(status, body):
    return {"status": status, "body": body}


def lambda_handler(event, context):
    """One function, five acts. read is asynchronous and invoked by open;
    the other four are invoked by the API and answered at once.

    Every answer to the API is {"status": <http status>, "body": {...}}, so
    the API relays it rather than interpreting it."""
    action = event.get("action")
    tenant_id = int(event["tenant_id"])

    if action == "read":
        return _read_safely(tenant_id, _session(event.get("session_id")))
    if action == "answer_read":
        return _answer_read_safely(tenant_id, _session(event.get("session_id")),
                                   str(event.get("suggestion_id") or ""))

    try:
        if action == "open":
            return _reply(202, open_session(tenant_id, event.get("email"),
                                            event.get("role")))

        session_id = _session(event.get("session_id"))

        if action == "poll":
            return _reply(200, poll(tenant_id, session_id))
        if action == "accept":
            return _reply(200, accept(
                tenant_id, event.get("email"), event.get("role"), session_id,
                event.get("suggestion_id"), event.get("value"),
                event.get("bind_to")))
        if action == "close":
            return _reply(200, close(tenant_id, event.get("email"),
                                     event.get("role"), session_id))
        if action == "answer":
            return _reply(202, answer(
                tenant_id, event.get("email"), event.get("role"), session_id,
                event.get("suggestion_id"), event.get("answer")))
        return _reply(400, {"error": "unknown action"})

    except wallet.InsufficientFunds as exc:
        return _reply(402, {
            "error": ("Payment has failed or the subscription has ended, so "
                      "only purchased credit can be spent, and there is not "
                      "enough." if exc.purchased_only
                      else "Not enough balance. Top up to continue."),
            "needed_cents": exc.needed_cents,
            "available_cents": exc.available_cents,
            "purchased_only": exc.purchased_only,
        })
    except wallet.Unpriced as exc:
        return _reply(409, {
            "error": "That is not priced yet, so it cannot be charged for.",
            "event_type": str(exc)})
    except Stale as exc:
        return _reply(409, {"error": str(exc), "stale": True})
    except PermissionError as exc:
        return _reply(403, {"error": str(exc)})
    except ValueError as exc:
        return _reply(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - never leak internals
        print("[review-error] action=%s tenant=%s %r" % (
            action, tenant_id, exc))
        return _reply(500, {"error": "internal error"})
