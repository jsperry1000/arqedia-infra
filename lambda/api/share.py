"""
share.py - sending a memorandum to somebody outside the workspace, listing
what has been sent, and taking it back.

Self-contained, as billing.py and seats.py are. app.py imports this inside
the three share routes only, because it imports share_rules from the
docprocessing layer - and a layer nobody rebuilt must stop sharing, not the
other fifty routes (CLAUDE.md, first warning).

WHERE THINGS LIVE. The grant, the recipient and the counters are in DynamoDB
(share.tf), because the viewer must never wake Aurora. What a tenant may
spend, its plan and the memorandum itself are in Aurora, read here, because
a tenant sending a share is already using the product.

THE SEND, IN ORDER (decided 1 October 2026):

  1. the day counter      20 a day per tenant, re-sends included
  2. render and stamp     the renderer's share mode writes base.pdf and
                          view.pdf; nothing has been promised yet
  3. the grant, pending   written; the viewer refuses a pending grant
  4. the period counter   an atomic add that returns the new count, so two
                          sends at nine of ten cannot both be free
  5. the charge           only past the allowance, through wallet.charge,
                          at a price the person accepted on the screen
  6. active, and the email

A charge refused at 5 undoes 4, 3 and 1 and deletes what 2 wrote: nothing has
moved and nothing was sent. A failure after 5 leaves a pending grant that
records its charge, and the retry - same idempotency key - finds it, does not
charge again (wallet.charge refuses the repeat) and activates it. So a share
is never refunded, because a share that was paid for is never left unsent.

A RE-SEND finds the same item - the key is "<memo_id>#<viewer_account_id>" -
and reinstates it if it was revoked: same item, same link token, a fresh
expiry, no allowance used and nothing charged. It still counts toward the
day's 20, because it still sends an email.
"""

import datetime
import json
import os
import time
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

import config
import mail
import share_rules as rules
import wallet

_rds = boto3.client("rds-data")
_lambda = boto3.client("lambda")
_s3 = boto3.client("s3")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
CURATED_BUCKET = os.environ["CURATED_BUCKET"]
RENDER_FUNCTION = os.environ["RENDER_FUNCTION"]
APP_URL = os.environ.get("APP_URL", "https://app.arqedia.com")

# A trial is Base's shape: Base's allowance, once, for the whole trial, and
# Base's overage price, whatever plan the tenant signed up for.
TRIAL_PLAN = "base"
TRIAL_PERIOD = "trial"

# Within the range a person might mean; the screen offers three.
MAX_EXPIRY_DAYS = 365

AUTHORITY_REQUIRED = (
    "Confirm that you are entitled to share this memorandum with this "
    "person. It carries third-party identity material, and that assurance "
    "is yours to give.")


class RateLimited(Exception):
    """Twenty today already. 429."""


class Capped(Exception):
    """No balance at all. A capped workspace may revoke but not send
    (wallet spec section 8). 402."""


class OverageNotAccepted(Exception):
    """Past the allowance, and the person did not accept the price - or
    accepted a different one. Nothing was sent or charged. 409, carrying
    the price so the screen can ask."""

    def __init__(self, unit_cents, allowance):
        self.unit_cents = unit_cents
        self.allowance = allowance
        super().__init__("past the allowance")


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


_dynamo = None


def _table(name):
    """A DynamoDB table, made when first asked for. Not at import: the tests
    replace boto3 with a fake that has no resource(), and nothing else in
    this function's import path should depend on DynamoDB existing."""
    global _dynamo
    if _dynamo is None:
        _dynamo = boto3.resource("dynamodb")
    return _dynamo.Table(rules.table(name))


def _plain(value):
    """DynamoDB's Decimals as ints, so a reply can be serialised."""
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _conditional_failure(exc):
    return (getattr(exc, "response", {}).get("Error", {}).get("Code")
            == "ConditionalCheckFailedException")


# --- reading Aurora --------------------------------------------------------

def _memo(tenant_id, memo_id):
    """The memorandum being shared, named as it was when it was written, or
    None where this tenant has no such memorandum. The tenant is the token's:
    a memo_id from another tenant is simply not found."""
    found = _sql(
        """
        SELECT m.memo_id, m.template_key, m.config_revision,
               m.parent_memo_id, m.revision, e.subject_name, e.name
        FROM memo m
        LEFT JOIN engagement e
               ON e.engagement_id = m.engagement_id
              AND e.tenant_id = m.tenant_id
        WHERE m.tenant_id = :t AND m.memo_id = :m
        """,
        [_p("t", tenant_id), _p("m", int(memo_id))]).get("records", [])
    if not found:
        return None
    r = found[0]
    label = config.load(tenant_id, _col(r, 2) or 1).label_for_template(
        _col(r, 1))
    return {"memo_id": int(_col(r, 0)),
            "label": "%s %s.%s" % (label, _col(r, 3) or _col(r, 0),
                                   _col(r, 4)),
            "subject": (_col(r, 5) or "").strip() or _col(r, 6) or ""}


def _tenant_name(tenant_id):
    found = _sql("SELECT name FROM tenant WHERE tenant_id = :t",
                 [_p("t", tenant_id)]).get("records", [])
    return (_col(found[0], 0) if found else None) or "a workspace"


def _plan_allowance(plan_key):
    found = _sql("SELECT share_allowance FROM plan WHERE plan_key = :k",
                 [_p("k", plan_key)]).get("records", [])
    if not found:
        raise ValueError("there is no %s plan to take an allowance from"
                         % plan_key)
    value = _col(found[0], 0)
    # NULL is unlimited (migration 018), not zero.
    return None if value is None else int(value)


def _subscription(tenant_id):
    found = _sql(
        """
        SELECT p.plan_key, s.current_period_ends_at
        FROM subscription s JOIN plan p ON p.plan_id = s.plan_id
        WHERE s.tenant_id = :t
        """,
        [_p("t", tenant_id)]).get("records", [])
    if not found:
        return None
    return {"plan_key": _col(found[0], 0),
            "period_ends_at": _col(found[0], 1)}


def _trial_ends_at(tenant_id):
    found = _sql("SELECT trial_ends_at FROM tenant WHERE tenant_id = :t",
                 [_p("t", tenant_id)]).get("records", [])
    return _col(found[0], 0) if found else None


# --- the allowance ---------------------------------------------------------

def _counted(tenant_id, period):
    item = _table("usage").get_item(
        Key={"tenant_id": int(tenant_id), "period": period},
        ConsistentRead=True).get("Item")
    return int((item or {}).get("count", 0))


def allowance(tenant_id):
    """Where this tenant stands: what its plan includes, how much of it is
    used, and what the next share past it would cost.

    THE PERIOD IS THE WALLET'S. A trial is one period, "trial", for the whole
    trial and never reset. A subscription's is its billing month, which ends
    at current_period_ends_at - the moment its monthly credit bucket expires
    - so the allowance and the credit turn over together.
    """
    standing = wallet.standing(tenant_id)
    trial = standing in (wallet.TRIAL, wallet.TRIAL_ENDED)
    sub = None if trial else _subscription(tenant_id)

    if trial or sub is None:
        plan_key, period = TRIAL_PLAN, TRIAL_PERIOD
        period_ends_at = _trial_ends_at(tenant_id)
    else:
        plan_key = sub["plan_key"]
        period_ends_at = sub["period_ends_at"]
        period = "p%s" % (period_ends_at or "none")

    included = _plan_allowance(plan_key)
    used = _counted(tenant_id, period)
    event = "share_overage_%s" % plan_key
    try:
        unit = wallet.unit_price(tenant_id, event)
    except wallet.Unpriced:
        unit = None

    today = "d" + rules.now().strftime("%Y-%m-%d")
    only = standing == wallet.PURCHASED_ONLY
    return {
        "plan": plan_key,
        "trial": trial,
        "standing": standing,
        "period": period,
        "period_ends_at": period_ends_at,
        # None is unlimited, never zero.
        "allowance": included,
        "used": used,
        "remaining": None if included is None else max(0, included - used),
        "overage_event": event,
        "overage_cents": unit,
        "today": _counted(tenant_id, today),
        "daily_limit": rules.DAILY_LIMIT,
        # Capped is available = 0 (wallet.py). It refuses a send, never a
        # revoke.
        "capped": wallet.available(tenant_id, purchased_only=only) <= 0,
    }


def _count(tenant_id, period, limit=None):
    """Add one and return the new count. With a limit, refuse - and add
    nothing - where the count is already at it."""
    kwargs = {
        "Key": {"tenant_id": int(tenant_id), "period": period},
        "UpdateExpression": "ADD #c :one",
        "ExpressionAttributeNames": {"#c": "count"},
        "ExpressionAttributeValues": {":one": 1},
        "ReturnValues": "UPDATED_NEW",
    }
    if limit is not None:
        kwargs["ConditionExpression"] = \
            "attribute_not_exists(#c) OR #c < :limit"
        kwargs["ExpressionAttributeValues"][":limit"] = int(limit)
    try:
        result = _table("usage").update_item(**kwargs)
    except ClientError as exc:
        if limit is not None and _conditional_failure(exc):
            raise RateLimited(
                "This workspace has shared %d memoranda today, which is the "
                "daily limit. It resets at midnight UTC." % limit)
        raise
    return int(result["Attributes"]["count"])


def _uncount(tenant_id, period):
    """Take back one, undoing a send that did not happen."""
    try:
        _table("usage").update_item(
            Key={"tenant_id": int(tenant_id), "period": period},
            UpdateExpression="ADD #c :minus",
            ExpressionAttributeNames={"#c": "count"},
            ExpressionAttributeValues={":minus": -1})
    except Exception as exc:  # noqa: BLE001 - logged; the refusal stands
        print("[share-uncount-failed] tenant=%s period=%s %r" % (
            tenant_id, period, exc))


# --- sending ---------------------------------------------------------------

def _link(grant_id, token):
    """The link in the email. The token is in the #fragment: the browser
    never sends a fragment to any server, so it is in no access log."""
    from urllib.parse import quote
    return "%s/view/%s#t=%s" % (APP_URL, quote(grant_id, safe=""), token)


def _render(tenant_id, memo_id, recipient, shared_at, prefix):
    response = _lambda.invoke(
        FunctionName=RENDER_FUNCTION,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tenant_id": tenant_id, "memo_id": int(memo_id),
                            "share": {"recipient_email": recipient,
                                      "shared_at": shared_at,
                                      "prefix": prefix}}))
    result = json.loads(response["Payload"].read())
    if result.get("status") != "ok":
        print("[share-render-failed] tenant=%s memo=%s %r" % (
            tenant_id, memo_id, result))
        raise RuntimeError("the memorandum could not be prepared for sharing")
    return result["base_key"], result["view_key"]


def _expiry_days(body):
    """None for the default, or the number of days the tenant chose."""
    days = (body or {}).get("expiry_days")
    if days is None or days == "":
        return None
    if isinstance(days, bool) or not isinstance(days, int) \
            or not 1 <= days <= MAX_EXPIRY_DAYS:
        raise ValueError("Access lasts between 1 and %d days."
                         % MAX_EXPIRY_DAYS)
    return days


def _registered(viewer_id):
    item = _table("viewer").get_item(
        Key={"viewer_account_id": viewer_id}).get("Item")
    return bool((item or {}).get("registered"))


def send(tenant_id, email, memo_id, body):
    """Share one memorandum with one address. Returns the grant as the list
    shows it, or None where the tenant has no such memorandum.

    Any seat may send, as any seat may file and generate."""
    body = body or {}
    recipient = rules.normalise_email(body.get("recipient"))
    if not rules.valid_email(recipient):
        raise ValueError("That is not an email address.")
    if body.get("authority_affirmed") is not True:
        raise ValueError(AUTHORITY_REQUIRED)
    days = _expiry_days(body)
    key = str(body.get("idempotency_key") or "").strip()[:64]
    if not key:
        raise ValueError("A share needs an idempotency key.")

    memo = _memo(tenant_id, memo_id)
    if memo is None:
        return None

    viewer_id = rules.viewer_account_id(recipient)
    grant_id = rules.grant_id(memo["memo_id"], viewer_id)
    grants = _table("grant")
    existing = grants.get_item(Key={"grant_id": grant_id},
                               ConsistentRead=True).get("Item")
    # memo_id is unique across tenants, so this cannot happen. If it ever
    # did, the grant is somebody else's and is not found.
    if existing and int(existing.get("tenant_id", -1)) != int(tenant_id):
        return None

    at = rules.now()
    tenant_expiry = (at + datetime.timedelta(days=days)) if days else None
    expires = rules.expires_at(at, _registered(viewer_id), tenant_expiry)
    tenant_name = _tenant_name(tenant_id)

    if existing and existing.get("status") == rules.ACTIVE:
        return _resend(tenant_id, email, existing, at, expires,
                       tenant_expiry is not None, tenant_name)

    return _send_new(tenant_id, email, memo, recipient, viewer_id, grant_id,
                     existing, at, expires, tenant_expiry is not None, key,
                     tenant_name, body)


def _resend(tenant_id, email, grant, at, expires, tenant_set, tenant_name):
    """The same memorandum to the same address again: reinstate the grant if
    it was revoked, refresh its expiry, and send the same link. No allowance
    and no charge (decision of 1 October 2026, item 8)."""
    _count(tenant_id, "d" + at.strftime("%Y-%m-%d"), rules.DAILY_LIMIT)

    was_revoked = bool(grant.get("revoked"))
    names = {"#r": "revoked"}
    values = {":f": False, ":sent": rules.iso(at),
              ":exp": rules.iso(expires), ":set": tenant_set,
              ":by": email, ":one": 1, ":t": int(tenant_id)}
    update = ("SET #r = :f, sent_at = :sent, expires_at = :exp, "
              "expiry_set_by_tenant = :set, authority_affirmed_at = :sent, "
              "sent_by = :by")
    if was_revoked:
        update += ", reinstated_at = :sent, reinstated_by = :by"
    update += " REMOVE revoked_at, revoked_by ADD resends :one"
    _table("grant").update_item(
        Key={"grant_id": grant["grant_id"]},
        UpdateExpression=update,
        ConditionExpression="tenant_id = :t",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values)

    grant = dict(grant, revoked=False, sent_at=rules.iso(at),
                 expires_at=rules.iso(expires), expiry_set_by_tenant=tenant_set,
                 sent_by=email)
    sent = _mail(email, tenant_name, grant)
    print("[share-resent] tenant=%s memo=%s reinstated=%s sent=%s" % (
        tenant_id, grant["memo_id"], was_revoked, sent))
    return dict(_view(grant), sent=sent, reinstated=was_revoked,
                charged_cents=0)


def _send_new(tenant_id, email, memo, recipient, viewer_id, grant_id,
              pending, at, expires, tenant_set, key, tenant_name, body):
    day = "d" + at.strftime("%Y-%m-%d")
    retry = bool(pending) and pending.get("idempotency_key") == key

    # A pending grant that was charged for is finished, never charged again
    # - whichever click it is (decision of 1 October 2026, send order).
    paid_already = bool(pending) and bool(pending.get("charge_entry_id"))

    standing = allowance(tenant_id)
    if standing["capped"] and not paid_already:
        raise Capped("This workspace has no balance, so it cannot share. "
                     "Revoking still works.")

    # 1. The day counter. A retry of the same click was counted already.
    if not retry:
        _count(tenant_id, day, rules.DAILY_LIMIT)

    # Each attempt renders into a folder of its own, so undoing one can never
    # delete the PDFs a live grant - or another attempt - is serving.
    prefix = rules.object_prefix(tenant_id, memo["memo_id"], viewer_id)         + at.strftime("%Y%m%dT%H%M%SZ") + "/"
    grants = _table("grant")
    made = []

    def undo(counted_period=None):
        """Everything this send did, taken back. Nothing has been sent."""
        try:
            grants.delete_item(
                Key={"grant_id": grant_id},
                ConditionExpression="#s = :pending",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":pending": rules.PENDING})
        except Exception as exc:  # noqa: BLE001 - logged; refusal stands
            print("[share-undo-grant-failed] %s %r" % (grant_id, exc))
        if counted_period:
            _uncount(tenant_id, counted_period)
        _uncount(tenant_id, day)
        for k in made:
            try:
                _s3.delete_object(Bucket=CURATED_BUCKET, Key=k)
            except Exception as exc:  # noqa: BLE001
                print("[share-undo-object-failed] %s %r" % (k, exc))

    try:
        # 2. Render and stamp, unless the pending grant already holds both.
        if retry and pending.get("view_key") and pending.get("base_key"):
            base_key, view_key = pending["base_key"], pending["view_key"]
            shared_at = pending["created_at"]
        else:
            shared_at = rules.iso(at)
            base_key, view_key = _render(tenant_id, memo["memo_id"],
                                         recipient, shared_at, prefix)
            made.extend([base_key, view_key])

        # 3. The grant, pending. A pending grant from an earlier attempt is
        # replaced; an active one never is - that is a re-send, above.
        token = (pending or {}).get("link_token") or rules.new_token()
        item = {
            "grant_id": grant_id,
            "tenant_id": int(tenant_id),
            "memo_id": memo["memo_id"],
            "viewer_account_id": viewer_id,
            "recipient_email": recipient,
            "status": rules.PENDING,
            "created_at": (pending or {}).get("created_at") or shared_at,
            "sent_at": rules.iso(at),
            "expires_at": rules.iso(expires),
            "expiry_set_by_tenant": tenant_set,
            "authority_affirmed_at": rules.iso(at),
            "revoked": False,
            "link_token": token,
            "base_key": base_key,
            "view_key": view_key,
            "memo_label": memo["label"],
            "subject": memo["subject"],
            "tenant_name": tenant_name,
            "sent_by": email,
            "idempotency_key": key,
            "opens": 0,
            "downloads": 0,
        }
        # What an earlier attempt already counted and charged stays counted
        # and charged, so no click counts or charges a grant twice.
        for kept in ("counted_period", "over", "charge_entry_id",
                     "charged_cents"):
            if pending and kept in pending:
                item[kept] = pending[kept]
        grants.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(grant_id) "
                                "OR #s = :pending",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":pending": rules.PENDING})
    except Exception:
        undo()
        raise

    # 4. The period counter, once per grant.
    counted = item.get("counted_period")
    over = bool(item.get("over"))
    if not counted:
        counted = standing["period"]
        n = _count(tenant_id, counted)
        over = standing["allowance"] is not None and n > standing["allowance"]
        grants.update_item(
            Key={"grant_id": grant_id},
            UpdateExpression="SET counted_period = :p, #o = :o",
            ExpressionAttributeNames={"#o": "over"},
            ExpressionAttributeValues={":p": counted, ":o": over})

    # 5. The charge, past the allowance only, at the price accepted.
    charged = int(item.get("charged_cents") or 0)
    if over and not item.get("charge_entry_id"):
        try:
            unit = wallet.unit_price(tenant_id, standing["overage_event"])
        except wallet.Unpriced:
            undo(counted)
            raise
        if body.get("accept_overage_cents") != unit:
            undo(counted)
            raise OverageNotAccepted(unit, standing["allowance"])
        try:
            paid = wallet.charge(
                tenant_id, email, standing["overage_event"], 1,
                reference="%s shared past the allowance" % memo["label"],
                idempotency_key=key)
        except (wallet.InsufficientFunds, wallet.Unpriced):
            undo(counted)
            raise
        charged = int(paid.get("amount_cents") or unit)
        grants.update_item(
            Key={"grant_id": grant_id},
            UpdateExpression="SET charge_entry_id = :e, charged_cents = :c",
            ExpressionAttributeValues={":e": int(paid["entry_id"]),
                                       ":c": charged})

    # 6. Active, and the email.
    grants.update_item(
        Key={"grant_id": grant_id},
        UpdateExpression="SET #s = :active, activated_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":active": rules.ACTIVE,
                                   ":now": rules.iso(rules.now())})
    item = dict(item, status=rules.ACTIVE, over=over, charged_cents=charged)

    sent = _mail(email, tenant_name, item)
    print("[share-sent] tenant=%s memo=%s over=%s charged=%s sent=%s" % (
        tenant_id, memo["memo_id"], over, charged, sent))
    return dict(_view(item), sent=sent, reinstated=False,
                charged_cents=charged)


def _mail(email, tenant_name, grant):
    """The email, after everything else has happened - and never at its
    expense (mail.py). The grant stands whether SES accepts it or not, and
    the screen says which."""
    subject, text = mail.share_invitation(
        email, tenant_name, grant["memo_label"], grant.get("subject"),
        _link(grant["grant_id"], grant["link_token"]),
        grant["expires_at"], bool(grant.get("expiry_set_by_tenant")))
    # The sender is copied, BCC, on the same message (feature/share-sender-
    # copy): the real ARQEDIA email in their own inbox, to forward if they
    # wish. It opens nothing for them or anybody they forward it to - the
    # link takes a device verified by a code sent to the grant's recipient,
    # and nobody else (fix/share-link-possession-read).
    return mail.send(grant["recipient_email"], subject, text,
                     reply_to=email, bcc=email)


# --- listing and revoking --------------------------------------------------

def _view(grant, registered=None):
    """A grant as the tenant's list shows it. Never the link token."""
    g = _plain(grant)
    expired = bool(g.get("expires_at")) and \
        rules.parse(g["expires_at"]) <= rules.now()
    out = {k: g.get(k) for k in (
        "grant_id", "memo_id", "memo_label", "subject", "recipient_email",
        "sent_by", "created_at", "sent_at", "expires_at",
        "expiry_set_by_tenant", "first_opened_at", "opens", "downloads",
        "revoked", "revoked_at", "revoked_by", "reinstated_at",
        "charged_cents")}
    out["revoked"] = bool(out["revoked"])
    out["expired"] = expired
    if registered is not None:
        out["registered"] = registered
    return out


def listing(tenant_id):
    """Every grant this tenant has made, newest first, and the allowance."""
    found, start = [], None
    while True:
        kwargs = {"IndexName": "tenant-index",
                  "KeyConditionExpression": "tenant_id = :t",
                  "ExpressionAttributeValues": {":t": int(tenant_id)},
                  "ScanIndexForward": False}
        if start:
            kwargs["ExclusiveStartKey"] = start
        page = _table("grant").query(**kwargs)
        found.extend(page.get("Items", []))
        start = page.get("LastEvaluatedKey")
        if not start or len(found) >= 500:
            break

    # Pending is not a share - nothing was sent - so it is not listed.
    grants = [g for g in found if g.get("status") == rules.ACTIVE]
    viewers = {g["viewer_account_id"] for g in grants}
    registered = {v: _registered(v) for v in viewers}
    return {"grants": [_view(g, registered[g["viewer_account_id"]])
                       for g in grants],
            "allowance": allowance(tenant_id)}


def revoke(tenant_id, email, grant_id):
    """End future access. Any seat, in every state, capped included
    (share_viewer_spec section 6).

    ONE WRITE, AND IT IS THE CONTROL. The viewer reads this item with a
    strongly consistent read on every request, so the next request after
    this returns is refused. The item stays: who was sent what, who opened
    it and who took it back is the audit.

    IT DOES NOT RECALL A COPY ALREADY DOWNLOADED, and the screen says so at
    the point of sending (section 5). Returns None where there is no such
    grant in this tenant."""
    at = rules.iso(rules.now())
    try:
        result = _table("grant").update_item(
            Key={"grant_id": str(grant_id)},
            UpdateExpression="SET #r = :y, revoked_at = :at, "
                             "revoked_by = :by",
            ConditionExpression="tenant_id = :t AND #s = :active",
            ExpressionAttributeNames={"#s": "status", "#r": "revoked"},
            ExpressionAttributeValues={":y": True, ":at": at, ":by": email,
                                       ":t": int(tenant_id),
                                       ":active": rules.ACTIVE},
            ReturnValues="ALL_NEW")
    except ClientError as exc:
        if _conditional_failure(exc):
            return None
        raise
    print("[share-revoked] tenant=%s grant=%s" % (tenant_id,
                                                   str(grant_id)[:12]))
    return _view(result["Attributes"])


# --- account deletion ------------------------------------------------------

def purge_tenant(tenant_id):
    """Everything sharing holds for one tenant, gone: its grants, their
    access log, its counters and its shares/ PDFs.

    NOT CALLED FROM ANYWHERE. Account deletion does not exist yet (CLAUDE.md,
    What is open); whoever builds it calls this beside the Aurora rows. A
    recipient's viewer_account is not the tenant's and is not touched - other
    tenants may have shared with the same person.

    Deleting a grant is what revokes it: the viewer finds nothing and
    refuses."""
    grants = _table("grant")
    log = _table("log")
    removed = 0
    start = None
    while True:
        kwargs = {"IndexName": "tenant-index",
                  "KeyConditionExpression": "tenant_id = :t",
                  "ExpressionAttributeValues": {":t": int(tenant_id)}}
        if start:
            kwargs["ExclusiveStartKey"] = start
        page = grants.query(**kwargs)
        for g in page.get("Items", []):
            entries = log.query(
                KeyConditionExpression="grant_id = :g",
                ExpressionAttributeValues={":g": g["grant_id"]})
            for e in entries.get("Items", []):
                log.delete_item(Key={"grant_id": e["grant_id"],
                                     "occurred_at": e["occurred_at"]})
            grants.delete_item(Key={"grant_id": g["grant_id"]})
            removed += 1
        start = page.get("LastEvaluatedKey")
        if not start:
            break

    usage = _table("usage")
    for u in usage.query(
            KeyConditionExpression="tenant_id = :t",
            ExpressionAttributeValues={":t": int(tenant_id)}).get("Items", []):
        usage.delete_item(Key={"tenant_id": u["tenant_id"],
                               "period": u["period"]})

    prefix = "shares/%d/" % int(tenant_id)
    token = None
    while True:
        args = {"Bucket": CURATED_BUCKET, "Prefix": prefix}
        if token:
            args["ContinuationToken"] = token
        page = _s3.list_objects_v2(**args)
        for obj in page.get("Contents", []):
            _s3.delete_object(Bucket=CURATED_BUCKET, Key=obj["Key"])
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")

    print("[share-purged] tenant=%s grants=%d" % (tenant_id, removed))
    return {"grants": removed}
