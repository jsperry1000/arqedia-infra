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
  POST /engagements                      open one by name, creating its row
  PUT  /engagements/{id}/state           archive it, or bring it back
  GET  /engagements/{id}/pending         analysed, awaiting confirmation
  POST /engagements/{id}/file            confirm types and file

An engagement names the company its memoranda are about. Nothing in it is
extracted until it does, because extraction reads a document for the
SUBJECT's facts and cannot tell which company that is unless it is told.
  PUT  /engagements/{id}/subject         set it, or change it
  GET  /engagements/{id}/documents       filed documents
  POST /documents/{document_id}/active   include or exclude from future memos
  DELETE /documents/{document_id}         discard one not yet filed
  PUT  /documents/{document_id}/type     the type chosen while it waits

One uploaded file may hold several documents. Each is a row of its own
sharing the file's s3_key and carrying its page range, so a citation still
names the file a reader was given. See db/migrations/011_document_parts.sql.
  GET  /documents/{document_id}/values   what was extracted, and what was not
  GET  /documents/{document_id}/passage  the text of one page, for a citation
  GET  /engagements/{id}/memos           memos generated for it
  POST /engagements/{id}/generate        compose a memo (deliberate act)
  GET  /templates                        the memoranda this tenant can write

Editing a section names the memorandum it belongs to, in the path. Two
memoranda may each carry a section called "summary".
  GET  /memos/{memo_id}                  a memo, its PDF link and its sources
  PUT  /memos/{memo_id}/state            archive the revision line, or restore it

A section of a memo may be rewritten by the model at a person's prompt. The
rewrite is recorded, and nothing changes until it is saved as a revision.
  POST /memos/{memo_id}/rewrites         start rewriting sections
  GET  /memos/{memo_id}/rewrites         how they are going, and what came back

A saved memo may be updated: every section written again from the
configuration in use and the documents now filed, and what is new set beside
the saved text, as a rewrite is. Charged as a generation.
  POST /memos/{memo_id}/update           start one
  GET  /memos/{memo_id}/update           how it is going (?run=)

A person's unsaved work on a memo is kept here, so leaving does not lose it.
  GET  /memos/{memo_id}/working          what they had not yet saved
  PUT  /memos/{memo_id}/working          keep it, or clear it
  POST /uploads                          a signed link to upload one file
  GET  /document-types                   the type list, for the dropdown

A client may configure from a memorandum of his own. The sample is read for
its shape and deleted; it is never filed, classified, extracted from or
charged for.
  POST /config/draft/sample              a signed link to upload one sample
  POST /config/draft/propose             read it, and propose a configuration
  GET  /config/draft/proposal            what it has proposed so far
  GET  /config/draft/proposals           proposals read and not yet accepted
  GET  /config/draft/working             what has been decided about one
  PUT  /config/draft/working             keep what has been decided
  PUT  /config/active                    which published revision is in use

AI Review of the draft (REV-01). Each is relayed to the reviewer, which holds
the checks and the money; this adds only the administrator gate.
  POST /config/draft/review              open a session, and start the read
  GET  /config/draft/review              the session so far (?session=)
  POST /config/draft/review/accept       write one suggestion into the draft
  POST /config/draft/review/close        end the session
  POST /config/draft/review/answer       answer a question it asked (S2)

The catalogue, in the ARQEDIA workspace and nowhere else.
  GET  /config/offer                     the revision and memoranda on offer
  PUT  /config/offer                     set them, all at once

Paying for a plan. Nothing here grants money; Paddle's webhooks do.
  GET  /billing/subscription             standing, plan, periods, plan rows
  POST /billing/checkout                 a Paddle transaction to open
  POST /billing/plan                     upgrade or downgrade
  POST /billing/payment-method           a Paddle transaction to change it
  POST /billing/resume                   resume a paused subscription
  GET  /billing/invoices                 from Paddle, a page at a time; or
                                         ?pdf=<transaction> for one's PDF
  POST /wallet/top-up                    buy $5 increments on the stored card

Deleting a workspace (PACK-02 D, workspaces.py): hidden for six months, then
removed; restorable until then. Administrators only, never the ARQEDIA
workspace's offerings.
  GET  /workspaces                       each, with what it holds; the deleted
  POST /workspaces/{workspace_id}/delete/code   email the administrator a code
  POST /workspaces/{workspace_id}/delete        the name, the code, and where
                                                its only members move
  POST /workspaces/{workspace_id}/restore       bring it back

A suggestion, from the rail's We want your suggestions. Any seat.
  POST /suggestions                      email it to us, and thank the sender

Sharing a memorandum with somebody outside the workspace (share.py). The
recipient's half is the share-viewer function, not this one.

WHICH WORKSPACE (PACK-01). A tenant's configuration is held in workspaces,
each with its own draft and revisions. Every route that reads or writes
configuration - uploads, filing, generating, the editors, publishing - takes
?workspace=<id> in the query string, and resolves it through
config.workspace: one of this tenant's, or, where none is named, the tenant's
only workspace, refused where it holds several. A query parameter rather than
a body field so that GET and POST carry it the same way, and rather than a
header so that no gateway CORS rule has to change. Rows already stored - a
document, a memo - carry their own workspace and are read in it.
  GET  /memos                            every live memo, for Share a memo
  GET  /shares                           what has been sent, and the allowance
  POST /memos/{memo_id}/shares           send one, or send it again
  POST /shares/{grant_id}/revoke         end future access
  POST /shares/notify                    one email for a batch just sent
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

import billing
import config
import editor
import mail
import paddle_api
import registry
import seats
import textract
import wallet
import workspaces

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
PROPOSER_FUNCTION = os.environ["PROPOSER_FUNCTION"]
REVIEWER_FUNCTION = os.environ["REVIEWER_FUNCTION"]
# Where an invitation link sends somebody. Configured rather than built from
# the request: the request arrives at the API's own hostname, and the person
# has to land on the application.
APP_URL = os.environ.get("APP_URL", "https://app.arqedia.com")


def _clean(name):
    """Make a name safe for a storage key while keeping it recognisable.

    Real documents are called things like "KCCA Trade Licence 2026.pdf".
    Rejecting them was a rule written for a machine rather than a person:
    whitespace becomes a dash, anything else unsafe is dropped."""
    name = re.sub(r"\s+", "-", (name or "").strip())
    name = re.sub(r"[^A-Za-z0-9._-]", "", name)
    name = re.sub(r"-{2,}", "-", name).strip("-.")
    return name[:120]


def _sql(statement, params=None, tx=None):
    """Data API call, retrying while the cluster wakes from zero capacity.

    `tx` runs the statement inside a transaction begun by the caller. Written
    the same way as wallet._sql, because the two do the same job and a second
    shape for it is a second thing to get right."""
    kwargs = dict(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                  database=DATABASE, sql=statement, parameters=params or [])
    if tx:
        kwargs["transactionId"] = tx
    for _ in range(12):
        try:
            return _rds.execute_statement(**kwargs)
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
    # attributes, so a user cannot promote themselves. Members exist now: an
    # invitation names the role, and the token carries it from that moment.
    #
    # A role changed after somebody signed in does not take effect until their
    # token refreshes. That is a property of tokens rather than a defect, and
    # it is why demotion is not a security control - removing the seat is.
    role = claims.get("custom:role") or "member"
    return int(raw), email, role


def _key(body, kind, engagement):
    """The idempotency key for a charge.

    The client should send one, and the screens will. Where it did not, a key
    is derived from what is being done so that an immediate retry is still
    refused as a repeat. It changes every minute, which is long enough to
    cover a double click and a stalled request and short enough that a
    genuine second filing an hour later is not mistaken for one.
    """
    given = (body or {}).get("idempotency_key")
    if given:
        return str(given)[:64]
    minute = datetime.datetime.utcnow().strftime("%Y%m%d%H%M")
    seed = "%s|%s|%s" % (kind, engagement, minute)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:64]


def _reply(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _asked_for_archived(query):
    """Whether Show archived is ticked (14.3).

    A query string carries text, and "false" and "0" are both text that is
    true in Python. Read positively instead: the tick is on for the values a
    screen sends when it is on, and off for everything else including
    absent."""
    return str((query or {}).get("archived", "")).lower() in (
        "1", "true", "yes", "on")


# --- what the ARQEDIA workspace may not do ---------------------------------
#
# Tenant 0 curates the catalogue: the base and the memoranda every tenant
# forks from. It is not a client workspace, and these five acts belong to one.
#
# NAMED IN ONE PLACE, not checked in five. A guard repeated at each route is a
# guard somebody forgets at the sixth.
#
# Three of them are refused today by something else - filing and generating by
# a wallet with no money, checkout by nothing at all until a card is entered -
# and one, a template fork, would quietly copy a memorandum into tenant 0's
# own draft beside the original it was taken from. None of those is a control:
# a wallet can be funded and a subscription can be bought. This is the control.
CURATOR_REFUSED_ROUTES = frozenset({
    "POST /config/templates/fork",
    "POST /uploads",
    "POST /engagements/{id}/file",
    "POST /engagements/{id}/generate",
    # Update is a generation over a saved memo, and charged as one.
    "POST /memos/{memo_id}/update",
    "POST /billing/checkout",
})

CURATOR_REFUSAL = ("The ARQEDIA workspace curates the catalogue. It does not "
                   "file documents, generate memoranda or subscribe.")

# The same guard the other way round. These read and set what ARQEDIA offers
# every other tenant, so they belong to the workspace that curates it and to
# nobody else. What a screen hides is not a control; this is.
CURATOR_ONLY_ROUTES = frozenset({
    "GET /config/offer",
    "PUT /config/offer",
})

CURATOR_ONLY_REFUSAL = ("What ARQEDIA offers is set in the ARQEDIA "
                        "workspace.")


def _curation_only(tenant_id, route):
    """The refusal to send, or None where the route is allowed.

    Returned rather than raised so the dispatcher stays one line, and so this
    can be asked the question directly - the repo has no test that dispatches
    a route."""
    curator = tenant_id == registry.PACK_TENANT
    if curator and route in CURATOR_REFUSED_ROUTES:
        return _reply(403, {"error": CURATOR_REFUSAL})
    if not curator and route in CURATOR_ONLY_ROUTES:
        return _reply(403, {"error": CURATOR_ONLY_REFUSAL})
    return None


def _label_for(registry, field_id):
    if "." in field_id:
        group = field_id.split(".", 1)[0]
        for col in (registry.group_columns(group) or []):
            if col[0] == field_id:
                return col[1]
    return registry.label_for(field_id)


# --- engagements -----------------------------------------------------------

def engagement_id(tenant_id, workspace_id, name, created_by=None):
    """The engagement's own row, created the first time the name is seen
    IN THIS WORKSPACE (PACK-01, migration 042). The same name in two
    workspaces is two engagements.

    MIRRORED IN lambda/normalizer/app.py, which stamps the id on every
    document row it writes and meets a name this has usually already
    created. Two copies rather than one in the layer, deliberately: a shared
    module reaches a Lambda only through the docprocessing layer, and adding
    a layer rebuild to this deploy buys nothing for fifteen lines. The two
    must not drift - they are the same rule, and the rule is that one name is
    one row.

    THE NAME FOLDS CASE, because the column's collation does (migration 030,
    decision of 21 September): "Meridian" and "meridian" are one engagement.
    S3 keeps both spellings as typed, which is why the row is found by name
    rather than minted per key.

    NOT LAST_INSERT_ID. It is per connection and the Data API does not
    promise the same one between calls - signup learned that the hard way and
    got tenant 0. The insert is written, then the row is read back; the
    unique key makes that read authoritative even if two uploads race.
    """
    name = (name or "").strip()
    if not name:
        return None

    where = [_p("t", tenant_id), _p("w", workspace_id), _p("n", name)]
    found = _sql(
        "SELECT engagement_id FROM engagement "
        "WHERE tenant_id = :t AND workspace_id = :w AND name = :n",
        where).get("records", [])
    if found:
        return _col(found[0], 0)

    _sql(
        "INSERT INTO engagement (tenant_id, workspace_id, name, created_by) "
        "VALUES (:t, :w, :n, :by) "
        "ON DUPLICATE KEY UPDATE engagement_id = engagement_id",
        where + [_p("by", created_by)])

    found = _sql(
        "SELECT engagement_id FROM engagement "
        "WHERE tenant_id = :t AND workspace_id = :w AND name = :n",
        where).get("records", [])
    return _col(found[0], 0) if found else None


# The company an engagement's memoranda are about. Stored verbatim, as a
# person writes it, so the bound is the column's (migration 031) rather than
# _clean()'s key alphabet.
_SUBJECT_MAX = 255
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

SUBJECT_REQUIRED = (
    "Name the subject of this engagement before filing: the company these "
    "memoranda are about. Every document is read for the subject's facts, "
    "and nothing in the file says which company that is.")

# A read naming an engagement that has no row. 404 rather than an empty list:
# "this engagement has nothing in it" and "there is no such engagement" are
# different answers, and a screen that cannot tell them apart shows an empty
# page for a typo (13.3 stage 4).
NO_SUCH_ENGAGEMENT = "no engagement called %s"

# Generating where the tenant holds no memorandum at all (18.12).
#
# NOT THE SAME FAULT AS A WRONG KEY, and it used to answer as though it were:
# TEMPLATE_KEY is None with nothing published, the default flowed into the
# validation, and a person who had never chosen a memorandum was told "no such
# template: None" - a machine identifier, the word None, and nothing they could
# act on. A tenant reaches this by signing up and leaving Get started without
# ticking anything, which fork_base allows on purpose: the base is the facts
# and the document types, and which memoranda a tenant holds is their choice.
#
# Says where to go, because the answer is one screen away and naming it is the
# whole difference between a refusal and a dead end.
NO_TEMPLATE_PUBLISHED = (
    "This workspace has no published memorandum, so there is nothing to "
    "generate. Take one under Template Catalogue and publish it.")

# Uploading or filing where the workspace has published nothing (PACK-01 G8).
# An empty workspace - one begun from a report of the tenant's own, or Add a
# workspace's empty route - has no revision in use, and active_revision()
# falls back to revision 1, which holds nothing in a new workspace. A document
# was read against nothing, and filing it still charged.
NOTHING_PUBLISHED = (
    "This workspace has nothing published yet, so there is nothing to read a "
    "document against. Publish its configuration first, under Report "
    "Catalogue.")


def _require_published(tenant_id, workspace_id):
    """Refuses work in a workspace with no revision in use. Workspace 0 - the
    pack tenant, and rows from before workspaces - reads the tenant's own
    revision and is not asked."""
    if int(workspace_id) == config.NO_WORKSPACE:
        return
    found = _sql("SELECT active_revision FROM workspace "
                 "WHERE tenant_id = :t AND workspace_id = :w",
                 [_p("t", tenant_id), _p("w", int(workspace_id))]
                 ).get("records", [])
    if not found or _col(found[0], 0) is None:
        raise ValueError(NOTHING_PUBLISHED)


def engagement_subject(tenant_id, workspace_id, name):
    """The subject recorded for an engagement, or None.

    Resolved by the CLEANED name, because that is the name the row carries:
    upload_url cleans before creating it (see engagement_id's caller), so a
    lookup on the raw path parameter would miss the row for any name a
    person typed with a space in it."""
    found = _sql(
        "SELECT subject_name FROM engagement "
        "WHERE tenant_id = :t AND workspace_id = :w AND name = :n",
        [_p("t", tenant_id), _p("w", workspace_id),
         _p("n", _clean(name))]).get("records", [])
    if not found:
        return None
    return (_col(found[0], 0) or "").strip() or None


def set_subject(tenant_id, workspace_id, email, engagement, subject_name):
    """Name the subject, or change it.

    ONE ROUTE FOR BOTH. The row is resolved or created by name through
    engagement_id, which is the same rule /uploads uses - so naming a
    subject before anything has been uploaded opens the engagement, and
    naming one afterwards edits it. There is no separate create.

    STORED VERBATIM. _clean() is not applied to the subject: it exists to
    make a string safe for a storage key and would turn "Cocoa Empire
    Uganda Ltd." into "Cocoa-Empire-Uganda-Ltd". This value goes into an
    extraction prompt and onto the front matter of a memorandum, and must
    read as a person wrote it.

    ANY SEAT. A Member uploads, files, generates and configures; naming
    what an engagement is about belongs in that set. No admin gate.

    EDITABLE AFTER EXTRACTION, deliberately. A changed subject reaches
    every memorandum generated afterwards. Values already extracted change
    only if the documents are re-extracted, which stays a separate, paid
    act - so this never silently rewrites what a filed document yielded."""
    name = _clean(engagement)
    if not name:
        raise ValueError("engagement is required")

    subject = str(subject_name or "").strip()
    if not subject:
        raise ValueError("A subject is required: the company these "
                         "memoranda are about.")
    if _CONTROL.search(subject):
        raise ValueError("a subject cannot contain control characters")
    if len(subject) > _SUBJECT_MAX:
        raise ValueError("a subject can be at most %d characters"
                         % _SUBJECT_MAX)

    found = engagement_id(tenant_id, workspace_id, name, email)
    if found is None:
        raise ValueError("that engagement could not be opened")

    _sql("UPDATE engagement SET subject_name = :s "
         "WHERE tenant_id = :t AND engagement_id = :e",
         [_p("s", subject), _p("t", tenant_id), _p("e", int(found))])

    print("[subject-set] tenant=%s engagement=%s by=%s" % (
        tenant_id, name, email))
    return {"engagement": name, "engagement_id": int(found),
            "subject_name": subject}


def engagement_named(tenant_id, workspace_id, engagement):
    """The engagement row behind a name in the address, or None.

    THE ONE PLACE A NAME BECOMES A ROW (13.3 stage 4). Every read below
    takes an engagement_id; this is what turns the name in the URL into one,
    so the address a person can bookmark stays a name and the queries stop
    depending on where a file happens to be stored.

    IT DOES NOT CREATE. engagement_id() above creates, because uploading into
    a new name is how an engagement begins. A read must not: asking to see an
    engagement that does not exist is a 404, and a create here would make
    every typo a new empty engagement.

    BY THE CLEANED NAME, for the reason engagement_subject gives - the row
    carries the cleaned name because upload_url cleans before creating it, so
    a lookup on the raw path parameter misses every name typed with a space
    in it."""
    found = _sql(
        "SELECT engagement_id, name, subject_name, status FROM engagement "
        "WHERE tenant_id = :t AND workspace_id = :w AND name = :n",
        [_p("t", tenant_id), _p("w", workspace_id),
         _p("n", _clean(engagement))]).get("records", [])
    if not found:
        return None
    return {"engagement_id": _col(found[0], 0),
            "engagement": _col(found[0], 1),
            "subject_name": (_col(found[0], 2) or "").strip() or None,
            "status": _col(found[0], 3)}


def open_engagement(tenant_id, workspace_id, email, engagement):
    """Open an engagement by name, creating its row where there is none.

    WHY THIS EXISTS (13.3 stage 4). The reads now ask engagement_id, so a
    name with no row is a 404 - which is right for an address somebody typed
    wrongly and wrong for the form that opens a new engagement. Before stage
    4 the reads grepped storage keys and answered an empty list for any name
    at all, so the form could simply navigate and the screen opened onto
    nothing. It cannot any more, and the honest fix is to make opening an
    engagement CREATE it rather than to make a missing one look empty again.

    THE SAME engagement_id() /uploads USES. One name is one row, and this is
    the second door into the same rule rather than a second rule - a new
    engagement opened here and then uploaded into lands in the row it
    already has.

    IDEMPOTENT, because engagement_id() is find-or-create. Opening the same
    name twice is one row and answers the same id both times.

    THE STORED NAME COMES BACK. The caller navigates to what this returns,
    not to what somebody typed, so the address and the row agree from the
    first moment (17.3)."""
    name = _clean(engagement)
    if not name:
        raise ValueError("an engagement needs a name")

    found = engagement_named(tenant_id, workspace_id, name)
    if found:
        return dict(found, created=False)

    opened = engagement_id(tenant_id, workspace_id, name, email)
    if opened is None:
        raise ValueError("that engagement could not be opened")

    print("[engagement-opened] tenant=%s engagement=%s by=%s" % (
        tenant_id, name, email))
    return {"engagement_id": int(opened), "engagement": name,
            "subject_name": None, "status": "open", "created": True}


# --- archiving (Group 14) --------------------------------------------------
#
# NOTHING IS DELETED, EVER, BY ANY OF THIS. Archiving sets a column and
# records who did it and when; restoring clears the same three. An archived
# engagement keeps its documents, its values and its memoranda; an archived
# memorandum keeps its text, its sources and its claims. The only thing that
# changes is which lists it appears in.
#
# ARCHIVING AN ENGAGEMENT DOES NOT ARCHIVE ITS MEMORANDA (decided in 13.3).
# A memorandum is a document somebody may have sent to a lender; tidying the
# matter it came out of must not quietly withdraw it from the list it is
# read from. The two are archived separately and deliberately.
#
# WHO MAY DO IT IS NOT DECIDED. Every act here is open to any seat, which is
# what filing, generating and setting a document aside already are. See the
# report accompanying this branch: the alternative is _require_admin, and it
# is one line per route.

ENGAGEMENT_STATUSES = ("open", "archived")
MEMO_STATES = ("live", "archived")


def set_engagement_state(tenant_id, workspace_id, email, engagement,
                         status):
    """Archive an engagement, or bring it back.

    Its memoranda are untouched: an archived engagement's memoranda stay live
    and stay in their own list, because a memorandum is a thing that has left
    the building.

    RESOLVED WITHOUT REGARD TO STATUS, so an archived engagement can be
    restored - a resolver that only found open ones would make archiving a
    one-way door."""
    if status not in ENGAGEMENT_STATUSES:
        raise ValueError("an engagement is open or archived, not %r" % status)

    found = engagement_named(tenant_id, workspace_id, engagement)
    if found is None:
        return None

    if status == "archived":
        _sql("UPDATE engagement SET status = 'archived', archived_by = :who, "
             "archived_at = UTC_TIMESTAMP() "
             "WHERE tenant_id = :t AND engagement_id = :e",
             [_p("who", email), _p("t", tenant_id),
              _p("e", int(found["engagement_id"]))])
    else:
        # Cleared, not left behind. A restored engagement that still said who
        # archived it would read as archived to anybody looking at the row.
        _sql("UPDATE engagement SET status = 'open', archived_by = NULL, "
             "archived_at = NULL "
             "WHERE tenant_id = :t AND engagement_id = :e",
             [_p("t", tenant_id), _p("e", int(found["engagement_id"]))])

    print("[engagement-%s] tenant=%s engagement=%s by=%s" % (
        status, tenant_id, found["engagement"], email))
    return {"engagement_id": found["engagement_id"],
            "engagement": found["engagement"], "status": status}


def set_memo_state(tenant_id, email, memo_id, state):
    """Archive a memorandum, or bring it back. THE WHOLE REVISION LINE.

    A memorandum and its revisions are one document to the person who wrote
    it - revise_memo already inherits the parent's state for that reason, so
    a revision of something archived does not quietly reappear. Archiving one
    revision and leaving its siblings would put half a line in the list and
    half out of it, which is not a state anybody asked for.

    The line is found through parent_memo_id: the root is the memo's parent
    where it has one, itself where it does not, and every row whose parent is
    that root travels with it."""
    if state not in MEMO_STATES:
        raise ValueError("a memorandum is live or archived, not %r" % state)

    found = _sql("SELECT parent_memo_id FROM memo "
                 "WHERE tenant_id = :t AND memo_id = :m",
                 [_p("t", tenant_id), _p("m", int(memo_id))]).get("records", [])
    if not found:
        return None
    root = _col(found[0], 0) or int(memo_id)

    if state == "archived":
        result = _sql(
            "UPDATE memo SET state = 'archived', archived_by = :who, "
            "archived_at = UTC_TIMESTAMP() "
            "WHERE tenant_id = :t AND (memo_id = :root OR parent_memo_id = :root)",
            [_p("who", email), _p("t", tenant_id), _p("root", int(root))])
    else:
        result = _sql(
            "UPDATE memo SET state = 'live', archived_by = NULL, "
            "archived_at = NULL "
            "WHERE tenant_id = :t AND (memo_id = :root OR parent_memo_id = :root)",
            [_p("t", tenant_id), _p("root", int(root))])

    revisions = result.get("numberOfRecordsUpdated", 0)
    print("[memo-%s] tenant=%s memo=%s root=%s revisions=%s by=%s" % (
        state, tenant_id, memo_id, root, revisions, email))
    return {"memo_id": int(memo_id), "root_memo_id": int(root),
            "state": state, "revisions": revisions}


def list_engagements(tenant_id, workspace_id, include_archived=False):
    """What this workspace has, and what each one is about.

    ONE WORKSPACE'S (PACK-01). An engagement belongs to the workspace it was
    opened in (migration 042), and the list shows the active one's only.

    FROM THE ENGAGEMENT TABLE, not from the documents' storage keys (13.3
    stage 4). The list used to be GROUP BY over a substring of s3_key, which
    meant an engagement existed only as long as a file did: naming a subject
    and then changing your mind about the first upload left a row nothing
    would ever show. An engagement with no documents now appears, with a
    count of zero, which is what somebody who has just opened one expects to
    see.

    LEFT JOIN, so that zero is a zero rather than a missing row. COUNT of
    d.document_id rather than COUNT(*), because COUNT(*) over a LEFT JOIN
    counts the engagement's own row and reports one document where there are
    none.

    ORDERED BY ACTIVITY, FALLING BACK TO WHEN IT WAS OPENED. A brand new
    engagement has no filed_at at all, and MAX() of nothing is NULL, which
    MySQL sorts last in DESC - so the one just created would appear at the
    bottom of the list, which is the opposite of useful.

    'open' ONLY, UNLESS ASKED OTHERWISE (14.2, 14.3). Archiving is a
    decision recorded on the row (migration 030); an archived engagement is
    out of the way rather than deleted, and Show archived brings it back into
    view so it can be restored. The status travels on every row, so the list
    can mark the archived ones rather than mixing them in unannounced."""
    result = _sql(
        """
        SELECT e.engagement_id,
               e.name,
               e.subject_name,
               COUNT(d.document_id) AS documents,
               MAX(d.filed_at)      AS last_activity,
               e.status,
               e.archived_by,
               e.archived_at
        FROM engagement e
        LEFT JOIN document d
               ON d.tenant_id = e.tenant_id
              AND d.engagement_id = e.engagement_id
        WHERE e.tenant_id = :tenant_id
          AND e.workspace_id = :workspace_id
          AND (e.status = 'open' OR :include_archived)
        GROUP BY e.engagement_id, e.name, e.subject_name, e.created_at,
                 e.status, e.archived_by, e.archived_at
        ORDER BY COALESCE(MAX(d.filed_at), e.created_at) DESC
        """,
        [_p("tenant_id", tenant_id), _p("workspace_id", workspace_id),
         _p("include_archived", bool(include_archived))],
    )
    return [
        {"engagement_id": _col(r, 0),
         "engagement": _col(r, 1),
         "subject_name": _col(r, 2),
         "documents": _col(r, 3),
         "last_activity": _col(r, 4),
         "status": _col(r, 5),
         "archived_by": _col(r, 6),
         "archived_at": _col(r, 7)}
        for r in result.get("records", [])
    ]


def list_pending(tenant_id, engagement_id):
    """Analysed but not yet filed: the proposed type, how sure, and why.

    'unreadable' travels with them. It is not fileable and the screen must not
    offer it as though it were - but it has to ARRIVE, because a file sent and
    never seen as a row is what left the review screen waiting ten minutes for
    something no process would ever create. The row is what clears that wait
    (decision record, 18 September, item 1).

    BY engagement_id (13.3 stage 4), not by a LIKE on the storage key. The
    column is what says which engagement a document belongs to; the key says
    where its bytes are, and the two were the same thing only by convention.
    A LIKE on '%/docs/NAME/%' also matched a name that was a prefix of
    another, and could not be indexed."""
    result = _sql(
        """
        SELECT document_id, filename, document_type, page_count,
               thin_text, char_count, type_confidence, type_reason, state,
               uploaded_by, part_index, page_from, page_to,
               refusal_code, refusal_reason, source_folder, chosen_type
        FROM document
        WHERE tenant_id = :tenant_id
          AND state IN ('analysed', 'reading', 'unreadable')
          AND engagement_id = :engagement_id
        ORDER BY document_id
        """,
        [_p("tenant_id", tenant_id),
         _p("engagement_id", int(engagement_id))],
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
         "uploaded_by": _col(r, 9),
         "part_index": _col(r, 10),
         "page_from": _col(r, 11),
         "page_to": _col(r, 12),
         "refusal_code": _col(r, 13),
         "refusal_reason": _col(r, 14),
         # Provenance, shown beside the filename (18.7). Null on every row
         # filed before migration 032 and on every upload that was not a
         # directory.
         "source_folder": _col(r, 15),
         # What a person chose while it waits (21.1, migration 034). Null is
         # nobody has chosen, and the screen shows the proposal; "" is a
         # choice of "Not classified". Beside proposed_type, never in place
         # of it.
         "chosen_type": _col(r, 16)}
        for r in result.get("records", [])
    ]


def set_document_type(tenant_id, email, document_id, type_key):
    """Record the type chosen for a document waiting to be filed (21.1).

    SAVED AS IT IS CHOSEN, so the choice outlives the screen. It lived in the
    browser until File was pressed, and leaving to top up threw away a
    quarter of an hour's work on a batch of fifty-seven.

    ON THE DOCUMENT, NOT THE PERSON. Two colleagues working through one batch
    see the same choices (decision of 24 September 2026). Any seat may
    choose, as any seat may file.

    NEVER THE PROPOSAL'S COLUMN. document_type keeps what the classifier
    proposed; this writes chosen_type beside it.

    "" OR None IS A CHOICE OF "NOT CLASSIFIED", stored as "" so that it is
    told apart from nobody having chosen (NULL). A key must be a document
    type in the tenant's configuration now in use - the one filing reads.

    ONLY WHILE IT WAITS. A document being read, filed or refused has had its
    type settled or has none to settle; changing it there would be a record
    that says something nobody can act on. Returns None where there is no
    such document, which the route answers as 404."""
    found = _sql("SELECT state, workspace_id FROM document "
                 "WHERE tenant_id = :t AND document_id = :d",
                 [_p("t", tenant_id), _p("d", int(document_id))]
                 ).get("records", [])
    if not found:
        return None
    if _col(found[0], 0) != "analysed":
        raise ValueError("this document is no longer waiting to be filed, "
                         "so its type cannot be changed here")

    # The types of the workspace the document was uploaded into, which is
    # the configuration it will be filed and extracted under.
    chosen = (type_key or "").strip()
    workspace_id = config.workspace_of(tenant_id, _col(found[0], 1))
    if chosen and chosen not in config.for_workspace(
            tenant_id, workspace_id).DOCUMENT_TYPES:
        raise ValueError("%s is not one of this workspace's document types"
                         % chosen)

    # The state is in the WHERE as well: a filing that lands between the read
    # above and this write must not have a choice written under it. The
    # updated-row count is NOT checked - MySQL reports zero for a row whose
    # value did not change, so choosing the same type twice would read as a
    # refusal.
    _sql("UPDATE document SET chosen_type = :c "
         "WHERE tenant_id = :t AND document_id = :d AND state = 'analysed'",
         [_p("c", chosen), _p("t", tenant_id), _p("d", int(document_id))])

    print("[type-chosen] tenant=%s doc=%s type=%s by=%s" % (
        tenant_id, document_id, chosen or "-", email))
    return {"document_id": int(document_id), "chosen_type": chosen}


def _in_list(values, prefix="id"):
    """An IN list and its parameters.

    Written out rather than interpolated. These are integers the caller sent,
    and a query that interpolates once is a query that interpolates twice.
    Mirrors registry._in."""
    names = [":%s%d" % (prefix, i) for i in range(len(values))]
    params = [_p("%s%d" % (prefix, i), v) for i, v in enumerate(values)]
    return ", ".join(names), params


def _envelope_suffix(page_from, part_index):
    """Where a document's envelope lives, relative to the file's own key.

    Parts of one file share an s3_key, so the part number is what tells their
    envelopes apart. A file holding one document keeps the unsuffixed name it
    has always had. Mirrors envelope_suffix in the normalizer, which writes
    them - the two must not drift."""
    if page_from is None:
        return ".analysed.json"
    return ".p" + str(part_index) + ".analysed.json"


# --- how a scan is read: overridden here, decided 5 October 2026 ------------
#
# THE CONFIGURATION SAYS FORMS AND ALWAYS-OCR; THIS IS WHAT HAPPENS INSTEAD.
# Both are properties of a document type in every tenant's configuration
# (config_document_type.read_mode and .always_ocr), and published revisions
# are never edited - so the override is code, here, and nowhere else. Undoing
# it is these two names: OCR_READ_MODE = None restores each type's configured
# mode, OCR_ONLY_WHEN_THIN = False restores always_ocr. Nothing else in the
# API changes; the Configure screen's notes and disabled controls would be
# lifted with it (ui/src/config-parts.tsx, and the "Read as" cell in
# Configure.tsx).
#
# READ MODE IS TEXT, WHATEVER THE TYPE SAYS. Twelve types asked for Textract
# FORMS (AnalyzeDocument with TABLES and FORMS, $0.065 a page) instead of
# DetectDocumentText ($0.0015). Nothing reads what FORMS adds: textract.fetch
# keeps only LINE blocks for the text, and the TABLE blocks it also collects
# go to envelope["tables"], which extraction never opens (tables_as_text has
# no caller). KEY_VALUE_SET, the FORMS output itself, is read by nothing in
# lambda/. Extraction was sent the same lines either way. On dev that was
# $32.60 of $33.30 OCR spend across 181 documents and 463 pages.
#
# WANTING IT BACK means something reading tables first - envelope["tables"]
# into the extraction prompt, or a table-aware field. Then a TABLES-only read
# ($0.015 a page) is the mode to return to, not FORMS: key-value pairs would
# still have no reader.
#
# OCR RUNS ONLY WHEN THE TEXT LAYER IS THIN, WHATEVER always_ocr SAYS. Four
# types (audited, interim and bank statements, aging reports) were OCR'd even
# with a text layer, on the reasoning that a garbled layer corrupts numbers
# worse than OCR does. Measured on dev: 22 of the 24 such documents had a
# layer carrying 92-100% of the numbers OCR then found, and at least 80% of
# its length; the other two failed the comparison only because a split part
# was given its whole file's OCR text (a separate defect). The garbled-layer
# case was not seen - so the rule went, at $12.35 of OCR on dev, and it may
# return if a garbled layer ever is.
#
# THE CONFIGURE CONTROLS STAY, and say this (ui/src/config-parts.tsx).
OCR_READ_MODE = textract.TEXT
OCR_ONLY_WHEN_THIN = True


def _ocr_mode(registry, document_type):
    """The Textract mode a document is read with. OCR_READ_MODE, unless that
    is lifted - see the note above it."""
    return OCR_READ_MODE or registry.read_mode_for(document_type)


def _start_ocr(registry, tenant_id, s3_key, parts):
    """Send a file to OCR once, for every document filed from it.

    ONE JOB PER FILE (ocr-split-parts, 5 October 2026). `parts` is every
    (document_id, document_type) in this filing that lives in the file and
    reads in the same mode. Textract reads the whole object whatever is
    asked, so one job per PART read the whole file once per part - the
    Manty accounts, two parts filed twice, were billed for 56 pages of
    paper that had 14. The job id goes on every part's row, and the
    collector cuts each part's own pages out of the one result.

    The job runs asynchronously; the collector picks it up on completion and
    releases each document to extraction then. The mode used is what
    textract_api records, so the collector fetches with the same one."""
    job_id, mode = textract.start(
        DOCS_BUCKET, s3_key, parts[0][1],
        TEXTRACT_TOPIC_ARN, TEXTRACT_ROLE_ARN,
        read_mode=_ocr_mode(registry, parts[0][1]))
    for document_id, document_type in parts:
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


# What a document is told when it was paid for and could not be read. The
# sentence about the charge is part of it rather than a separate notice
# somebody has to find (decision record, 18 September, item 16).
OCR_FAILED_REASON = (
    "This file could not be read, even with OCR. It can't be used in its "
    "current state. Please fix it on your side and upload it again. The "
    "charge for it has been refunded.")


def _fail_and_refund(tenant_id, email, document_id, charge_entry_id, why):
    """One document paid for and not delivered: say so, and give the money
    back.

    Terminal, and in the SAME state Stage 1 uses for a document nobody could
    read. One refusal state, one block on the screen, one Remove - a second
    state would mean a second of each, telling a person the same thing twice
    in two different words.

    Returns 1 where money came back and 0 otherwise, so the caller can report
    it. Never raises: it is already handling a failure, and a refund that
    throws would lose both the refusal and the money.
    """
    _sql(
        "UPDATE document SET state = 'unreadable', refusal_code = 'ocr_failed',"
        " refusal_reason = :r WHERE tenant_id = :t AND document_id = :d",
        [_p("r", OCR_FAILED_REASON), _p("t", tenant_id), _p("d", document_id)])

    try:
        given = wallet.refund(tenant_id, document_id, charge_entry_id, email)
    except Exception as exc:  # noqa: BLE001 - the refusal stands regardless
        print("[refund-failed] tenant=%s doc=%s entry=%s %r" % (
            tenant_id, document_id, charge_entry_id, exc))
        return 0

    print("[ocr-failed] tenant=%s doc=%s why=%s refunded=%s repeated=%s "
          "cents=%s" % (tenant_id, document_id, why, given.get("refunded"),
                        given.get("repeated"), given.get("amount_cents")))
    return 1 if given.get("refunded") else 0


def file_documents(tenant_id, workspace_id, email, engagement, decisions,
                   idempotency_key):
    """Confirm types and file. The deliberate act that starts extraction, and
    the point at which money changes hands.

    A document that could not be read goes to OCR instead, and reaches
    extraction when the OCR finishes. A rejected document is marked and kept,
    never deleted.

    CHARGED BEFORE ANYTHING IS DONE, for the documents being included. The
    price was shown and accepted on the screen before this call; somebody who
    accepted it should not find the work ran and the money did not.

    A rejected document costs nothing - it is not read. Neither does one sent
    to OCR pay twice: it is charged here, once, as the document it will
    become.

    The key makes this safe to call from a click. Eighteen documents are one
    click and one charge of eighteen; a retry or a double click must not
    charge again, and wallet.charge refuses the repeat.

    NOTHING IS FILED INTO AN ENGAGEMENT WITH NO SUBJECT (SUBJ-01). Filing
    is what starts extraction - it is the only thing in the product that
    writes .normalized.json, which is what the extraction trigger listens
    for - so this is the gate, and it is the FIRST thing here, above the
    charge. Extraction carries a second line of its own for a document that
    reaches it by some other route; this one is the one a person meets.

    NOR INTO A WORKSPACE WITH NOTHING PUBLISHED (PACK-01 G8): refused by the
    route, before this is called and so before the charge.
    """
    held = engagement_subject(tenant_id, workspace_id, engagement)
    if not held:
        raise ValueError(SUBJECT_REQUIRED)

    # Each document is read under its own workspace's configuration, the one
    # it was uploaded into. Loaded once per workspace in the filing.
    registries = {}

    def registry_for(workspace_id):
        workspace_id = config.workspace_of(tenant_id, workspace_id)
        if workspace_id not in registries:
            registries[workspace_id] = config.for_workspace(
                tenant_id, workspace_id)
        return registries[workspace_id]

    # A document nobody could read is not fileable, and must not be counted
    # before the charge. The screen does not offer it, so reaching here means a
    # request made by hand - but the money moves two lines below, and a guard
    # that runs after the charge is not a guard (decision record, 18
    # September, items 5 and 11: a refused document costs nothing).
    included = [d for d in decisions if d.get("include", True)]
    wanted = [int(d["document_id"]) for d in decisions
              if d.get("document_id") is not None]
    known = {}
    # What each document's type is, where the decision does not say (21.1):
    # the type a person chose while it waited, else the proposal.
    held_type = {}
    if wanted:
        names, params = _in_list(wanted)
        for r in _sql(
                "SELECT document_id, filename, state, chosen_type, "
                "document_type FROM document "
                "WHERE tenant_id = :t AND document_id IN (%s)" % names,
                [_p("t", tenant_id)] + params).get("records", []):
            known[_col(r, 0)] = (_col(r, 1), _col(r, 2))
            chosen = _col(r, 3)
            # "" is a choice of "Not classified" and must stay one, so it is
            # not the same as NULL and does not fall back to the proposal.
            held_type[_col(r, 0)] = (chosen if chosen is not None
                                     else _col(r, 4))

        blocked = [n for _id, (n, st) in known.items() if st == "unreadable"]
        if blocked:
            raise ValueError(
                "one of these could not be read and cannot be filed: %s"
                % ", ".join(sorted(blocked)))

    def type_of(d):
        """The decision's own type where it names one, else what the
        document holds. A decision is what a person pressed File on; the
        chosen type is what they picked on the way there."""
        if "document_type" in d:
            return (d.get("document_type") or "").strip() or None
        return (held_type.get(int(d["document_id"])) or "").strip() or None

    # A SCAN ARRIVES WITH NO TYPE, and the read mode comes from the confirmed
    # type - so _start_ocr would fail on a null, AFTER the charge. Refused
    # here, before the money moves, and named so a person knows which one
    # (decision record, 18 September, item 7).
    typeless = sorted(
        known.get(int(d["document_id"]), (str(d.get("document_id")), None))[0]
        for d in included
        if d.get("document_id") is not None
        and not type_of(d))
    if typeless:
        raise ValueError(
            "Choose a type for %s before filing. A scan has no type until "
            "you give it one, and the type decides how it is read."
            % ", ".join(typeless))

    chargeable = sum(1 for d in decisions if d.get("include", True))
    charge_entry_id = None
    if chargeable:
        paid = wallet.charge(
            tenant_id, email, "document_filed", chargeable,
            reference=str(chargeable) + " documents filed",
            idempotency_key=idempotency_key)
        charge_entry_id = (paid or {}).get("entry_id")

    filed, rejected, reading, refunded = 0, 0, 0, 0
    # (s3_key, mode) -> [(document_id, document_type)]: the files to OCR, one
    # job each, and the documents each job reads for.
    to_ocr = {}

    for d in decisions:
        document_id = int(d.get("document_id"))

        if not d.get("include", True):
            _sql("UPDATE document SET state = 'rejected' "
                 "WHERE tenant_id = :t AND document_id = :d",
                 [_p("t", tenant_id), _p("d", document_id)])
            rejected += 1
            continue

        document_type = type_of(d)

        row = _sql("SELECT s3_key, thin_text, page_from, part_index, "
                   "workspace_id FROM document "
                   "WHERE tenant_id = :t AND document_id = :d",
                   [_p("t", tenant_id), _p("d", document_id)])
        records = row.get("records", [])
        if not records:
            continue
        s3_key = _col(records[0], 0)
        thin = bool(_col(records[0], 1))
        suffix = _envelope_suffix(_col(records[0], 2), _col(records[0], 3))
        registry = registry_for(_col(records[0], 4))

        # Which entry paid for it, before anything can fail. A refund has to
        # name the charge, and one click is one ledger row for every document
        # in it - so without this there is no way back from a document to the
        # money (migration 026).
        _sql("UPDATE document SET charge_entry_id = :e "
             "WHERE tenant_id = :t AND document_id = :d",
             [_p("e", charge_entry_id), _p("t", tenant_id),
              _p("d", document_id)])

        # always_ocr is configured and no longer obeyed: see the note above
        # _start_ocr. A thin layer is the only reason to OCR.
        if thin or (not OCR_ONLY_WHEN_THIN
                    and registry.always_ocr(document_type)):
            # Gathered, not started: every part of one file in this filing
            # shares one read (ocr-split-parts). Started after the loop.
            to_ocr.setdefault(
                (s3_key, _ocr_mode(registry, document_type)), []
            ).append((document_id, document_type, registry))
            continue

        # Everything here is after the charge too. A missing envelope, a KMS
        # refusal, malformed JSON - any of them used to leave the money gone
        # and the document in limbo with a 500 on screen.
        try:
            _sql("UPDATE document SET document_type = :ty, type_confirmed = 1, "
                 "state = 'filed' WHERE tenant_id = :t AND document_id = :d",
                 [_p("ty", document_type), _p("t", tenant_id),
                  _p("d", document_id)])

            # Extraction listens for .normalized.json. Renaming the envelope is
            # what starts it - filing, not uploading.
            body = _s3.get_object(Bucket=REVIEW_BUCKET,
                                  Key=s3_key + suffix)["Body"].read()
            envelope = json.loads(body.decode("utf-8"))
            envelope["document_type"] = document_type
            envelope["document_type_confirmed"] = True
            _s3.put_object(
                Bucket=REVIEW_BUCKET,
                Key=s3_key + suffix.replace(".analysed.", ".normalized."),
                Body=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
                ContentType="application/json")
            filed += 1
        except Exception as exc:  # noqa: BLE001 - refunded, then reported
            refunded += _fail_and_refund(
                tenant_id, email, document_id, charge_entry_id,
                "filing: %s" % type(exc).__name__)

    # One job per file. PAID FOR ALREADY: everything here can fail with the
    # money gone, which is what item 14 exists to answer - each document is
    # told, and the charge for it comes back. The rest of the batch carries
    # on - one bad file must not strand seventeen good ones that have also
    # been paid for.
    for (s3_key, _mode), parts in to_ocr.items():
        try:
            # Parts of one file share its upload, and so its workspace.
            _start_ocr(parts[0][2], tenant_id, s3_key,
                       [(d, t) for d, t, _reg in parts])
            reading += len(parts)
        except Exception as exc:  # noqa: BLE001 - refunded, then reported
            for document_id, _type, _reg in parts:
                refunded += _fail_and_refund(
                    tenant_id, email, document_id, charge_entry_id,
                    "textract.start: %s" % type(exc).__name__)

    return {"filed": filed, "reading": reading, "rejected": rejected,
            "refunded": refunded}


# --- documents -------------------------------------------------------------

def remove_document(tenant_id, document_id):
    """Delete a document, and everything read out of it.

    THE ONE DESTRUCTIVE ACT ON A TENANT'S OWN WORK, outside closing the
    account. It was limited to documents that had not been filed; on 20
    September it was extended to filed ones, with the facts extracted from
    them, by decision - which overrides "non-destructive throughout" for this
    act and for nothing else.

    WHAT GOES: the evidence binding this document's values to sentences, the
    values, both envelopes, the upload, and the row.

    WHAT STAYS, deliberately:
      memo            a memorandum already written is what it said when it was
                      written. A clean one is a new generation, charged.
      memo_source     kept, and given the document's name on the way out
                      (migration 028), so a citation to a deleted source
                      renders as present-but-dead rather than silently
                      becoming prose.
      claim           a claim binds a sentence that still exists. Deleting it
                      would say the sentence was never evidenced, rather than
                      that its evidence was deleted.
      wallet_*        the ledger is append-only. The charge stays and is not
                      refunded; what is lost is the link back from that line
                      to what it bought, which the confirmation says.

    ONLY `reading` IS REFUSED. A Textract job in flight would write back to a
    row that is no longer there.

    THE DATABASE WORK IS ONE TRANSACTION, with the two S3 deletes inside it.
    That ordering is the instruction and it has a cost worth naming: if the
    row delete fails after the objects are gone, the rollback restores the
    rows and the file does not come back. The alternative - commit, then
    delete - fails the other way, leaving objects nobody can reach. Neither is
    free; this one at least leaves a row a person can see and retry.
    """
    row = _sql("SELECT s3_key, state, page_from, part_index, filename "
               "FROM document WHERE tenant_id = :t AND document_id = :d",
               [_p("t", tenant_id), _p("d", document_id)])
    records = row.get("records", [])
    if not records:
        return None

    s3_key = _col(records[0], 0)
    state = _col(records[0], 1)
    page_from = _col(records[0], 2)
    suffix = _envelope_suffix(page_from, _col(records[0], 3))
    filename = _col(records[0], 4)
    if state == "reading":
        return {"refused": state}

    # One uploaded file can hold several documents, all reading from the same
    # object. Removing one part must not take the file its siblings are read
    # from, so the upload goes only when the last of them does.
    siblings = _sql(
        "SELECT COUNT(*) FROM document "
        "WHERE tenant_id = :t AND s3_key = :k AND document_id <> :d",
        [_p("t", tenant_id), _p("k", s3_key), _p("d", document_id)])
    remaining = _col(siblings.get("records", [[{}]])[0], 0) or 0

    where = [_p("t", tenant_id), _p("d", document_id)]
    tx = _rds.begin_transaction(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                                database=DATABASE)["transactionId"]
    try:
        # The name, before the row that holds it goes. Every memo citing this
        # document reads its filename from here afterwards.
        _sql("UPDATE memo_source SET filename = :f "
             "WHERE tenant_id = :t AND document_id = :d",
             [_p("f", filename)] + where, tx=tx)

        # Evidence first: it points at the values, and the values are about to
        # go. A claim with nothing left behind it stays - see the docstring.
        _sql("DELETE FROM claim_evidence WHERE value_id IN "
             "(SELECT value_id FROM extracted_value "
             " WHERE tenant_id = :t AND document_id = :d)", where, tx=tx)

        _sql("DELETE FROM extracted_value "
             "WHERE tenant_id = :t AND document_id = :d", where, tx=tx)

        # Deleting a key that is not there is not an error in S3, so neither
        # call needs to know whether the normalizer, filing or OCR got that
        # far. The suffix comes from _envelope_suffix, which the normalizer
        # and the collector mirror - there is no fourth copy of that rule.
        _s3.delete_object(Bucket=REVIEW_BUCKET,
                          Key=s3_key + suffix.replace(".analysed.",
                                                      ".normalized."))
        _s3.delete_object(Bucket=REVIEW_BUCKET, Key=s3_key + suffix)
        if not remaining:
            _s3.delete_object(Bucket=DOCS_BUCKET, Key=s3_key)

        _sql("DELETE FROM document WHERE tenant_id = :t AND document_id = :d",
             where, tx=tx)
    except Exception:
        _rds.rollback_transaction(resourceArn=CLUSTER_ARN,
                                  secretArn=SECRET_ARN, transactionId=tx)
        raise
    _rds.commit_transaction(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                            transactionId=tx)

    print("[document-deleted] tenant=%s doc=%s state=%s" % (
        tenant_id, document_id, state))
    return {"removed": document_id}


def list_documents(tenant_id, engagement_id):
    """Filed documents. `reading` documents are included so the screen can see
    that something is in flight and hold the generate action.

    BY engagement_id (13.3 stage 4). See list_pending for why the storage key
    stopped being the answer to which engagement a document is in."""
    result = _sql(
        """
        SELECT document_id, filename, document_type, page_count,
               extraction_method, filed_at, uploaded_by, active, state,
               deactivated_by, deactivated_at, extracted_at,
               extraction_error,
               (SELECT COUNT(*) FROM extracted_value v
                 WHERE v.document_id = d.document_id
                   AND v.tenant_id = d.tenant_id) AS values_found
        FROM document d
        WHERE tenant_id = :tenant_id
          AND state IN ('filed', 'reading')
          AND engagement_id = :engagement_id
        ORDER BY document_id
        """,
        [_p("tenant_id", tenant_id),
         _p("engagement_id", int(engagement_id))],
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
         # And why it did not finish, where it did not (migration 029). Set
         # with no timestamp is the third answer the pair could not give
         # before: extraction ran, failed, and nothing further will happen on
         # its own. Whatever values it did write are still counted below -
         # a failure part way through leaves real facts behind it.
         "extraction_error": _col(r, 12),
         "values": _col(r, 13)}
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
               config_revision, workspace_id
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
    registry = config.load(
        tenant_id, config.workspace_of(tenant_id, _col(records[0], 5)),
        _col(records[0], 4) or 1)

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

    # What deleting this document would reach, read live so the confirmation
    # states a fact rather than a guess (8.2). Cheap: two counts on indexed
    # columns, and this is the call the drawer already makes.
    reach = _sql(
        """
        SELECT (SELECT COUNT(DISTINCT memo_id) FROM memo_source
                 WHERE tenant_id = :t AND document_id = :d) AS memos,
               (SELECT charge_entry_id FROM document
                 WHERE tenant_id = :t AND document_id = :d) AS entry
        """,
        [_p("t", tenant_id), _p("d", int(document_id))],
    ).get("records", [[{}, {}]])

    return {
        "document_id": int(document_id),
        "filename": _col(records[0], 0),
        "document_type": document_type,
        "pages": _col(records[0], 2),
        "method": _col(records[0], 3),
        "values": values,
        "missing": missing,
        "expected": len(expected),
        # How many memoranda cite it, and whether a ledger line paid for it.
        "memos": _col(reach[0], 0) or 0,
        "charged": _col(reach[0], 1) is not None,
    }


def document_passage(tenant_id, document_id, unit):
    """The text of one page, so a citation can be checked against what the
    system actually read.

    This is what was read, not the original image - which is arguably the more
    useful thing when checking an extraction, since a wrong value is usually a
    misreading rather than a misprint."""
    row = _sql(
        "SELECT s3_key, filename, page_count, state, page_from, part_index "
        "FROM document WHERE tenant_id = :t AND document_id = :d",
        [_p("t", tenant_id), _p("d", int(document_id))],
    )
    records = row.get("records", [])
    if not records:
        return None

    s3_key = _col(records[0], 0)
    state = _col(records[0], 3)
    suffix = _envelope_suffix(_col(records[0], 4), _col(records[0], 5))

    # A document waiting to be filed has only the analysed envelope. Reading
    # before filing is the point: it is how a person decides what the thing is
    # without paying to find out.
    if state != "filed":
        suffix = suffix.replace(".analysed.", ".analysed.")
    else:
        suffix = suffix.replace(".analysed.", ".normalized.")

    # A refusal has no envelope at all - nothing was read, so there was
    # nothing to write one from - and a scan's is empty until OCR fills it.
    # Neither is an error here: the point of opening one of these is to look
    # at the ORIGINAL, and source_url below is what does that.
    try:
        envelope = json.loads(
            _s3.get_object(Bucket=REVIEW_BUCKET,
                           Key=s3_key + suffix)["Body"].read()
            .decode("utf-8"))
    except ClientError:
        envelope = {}

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

def list_memos(tenant_id, engagement_id, include_archived=False):
    """Memos for one engagement, each named as it was when it was written.

    BY engagement_id AND state 'live' (13.3 stage 4, 14.2). The engagement
    comes from the column rather than from the memo's storage key; the state
    keeps an archived memorandum out of the list without deleting it, which
    is what archiving is for. A revision inherits its parent's state, so
    archiving a line archives all of it and revising something archived does
    not put it back (see revise_memo).

    Show archived asks for them anyway, so a line can be restored from the
    list it left. The state travels on every row for the same reason it does
    on an engagement: an archived memorandum shown unmarked is a lie.

    THE NAME COMES FROM THE MEMO'S OWN REVISION, not from the tenant's active
    one. A memorandum renamed in September must not rename the memo somebody
    generated under it in March: that memo was written against config_revision
    N, and config_template holds the label per revision, so the row at N is
    what the memo was called. The key is returned beside it, unchanged - it is
    the identity, and the name is only what a person reads.

    Loaded through config.load, which caches on (tenant, workspace,
    revision), so a page of memos sharing a revision is one load."""
    result = _sql(
        """
        SELECT memo_id, template_key, generated_at, generated_by,
               parent_memo_id, revision, modified_by, modified_at, pdf_key,
               config_revision, state, archived_by, archived_at, workspace_id
        FROM memo
        WHERE tenant_id = :tenant_id
          AND engagement_id = :engagement_id
          AND (state = 'live' OR :include_archived)
        ORDER BY COALESCE(parent_memo_id, memo_id) DESC, revision DESC
        """,
        [_p("tenant_id", tenant_id),
         _p("engagement_id", int(engagement_id)),
         _p("include_archived", bool(include_archived))],
    )
    return [
        {"memo_id": _col(r, 0),
         "template": _col(r, 1),
         # A revision that no longer names this template falls back to the
         # key, which is what label_for_template does and is better than a
         # blank column.
         "template_label": config.load(
             tenant_id, config.workspace_of(tenant_id, _col(r, 13)),
             _col(r, 9) or 1).label_for_template(_col(r, 1)),
         "generated_at": _col(r, 2),
         "generated_by": _col(r, 3),
         "parent_memo_id": _col(r, 4),
         "revision": _col(r, 5),
         "modified_by": _col(r, 6),
         "modified_at": _col(r, 7),
         "label": "%s.%s" % (_col(r, 4) or _col(r, 0), _col(r, 5)),
         "has_pdf": bool(_col(r, 8)),
         "state": _col(r, 10),
         "archived_by": _col(r, 11),
         "archived_at": _col(r, 12)}
        for r in result.get("records", [])
    ]


# --- a memo's identity in its front matter (23 October 2026) ----------------
#
# Number, version and workspace, as rows of the title block. NOT STORED: the
# markdown is written, and hashed, before the memo row that numbers it exists,
# and a revision's text is its parent's edited - a stored "Version 1" would be
# wrong in every revision after it. So they are filled in from the memo row
# whenever a memo is read, and taken out again before a revision is saved.
# Every memo has them, including those written before this, and none is wrong.
#
# The renderer draws the same three in the PDF's masthead from the same row.

_IDENTITY_ROW = re.compile(
    r"^\|\s*\*\*(?:Number|Version|Workspace)\*\*\s*\|.*\|\s*$")
_SECTION_START = re.compile(r"^##(?!#)\s+\S")
_EMPTY_HEADER = re.compile(r"^\|\s*\|\s*\|\s*$")


def _head_length(lines):
    """How many lines come before the first section: the title block."""
    for i, line in enumerate(lines):
        if _SECTION_START.match(line):
            return i
    return len(lines)


def _without_identity(markdown):
    """The text with the identity rows taken out of its title block, and
    nothing else touched. A body table whose first cell happens to read
    Number is below the first section, and is left alone."""
    lines = (markdown or "").split("\n")
    end = _head_length(lines)
    head = [line for line in lines[:end] if not _IDENTITY_ROW.match(line)]
    return "\n".join(head + lines[end:])


def _with_identity(markdown, number, version, workspace):
    """The text with the identity rows at the foot of its title block. A memo
    with no title block - nothing composition writes, but a person can delete
    one - is returned as it is."""
    lines = _without_identity(markdown).split("\n")
    end = _head_length(lines)
    for i in range(end - 1):
        if _EMPTY_HEADER.match(lines[i]) \
                and lines[i + 1].lstrip().startswith("|"):
            j = i + 2
            while j < end and lines[j].lstrip().startswith("|"):
                j += 1
            rows = ["| **Number** | %s |" % number,
                    "| **Version** | %s |" % version]
            if workspace:
                rows.append("| **Workspace** | %s |"
                            % str(workspace).replace("|", "\\|"))
            return "\n".join(lines[:j] + rows + lines[j:])
    return "\n".join(lines)


def get_memo(tenant_id, memo_id):
    """A memo, a signed link to its PDF, and the documents behind it.

    The sources are returned so the reader can turn a citation - which names a
    filename - into something it can open. The memo text has no document
    identifiers in it; this is the map.

    The text carries the memo's number, version and workspace in its title
    block, filled in here (see _with_identity)."""
    result = _sql(
        """
        SELECT m.s3_bucket, m.s3_key, m.generated_at, m.generated_by,
               m.pdf_key, m.parent_memo_id, m.revision, m.modified_by,
               m.modified_at, w.name
        FROM memo m
        LEFT JOIN workspace w
               ON w.workspace_id = m.workspace_id
              AND w.tenant_id = m.tenant_id
        WHERE m.tenant_id = :tenant_id AND m.memo_id = :memo_id
        """,
        [_p("tenant_id", tenant_id), _p("memo_id", int(memo_id))],
    )
    records = result.get("records", [])
    if not records:
        return None
    r = records[0]

    markdown = _s3.get_object(
        Bucket=_col(r, 0), Key=_col(r, 1))["Body"].read().decode("utf-8")
    workspace = _col(r, 9)
    markdown = _with_identity(markdown, _col(r, 5) or int(memo_id),
                              _col(r, 6), workspace)

    # LEFT JOIN, and the name from whichever side still holds it.
    #
    # An inner join dropped a deleted source out of this list altogether, and
    # the reader builds its filename -> document_id map from this list - so
    # every citation naming that file quietly stopped being a citation and
    # read as ordinary prose. A memorandum that loses its evidence must say
    # so. The row survives the delete and carries the name (migration 028), so
    # the source is still listed, marked removed, and its citations render as
    # present and not clickable.
    sources = _sql(
        """
        SELECT ms.document_id,
               COALESCE(d.filename, ms.filename) AS filename,
               d.document_id IS NULL AS removed
        FROM memo_source ms
        LEFT JOIN document d
               ON d.document_id = ms.document_id
              AND d.tenant_id = ms.tenant_id
        WHERE ms.tenant_id = :t AND ms.memo_id = :m
        """,
        [_p("t", tenant_id), _p("m", int(memo_id))],
    )

    # No PDF link here. The PDF is a view of the memo, rendered on demand from
    # the markdown, so it is always current with whatever the renderer does
    # today. Serving a file rendered weeks ago meant a presentation
    # improvement never reached a memo already written.

    # Sections of this revision the model rewrote, and at whose prompt. A
    # reader must never have to guess which words a person wrote and which a
    # model did.
    #
    # source says which: NULL at a person's prompt, 'update' from Update
    # (migration 039), with the revision Update wrote it under.
    rewritten = _sql(
        """
        SELECT section_heading, prompted_by, model_id, completed_at,
               source, config_revision
        FROM memo_rewrite
        WHERE tenant_id = :t AND accepted_in_memo_id = :m
        ORDER BY rewrite_id
        """,
        [_p("t", tenant_id), _p("m", int(memo_id))],
    )

    return {
        "memo_id": int(memo_id),
        "generated_at": _col(r, 2),
        "generated_by": _col(r, 3),
        "parent_memo_id": _col(r, 5),
        "revision": _col(r, 6),
        "label": "%s.%s" % (_col(r, 5) or int(memo_id), _col(r, 6)),
        "modified_by": _col(r, 7),
        "modified_at": _col(r, 8),
        # The workspace's name, null for a memo from before workspaces.
        "workspace": workspace,
        "markdown": markdown,
        "sources": [{"document_id": _col(s, 0),
                     # A source deleted before migration 028 ran has no name
                     # anywhere. Said rather than left blank.
                     "filename": _col(s, 1) or "a deleted document",
                     "removed": bool(_col(s, 2))}
                    for s in sources.get("records", [])],
        "rewrites": [{"section_heading": _col(w, 0), "prompted_by": _col(w, 1),
                      "model_id": _col(w, 2), "completed_at": _col(w, 3),
                      "source": _col(w, 4), "config_revision": _col(w, 5)}
                     for w in rewritten.get("records", [])],
    }


def revise_memo(tenant_id, email, memo_id, markdown, rewrite_ids=None,
                config_revision=None, add_sources=False):
    """Save an edited memo as a NEW row. The original and its PDF are never
    touched: a compliance record is not overwritten, and which version anyone
    read stays answerable.

    Sources carry forward - the revision rests on the same documents. Claims
    do not. A claim binds a generated sentence to the values behind it, and
    once a person has rewritten that sentence the binding describes text that
    no longer exists. The editor's review is the evidence for a revision; that
    is what signing off means, and it belongs to a person rather than to the
    machinery.

    TWO THINGS ONLY UPDATE ASKS FOR, and every other caller leaves alone.

    config_revision names the revision the new row records. Absent, the
    parent's is inherited, as it always has been. Update passes the revision
    its sections were written under, which may be newer or older than the
    parent's: an administrator can select an earlier one.

    add_sources lets a citation name a document filed in the memo's
    engagement since its root was written. Update writes from every document
    now on file, so its text cites documents the root never had. Each one the
    text cites is checked against the engagement's filed, active documents
    and added to the new revision's sources; the check refuses anything else
    exactly as it did.

    THE IDENTITY ROWS ARE TAKEN OUT FIRST. get_memo fills the parent's number
    and version into the text the editor started from; stored, they would
    name the parent in the revision. They are filled in again, right, when
    the revision is read.
    """
    markdown = _without_identity(markdown)
    parent = _sql(
        """
        SELECT s3_key, template_key, config_revision, parent_memo_id, revision,
               engagement_id, state, workspace_id
        FROM memo WHERE tenant_id = :t AND memo_id = :m
        """,
        [_p("t", tenant_id), _p("m", int(memo_id))],
    )
    records = parent.get("records", [])
    if not records:
        return None

    parent_key = _col(records[0], 0)
    template_key = _col(records[0], 1)
    if config_revision is None:
        config_revision = _col(records[0], 2)
    root_id = _col(records[0], 3) or int(memo_id)
    # Both inherited from the memo being revised (migration 030). The
    # engagement because a revision is the same matter as its parent, and the
    # state because a memorandum and its revisions are one document to the
    # person who wrote it: revising something archived must not quietly
    # unarchive it and put it back in the list.
    parent_engagement = _col(records[0], 5)
    parent_state = _col(records[0], 6) or "live"
    # And the workspace: a revision is written under its parent's
    # configuration series, and Update's revision is one of that series.
    parent_workspace = config.workspace_of(tenant_id, _col(records[0], 7))

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

    # Documents filed in the engagement since, by filename, for Update only.
    # Filed and active: the set composition writes from. One file can hold
    # several documents sharing its name, so a name maps to every one.
    filed_since = {}
    if add_sources and parent_engagement is not None:
        for r in _sql(
                """
                SELECT document_id, filename FROM document
                WHERE tenant_id = :t AND engagement_id = :e
                  AND workspace_id = :w
                  AND state = 'filed' AND active = 1
                """,
                [_p("t", tenant_id), _p("e", int(parent_engagement)),
                 _p("w", parent_workspace)],
        ).get("records", []):
            if _col(r, 1) not in known:
                filed_since.setdefault(_col(r, 1), []).append(_col(r, 0))

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

    unknown = sorted(c for c in cited
                     if c not in known and c not in filed_since)
    if unknown:
        raise ValueError(
            "these citations name documents that are not sources of this "
            "memo: " + ", ".join(unknown[:6]))

    # Rewrites the person accepted into this revision. Checked BEFORE anything
    # is written, so a bad id refuses the whole save rather than producing a
    # revision whose record of model-written sections is incomplete. Each must
    # belong to this tenant and to the memo being revised, must have finished,
    # and must not already sit in another revision.
    accepted = sorted({int(r) for r in (rewrite_ids or [])})
    if accepted:
        slots = ", ".join(":r%d" % i for i in range(len(accepted)))
        eligible = _sql(
            """
            SELECT rewrite_id FROM memo_rewrite
            WHERE tenant_id = :t AND memo_id = :m AND status = 'done'
              AND accepted_in_memo_id IS NULL
              AND rewrite_id IN (%s)
            """ % slots,
            [_p("t", tenant_id), _p("m", int(memo_id))]
            + [_p("r%d" % i, r) for i, r in enumerate(accepted)],
        )
        found = {_col(r, 0) for r in eligible.get("records", [])}
        missing = [r for r in accepted if r not in found]
        if missing:
            raise ValueError(
                "these rewrites cannot be saved into this revision: "
                + ", ".join(str(r) for r in missing[:6]))

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
          (tenant_id, workspace_id, engagement_id, template_key,
           config_revision, s3_bucket, s3_key, s3_version_id, sha256,
           parent_memo_id, revision, state, modified_by, modified_at)
        VALUES
          (:tenant_id, :workspace_id, :engagement_id, :template_key,
           :config_revision, :s3_bucket, :s3_key, :s3_version_id, :sha256,
           :parent_memo_id, :revision, :state, :modified_by, UTC_TIMESTAMP())
        """,
        [
            _p("tenant_id", tenant_id),
            _p("workspace_id", parent_workspace),
            _p("engagement_id", parent_engagement),
            _p("template_key", template_key),
            _p("config_revision", config_revision),
            _p("s3_bucket", CURATED_BUCKET),
            _p("s3_key", new_key),
            _p("s3_version_id", put.get("VersionId")),
            _p("sha256", sha),
            _p("parent_memo_id", root_id),
            _p("revision", next_revision),
            _p("state", parent_state),
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

    # And the documents filed since that this text cites (Update only).
    added = sorted({d for name in cited if name in filed_since
                    for d in filed_since[name]})
    for document_id in added:
        _sql(
            """
            INSERT IGNORE INTO memo_source (memo_id, document_id, tenant_id)
            VALUES (:new_id, :d, :t)
            """,
            [_p("new_id", new_id), _p("d", document_id), _p("t", tenant_id)],
        )

    # The record that this revision carries model-written sections. Set once:
    # a rewrite already accepted elsewhere is never moved.
    if accepted:
        slots = ", ".join(":r%d" % i for i in range(len(accepted)))
        _sql(
            """
            UPDATE memo_rewrite SET accepted_in_memo_id = :new_id
            WHERE tenant_id = :t AND memo_id = :m AND status = 'done'
              AND accepted_in_memo_id IS NULL
              AND rewrite_id IN (%s)
            """ % slots,
            [_p("new_id", new_id), _p("t", tenant_id),
             _p("m", int(memo_id))]
            + [_p("r%d" % i, r) for i, r in enumerate(accepted)],
        )

    _lambda.invoke(
        FunctionName=RENDER_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps({"tenant_id": tenant_id, "memo_id": new_id}))

    # The work is now a revision, so the kept copy of it is finished. Cleared,
    # not deleted: a copy left behind would reopen on the old memo and offer
    # to save the same changes twice. A failure here must not fail a save
    # that has already happened.
    try:
        _put_working(tenant_id, email, memo_id, None, cleared_by=new_id)
    except Exception as exc:  # noqa: BLE001 - logged; the revision stands
        print("[working-not-cleared] memo=%s by=%s %r" % (memo_id, email, exc))

    print("[revised] memo=%s from=%s revision=%d by=%s rewrites=%d "
          "config_revision=%s sources_added=%d" % (
              new_id, memo_id, next_revision, email, len(accepted),
              config_revision, len(added)))

    return {"memo_id": new_id, "parent_memo_id": root_id,
            "revision": next_revision,
            "label": "%s.%s" % (root_id, next_revision),
            "config_revision": config_revision}


# --- rewriting a section ---------------------------------------------------
#
# A person writes a prompt against one or more sections and presses Go. Each
# section becomes a memo_rewrite row and one asynchronous invocation of
# composition, which holds the model call and the citation masking. Nothing
# about the memo changes: a rewrite is saved only by revise, and only if the
# person accepted it.

# Bounds on one Go. The section count is the largest template any plan allows
# (plans spec, 50 sections per template). The prompt bound keeps a poll of
# every row in one Go well inside the Data API's 1 MiB response limit.
_REWRITE_MAX_SECTIONS = 50
_REWRITE_MAX_PROMPT = 4000
_REWRITE_POLL_LATEST = 10

# What a person is told when composition could not be asked to rewrite a
# section (ERR-02). The row's error is shown as written; the exception is
# logged.
REWRITE_NOT_STARTED = ("The rewrite could not be started because of a fault "
                       "on our side. Try it again.")


def start_rewrites(tenant_id, email, memo_id, sections):
    """Record each section's rewrite and start it. Returns the rows started.

    Every section is checked before any row is written, so a bad section
    refuses the Go rather than starting half of it."""
    memo = _sql("SELECT memo_id, workspace_id FROM memo "
                "WHERE tenant_id = :t AND memo_id = :m",
                [_p("t", tenant_id), _p("m", int(memo_id))])
    if not memo.get("records"):
        return None
    workspace_id = config.workspace_of(tenant_id,
                                       _col(memo["records"][0], 1))

    if not isinstance(sections, list) or not sections:
        raise ValueError("no sections were given to rewrite")
    if len(sections) > _REWRITE_MAX_SECTIONS:
        raise ValueError("at most %d sections can be rewritten at once"
                         % _REWRITE_MAX_SECTIONS)

    checked = []
    for s in sections:
        heading = str((s or {}).get("heading") or "").strip()
        text = str((s or {}).get("text") or "")
        prompt = str((s or {}).get("prompt") or "").strip()
        if not heading or len(heading) > 512:
            raise ValueError("every section needs a heading of at most 512 "
                             "characters")
        if not text.strip():
            raise ValueError("%s has no text to rewrite" % heading)
        if not prompt:
            raise ValueError("%s has no prompt" % heading)
        if len(prompt) > _REWRITE_MAX_PROMPT:
            raise ValueError("the prompt for %s is longer than %d characters"
                             % (heading, _REWRITE_MAX_PROMPT))
        checked.append((heading, text, prompt))

    started = []
    for heading, text, prompt in checked:
        created = _sql(
            """
            INSERT INTO memo_rewrite
              (tenant_id, workspace_id, memo_id, section_heading, prompt,
               prompted_by, input_text, status)
            VALUES
              (:t, :w, :m, :heading, :prompt, :who, :input, 'running')
            """,
            [_p("t", tenant_id), _p("w", workspace_id), _p("m", int(memo_id)),
             _p("heading", heading), _p("prompt", prompt),
             _p("who", email), _p("input", text)],
        )
        rewrite_id = created.get("generatedFields", [{}])[0].get("longValue")

        status = "running"
        try:
            _lambda.invoke(
                FunctionName=COMPOSITION_FUNCTION,
                InvocationType="Event",
                Payload=json.dumps({"action": "rewrite",
                                    "tenant_id": tenant_id,
                                    "rewrite_id": rewrite_id}))
        except Exception as exc:  # noqa: BLE001 - recorded on the row
            # Left running, the row would be polled for ever. The row carries
            # the sentence and the log carries the exception (ERR-02).
            print("[rewrite-not-started] tenant=%s memo=%s rewrite=%s %r" % (
                tenant_id, memo_id, rewrite_id, exc))
            status = "failed"
            _sql(
                """
                UPDATE memo_rewrite
                SET status = 'failed', error = :e, completed_at = UTC_TIMESTAMP()
                WHERE tenant_id = :t AND rewrite_id = :r AND status = 'running'
                """,
                [_p("e", REWRITE_NOT_STARTED),
                 _p("t", tenant_id), _p("r", rewrite_id)],
            )

        started.append({"rewrite_id": rewrite_id, "section_heading": heading,
                        "status": status})

    print("[rewrites-started] tenant=%s memo=%s sections=%d by=%s" % (
        tenant_id, memo_id, len(started), email))
    return {"memo_id": int(memo_id), "rewrites": started}


def list_rewrites(tenant_id, memo_id, ids=None):
    """How the rewrites are going, and the text of any that have finished.

    Named ids are what the screen polls while a Go is running. With none, the
    latest few for the memo, so a reloaded page can find its work again.

    The text is read one row at a time. A section's rewrite can run to
    thousands of words, and fifty in one result would pass the Data API's
    1 MiB response limit - which terminates the call rather than truncating
    it."""
    params = [_p("t", tenant_id), _p("m", int(memo_id))]
    if ids:
        wanted = sorted({int(x) for x in str(ids).split(",") if x.strip()})
        if not wanted:
            raise ValueError("no rewrite ids were given")
        if len(wanted) > _REWRITE_MAX_SECTIONS:
            raise ValueError("at most %d rewrites can be read at once"
                             % _REWRITE_MAX_SECTIONS)
        slots = ", ".join(":r%d" % i for i in range(len(wanted)))
        scope = "AND rewrite_id IN (%s) ORDER BY rewrite_id" % slots
        params += [_p("r%d" % i, r) for i, r in enumerate(wanted)]
    else:
        scope = "ORDER BY rewrite_id DESC LIMIT %d" % _REWRITE_POLL_LATEST

    result = _sql(
        """
        SELECT rewrite_id, section_heading, prompt, prompted_by, status,
               error, citations_dropped, tokens_in, tokens_out, model_id,
               created_at, completed_at, accepted_in_memo_id, source,
               config_revision, input_text = '' AS adds_section
        FROM memo_rewrite
        WHERE tenant_id = :t AND memo_id = :m
        """ + scope,
        params,
    )

    rows = []
    for r in result.get("records", []):
        row = {
            "rewrite_id": _col(r, 0),
            "section_heading": _col(r, 1),
            "prompt": _col(r, 2),
            "prompted_by": _col(r, 3),
            "status": _col(r, 4),
            "error": _col(r, 5),
            "citations_dropped": _col(r, 6),
            "tokens_in": _col(r, 7),
            "tokens_out": _col(r, 8),
            "model_id": _col(r, 9),
            "created_at": _col(r, 10),
            "completed_at": _col(r, 11),
            "accepted_in_memo_id": _col(r, 12),
            # NULL at a person's prompt, 'update' from Update (039).
            "source": _col(r, 13),
            "config_revision": _col(r, 14),
            # An Update row for a section new in the template replaces
            # nothing: it is added at the end. Said by the row, so the screen
            # never decides it from a heading that may happen to match one.
            "adds_section": bool(_col(r, 15)),
            "output_text": None,
        }
        if row["status"] == "done":
            text = _sql(
                "SELECT output_text FROM memo_rewrite "
                "WHERE tenant_id = :t AND rewrite_id = :r",
                [_p("t", tenant_id), _p("r", row["rewrite_id"])],
            ).get("records", [])
            row["output_text"] = _col(text[0], 0) if text else None
        rows.append(row)

    return {"memo_id": int(memo_id), "rewrites": rows}


# --- updating a saved memo -------------------------------------------------
#
# Every section written again from the configuration in use and the documents
# filed now, by composition, with what is new set beside the saved text as a
# memo_rewrite row per changed section (source 'update', migration 039). The
# saved text is never changed by it: what is accepted is saved through
# revise, which takes the revision and any documents filed since from the
# rows themselves.
#
# The run's progress is an object in the curated bucket, as a proposal's is.
# A row cannot say an Update finished with nothing to change, because there
# would be no row; the object can.

_RUN = re.compile(r"^[0-9a-f]{32}$")


def _update_key(tenant_id, memo_id, run):
    """MIRRORED in lambda/composition/app.py, which finishes what this
    starts. The two must not drift."""
    return "tenants/%d/updates/memos/%d/%s.json" % (
        int(tenant_id), int(memo_id), run)


def update_memo(tenant_id, email, memo_id, idempotency_key):
    """Charge for one Update and start it. Returns the run to poll.

    CHARGED AS A GENERATION, memo_generated, on the click (decision of 16
    October 2026). Every refusal below is above the charge, as generate's
    are: a memo that cannot be updated must not take a dollar on its way to
    failing. A run that fails after the charge is refunded (UX02 20.1): here
    when composition cannot be started, by composition when the run fails.
    A run that finishes with some sections failed is not - it delivered.

    THE REVISION IN USE, read here once and carried in the event, so the
    revision charged for is the revision that runs."""
    found = _sql(
        """
        SELECT template_key, engagement_id, parent_memo_id, revision,
               workspace_id
        FROM memo WHERE tenant_id = :t AND memo_id = :m
        """,
        [_p("t", tenant_id), _p("m", int(memo_id))]).get("records", [])
    if not found:
        return None
    template_key = _col(found[0], 0)
    # The memo's own workspace: an Update rewrites it under the configuration
    # now in use THERE, never another workspace's.
    workspace_id = config.workspace_of(tenant_id, _col(found[0], 4))
    engagement = _col(found[0], 1)
    label = "%s.%s" % (_col(found[0], 2) or int(memo_id), _col(found[0], 3))

    if engagement is None:
        raise ValueError("this memorandum belongs to no engagement, so there "
                         "is nothing to update it from")

    revision = config.active_revision(tenant_id, workspace_id)
    registry_now = config.load(tenant_id, workspace_id, revision)
    if not registry_now.has_template(template_key):
        raise ValueError("this memorandum is not in the configuration in "
                         "use, so it cannot be updated")

    paid = wallet.charge(
        tenant_id, email, "memo_generated", 1,
        reference=registry_now.label_for_template(template_key)
                  + " - update of memo " + label,
        idempotency_key=idempotency_key)

    # THE RUN IS THE CHARGE'S, derived from its key. wallet.charge answers a
    # repeated key with repeated rather than refusing it, so a retry of the
    # same click lands here having paid nothing - and must be given the run
    # it already paid for, not start a second one for free.
    run = hashlib.sha256(("%s|%s|%s" % (
        tenant_id, memo_id, idempotency_key)).encode("utf-8")
    ).hexdigest()[:32]
    if (paid or {}).get("repeated"):
        print("[update-repeated] tenant=%s memo=%s run=%s" % (
            tenant_id, memo_id, run))
        return {"status": "repeated", "memo_id": int(memo_id), "run": run,
                "config_revision": revision}

    started_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")

    entry_id = (paid or {}).get("entry_id")
    state = {"status": "running", "run": run, "memo_id": int(memo_id),
             "config_revision": revision, "requested_by": email,
             "started_at": started_at}

    # Written before the invocation, so the first poll finds a run rather
    # than nothing.
    _s3.put_object(
        Bucket=CURATED_BUCKET, Key=_update_key(tenant_id, memo_id, run),
        Body=json.dumps(state).encode("utf-8"),
        ContentType="application/json")

    try:
        _lambda.invoke(
            FunctionName=COMPOSITION_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps({"action": "update", "tenant_id": tenant_id,
                                "workspace_id": workspace_id,
                                "memo_id": int(memo_id),
                                "engagement_id": int(engagement),
                                "template_key": template_key,
                                "config_revision": revision,
                                "run": run, "requested_by": email,
                                "entry_id": entry_id}))
    except Exception as exc:  # noqa: BLE001 - refunded, then reported
        # Left running, the screen would poll a run nothing will finish.
        print("[update-not-started] tenant=%s memo=%s run=%s %r" % (
            tenant_id, memo_id, run, exc))
        given = _refund_generation(tenant_id, email, entry_id,
                                   "update invoke: %s" % type(exc).__name__)
        state.update(status="failed", error=GENERATE_NOT_STARTED,
                     refunded=bool(given.get("refunded")),
                     amount_cents=given.get("amount_cents") or 0)
        try:
            _s3.put_object(
                Bucket=CURATED_BUCKET,
                Key=_update_key(tenant_id, memo_id, run),
                Body=json.dumps(state).encode("utf-8"),
                ContentType="application/json")
        except Exception as put_exc:  # noqa: BLE001 - the answer says it
            print("[update-state-not-written] memo=%s run=%s %r" % (
                memo_id, run, put_exc))
        return {"status": "failed", "memo_id": int(memo_id), "run": run,
                "config_revision": revision, "error": GENERATE_NOT_STARTED,
                "refunded": state["refunded"],
                "amount_cents": state["amount_cents"]}

    print("[update-started] tenant=%s memo=%s run=%s revision=%s by=%s" % (
        tenant_id, memo_id, run, revision, email))
    return {"status": "started", "memo_id": int(memo_id), "run": run,
            "config_revision": revision}


def update_progress(tenant_id, memo_id, run):
    """How an Update is going. Finished, it names the rows written, and the
    rows themselves come with it so the screen needs no second call."""
    if not _RUN.match(str(run or "")):
        raise ValueError("no update was named")
    if not _own_memo(tenant_id, memo_id):
        return None
    try:
        body = _s3.get_object(
            Bucket=CURATED_BUCKET,
            Key=_update_key(tenant_id, memo_id, run))["Body"].read()
    except ClientError as exc:
        # As memo_working: a missing key reads as AccessDenied to a role
        # without ListBucket.
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404", "AccessDenied", "403"):
            return None
        raise
    state = json.loads(body.decode("utf-8"))

    ids = state.get("rewrite_ids") or []
    state["rewrites"] = []
    if state.get("status") == "done" and ids:
        state["rewrites"] = list_rewrites(
            tenant_id, memo_id, ",".join(str(i) for i in ids))["rewrites"]
    return state


def _update_revision(tenant_id, memo_id, rewrite_ids):
    """The revision a save takes from the Update rows it accepts, or None
    where it accepts none.

    Rows from two Updates run under different revisions cannot both be
    right about which configuration the new revision was written under, so
    such a save is refused rather than given one of the two."""
    wanted = sorted({int(r) for r in (rewrite_ids or [])})
    if not wanted:
        return None
    slots, params = _in_list(wanted, "r")
    found = _sql(
        """
        SELECT DISTINCT config_revision FROM memo_rewrite
        WHERE tenant_id = :t AND memo_id = :m AND source = 'update'
          AND rewrite_id IN (%s)
        """ % slots,
        [_p("t", tenant_id), _p("m", int(memo_id))] + params,
    ).get("records", [])
    revisions = {_col(r, 0) for r in found}
    if len(revisions) > 1:
        raise ValueError("these sections come from updates made under "
                         "different configurations. Accept the sections of "
                         "one update, save, and update again.")
    return revisions.pop() if revisions else None


# --- work in progress on a memo -------------------------------------------
#
# Prompts typed, rewrites accepted, hand edits - everything short of a saved
# revision. Held only in the browser, it was lost to Close, Back, a reload or
# opening another memo. Kept here instead, the same answer as the proposal's
# working copy and for the same reason.
#
# One copy per memo per person: two people revising the same memo do not
# overwrite each other. Stored opaque - the screen owns its shape.
#
# In the curated bucket beside the memos, under working/. Nothing watches that
# bucket, so a write here starts nothing.

_WORKING_MAX_BYTES = 4 * 1024 * 1024


def _working_key(tenant_id, memo_id, email):
    # The person's address is hashed rather than written into the key: an
    # address can carry characters a key should not, and the key is not
    # where who-did-what is recorded.
    who = hashlib.sha256((email or "").strip().lower().encode("utf-8"))
    return "tenants/%d/working/memos/%d/%s.json" % (
        tenant_id, int(memo_id), who.hexdigest()[:32])


def _own_memo(tenant_id, memo_id):
    found = _sql("SELECT memo_id FROM memo WHERE tenant_id = :t AND memo_id = :m",
                 [_p("t", tenant_id), _p("m", int(memo_id))])
    return bool(found.get("records"))


def _put_working(tenant_id, email, memo_id, working, cleared_by=None):
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    stored = {"working": working, "saved_by": email, "saved_at": now}
    if cleared_by is not None:
        stored["cleared_by_revision"] = cleared_by
    body = json.dumps(stored, ensure_ascii=False).encode("utf-8")
    if len(body) > _WORKING_MAX_BYTES:
        raise ValueError("these changes are too large to keep")
    _s3.put_object(Bucket=CURATED_BUCKET,
                   Key=_working_key(tenant_id, memo_id, email),
                   Body=body, ContentType="application/json")
    return now


def memo_working(tenant_id, email, memo_id):
    """The person's unsaved work on a memo, or none."""
    if not _own_memo(tenant_id, memo_id):
        return None
    try:
        body = _s3.get_object(
            Bucket=CURATED_BUCKET,
            Key=_working_key(tenant_id, memo_id, email))["Body"].read()
    except ClientError as exc:
        # Nothing kept is the ordinary case. S3 reports a missing key as
        # NoSuchKey, or as AccessDenied to a caller without ListBucket, which
        # this role is. Anything else is a real failure and is not hidden -
        # the screen must not mistake an unreadable copy for no copy.
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404", "AccessDenied", "403"):
            return {"memo_id": int(memo_id), "working": None}
        raise
    stored = json.loads(body.decode("utf-8"))
    return {"memo_id": int(memo_id), "working": stored.get("working"),
            "saved_at": stored.get("saved_at")}


def _has_unsaved(tenant_id, email, memo_id):
    """Whether this person keeps unsaved work on this memo - the rule the
    memo page's own Share button follows, so "Share a memo" greys out the
    same memoranda. Per person: a colleague's unsaved work greys nothing out
    for anybody else. An unreadable copy counts as unsaved, so a memo is
    never offered on a guess.

    A KEPT COPY IS NOT ALWAYS UNSAVED WORK (UNDO-01). After Discard the copy
    holds the memo's own text and the step that undoes the Discard, and the
    memo page offers Share. The screen writes unsaved: false on such a copy,
    and that is what is read; a copy that does not say - kept before undo -
    is unsaved, as every copy was."""
    try:
        body = _s3.get_object(
            Bucket=CURATED_BUCKET,
            Key=_working_key(tenant_id, memo_id, email))["Body"].read()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404", "AccessDenied", "403"):
            return False
        print("[working-unreadable] memo=%s %r" % (memo_id, exc))
        return True
    try:
        working = json.loads(body.decode("utf-8")).get("working")
    except ValueError:
        return True
    if working is None:
        return False
    return not (isinstance(working, dict) and working.get("unsaved") is False)


# The longest list "Share a memo" offers. Newest first; a memorandum older
# than the two-hundredth is still shared from its own page.
_ALL_MEMOS_LIMIT = 200


def list_all_memos(tenant_id, workspace_id, email):
    """Every live memorandum this tenant holds, across engagements, newest
    first - what "Share a memo" picks from (feature/share-multi-memo).

    THE SAME SET THE SHARE BUTTON SHARES FROM: live memoranda, each named as
    it was when it was written (list_memos explains why), with the number a
    person reads - root.revision - and the engagement it belongs to.

    unsaved IS PER PERSON, read from the same kept working copy the memo page
    keeps. A memorandum with unsaved changes is shown and not selectable, as
    its own Share button is disabled. The reads run side by side: one small
    object per memorandum, and a list of them one at a time would be slow.

    THE ACTIVE WORKSPACE'S (PACK-01), as every other list is."""
    from concurrent.futures import ThreadPoolExecutor

    rows = _sql(
        """
        SELECT m.memo_id, m.template_key, m.config_revision,
               m.parent_memo_id, m.revision, m.generated_at,
               e.name, e.subject_name, m.workspace_id
        FROM memo m
        LEFT JOIN engagement e
               ON e.engagement_id = m.engagement_id
              AND e.tenant_id = m.tenant_id
        WHERE m.tenant_id = :t AND m.workspace_id = :w AND m.state = 'live'
        ORDER BY m.generated_at DESC, m.memo_id DESC
        LIMIT %d
        """ % _ALL_MEMOS_LIMIT,
        [_p("t", tenant_id), _p("w", workspace_id)]).get("records", [])

    memos = [{
        "memo_id": _col(r, 0),
        "label": config.load(tenant_id,
                             config.workspace_of(tenant_id, _col(r, 8)),
                             _col(r, 2) or 1)
                       .label_for_template(_col(r, 1)),
        "number": "%s.%s" % (_col(r, 3) or _col(r, 0), _col(r, 4)),
        "generated_at": _col(r, 5),
        "engagement": _col(r, 6),
        "subject_name": _col(r, 7),
    } for r in rows]

    with ThreadPoolExecutor(max_workers=16) as pool:
        flags = list(pool.map(
            lambda m: _has_unsaved(tenant_id, email, m["memo_id"]), memos))
    for m, unsaved in zip(memos, flags):
        m["unsaved"] = unsaved
    return {"memos": memos, "limit": _ALL_MEMOS_LIMIT}


def keep_memo_working(tenant_id, email, memo_id, working):
    """Keep the person's unsaved work, or clear it with None."""
    if not _own_memo(tenant_id, memo_id):
        return None
    if working is not None and not isinstance(working, dict):
        raise ValueError("working must be an object or null")
    saved_at = _put_working(tenant_id, email, memo_id, working)
    return {"memo_id": int(memo_id), "saved": True, "saved_at": saved_at}


# --- settings --------------------------------------------------------------

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_LOGO_TYPES = {"image/png": ".png", "image/jpeg": ".jpg"}


def get_settings(tenant_id, role=None):
    """The tenant's name, plan and branding. Branding is returned whatever the
    plan, so a Base tenant can see what a paid plan would let them set rather
    than finding an empty screen.

    THE CALLER'S ROLE TRAVELS WITH IT. Branding has two server gates -
    _require_branding refuses a member and refuses a plan below Business - and
    the screen could only see one of them, so a member on Business was shown
    live swatches that answered 403 on the first click. The role is returned
    so the screen can disable them and say why, which is what it already does
    for the plan. It is NOT the control: _require_branding is."""
    result = _sql(
        """
        SELECT name, plan, brand_logo_key, brand_deep, brand_mid,
               brand_highlight, brand_light
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

    # AI Review's plan, read as the reviewer reads it (REV-01): the
    # subscription's plan first, tenant.plan only on a trial, where there is
    # none. Display only, as may_brand is - the reviewer's own gate is the
    # control, and this lets the screen disable the switch and say why.
    subscribed = _sql(
        "SELECT p.plan_key FROM subscription s "
        "JOIN plan p ON p.plan_id = s.plan_id WHERE s.tenant_id = :t",
        [_p("t", tenant_id)]).get("records", [])
    review_plan = ((_col(subscribed[0], 0) or "") if subscribed
                   else plan).strip().lower().replace(" ", "_")

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
        # The tenant's workspaces, for the selector (PACK-01). Here because
        # this route is open to any seat and needs no workspace to answer -
        # a screen with several to choose from has to be told them before it
        # can name one. A member's list is cut to their own by the dispatcher
        # (_visible, PACK-02 C).
        "workspaces": [{"workspace_id": w["workspace_id"], "name": w["name"]}
                       for w in config.workspaces(tenant_id)],
        # How many the plan holds, null for no limit, and how many the
        # tenant has - all of them, whoever is asking (PACK-02). Display only:
        # billing.require_workspace_room is the control.
        "workspace_limit": billing.workspace_limit(tenant_id),
        "workspaces_held": billing.workspaces_held(tenant_id),
        "plan": plan,
        # What the token says this caller is, echoed rather than decided here.
        "role": role,
        "may_brand": plan in ("business", "enterprise"),
        "may_remove_footer": plan == "enterprise",
        # The ARQEDIA workspace reviews whatever its plan, as the reviewer
        # allows it (_curator there, decision of 23 October 2026).
        "may_review": (review_plan in ("business", "enterprise")
                       or tenant_id == registry.PACK_TENANT),
        "logo_key": logo_key,
        "logo_url": logo_url,
        "deep": _col(r, 3),
        "mid": _col(r, 4),
        "highlight": _col(r, 5),
        "light": _col(r, 6),
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
    """Set the four colours, or clear them. Clearing returns the tenant to
    the platform palette rather than leaving a half-set page."""
    _require_branding(tenant_id, role)

    fields, params = [], [_p("t", tenant_id)]
    for key, column in (("deep", "brand_deep"),
                        ("mid", "brand_mid"),
                        ("highlight", "brand_highlight"),
                        ("light", "brand_light")):
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
        return get_settings(tenant_id, role)

    _sql("UPDATE tenant SET " + ", ".join(fields) + " WHERE tenant_id = :t",
         params)
    return get_settings(tenant_id, role)


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
    return get_settings(tenant_id, role)


# --- uploads and generation ------------------------------------------------

_FOLDER_MAX = 255
_NOT_ASCII_PRINTABLE = re.compile(r"[^\x20-\x7e]")


def _folder(name):
    """A folder name, made safe to travel as S3 user metadata (18.7).

    NOT _clean(). That exists to make a string safe for a storage KEY and
    would turn "2024 Statutory Accounts" into "2024-Statutory-Accounts". This
    is provenance a person reads, so it keeps its spaces and its case.

    WHAT IT DOES STRIP IS FORCED BY S3, not chosen here: AWS documents
    user-defined metadata as US-ASCII only, capped at 2 KB across every key
    and value together, and says unprintable characters are dropped and
    counted in x-amz-missing-meta. So anything outside printable ASCII goes
    here rather than being rejected by storage with the upload half done, and
    the result is bounded to the column's 255 (migration 032).

    A folder named in Greek or Chinese therefore arrives thinner than it went
    in, or empty. That is a limitation of carrying it as metadata and it is
    recorded in the migration as well, because the next person will find a
    stripped folder name and look for the defect in the wrong place.

    Empty comes back as None rather than "": absent means "not a directory
    upload", and an empty string in the column would mean "the root"."""
    text = _NOT_ASCII_PRINTABLE.sub("", str(name or "")).strip()
    return text[:_FOLDER_MAX] or None


def upload_url(tenant_id, workspace_id, email, engagement, filename,
               source_folder=None):
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

    # THE ENGAGEMENT BECOMES A ROW HERE, at the moment its name is first
    # typed (migration 030). This is the only place in the product that knows
    # WHO opened it - the normalizer meets the same name later with only an
    # object and its metadata - so created_by is recorded here or nowhere.
    #
    # Nothing reads it yet: every list still matches on the S3 key, and
    # switching them over is stage 4. What this closes is the older half of
    # the problem, that an engagement with no documents did not exist at all.
    engagement_id(tenant_id, workspace_id, engagement, email)

    # THE FOLDER TRAVELS AS METADATA, as the uploader's address already does,
    # and for the same reason: this function knows it and the normalizer -
    # which writes the row - does not, so the answer has to arrive with the
    # object (18.7).
    #
    # SIGNED ONLY WHERE THERE IS ONE. Every header a presigned PUT was signed
    # with must be sent back or S3 refuses the request, so the key is in the
    # signature exactly when the browser will send it. The cleaned value goes
    # back to the caller for that purpose - the browser echoes what was
    # signed rather than working out the rule a second time, which is the
    # lesson of 17.4.
    folder = _folder(source_folder)
    metadata = {"uploaded-by": email}
    if folder:
        metadata["source-folder"] = folder

    # THE WORKSPACE IS IN THE KEY (PACK-01). Resolved here, where the request
    # is, and read off the key by the normalizer, which classifies against
    # that workspace's document types alone (decision of 22 October 2026:
    # the workspace is chosen before upload).
    #
    # NOT METADATA. It was signed as x-amz-meta-workspace-id, and every
    # header a presigned PUT is signed with must be sent back - a screen that
    # did not send it had every upload refused by S3. And in the key it
    # keeps two workspaces' engagements of one name, and the files in them,
    # from landing on the same object: the second upload would have replaced
    # the first.
    #
    # Workspace 0 - the pack tenant, which does not upload - keeps the layout
    # every document before workspaces was stored under.
    if workspace_id:
        key = "tenants/%d/w/%d/docs/%s/%s" % (tenant_id, int(workspace_id),
                                              engagement, filename)
    else:
        key = "tenants/%d/docs/%s/%s" % (tenant_id, engagement, filename)
    url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": DOCS_BUCKET, "Key": key,
                "ServerSideEncryption": "aws:kms",
                "Metadata": metadata},
        ExpiresIn=900)
    # BOTH CLEANED NAMES GO BACK (17.3, 17.4).
    #
    # The engagement, because _clean turned "TEST - 2" into "TEST-2" here and
    # the screen kept what was typed: it polled an engagement that existed
    # nowhere, the pending list matched no rows, the upload sat on
    # "analysing" for ever, and two perfectly good documents waited under a
    # name nobody was looking at. The caller is told what the name became,
    # and navigates to that.
    #
    # The filename for the same reason one step later. The screen watches for
    # the row an upload produces, and matching needs the name the row will
    # carry - which is this one, because the normalizer reads the filename
    # off the key. It used to work that name out itself, with a copy of
    # _clean in TypeScript: two implementations of the rule that decides
    # where a file is kept, agreeing today and one edit away from not. The
    # browser holds no rule now and is told.
    return {"url": url, "key": key, "uploaded_by": email,
            "engagement": engagement, "filename": filename,
            # Null where there was none, and the browser then sends no header
            # at all - which is what keeps the request and the signature in
            # step (18.7).
            "source_folder": folder,
            # Which workspace the file was filed into, for the screen to say.
            # Carried by the key, so the browser sends nothing for it.
            "workspace_id": workspace_id}


def templates(tenant_id, workspace_id):
    """The memoranda this workspace can write, at its active revision.

    A tenant may hold a credit, a KYC and a lender template over the same
    documents. The documents are extracted once; which memo is written from
    them is a choice made at generation."""
    return config.for_workspace(tenant_id, workspace_id).template_list()


# --- a generation's run (UX02 20.1) -----------------------------------------
#
# A generation is charged here and written by composition, minutes later, in
# another function. The memo list could say a memo had arrived and could not
# say one never would: a run that failed left the screen waiting until it
# gave up, and the dollar gone. The run's progress is an object in the curated
# bucket, as an Update's is, and it is what says a generation failed and that
# its charge came back.

# What a person is told when composition could not even be started.
GENERATE_NOT_STARTED = ("The memorandum could not be started because of a "
                        "fault on our side. Try it again.")


def _generate_key(tenant_id, engagement_id, run):
    """MIRRORED in lambda/composition/app.py, which finishes what this
    starts. The two must not drift."""
    return "tenants/%d/runs/generate/%d/%s.json" % (
        int(tenant_id), int(engagement_id), run)


def _put_generate(tenant_id, engagement_id, run, state):
    _s3.put_object(Bucket=CURATED_BUCKET,
                   Key=_generate_key(tenant_id, engagement_id, run),
                   Body=json.dumps(state).encode("utf-8"),
                   ContentType="application/json")


def _refund_generation(tenant_id, email, entry_id, why):
    """Give a generation's charge back. Never raises: it is already handling
    a failure, and a refund that throws would lose the money and the record
    of the failure both. Returns what wallet.refund_generation answered, or
    refunded False where it could not be asked."""
    try:
        given = wallet.refund_generation(tenant_id, entry_id, email)
    except Exception as exc:  # noqa: BLE001 - reported on the run instead
        print("[refund-failed] tenant=%s entry=%s %r" % (
            tenant_id, entry_id, exc))
        return {"refunded": False, "amount_cents": 0, "repeated": False}
    print("[generation-refunded] tenant=%s entry=%s why=%s refunded=%s "
          "repeated=%s cents=%s" % (tenant_id, entry_id, why,
                                    given.get("refunded"), given.get("repeated"),
                                    given.get("amount_cents")))
    return given


def generate_progress(tenant_id, engagement_id, run):
    """How one generation is going, or None where nothing is recorded for it
    - a run started before this existed, or one whose first write has not
    landed. The screen keeps polling the memo list either way."""
    if not _RUN.match(str(run or "")):
        raise ValueError("no generation was named")
    try:
        body = _s3.get_object(
            Bucket=CURATED_BUCKET,
            Key=_generate_key(tenant_id, engagement_id, run))["Body"].read()
    except ClientError as exc:
        # As memo_working: a missing key reads as AccessDenied to a role
        # without ListBucket.
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404", "AccessDenied", "403"):
            return None
        raise
    return json.loads(body.decode("utf-8"))


def generate(tenant_id, workspace_id, email, engagement, template_key=None,
             idempotency_key=None):
    """Composition takes over a minute, so this starts it and returns. The
    caller polls the memo list, and the run (generate_progress).

    The template is validated HERE rather than left to composition. The
    invocation is asynchronous, so a bad key would otherwise fail four minutes
    later in a log nobody is watching, having returned 202 to a caller that
    thinks a memo is being written.

    TWO REFUSALS, NOT ONE (18.12). Nothing published and a key that does not
    exist are different faults and read differently: the first is a workspace
    that has not been set up, the second is a bad request. Both are 400 and
    neither charges - the money moves below.

    ONE WORKSPACE. The memo is written under that workspace's configuration
    in use, from that workspace's documents, and records the workspace."""
    registry_now = config.for_workspace(tenant_id, workspace_id)

    # Asked for nothing, and there is no default to fall back on.
    if not template_key and registry_now.TEMPLATE_KEY is None:
        raise ValueError(NO_TEMPLATE_PUBLISHED)

    template_key = template_key or registry_now.TEMPLATE_KEY

    if not registry_now.has_template(template_key):
        raise ValueError("no such template: %s" % template_key)

    # THE ENGAGEMENT IS RESOLVED HERE, BEFORE THE CHARGE, and its id travels
    # in the payload (13.3 stage 4). Composition reads its values by
    # engagement_id and holds no copy of _clean; the name stays in the
    # payload because the memo's storage key is built from it and because
    # every log line about a memo names it.
    #
    # Before the charge for the same reason the template is: an engagement
    # that does not exist must not take a dollar on its way to failing.
    found = engagement_named(tenant_id, workspace_id, engagement)
    if found is None:
        raise ValueError(NO_SUCH_ENGAGEMENT % engagement)

    paid = wallet.charge(
        tenant_id, email, "memo_generated", 1,
        reference=registry_now.label_for_template(template_key)
                  + " - " + engagement,
        idempotency_key=idempotency_key)
    entry_id = (paid or {}).get("entry_id")

    answer = {"engagement": engagement, "template_key": template_key,
              "template": registry_now.label_for_template(template_key)}

    # THE RUN IS THE CHARGE'S, derived from its key, as Update's is. A repeat
    # of the same click has paid nothing (wallet.charge answers repeated), so
    # it is given the run already paid for rather than starting a second
    # memo for one charge - the defect found on 16 October 2026.
    run = hashlib.sha256(("%s|%s|%s" % (
        tenant_id, found["engagement_id"], idempotency_key)).encode("utf-8")
    ).hexdigest()[:32]
    answer["run"] = run
    if (paid or {}).get("repeated"):
        print("[generate-repeated] tenant=%s engagement=%s run=%s" % (
            tenant_id, found["engagement_id"], run))
        return dict(answer, status="repeated")

    state = {"status": "running", "run": run,
             "engagement_id": int(found["engagement_id"]),
             "template_key": template_key, "entry_id": entry_id,
             "requested_by": email,
             "started_at": datetime.datetime.now(
                 datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

    # Written before the invocation, so the first poll finds a run rather
    # than nothing. A failure to write it costs the screen its failure
    # notice, not the memo: composition writes the run again when it ends.
    try:
        _put_generate(tenant_id, found["engagement_id"], run, state)
    except Exception as exc:  # noqa: BLE001 - logged; the memo still runs
        print("[generate-state-not-written] tenant=%s run=%s %r" % (
            tenant_id, run, exc))

    try:
        _lambda.invoke(
            FunctionName=COMPOSITION_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps({"tenant_id": tenant_id,
                                "workspace_id": workspace_id,
                                "engagement": engagement,
                                "engagement_id": found["engagement_id"],
                                "template_key": template_key,
                                "generated_by": email,
                                "entry_id": entry_id, "run": run}))
    except Exception as exc:  # noqa: BLE001 - refunded, then reported
        # Paid for, and nothing will ever write it. The money comes back
        # here, because there is no other function that could do it.
        print("[generate-not-started] tenant=%s run=%s %r" % (
            tenant_id, run, exc))
        given = _refund_generation(tenant_id, email, entry_id,
                                   "invoke: %s" % type(exc).__name__)
        state.update(status="failed", error=GENERATE_NOT_STARTED,
                     refunded=bool(given.get("refunded")),
                     amount_cents=given.get("amount_cents") or 0)
        try:
            _put_generate(tenant_id, found["engagement_id"], run, state)
        except Exception as put_exc:  # noqa: BLE001 - the answer says it
            print("[generate-state-not-written] tenant=%s run=%s %r" % (
                tenant_id, run, put_exc))
        return dict(answer, status="failed", error=GENERATE_NOT_STARTED,
                    refunded=state["refunded"],
                    amount_cents=state["amount_cents"])

    return dict(answer, status="started")


def document_types(tenant_id, workspace_id):
    """The tenant's own type list, with what filing each one will do - so the
    screen can say whether confirming a type triggers OCR.

    Read mode and always-OCR are properties of the TYPE now, not of a
    hard-coded table, because the type is what a person confirms."""
    return config.for_workspace(tenant_id, workspace_id).document_type_list()


# --- configuration ---------------------------------------------------------
#
# Authoring is an admin act. It changes what every future memo says, which is
# a heavier thing than uploading a document.

def _require_admin(role):
    if role != "admin":
        raise PermissionError("only an administrator may change the "
                              "configuration")


def _require_seats_admin(role):
    """Separate from _require_admin only so the message names what was
    refused. Being told "only an administrator may change the configuration"
    after trying to invite somebody is worse than no message at all."""
    if role != "admin":
        raise PermissionError(
            "only an administrator may change seats, the plan or the card")


def config_state(tenant_id, workspace_id):
    """Where this workspace stands: what is published, whether a draft is
    open, and what publishing it would flag - with the tenant's workspaces,
    so a screen can say which one it is showing."""
    revisions = registry.revisions(tenant_id, workspace_id)
    draft = next((r for r in revisions if r["is_draft"]), None)

    # forked_pack was returned here to pre-tick Get started. Signup stopped
    # asking which memorandum somebody wants, so it is NULL for every tenant
    # created from now on and the pre-tick could never fire. A field that is
    # always null is not a field, it is a question nobody answers.

    published = [r for r in revisions if not r["is_draft"]]

    state = {
        "workspace_id": workspace_id,
        "workspaces": [{"workspace_id": w["workspace_id"], "name": w["name"]}
                       for w in config.workspaces(tenant_id)],
        # NULL WHERE NOTHING IS PUBLISHED (PACK-02). config.active_revision
        # answers 1 for a workspace with none, which is right for the
        # pipeline's oldest readers and wrong on a screen: an empty
        # workspace showed "Live: revision 1", and revision 1 is another
        # workspace's - in the pack tenant, Trade Finance's.
        "active_revision": (config.active_revision(tenant_id, workspace_id)
                            if published else None),
        "revisions": published,
        "draft": draft,
        # Which memoranda exist, so a screen can name the one being edited
        # rather than leaving a person to infer it.
        "templates": config.for_workspace(
            tenant_id, workspace_id).template_list(),
    }
    if draft:
        state["validation"] = registry.validate(tenant_id, workspace_id,
                                                registry.DRAFT)
    return state


def config_read(tenant_id, workspace_id, revision):
    """A whole revision, for an editor to work on or a reader to inspect.

    Loaded through the same path the pipeline uses, so what an editor sees is
    what extraction will do. It must be a revision of the workspace asked
    about; another workspace's revision is not found here."""
    held = _sql("SELECT revision FROM config_revision "
                "WHERE tenant_id = :t AND workspace_id = :w AND revision = :r",
                [_p("t", tenant_id), _p("w", workspace_id),
                 _p("r", int(revision))]).get("records", [])
    if not held:
        raise ValueError("this workspace has no revision %d" % int(revision))
    reg = config.load(tenant_id, workspace_id, int(revision))
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


# --- configuring from the client's own memorandum ---------------------------
#
# A client arrives with a report format of his own. He gives us a copy, we
# read its shape, and we put a configuration to him for correction.
#
# THE FILE IS FORM, NOT SUBSTANCE. It goes to the review bucket under
# proposals/, which nothing watches. The docs bucket is watched: a file
# landing there is classified, filed and charged for, which is exactly what
# must not happen to a blank form somebody is showing us for its layout.

_SAMPLE_TYPES = {".pdf", ".docx"}


def _sample_prefix(tenant_id):
    return "tenants/%d/proposals/" % tenant_id


def _require_open_draft(tenant_id, workspace_id):
    """A proposal is accepted into the draft, so refusing here rather than
    after two minutes of reading is the difference between a sentence and a
    wasted wait."""
    result = _sql("SELECT revision FROM config_revision "
                  "WHERE tenant_id = :t AND workspace_id = :w "
                  "AND revision = 0",
                  [_p("t", tenant_id), _p("w", workspace_id)])
    if not result.get("records"):
        raise ValueError("open a draft before reading a memorandum into it")


def sample_upload_url(tenant_id, workspace_id, email, role, filename):
    """A signed link for the sample, as documents and logos use.

    The key is built from the token's tenant, so a caller cannot place a file
    in another tenant's space - and the prefix is proposals/, so it cannot
    place one where the normalizer would find it either."""
    _require_admin(role)
    _require_open_draft(tenant_id, workspace_id)

    filename = _clean(filename)
    if not filename:
        raise ValueError("a file name is required")

    dot = filename.rfind(".")
    if dot == -1 or filename[dot:].lower() not in _SAMPLE_TYPES:
        raise ValueError("a sample memorandum must be a PDF or a Word file")

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")
    key = _sample_prefix(tenant_id) + stamp + "-" + filename

    url = _s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": REVIEW_BUCKET, "Key": key,
                "ServerSideEncryption": "aws:kms",
                "Metadata": {"uploaded-by": email}},
        ExpiresIn=900)
    return {"url": url, "key": key, "uploaded_by": email}


def _own_sample(tenant_id, key):
    """The one place a key from a request is trusted, so it is checked here.

    The tenant still comes from the token; this only refuses a key that does
    not sit under that tenant's own proposals prefix."""
    if not key or not key.startswith(_sample_prefix(tenant_id)):
        raise ValueError("that file does not belong to this tenant")
    return key


def propose(tenant_id, workspace_id, email, role, key):
    """Start the read and return. One model call per section, so this takes
    minutes and the caller polls - the same shape as generating a memo."""
    _require_admin(role)
    _require_open_draft(tenant_id, workspace_id)
    key = _own_sample(tenant_id, key)

    # The object must be there. An invocation against a key the browser never
    # finished uploading fails two minutes later in a log nobody is watching.
    try:
        _s3.head_object(Bucket=REVIEW_BUCKET, Key=key)
    except ClientError:
        raise ValueError("that file has not finished uploading")

    _lambda.invoke(
        FunctionName=PROPOSER_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps({"tenant_id": tenant_id,
                            "workspace_id": workspace_id, "key": key,
                            "requested_by": email}))

    print("[proposal-started] tenant=%s key=%s by=%s" % (
        tenant_id, key, email))
    return {"status": "started", "key": key}


def proposal(tenant_id, key):
    """What the reader has produced so far.

    Rewritten after every section, so this is also the progress: the screen
    shows sections arriving rather than a spinner, and a function that has
    died stops being indistinguishable from one that is working."""
    key = _own_sample(tenant_id, key)

    try:
        body = _s3.get_object(Bucket=REVIEW_BUCKET,
                              Key=key + ".proposal.json")["Body"].read()
    except ClientError:
        # The invocation has not landed yet. Not an error, and not a 404 the
        # screen would have to treat as a special case.
        return {"status": "starting", "key": key}

    return json.loads(body.decode("utf-8"))


def save_working(tenant_id, key, working):
    """The decisions a person has made about a proposal, kept as they make
    them.

    Reading a report is minutes of machine time; deciding what it proposed is
    an hour of a person's. Held only in the browser, that hour was lost to a
    closed tab, a stray refresh, or an accept that stopped part way - which is
    what happened, and is why this exists.

    Beside the proposal, not inside it: the reader owns one object and the
    person owns the other, so neither can overwrite the other's work."""
    key = _own_sample(tenant_id, key)
    _s3.put_object(
        Bucket=REVIEW_BUCKET,
        Key=key + ".working.json",
        Body=json.dumps(working, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    return {"saved": True, "key": key}


def working(tenant_id, key):
    """What was decided, if anything was. Absent is the ordinary case - a
    proposal just read has nothing decided about it yet."""
    key = _own_sample(tenant_id, key)
    try:
        body = _s3.get_object(Bucket=REVIEW_BUCKET,
                              Key=key + ".working.json")["Body"].read()
    except ClientError:
        return {"key": key, "working": None}
    return {"key": key, "working": json.loads(body.decode("utf-8"))}


def proposals(tenant_id):
    """Every proposal this tenant has read and not yet accepted.

    Listed so a person can put one down and pick it up tomorrow. The sample
    itself is long gone - the reader deletes it - so what is listed here is
    the proposal and whatever was decided about it."""
    prefix = _sample_prefix(tenant_id)
    found = {}

    token = None
    while True:
        args = {"Bucket": REVIEW_BUCKET, "Prefix": prefix}
        if token:
            args["ContinuationToken"] = token
        page = _s3.list_objects_v2(**args)

        for obj in page.get("Contents", []):
            name = obj["Key"]
            if not name.endswith(".proposal.json"):
                continue
            sample = name[: -len(".proposal.json")]
            found[sample] = obj["LastModified"].strftime("%Y-%m-%dT%H:%M:%SZ")

        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")

    out = []
    for sample, at in sorted(found.items(), key=lambda kv: kv[1], reverse=True):
        try:
            body = _s3.get_object(Bucket=REVIEW_BUCKET,
                                  Key=sample + ".proposal.json")["Body"].read()
            p = json.loads(body.decode("utf-8"))
        except (ClientError, ValueError):
            continue
        out.append({
            "key": sample,
            "filename": sample.rsplit("/", 1)[-1],
            "status": p.get("status"),
            "memorandum_label": p.get("memorandum_label"),
            "sections": len(p.get("sections") or []),
            "requested_by": p.get("requested_by"),
            "read_at": at,
        })
    return {"proposals": out}


# --- AI Review of the draft (REV-01) ----------------------------------------
#
# THE REVIEWER HOLDS THE RULES. Its plan gate, the draft check, the price,
# the stale check and the charge all live in lambda/reviewer/app.py, and each
# of its answers already carries the status it means. Deciding any of them a
# second time here would be a second copy of a money rule, which is how two
# copies come to disagree. This adds the one thing every draft route adds -
# the administrator gate - and relays the rest unchanged.
#
# SYNCHRONOUS, as render_memo and preview_branding call the renderer. Every act
# answers in seconds: open starts the read with an asynchronous invocation of
# its own and returns, so nothing here waits on the model.

def _require_review_admin(role):
    """Separate from _require_admin only so the message names what was
    refused, as _require_seats_admin is. Polling a review changes nothing, and
    a member told "only an administrator may change the configuration" for
    reading one is told something untrue. The wording is the reviewer's own,
    so the two refusals read the same whichever of them answers."""
    if role != "admin":
        raise PermissionError("only an administrator may review the "
                              "configuration")


def review(tenant_id, workspace_id, email, role, action, **fields):
    """One act of a review session, relayed. Returns the reply to send.

    The tenant, email and role come from the token, via caller(), and go
    last so a field from the request can never replace them. The workspace
    was resolved against that tenant before it got here, and goes last for
    the same reason."""
    _require_review_admin(role)

    payload = dict(fields, action=action, tenant_id=tenant_id, email=email,
                   role=role, workspace_id=workspace_id)
    response = _lambda.invoke(
        FunctionName=REVIEWER_FUNCTION,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload))

    result = json.loads(response["Payload"].read())
    # An exception the reviewer did not catch comes back as errorMessage with
    # no status. Its text is the reviewer's internals, so it is logged and not
    # sent.
    if "status" not in result:
        print("[review-relay-error] action=%s tenant=%s %r" % (
            action, tenant_id, result))
        raise RuntimeError("the reviewer did not answer")
    return _reply(result["status"], result["body"])


# --- sharing ---------------------------------------------------------------
#
# IMPORTED HERE, NOT AT THE TOP. share.py imports share_rules, which reaches
# this function only through the docprocessing layer. At the top of the
# module a stale layer would take every route down with it (CLAUDE.md, first
# warning); here it takes down sharing, and says so.

SHARE_ROUTES = frozenset({
    "GET /shares",
    "POST /memos/{memo_id}/shares",
    "POST /shares/{grant_id}/revoke",
    # One email for a batch of shares just sent (feature/share-multi-memo).
    "POST /shares/notify",
})


def share_route(route, tenant_id, email, params, event, workspace=None):
    """The three share routes, and what each refusal means.

    workspace resolves the request's workspace, and is asked only by the
    History list (PACK-01): sending, revoking and notifying act on a memo or
    a grant that is already the tenant's, wherever it sits.

    ANY SEAT. Sending is the work, as filing and generating are; revoking is
    a reduction of access, and is open in every state - capped included -
    because a tenant locked out for non-payment must still be able to pull a
    memorandum back (share_viewer_spec section 6)."""
    import share

    try:
        if route == "GET /shares":
            return _reply(200, share.listing(
                tenant_id, workspace() if workspace else None))

        if route == "POST /memos/{memo_id}/shares":
            body = json.loads(event.get("body") or "{}")
            sent = share.send(tenant_id, email, params.get("memo_id"), body)
            if sent is None:
                return _reply(404, {"error": "not found"})
            return _reply(201, sent)

        if route == "POST /shares/{grant_id}/revoke":
            # The id carries a '#'. Unquoted, as an engagement name is, so it
            # reads the same whether or not the gateway decoded it first.
            grant_id = urllib.parse.unquote(params.get("grant_id") or "")
            revoked = share.revoke(tenant_id, email, grant_id)
            if revoked is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, revoked)

        if route == "POST /shares/notify":
            body = json.loads(event.get("body") or "{}")
            notified = share.notify(tenant_id, email, body.get("grant_ids"))
            if notified is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, notified)

    except share.AlreadyNotified as exc:
        return _reply(409, {"error": str(exc)})
    except share.RateLimited as exc:
        return _reply(429, {"error": str(exc)})
    except share.Capped as exc:
        return _reply(402, {"error": str(exc)})
    except share.OverageNotAccepted as exc:
        # Nothing was sent or charged. The price travels so the screen can
        # put it to the person and send again with it accepted.
        return _reply(409, {
            "error": ("This workspace has used the %s shares its plan "
                      "includes. Sending this one costs $%.2f."
                      % (exc.allowance, exc.unit_cents / 100.0)),
            "overage_cents": exc.unit_cents,
            "allowance": exc.allowance,
        })

    return _reply(404, {"error": "unknown route"})


# --- which workspaces a member may reach (PACK-02 C) -------------------------

NOT_YOUR_WORKSPACE = ("That workspace is not one of yours. An administrator "
                      "can add you to it on the seats screen.")
NO_WORKSPACE_ASSIGNED = ("No workspace is assigned to you yet. Ask an "
                         "administrator to add you to one on the seats "
                         "screen.")


REVIEW_ROUTES = frozenset({
    "POST /config/draft/review",
    "GET /config/draft/review",
    "POST /config/draft/review/accept",
    "POST /config/draft/review/close",
    "POST /config/draft/review/answer",
})


def _visible(workspaces, mine):
    """A list of workspaces narrowed to a member's own; untouched for an
    administrator (mine is None)."""
    if mine is None:
        return workspaces
    return [w for w in workspaces if int(w["workspace_id"]) in mine]


def _outside_assignment(tenant_id, params, allowed):
    """Whether a memo, document or share named in the path is in a workspace
    this caller may not reach: a DELETED one, for anybody (PACK-02 D), or one
    not assigned to a member (C). False where the row is not found: the route
    answers that itself, exactly as it does for anybody.

    A grant's id begins with its memo's ("<memo_id>#<viewer>", share_rules),
    so a share is placed by its memo."""
    if params.get("memo_id"):
        table, key = "memo", "memo_id"
        value = params.get("memo_id")
    elif params.get("document_id"):
        table, key = "document", "document_id"
        value = params.get("document_id")
    elif params.get("grant_id"):
        table, key = "memo", "memo_id"
        value = urllib.parse.unquote(params.get("grant_id")).split("#", 1)[0]
    else:
        return False
    try:
        value = int(value)
    except (TypeError, ValueError):
        return False
    found = _sql("SELECT x.workspace_id, w.deleted_at IS NOT NULL "
                 "FROM %s x LEFT JOIN workspace w "
                 "ON w.workspace_id = x.workspace_id "
                 "AND w.tenant_id = x.tenant_id "
                 "WHERE x.tenant_id = :t AND x.%s = :v" % (table, key),
                 [_p("t", tenant_id), _p("v", value)]).get("records", [])
    if not found:
        return False
    if _col(found[0], 1):
        return True
    mine = allowed()
    return mine is not None and int(_col(found[0], 0) or 0) not in mine


# --- suggestions (25 October 2026) ------------------------------------------
#
# From the rail's We want your suggestions, by any seat. Two emails and no
# row: the suggestion to the mailbox that reads them, with the sender as its
# Reply-To, and a note back to the sender saying it arrived.

SUGGESTIONS_TO = "info@arqedia.com"
_SUGGESTION_MAX = 5000
# Everything but a tab and a line break. A suggestion is prose in a plain
# text email, and a control character in it is nothing a person typed.
_SUGGESTION_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

SUGGESTION_EMPTY = "Write your suggestion first."
SUGGESTION_NOT_SENT = ("Your suggestion could not be sent just now. It is "
                       "still in the box - try again in a minute.")


def suggest(tenant_id, email, role, body):
    """Send one suggestion. Returns whether the thank-you went too, or None
    where the suggestion itself could not be sent.

    THE THANK-YOU ONLY AFTER THE SUGGESTION HAS GONE. Thanking somebody for
    something that never arrived is the one outcome worse than an error, so
    a refused send answers None, the route says so, and nothing is sent to
    them. A thank-you that fails is logged and reported; the suggestion it
    follows has still arrived."""
    text = _SUGGESTION_CONTROL.sub("", str(body.get("text") or "")).strip()
    if not text:
        raise ValueError(SUGGESTION_EMPTY)
    if len(text) > _SUGGESTION_MAX:
        raise ValueError("A suggestion can be at most %d characters. Send it "
                         "in two." % _SUGGESTION_MAX)
    page = _SUGGESTION_CONTROL.sub("", str(body.get("page") or ""))[:200]

    found = _sql("SELECT name FROM tenant WHERE tenant_id = :t",
                 [_p("t", tenant_id)]).get("records", [])
    tenant_name = (_col(found[0], 0) if found else None) or "-"

    subject, note = mail.suggestion(email, tenant_name, tenant_id, role, page,
                                    text)
    if not mail.send(SUGGESTIONS_TO, subject, note, reply_to=email):
        print("[suggestion-not-sent] tenant=%s chars=%d" % (
            tenant_id, len(text)))
        return None

    subject, note = mail.suggestion_thanks(text, SUGGESTIONS_TO)
    thanked = mail.send(email, subject, note, reply_to=SUGGESTIONS_TO)
    print("[suggestion] tenant=%s chars=%d thanked=%s" % (
        tenant_id, len(text), thanked))
    return {"sent": True, "thanked": thanked}


# --- dispatch --------------------------------------------------------------

# A request whose JSON could not be read (copy review, 17 October 2026). Every
# deliberate refusal is a ValueError and keeps its own sentence; this is the
# answer for the parser's.
REQUEST_UNREADABLE = ("That request could not be read. Reload the page and "
                      "try again.")

# A number in the address, the query or the body that is not a number
# (ERR-03): int() and float() raise ValueError, which every deliberate refusal
# also is. Request input reaches int() in dozens of places here and in the
# shared modules, so this is told apart at the one place they all arrive -
# by the interpreter's own wording, which no refusal of ours begins with.
_NOT_A_NUMBER = re.compile(
    r"^(invalid literal for int\(\)|could not convert string to float)")
REQUEST_NOT_A_NUMBER = ("That request carried something other than a number "
                        "where a number belongs. Reload the page and try "
                        "again.")


def lambda_handler(event, context):
    """Every request, and what became of it.

    ONE LINE PER REQUEST. The log carried START, END and REPORT and nothing
    else, so it could not answer "did POST /uploads arrive" - which is exactly
    what was asked of it on 18 September, when sixteen of seventeen uploads
    left no trace anywhere. Route and status are what make the log readable;
    without them an invocation count is all there is.

    NOT THE BODY, AND NOT THE EMAIL. The body carries the customer's address.
    Tenant and route identify the request well enough to follow it, and
    neither is personal data.
    """
    started = time.time()
    route = event.get("routeKey", "")
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    claims = (authorizer.get("jwt") or {}).get("claims") or {}
    tenant = claims.get("custom:tenant_id", "-")

    reply = _dispatch(event, context)

    print("[api] route=%s tenant=%s status=%s ms=%.0f" % (
        route or "-", tenant, (reply or {}).get("statusCode"),
        (time.time() - started) * 1000))
    return reply


def _dispatch(event, context):
    try:
        tenant_id, email, role = caller(event)
    except (PermissionError, ValueError, TypeError):
        return _reply(403, {"error": "no tenant on token"})

    route = event.get("routeKey", "")
    refused = _curation_only(tenant_id, route)
    if refused:
        return refused

    params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}
    engagement = urllib.parse.unquote(params.get("id", "")) \
        if params.get("id") else None

    # Which workspaces this caller may work in (PACK-02 C): None for an
    # administrator, the seat's assigned set for a member. Read at most once
    # a request, and only by a request that needs it.
    held = []

    def allowed():
        if not held:
            held.append(seats.allowed_workspaces(tenant_id, email, role))
        return held[0]

    # The workspace a route works in (PACK-01), from ?workspace= against this
    # tenant's own. Resolved only by the routes that touch configuration, so
    # a tenant with several workspaces is never asked to choose one to read
    # its wallet. Raises ValueError, answered as 400 below.
    #
    # A MEMBER, ONLY ONE ASSIGNED TO THEM (PACK-02 C). Named, it must be one
    # of theirs - refused as 403 otherwise, after the tenant check, so another
    # tenant's number is still a 400. Unnamed, the one rule as before, over
    # their own workspaces instead of the tenant's.
    def ws():
        mine = allowed()
        if mine is None:
            return config.workspace(tenant_id, query.get("workspace"))
        if query.get("workspace") not in (None, ""):
            resolved = config.workspace(tenant_id, query.get("workspace"))
            if resolved not in mine:
                raise PermissionError(NOT_YOUR_WORKSPACE)
            return resolved
        if not mine:
            raise PermissionError(NO_WORKSPACE_ASSIGNED)
        if len(mine) == 1:
            return next(iter(mine))
        raise config.WorkspaceRequired(config.CHOOSE_A_WORKSPACE)

    try:
        # AI Review is an administrator's, and says so before anything else
        # is asked of the request - a member is told that, not which
        # workspaces are theirs (PACK-02 C put a workspace check ahead of it).
        if route in REVIEW_ROUTES:
            _require_review_admin(role)

        # A MEMO OR A DOCUMENT NAMED BY ITS NUMBER is in a workspace too, and
        # a member reaches it only if that workspace is theirs (PACK-02 C);
        # nobody reaches it in a deleted one (D). Checked here, once, for
        # every route that names one - a check at each route is a check
        # somebody forgets at the next. Answered as not found, as another
        # tenant's number already is.
        if _outside_assignment(tenant_id, params, allowed):
            return _reply(404, {"error": "not found"})

        if route == "GET /engagements":
            # ?name= asks what a typed name would become, and is how the
            # screen shows "Will be saved as TEST-2" while somebody types
            # (17.3). THE RULE STAYS HERE. A copy of _clean in TypeScript
            # would be a second implementation of a rule that decides where
            # a file is stored, and the two would drift the first time one
            # of them learned about a new character - which is exactly how
            # this bug arrived. The browser holds no rule and asks.
            #
            # On this route rather than one of its own: an existing route
            # answering one more question needs no Terraform, and a new
            # route for a string transformation is a route to maintain.
            asked = (query.get("name") or "").strip()
            answer = {"engagements": list_engagements(
                tenant_id, ws(), _asked_for_archived(query))}
            if asked:
                answer["cleaned"] = _clean(asked)
            return _reply(200, answer)

        # Archiving an engagement, and bringing it back. One route for both:
        # restoring is the same act with the other value, and a pair of
        # routes would be two things to keep in step (14.1, 14.3).
        if route == "PUT /engagements/{id}/state":
            body = json.loads(event.get("body") or "{}")
            changed = set_engagement_state(tenant_id, ws(), email, engagement,
                                           body.get("status", ""))
            if changed is None:
                return _reply(404, {"error": NO_SUCH_ENGAGEMENT % engagement})
            return _reply(200, changed)

        # Opening an engagement from the form. A POST because it creates a
        # row; GET /engagements answers what exists and must never make
        # something exist.
        if route == "POST /engagements":
            body = json.loads(event.get("body") or "{}")
            return _reply(201, open_engagement(
                tenant_id, ws(), email, body.get("engagement", "")))

        if route == "DELETE /documents/{document_id}":
            removing = int((event.get("pathParameters") or {})
                           .get("document_id"))
            outcome = remove_document(tenant_id, removing)
            if outcome is None:
                return _reply(404, {"error": "no such document"})
            if "refused" in outcome:
                return _reply(409, {"error": outcome["refused"]})
            return _reply(200, outcome)

        # The type chosen for a document while it waits to be filed (21.1).
        # Saved on each change, so leaving the screen keeps it.
        if route == "PUT /documents/{document_id}/type":
            body = json.loads(event.get("body") or "{}")
            chosen = set_document_type(tenant_id, email,
                                       params.get("document_id"),
                                       body.get("type"))
            if chosen is None:
                return _reply(404, {"error": "no such document"})
            return _reply(200, chosen)

        if route == "GET /engagements/{id}/pending":
            # The subject travels with the pending list because the screen
            # that shows the list is the screen that has to hold the File
            # button and say why. It comes off the row this route already
            # resolved, so naming the subject costs no second query at all
            # now - it used to cost one.
            found = engagement_named(tenant_id, ws(), engagement)
            if found is None:
                return _reply(404, {"error": NO_SUCH_ENGAGEMENT % engagement})
            return _reply(200, {
                "pending": list_pending(tenant_id, found["engagement_id"]),
                "subject_name": found["subject_name"]})

        if route == "POST /engagements/{id}/file":
            body = json.loads(event.get("body") or "{}")
            # Nothing to read against, so nothing filed and nothing charged
            # (PACK-01 G8).
            _require_published(tenant_id, ws())
            return _reply(200, file_documents(
                tenant_id, ws(), email, engagement, body.get("decisions", []),
                _key(body, "file", engagement)))

        if route == "PUT /engagements/{id}/subject":
            body = json.loads(event.get("body") or "{}")
            return _reply(200, set_subject(tenant_id, ws(), email, engagement,
                                           body.get("subject_name")))

        if route == "GET /engagements/{id}/documents":
            found = engagement_named(tenant_id, ws(), engagement)
            if found is None:
                return _reply(404, {"error": NO_SUCH_ENGAGEMENT % engagement})
            return _reply(200, {"documents": list_documents(
                tenant_id, found["engagement_id"])})

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

        # Every live memorandum, across engagements, for "Share a memo".
        if route == "GET /memos":
            return _reply(200, list_all_memos(tenant_id, ws(), email))

        if route == "GET /engagements/{id}/memos":
            found = engagement_named(tenant_id, ws(), engagement)
            if found is None:
                return _reply(404, {"error": NO_SUCH_ENGAGEMENT % engagement})
            answer = {"memos": list_memos(
                tenant_id, found["engagement_id"],
                _asked_for_archived(query))}
            # ?run= asks how one generation is going (20.1). On this route
            # rather than one of its own, for the reason ?name= is on GET
            # /engagements: the screen already polls it while it waits, and
            # a new route is Terraform.
            if query.get("run"):
                answer["run"] = generate_progress(
                    tenant_id, found["engagement_id"], query.get("run"))
            return _reply(200, answer)

        # Archiving a memorandum, and bringing it back. The whole revision
        # line moves, because a memorandum and its revisions are one document
        # to the person who wrote it (14.1).
        if route == "PUT /memos/{memo_id}/state":
            body = json.loads(event.get("body") or "{}")
            changed = set_memo_state(tenant_id, email,
                                     params.get("memo_id"),
                                     body.get("state", ""))
            if changed is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, changed)

        if route == "POST /engagements/{id}/generate":
            body = json.loads(event.get("body") or "{}")
            return _reply(202, generate(
                tenant_id, ws(), email, engagement, body.get("template_key"),
                _key(body, "generate", engagement)))

        # --- the wallet ----------------------------------------------------

        if route == "GET /wallet":
            return _reply(200, wallet.balance(tenant_id))

        if route == "GET /wallet/ledger":
            return _reply(200, {"ledger": wallet.ledger(
                tenant_id, int(query.get("limit") or 50))})

        if route == "GET /wallet/quote":
            return _reply(200, wallet.quote(
                tenant_id,
                query.get("event") or "document_filed",
                int(query.get("n") or 1)))

        if route == "POST /wallet/top-up":
            body = json.loads(event.get("body") or "{}")
            return _reply(202, billing.top_up(tenant_id, email, role, body))

        # --- paying for a plan ---------------------------------------------
        #
        # Reading is open to any seat. Checkout, a plan change and a top-up
        # are refused to a member in billing, as seats are.

        if route == "GET /billing/subscription":
            return _reply(200, billing.subscription_view(tenant_id))

        if route == "POST /billing/checkout":
            body = json.loads(event.get("body") or "{}")
            return _reply(201, billing.checkout(tenant_id, role, body))

        if route == "POST /billing/plan":
            body = json.loads(event.get("body") or "{}")
            return _reply(202, billing.change_plan(tenant_id, email, role,
                                                   body))

        if route == "POST /billing/payment-method":
            return _reply(201, billing.payment_method(tenant_id, role))

        if route == "POST /billing/resume":
            return _reply(202, billing.resume(tenant_id, role))

        # Administrator only, refused in billing. None is a PDF asked for
        # that is not this tenant's.
        if route == "GET /billing/invoices":
            out = billing.invoices(tenant_id, role, query)
            return _reply(200, out) if out is not None \
                else _reply(404, {"error": "not found"})

        # --- seats ---------------------------------------------------------
        #
        # Reading is open to anybody holding a seat. Who else is in the
        # workspace is not privileged, and a member who cannot see the
        # administrators cannot work out whom to ask.
        #
        # Changing is not. Seats decide who may spend money and who may alter
        # what every future memorandum says.

        if route == "GET /seats":
            return _reply(200, seats.listing(tenant_id, email))

        if route == "POST /seats/invitations":
            _require_seats_admin(role)
            body = json.loads(event.get("body") or "{}")
            # A member's invitation names the workspaces they will see, at
            # least one (PACK-02 C); seats.invite refuses otherwise.
            invited = seats.invite(tenant_id, email,
                                   body.get("email", ""),
                                   body.get("role", "member"),
                                   body.get("workspaces"))
            # The token is returned once, in clear, and never again. The
            # screen still shows the link to copy: it is the fallback when an
            # invitation is lost, filtered or sent to the wrong address, and
            # the person holding it is the administrator who just minted it.
            invited["accept_url"] = "%s/invitation?email=%s&token=%s" % (
                APP_URL, urllib.parse.quote(invited["email"]),
                urllib.parse.quote(invited["token"]))

            # SENT AFTER THE SEAT IS RESERVED, AND NEVER AT ITS EXPENSE
            # (10.5). The row is written and committed above; mail.send
            # answers True or False and raises nothing, so a refusal from SES
            # cannot undo an invitation that exists. The screen is told which
            # it was, and shows the link either way.
            subject, text = mail.invitation(
                email, invited["accept_url"], invited["expires_at"],
                invited["role"])
            invited["sent"] = mail.send(invited["email"], subject, text,
                                        reply_to=email)
            return _reply(201, invited)

        if route == "DELETE /seats/invitations/{invitation_id}":
            _require_seats_admin(role)
            return _reply(200, seats.revoke_invitation(
                tenant_id, params.get("invitation_id")))

        # The seat's rights, its workspaces (PACK-02 C), or both. Each is
        # changed only where the body names it: a body carrying only
        # workspaces must not reset the role to its default and demote an
        # administrator. A body naming neither is the role change it always
        # was, so a screen that predates workspaces behaves as before.
        if route == "PUT /seats/{seat_id}":
            _require_seats_admin(role)
            body = json.loads(event.get("body") or "{}")
            changed = {"seat_id": int(params.get("seat_id"))}
            if "role" in body or "workspaces" not in body:
                changed.update(seats.set_role(
                    tenant_id, params.get("seat_id"),
                    body.get("role", "member")))
            if "workspaces" in body:
                changed.update(seats.set_workspaces(
                    tenant_id, email, params.get("seat_id"),
                    body.get("workspaces")))
            return _reply(200, changed)

        if route == "DELETE /seats/{seat_id}":
            _require_seats_admin(role)
            return _reply(200, seats.remove(tenant_id, params.get("seat_id")))

        # --- deleting a workspace (PACK-02 D) ------------------------------
        # Hidden for six months, then removed; restorable until then. The
        # steps and their refusals are workspaces.py's. No ws(): these name
        # their workspace in the path, and a hidden one is exactly what
        # config.workspace would refuse.
        if route == "GET /workspaces":
            return _reply(200, workspaces.listing(tenant_id, role))

        if route == "POST /workspaces/{workspace_id}/delete/code":
            out = workspaces.request_code(tenant_id, email, role,
                                          params.get("workspace_id"))
            return _reply(200, out) if out is not None \
                else _reply(404, {"error": "not found"})

        if route == "POST /workspaces/{workspace_id}/delete":
            out = workspaces.delete(tenant_id, email, role,
                                    params.get("workspace_id"),
                                    json.loads(event.get("body") or "{}"))
            return _reply(200, out) if out is not None \
                else _reply(404, {"error": "not found"})

        if route == "POST /workspaces/{workspace_id}/restore":
            out = workspaces.restore(tenant_id, email, role,
                                     params.get("workspace_id"))
            return _reply(200, out) if out is not None \
                else _reply(404, {"error": "not found"})

        # --- a suggestion --------------------------------------------------
        if route == "POST /suggestions":
            out = suggest(tenant_id, email, role,
                          json.loads(event.get("body") or "{}"))
            return _reply(201, out) if out is not None \
                else _reply(502, {"error": SUGGESTION_NOT_SENT})

        # --- sharing -------------------------------------------------------
        if route in SHARE_ROUTES:
            return share_route(route, tenant_id, email, params, event, ws)

        if route == "POST /memos/{memo_id}/revise":
            body = json.loads(event.get("body") or "{}")
            # Accepting Update rows is what makes a save an Update's: the
            # revision and the documents filed since come from them, never
            # from the request.
            from_update = _update_revision(tenant_id, params.get("memo_id"),
                                           body.get("rewrites") or [])
            revised = revise_memo(tenant_id, email, params.get("memo_id"),
                                  body.get("markdown", ""),
                                  body.get("rewrites") or [],
                                  config_revision=from_update,
                                  add_sources=from_update is not None)
            if revised is None:
                return _reply(404, {"error": "not found"})
            return _reply(201, revised)

        if route == "POST /memos/{memo_id}/rewrites":
            body = json.loads(event.get("body") or "{}")
            started = start_rewrites(tenant_id, email, params.get("memo_id"),
                                     body.get("sections"))
            if started is None:
                return _reply(404, {"error": "not found"})
            return _reply(202, started)

        if route == "GET /memos/{memo_id}/rewrites":
            return _reply(200, list_rewrites(tenant_id, params.get("memo_id"),
                                             query.get("ids")))

        if route == "POST /memos/{memo_id}/update":
            body = json.loads(event.get("body") or "{}")
            started = update_memo(tenant_id, email, params.get("memo_id"),
                                  _key(body, "update", params.get("memo_id")))
            if started is None:
                return _reply(404, {"error": "not found"})
            return _reply(202, started)

        if route == "GET /memos/{memo_id}/update":
            progress = update_progress(tenant_id, params.get("memo_id"),
                                       query.get("run"))
            if progress is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, progress)

        if route == "GET /memos/{memo_id}/working":
            found = memo_working(tenant_id, email, params.get("memo_id"))
            if found is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, found)

        if route == "PUT /memos/{memo_id}/working":
            body = json.loads(event.get("body") or "{}")
            kept = keep_memo_working(tenant_id, email, params.get("memo_id"),
                                     body.get("working"))
            if kept is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, kept)

        if route == "GET /memos/{memo_id}":
            memo = get_memo(tenant_id, params.get("memo_id"))
            if memo is None:
                return _reply(404, {"error": "not found"})
            return _reply(200, memo)

        if route == "POST /uploads":
            body = json.loads(event.get("body") or "{}")
            # Before the engagement row is made, so a refusal leaves nothing
            # behind (PACK-01 G8).
            _require_published(tenant_id, ws())
            return _reply(200, upload_url(tenant_id, ws(), email,
                                          body.get("engagement", ""),
                                          body.get("filename", ""),
                                          body.get("source_folder")))

        if route == "GET /settings":
            settings = get_settings(tenant_id, role)
            if settings is None:
                return _reply(404, {"error": "not found"})
            # A member is shown the workspaces assigned to them, and no
            # others (PACK-02 C) - the list the header's picker draws.
            return _reply(200, dict(settings, workspaces=_visible(
                settings["workspaces"], allowed())))

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

        if route == "GET /templates":
            return _reply(200, {"templates": templates(tenant_id, ws())})

        if route == "GET /config":
            state = config_state(tenant_id, ws())
            return _reply(200, dict(state, workspaces=_visible(
                state["workspaces"], allowed())))

        if route == "GET /config/{revision}":
            return _reply(200, config_read(tenant_id, ws(),
                                           params.get("revision")))

        if route == "POST /config/draft":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(201, registry.open_draft(
                tenant_id, ws(), email, body.get("from_revision")))

        # Which published revision new work is written against. Publishing
        # makes a revision available; this puts one in use, and reverting is
        # choosing an earlier one. An administrator act, like publishing: it
        # changes what every future memorandum in the tenant says.
        if route == "PUT /config/active":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(200, registry.select_revision(
                tenant_id, ws(), body.get("revision")))

        # What every other tenant is offered. The ARQEDIA workspace only -
        # _curation_only refuses both of these to anybody else before the
        # dispatcher reaches here.
        #
        # ONE OFFERING AT A TIME (PACK-02): the curator's active workspace is
        # the offering whose catalogue is read and set.
        if route == "GET /config/offer":
            return _reply(200, registry.offer(ws()))

        # The whole catalogue in one call: a revision, and the memoranda
        # offered from it. Ticking, unticking and moving the offer to a newer
        # revision are all this one act, which is what makes marks that span
        # two revisions impossible to express.
        if route == "PUT /config/offer":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(200, registry.set_offer(
                ws(), body.get("revision"), body.get("templates"), email))

        if route == "DELETE /config/draft":
            _require_admin(role)
            return _reply(200, registry.discard_draft(tenant_id, ws()))

        if route == "GET /config/draft/validate":
            return _reply(200, registry.validate(tenant_id, ws(),
                                                 registry.DRAFT))

        if route == "POST /config/publish":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            result = registry.publish(tenant_id, ws(), email,
                                      body.get("note"))
            # A refused publish is not an error: the person is told what to
            # fix and the draft is untouched.
            return _reply(200 if result["published"] else 409, result)

        # Our offerings: one base each, with the offering's workspace and
        # name (PACK-02). What Add a workspace chooses from.
        if route == "GET /config/packs":
            return _reply(200, {"packs": registry.packs()})

        # A base forked becomes a NEW workspace of this tenant (PACK-01),
        # named by the caller. No workspace is resolved: this makes one.
        #
        # FROM AN OFFERING, OR EMPTY (PACK-02). "offering" names which of
        # ours; unnamed, the only one. "empty" makes a workspace with
        # nothing in it and a draft open - a new offering in the ARQEDIA
        # workspace, a report of the tenant's own anywhere else. On this
        # route rather than one of its own because both acts make a
        # workspace, and a new route is Terraform.
        if route == "POST /config/fork":
            _require_admin(role)
            # The plan's workspace limit, before anything is made (PACK-02).
            billing.require_workspace_room(tenant_id)
            body = json.loads(event.get("body") or "{}")
            if body.get("empty") is True:
                return _reply(201, registry.new_workspace(
                    tenant_id, email, body.get("name")))
            revision = body.get("revision")
            return _reply(201, registry.fork_base(
                tenant_id, email, body.get("name"),
                pack_revision=int(revision) if revision is not None else None,
                offering=body.get("offering")))

        # The memoranda we ship, and whether this tenant already holds each:
        # the active workspace's offering's (PACK-02). ?offering= asks for
        # one by name instead, for a workspace not yet made - Get started
        # lists the memoranda of the offering a person has just chosen.
        if route == "GET /config/templates/available":
            _require_admin(role)
            asked = query.get("offering")
            if asked not in (None, ""):
                return _reply(200, {"templates": registry.template_packs(
                    tenant_id, None, offering=int(asked))})
            return _reply(200, {
                "templates": registry.template_packs(tenant_id, ws())})

        # Adding one. It lands in the draft and says what it brought with it,
        # so a fact that was deleted and is now back is explained rather than
        # discovered.
        if route == "POST /config/templates/fork":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(201, registry.fork_template(
                tenant_id, ws(), email, body.get("pack_key") or ""))

        # --- configuring from the client's own memorandum ---------------
        if route == "POST /config/draft/sample":
            body = json.loads(event.get("body") or "{}")
            return _reply(200, sample_upload_url(
                tenant_id, ws(), email, role, body.get("filename", "")))

        if route == "POST /config/draft/propose":
            body = json.loads(event.get("body") or "{}")
            return _reply(202, propose(tenant_id, ws(), email, role,
                                       body.get("key", "")))

        if route == "GET /config/draft/proposal":
            return _reply(200, proposal(tenant_id, query.get("key", "")))

        if route == "GET /config/draft/proposals":
            _require_admin(role)
            return _reply(200, proposals(tenant_id))

        if route == "GET /config/draft/working":
            return _reply(200, working(tenant_id, query.get("key", "")))

        if route == "PUT /config/draft/working":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(200, save_working(
                tenant_id, body.get("key", ""), body.get("working") or {}))

        # --- AI Review of the draft (REV-01) -----------------------------
        if route == "POST /config/draft/review":
            return review(tenant_id, ws(), email, role, "open")

        if route == "GET /config/draft/review":
            return review(tenant_id, ws(), email, role, "poll",
                          session_id=query.get("session", ""))

        if route == "POST /config/draft/review/accept":
            body = json.loads(event.get("body") or "{}")
            return review(tenant_id, ws(), email, role, "accept",
                          session_id=body.get("session", ""),
                          suggestion_id=body.get("suggestion_id"),
                          value=body.get("value"),
                          bind_to=body.get("bind_to"))

        if route == "POST /config/draft/review/close":
            body = json.loads(event.get("body") or "{}")
            return review(tenant_id, ws(), email, role, "close",
                          session_id=body.get("session", ""))

        # A question the review asked, answered. The reviewer turns the
        # answer into one suggestion in the background; nothing is written
        # or charged until that suggestion is accepted.
        if route == "POST /config/draft/review/answer":
            body = json.loads(event.get("body") or "{}")
            return review(tenant_id, ws(), email, role, "answer",
                          session_id=body.get("session", ""),
                          suggestion_id=body.get("suggestion_id"),
                          answer=body.get("answer"))

        # --- editing the draft -----------------------------------------
        if route == "GET /config/draft":
            return _reply(200, editor.draft(tenant_id, ws()))

        if route == "POST /config/draft/sections":
            _require_admin(role)
            return _reply(200, editor.save_section(
                tenant_id, ws(), json.loads(event.get("body") or "{}")))

        # The memorandum is part of the address. Two memoranda may each carry
        # a section called "summary"; identified by section alone, deleting
        # one removed it from both and binding fields wrote to whichever the
        # database returned first.
        if route == ("DELETE /config/draft/templates/{template}"
                     "/sections/{key}"):
            _require_admin(role)
            return _reply(200, editor.delete_section(
                tenant_id, ws(), params.get("template"), params.get("key")))

        if route == ("PUT /config/draft/templates/{template}"
                     "/sections/{key}/fields"):
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(200, editor.set_section_fields(
                tenant_id, ws(), params.get("template"), params.get("key"),
                body.get("fields") or []))

        if route == "POST /config/draft/templates":
            _require_admin(role)
            return _reply(200, editor.save_template(
                tenant_id, ws(), json.loads(event.get("body") or "{}")))

        if route == "POST /config/draft/templates/{template}/duplicate":
            _require_admin(role)
            return _reply(200, editor.duplicate_template(
                tenant_id, ws(), params.get("template")))

        if route == "DELETE /config/draft/templates/{template}":
            _require_admin(role)
            return _reply(200, editor.delete_template(
                tenant_id, ws(), params.get("template")))

        if route == "POST /config/draft/fields":
            _require_admin(role)
            return _reply(200, editor.save_field(
                tenant_id, ws(), json.loads(event.get("body") or "{}")))

        if route == "DELETE /config/draft/fields/{key}":
            _require_admin(role)
            return _reply(200, editor.delete_field(tenant_id, ws(),
                                                   params.get("key")))

        if route == "PUT /config/draft/fields/{key}/documents":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(200, editor.set_field_documents(
                tenant_id, ws(), params.get("key"), body.get("documents") or []))

        if route == "PUT /config/draft/types/{key}/fields":
            _require_admin(role)
            body = json.loads(event.get("body") or "{}")
            return _reply(200, editor.set_document_fields(
                tenant_id, ws(), params.get("key"), body.get("fields") or []))

        if route == "POST /config/draft/types":
            _require_admin(role)
            return _reply(200, editor.save_document_type(
                tenant_id, ws(), json.loads(event.get("body") or "{}")))

        if route == "DELETE /config/draft/types/{key}":
            _require_admin(role)
            return _reply(200, editor.delete_document_type(
                tenant_id, ws(), params.get("key")))

        if route == "POST /config/draft/categories":
            _require_admin(role)
            return _reply(200, editor.save_category(
                tenant_id, ws(), json.loads(event.get("body") or "{}")))

        if route == "DELETE /config/draft/categories/{key}":
            _require_admin(role)
            return _reply(200, editor.delete_category(
                tenant_id, ws(), params.get("key")))

        if route == "GET /document-types":
            return _reply(200, {"types": document_types(tenant_id, ws())})

        return _reply(404, {"error": "unknown route"})

    except wallet.InsufficientFunds as exc:
        # 402, which is what it is. Nothing was debited: wallet.charge rolls
        # back before it raises, so a refusal here never costs anybody
        # anything.
        # PROPOSED wording for a tenant spending purchased cash only.
        return _reply(402, {
            "error": ("Payment has failed or the subscription has ended, so "
                      "only purchased credit can be spent, and there is not "
                      "enough." if exc.purchased_only
                      else "Not enough balance. Top up to continue."),
            "needed_cents": exc.needed_cents,
            "available_cents": exc.available_cents,
            "purchased_only": exc.purchased_only,
        })
    except billing.Refused as exc:
        return _reply(409, {"error": str(exc)})
    except paddle_api.PaddleError as exc:
        # PROPOSED: 502. Paddle's own error code is returned; nothing else of
        # its response is.
        print("[paddle-error] route=%s tenant=%s status=%s code=%s"
              % (route, tenant_id, exc.status, exc.code))
        return _reply(502, {"error": "Paddle did not accept the request.",
                            "paddle_code": exc.code})
    except seats.SeatsFull as exc:
        # 409: nothing is wrong with the request - there is simply no room.
        return _reply(409, {"error": str(exc)})
    except workspaces.Refused as exc:
        return _reply(409, {"error": str(exc)})
    except seats.LastAdmin as exc:
        return _reply(409, {"error": str(exc)})
    except wallet.Unpriced as exc:
        return _reply(409, {
            "error": "That is not priced yet, so it cannot be charged for.",
            "event_type": str(exc),
        })
    except PermissionError as exc:
        return _reply(403, {"error": str(exc)})
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # Both are ValueErrors, so without this they reached the line below
        # and the parser's own text ("Expecting value: line 1 column 1") was
        # the answer. Logged, and the person is told what to do.
        print("[api-unreadable] route=%s tenant=%s %r" % (
            route, tenant_id, exc))
        return _reply(400, {"error": REQUEST_UNREADABLE})
    except ValueError as exc:
        if _NOT_A_NUMBER.match(str(exc)):
            print("[api-not-a-number] route=%s tenant=%s %r" % (
                route, tenant_id, exc))
            return _reply(400, {"error": REQUEST_NOT_A_NUMBER})
        return _reply(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - never leak internals to a client
        print("[api-error] route=%s tenant=%s %r" % (route, tenant_id, exc))
        return _reply(500, {"error": "internal error"})
