"""
app.py - the viewer: what a person a memorandum was shared with can do.

Read it, download a watermarked copy, and register to keep access longer.
Nothing else - no source documents, no configuration, no other memorandum
(share_viewer_spec section 2).

NOTHING HERE TOUCHES AURORA. The cluster pauses and takes fifteen seconds to
wake, and this is the first thing a recipient sees of the product. The grant
in DynamoDB carries everything the page needs; the PDFs were rendered and
watermarked when it was sent. The role has no rds-data permission at all, so
this is a guarantee and not a convention.

TWO WAYS IN.

  The link       "Authorization: Share <token>" on the /view routes, checked
                 against the grant with a strongly consistent read on every
                 request. A revoke is one write to that item, so the next
                 request after it is refused. Reading and downloading also
                 take a verified device - "X-Arqedia-Device: <token>", issued
                 once a code emailed to the recipient is entered on that
                 browser. The link alone opens nothing.
  Signed in      a registered viewer's token from the viewer pool, on the
                 /viewer/shares routes. The gateway verifies it; this checks
                 the grant names the same person.

EVERY REFUSAL READS THE SAME. A wrong token, a revoked grant, an expired one
and one that never existed all say the link does not work. The log says
which; the person does not learn which part of a guess was wrong.

Routes:
  GET  /view/{grant_id}                     the memorandum: link + device
  POST /view/{grant_id}/download            a copy stamped with this moment
  POST /view/{grant_id}/verify/code         email a code to verify a browser
  POST /view/{grant_id}/verify              the code; a device token back
  POST /view/{grant_id}/register/code       email the recipient a code
  POST /view/{grant_id}/register            the code, a password, MFA setup
  POST /view/{grant_id}/register/confirm    the authenticator's first code
  POST /viewer/sign-in                      a registered viewer, password
  POST /viewer/sign-in/mfa                  ... and the code
  GET  /viewer/shares                       everything shared with them
  GET  /viewer/shares/{grant_id}            one of them, signed in
  POST /viewer/shares/{grant_id}/download   a copy of it, signed in
  POST /viewer/trial-prompt                 "Not now" or "Yes" to a trial

A TENANT WHOSE EMAIL WAS ALSO SHARED WITH (feature/viewer-tenant-integration).
The customer pool's token, on routes of their own. Answered only where the
viewer account for that email is linked to this exact customer user
(customer_sub = the token's sub), so a viewer's token - a different sub -
never matches, and no tenant sees anything but what was sent to its own
person's address:
  GET  /me/shared                           shared with me, from the app
  GET  /me/shared/{grant_id}                one of them
  POST /me/shared/{grant_id}/download       a copy of it
"""

import datetime
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.parse
import uuid
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

import share_rules as rules

_s3 = boto3.client("s3")
_lambda = boto3.client("lambda")
_cognito = boto3.client("cognito-idp")
_ses = boto3.client("ses")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]
VIEWER_POOL_ID = os.environ["VIEWER_POOL_ID"]
VIEWER_CLIENT_ID = os.environ["VIEWER_CLIENT_ID"]

# Long enough for a browser to start loading the PDF it was handed, and no
# longer: the link in the page is not a way back in.
URL_SECONDS = 120

LINK_DEAD = ("This link does not work. It may have expired or been "
             "withdrawn by the person who sent it. Ask them to send it "
             "again.")
SIGN_IN_FAILED = "That email and password do not match a registered viewer."
CODE_FAILED = "That code was not accepted. Check the time on your device and try again."

# The one-time code emailed to a recipient's own address (fix/share-
# registration-takeover). Ten minutes, five tries, one a minute, five an hour:
# long enough to fetch from a mailbox, short and scarce enough that the code
# is the inbox's to give and nobody else's to guess or to flood.
EMAIL_CODE_MINUTES = 10
EMAIL_CODE_TRIES = 5
EMAIL_CODE_GAP_SECONDS = 60
EMAIL_CODE_PER_HOUR = 5
EMAIL_CODE_FAILED = ("That code is not right, or has expired. Ask for a new "
                     "one.")
EMAIL_CODE_NOT_SENT = ("We couldn't send the code just now. Nothing was used "
                       "up - try again.")


class EmailNotSent(Exception):
    """SES did not accept the code email. Nothing was counted and no code
    was left behind. 502: the fault is ours, not the request's."""


# A browser verified for one recipient (fix/share-link-possession-read).
# Holding the link is no longer enough to read: the browser must also hold a
# device token, issued once a code emailed to the recipient has been entered
# on it. Six months from verification and not renewed by use; ten per
# recipient, the oldest dropped; a device verified in the last fifteen
# minutes is proof enough to register without a second code (decisions of
# 7 October 2026).
DEVICE_HEADER = "x-arqedia-device"
DEVICE_MONTHS = 6
DEVICE_CAP = 10
DEVICE_FRESH_MINUTES = 15
DEVICE_NEEDED = ("To open this on this device, confirm it's you. We'll email "
                 "a code to the address it was shared with.")


# The trial prompt a registered viewer sees on signing in: asked again 30 days
# after it was last answered, and never once the viewer is also a linked
# tenant (decision of 9 October 2026).
TRIAL_PROMPT_DAYS = 30
TRIAL_ANSWERS = ("yes", "not_now")


class CodeRequired(Exception):
    """Registering needs an emailed code: this browser was not verified in
    the last fifteen minutes. 400, with code_required: true."""


class DeviceNeeded(Exception):
    """The link is good but this browser has not been verified for its
    recipient. 401, saying so - nothing of the memorandum is served."""

    def __init__(self, grant, registered):
        self.sent_to = _masked(grant["recipient_email"])
        self.registered = registered
        super().__init__(DEVICE_NEEDED)


_dynamo = None


def _table(name):
    global _dynamo
    if _dynamo is None:
        _dynamo = boto3.resource("dynamodb")
    return _dynamo.Table(rules.table(name))


def _plain(value):
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _reply(status, body):
    return {"statusCode": status,
            "headers": {"content-type": "application/json",
                        # Nothing a recipient sees is to be cached anywhere.
                        "cache-control": "no-store"},
            "body": json.dumps(body)}


def _code(exc):
    return getattr(exc, "response", {}).get("Error", {}).get("Code")


# --- the grant ---------------------------------------------------------------

def _grant(grant_id):
    """The grant, read strongly consistent, or None. Consistent because a
    revoke a moment ago must already be seen."""
    if rules.split_grant_id(grant_id) is None:
        return None
    return _table("grant").get_item(Key={"grant_id": grant_id},
                                    ConsistentRead=True).get("Item")


def _authorised(grant_id, token=None, viewer_id=None):
    """(grant, None) where the request may see it, (None, reply) where not."""
    grant = _grant(grant_id)
    reason = rules.refusal(grant, rules.now(), token=token,
                           viewer_id=viewer_id)
    if reason:
        print("[view-refused] grant=%s reason=%s" % (
            str(grant_id)[:12], reason))
        return None, _reply(404, {"error": LINK_DEAD})
    return grant, None


def _account(viewer_id):
    return _table("viewer").get_item(
        Key={"viewer_account_id": viewer_id}).get("Item") or {}


def _arrived(grant):
    """The first time this recipient opens any link, they become a viewer -
    "verified" in the spec's word: they held the link that was sent to their
    address (section 3). Made once and never overwritten."""
    try:
        _table("viewer").put_item(
            Item={"viewer_account_id": grant["viewer_account_id"],
                  "email": grant["recipient_email"],
                  "verified_at": rules.iso(rules.now()),
                  "created_at": rules.iso(rules.now()),
                  "registered": False,
                  "marketing_opt_in": False},
            ConditionExpression="attribute_not_exists(viewer_account_id)")
    except ClientError as exc:
        if _code(exc) != "ConditionalCheckFailedException":
            raise


def _record(context, event, grant, action):
    """The access log, off the hot path: this function invokes itself and
    does not wait. A log write that fails costs the recipient nothing."""
    ip = ((event.get("requestContext") or {}).get("http") or {}).get(
        "sourceIp") or ""
    agent = ((event.get("requestContext") or {}).get("http") or {}).get(
        "userAgent") or ""
    try:
        _lambda.invoke(
            FunctionName=context.function_name,
            InvocationType="Event",
            Payload=json.dumps({
                "action": "log", "grant_id": grant["grant_id"],
                "tenant_id": int(grant["tenant_id"]), "kind": action,
                "at": rules.iso(rules.now()),
                # Hashed: what is kept is whether two opens came from one
                # place, not where that place is.
                "ip_hash": hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]
                           if ip else None,
                "user_agent": agent[:256]}))
    except Exception as exc:  # noqa: BLE001 - the page is served regardless
        print("[view-log-not-queued] grant=%s %r" % (
            str(grant["grant_id"])[:12], exc))


def _write_log(event):
    """The asynchronous half of _record."""
    _table("log").put_item(Item={
        "grant_id": event["grant_id"],
        "occurred_at": "%s#%s" % (event["at"], uuid.uuid4().hex[:8]),
        "tenant_id": int(event["tenant_id"]),
        "action": event["kind"],
        "ip_hash": event.get("ip_hash"),
        "user_agent": event.get("user_agent")})
    counter = "opens" if event["kind"] == "view" else "downloads"
    _table("grant").update_item(
        Key={"grant_id": event["grant_id"]},
        UpdateExpression="ADD #n :one SET first_opened_at = "
                         "if_not_exists(first_opened_at, :at)",
        ExpressionAttributeNames={"#n": counter},
        ExpressionAttributeValues={":one": 1, ":at": event["at"]})
    return {"status": "ok"}


# --- reading and downloading -----------------------------------------------

def _presign(key, attachment=None):
    params = {"Bucket": CURATED_BUCKET, "Key": key,
              "ResponseContentType": "application/pdf"}
    if attachment:
        params["ResponseContentDisposition"] = (
            'attachment; filename="%s"' % attachment)
    else:
        params["ResponseContentDisposition"] = "inline"
    return _s3.generate_presigned_url("get_object", Params=params,
                                      ExpiresIn=URL_SECONDS)


def _unused_device_code_at(account):
    """When a code to open this recipient's shares on a new device was
    emailed and has not been used, or None.

    Asked for on 7 October: is the warning email the recipient's only sign
    that somebody else tried? It was. A code spent - on this browser or any
    other - is removed, so one still held was asked for and not entered:
    either the recipient gave up on a device, or the link is in somebody
    else's hands. The page shows it to a verified browser, which is the
    recipient, and lets them decide which."""
    if account.get("code_purpose") == "device" and account.get("code_hash"):
        return account.get("code_sent_at")
    return None


def _page(grant, account=None, device=None):
    """What the viewer page shows around the memorandum."""
    g = _plain(grant)
    if account is None:
        account = _account(g["viewer_account_id"])
    return {
        "grant_id": g["grant_id"],
        "memo_label": g.get("memo_label"),
        "subject": g.get("subject"),
        "tenant_name": g.get("tenant_name"),
        "recipient_email": g.get("recipient_email"),
        "sent_at": g.get("sent_at"),
        "expires_at": g.get("expires_at"),
        "expiry_set_by_tenant": bool(g.get("expiry_set_by_tenant")),
        "registered": bool(account.get("registered")),
        # The watermarked copy rendered when it was shared. No HTML of the
        # memorandum is ever served: that would be its text without the
        # watermark (decision of 1 October 2026, item 4).
        "view_url": _presign(g["view_key"]),
        "unused_device_code_at": _unused_device_code_at(account),
        # A browser verified in the last fifteen minutes registers without a
        # second emailed code; any other needs one.
        "register_needs_code": not _fresh(device),
    }


def _filename(grant):
    label = str(grant.get("memo_label") or "memorandum")
    subject = str(grant.get("subject") or "")
    raw = ("%s %s" % (subject, label)).strip()
    safe = "".join(ch if ch.isalnum() or ch in " .-_" else "-" for ch in raw)
    return (safe.strip() or "memorandum")[:120] + ".pdf"


def _download(grant):
    """A copy stamped with this moment, from base.pdf and nothing else.

    base.pdf already carries the recipient and the tenant across every page;
    this adds the time along the foot. So the copy in somebody's hands says
    when it was taken, which the view - stamped when it was shared - does
    not."""
    import stamp  # the layer; only a download needs pypdf

    at = rules.now()
    base = _s3.get_object(Bucket=CURATED_BUCKET,
                          Key=grant["base_key"])["Body"].read()
    pdf = stamp.stamp(base, line=stamp.downloaded_line(
        grant["recipient_email"], grant.get("tenant_name") or "",
        rules.iso(at)))

    prefix = grant["base_key"].rsplit("/", 1)[0] + "/downloads/"
    key = "%s%s-%s.pdf" % (prefix, at.strftime("%Y%m%dT%H%M%SZ"),
                           uuid.uuid4().hex[:8])
    _s3.put_object(Bucket=CURATED_BUCKET, Key=key, Body=pdf,
                   ContentType="application/pdf")
    return {"download_url": _presign(key, attachment=_filename(grant))}


# --- a code to the recipient's own inbox -----------------------------------
#
# THE LINK PROVES NOTHING ABOUT WHO HOLDS IT. It can be forwarded, and until
# this existed whoever held it could register the recipient's address with
# their own password and authenticator - before the real recipient did, or
# over a registration they had started and not finished. A code sent to the
# recipient's address at the moment it is needed is what the link holder
# cannot produce on the recipient's behalf.
#
# KEPT ON THE VIEWER ACCOUNT, hashed. One live code per recipient, for one
# purpose; asking again replaces it. A hash rather than the code, so the
# table does not hold something that can be typed in - though six digits
# hashed are no secret from somebody who can read the table, which is why the
# five tries and ten minutes are the protection and the hash is not.
#
# SENT FROM HERE, not through the API's mail.py. The signup function sends its
# own code for the same reason: this function's role holds what it needs and
# nothing else, and the API's mail module is not in this function's package.

def _sender():
    """Read when a code is sent, not at import, as mail.sender() does: a
    missing SENDER should fail the send, not every route."""
    return os.environ.get("SENDER") or ""


def _code_hash(viewer_id, purpose, code):
    return hashlib.sha256(("%s:%s:%s" % (viewer_id, purpose, code))
                          .encode("utf-8")).hexdigest()


def _masked(address):
    local, _, domain = str(address or "").partition("@")
    return (local[:1] or "?") + "***@" + domain


def _email_code_message(grant, code, purpose):
    """What the code email says. Plain text, like every message the product
    sends. It says what the code is for, so a recipient who did not ask for
    one knows somebody else holds their link."""
    firm = grant.get("tenant_name") or "a firm"
    why = {
        "register": ("Someone is using the link to a memorandum %s shared "
                     "with this address, to register and keep access to it."
                     % firm),
        # The cheap answer to a forwarded link that is being used to flood
        # this inbox: say plainly what it means (decision of 7 October).
        "device": ("Someone opened the link to a memorandum %s shared with "
                   "this address, on a device that hasn't been confirmed. If "
                   "you didn't just open this link on a new device, someone "
                   "else has it - tell the person who sent it to you." % firm),
    }[purpose]
    subject = "Your ARQEDIA code: %s" % code
    body = (
        "Your ARQEDIA code is %s\n"
        "\n"
        "It lasts %d minutes.\n"
        "\n"
        "%s If that is you, enter the code where you were asked for it.\n"
        "\n"
        "If it is not you, do not pass this code on. Nothing changes without "
        "it, and the memorandum stays as it was.\n"
        "\n"
        "ARQEDIA\n"
        "This address does not take replies.\n"
    ) % (code, EMAIL_CODE_MINUTES, why)
    return subject, body


def _send_email_code(grant, purpose):
    """Email a fresh code to the grant's recipient, and to nobody else.

    The address is the grant's - the one the tenant sent to - never one from
    the request. Refused, without sending, inside a minute of the last code
    or past five in an hour, so a link holder cannot flood the recipient."""
    viewer_id = grant["viewer_account_id"]
    at = rules.now()
    account = _table("viewer").get_item(
        Key={"viewer_account_id": viewer_id},
        ConsistentRead=True).get("Item") or {}

    last = account.get("code_sent_at")
    if last and (at - rules.parse(last)).total_seconds() \
            < EMAIL_CODE_GAP_SECONDS:
        raise ValueError("A code was sent less than a minute ago. Check your "
                         "inbox, or ask again in a minute.")

    window = account.get("code_window_start")
    count = int(account.get("code_window_count") or 0)
    if not window or (at - rules.parse(window)).total_seconds() >= 3600:
        window, count = rules.iso(at), 0
    if count >= EMAIL_CODE_PER_HOUR:
        raise ValueError("Too many codes have been sent to this address in "
                         "the last hour. Try again later.")

    sender = _sender()
    if not sender:
        print("[email-code-not-sent] reason=no-sender")
        raise EmailNotSent()

    # THE CODE IS WRITTEN BEFORE THE SEND, so it is there to check when the
    # email arrives - but THE LIMITS ARE COUNTED ONLY AFTER SES ACCEPTS IT.
    # On 6 October a send refused by SES had already counted, and the
    # person's retry was told a code had gone out a minute ago when none had
    # gone at all.
    code = "%06d" % secrets.randbelow(1000000)
    _table("viewer").update_item(
        Key={"viewer_account_id": viewer_id},
        UpdateExpression=(
            "SET code_hash = :h, code_purpose = :p, code_expires_at = :e, "
            "code_tries = :zero"),
        ExpressionAttributeValues={
            ":h": _code_hash(viewer_id, purpose, code), ":p": purpose,
            ":e": rules.iso(at + datetime.timedelta(
                minutes=EMAIL_CODE_MINUTES)),
            ":zero": 0})

    subject, text = _email_code_message(grant, code, purpose)
    try:
        sent = _ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [grant["recipient_email"]]},
            Message={"Subject": {"Data": subject, "Charset": "UTF-8"},
                     "Body": {"Text": {"Data": text, "Charset": "UTF-8"}}})
    except Exception as exc:  # noqa: BLE001 - undone, then reported
        # Taken back: a code nobody was sent is not one anybody can use, and
        # nothing was counted. Removed only if it is still the code written
        # above, so a later request's code is never the one removed.
        print("[email-code-not-sent] viewer=%s %r" % (viewer_id[:8], exc))
        try:
            _table("viewer").update_item(
                Key={"viewer_account_id": viewer_id},
                UpdateExpression="REMOVE code_hash, code_purpose, "
                                 "code_expires_at, code_tries",
                ConditionExpression="code_hash = :h",
                ExpressionAttributeValues={
                    ":h": _code_hash(viewer_id, purpose, code)})
        except Exception as undo:  # noqa: BLE001 - the refusal stands
            print("[email-code-undo-failed] viewer=%s %r" % (
                viewer_id[:8], undo))
        raise EmailNotSent()

    _table("viewer").update_item(
        Key={"viewer_account_id": viewer_id},
        UpdateExpression=("SET code_sent_at = :at, code_window_start = :w, "
                          "code_window_count = :n"),
        ExpressionAttributeValues={":at": rules.iso(at), ":w": window,
                                   ":n": count + 1})
    print("[email-code-sent] viewer=%s purpose=%s message=%s" % (
        viewer_id[:8], purpose, sent.get("MessageId")))
    return {"sent_to": _masked(grant["recipient_email"]),
            "minutes": EMAIL_CODE_MINUTES}


def _spend_email_code(viewer_id, purpose, presented):
    """True once, for the right code, inside its ten minutes and five tries -
    and the code is gone the moment it is spent, so it cannot be used twice.
    Raises ValueError(EMAIL_CODE_FAILED) otherwise, saying nothing about why:
    wrong, expired and used-up all read the same."""
    presented = re.sub(r"\s+", "", str(presented or ""))
    account = _table("viewer").get_item(
        Key={"viewer_account_id": viewer_id},
        ConsistentRead=True).get("Item") or {}

    held = account.get("code_hash")
    live = bool(held and account.get("code_purpose") == purpose
                and account.get("code_expires_at")
                and rules.parse(account["code_expires_at"]) > rules.now()
                and int(account.get("code_tries") or 0) < EMAIL_CODE_TRIES)
    if not live:
        raise ValueError(EMAIL_CODE_FAILED)

    if not re.match(r"^\d{6}$", presented) or not hmac.compare_digest(
            _code_hash(viewer_id, purpose, presented), held):
        _table("viewer").update_item(
            Key={"viewer_account_id": viewer_id},
            UpdateExpression="ADD code_tries :one",
            ExpressionAttributeValues={":one": 1})
        raise ValueError(EMAIL_CODE_FAILED)

    # Spent: removed on the condition that it is still the code just
    # checked, so two requests racing with the same code cannot both pass.
    try:
        _table("viewer").update_item(
            Key={"viewer_account_id": viewer_id},
            UpdateExpression="REMOVE code_hash, code_purpose, "
                             "code_expires_at, code_tries",
            ConditionExpression="code_hash = :h",
            ExpressionAttributeValues={":h": held})
    except ClientError as exc:
        if _code(exc) == "ConditionalCheckFailedException":
            raise ValueError(EMAIL_CODE_FAILED)
        raise
    return True


# The viewer pool's policy (share.tf), checked here before a code is spent,
# so a password Cognito would refuse does not cost the person their code.
_PASSWORD_RULE = ("That password is not accepted: at least 12 characters, "
                  "with upper case, lower case and a number.")


def _password_ok(password):
    return bool(len(password) >= 12 and re.search(r"[a-z]", password)
                and re.search(r"[A-Z]", password)
                and re.search(r"\d", password))


# --- a verified device -------------------------------------------------------
#
# THE LINK IS NOT ENOUGH TO READ. Until this existed GET /view authorised on
# the link token alone, so anybody it was forwarded to could read and
# download for as long as the grant lived - registered recipient or not.
# Now the browser must also present a device token for the grant's
# recipient, which it gets only by entering a code emailed to the
# recipient's own address (the same _send_email_code and _spend_email_code
# registration uses, purpose "device").
#
# PER RECIPIENT, NOT PER GRANT. One verified browser opens every share to
# that recipient, from any tenant, until the device expires.
#
# THE TOKEN IS "<device id>.<secret>". The id finds the entry on the viewer
# account; only a hash of the secret is kept. The browser holds the token in
# local storage and sends it in the X-Arqedia-Device header - not a cookie:
# the API is on its own AWS hostname, so a cookie would be third-party to
# app.arqedia.com and refused by browsers that block those.

def _device_from_headers(headers):
    for key, value in (headers or {}).items():
        if key.lower() == DEVICE_HEADER:
            return str(value or "").strip() or None
    return None


def _device_hash(viewer_id, secret):
    return hashlib.sha256(("%s:device:%s" % (viewer_id, secret))
                          .encode("utf-8")).hexdigest()


def _known_device(viewer_id, account, presented):
    """The live device entry the presented token names, or None. Wrong,
    unknown and expired all answer None."""
    if not presented or "." not in presented:
        return None
    device_id, secret = presented.split(".", 1)
    entry = (account.get("devices") or {}).get(device_id)
    if not entry or not entry.get("hash"):
        return None
    if not hmac.compare_digest(_device_hash(viewer_id, secret),
                               str(entry["hash"])):
        return None
    if rules.parse(entry["expires_at"]) <= rules.now():
        return None
    return entry


def _require_device(grant, headers):
    """(account, device entry) for a browser verified for this grant's
    recipient; DeviceNeeded otherwise. Registered or not: a registered
    recipient's link alone no longer opens anything either, and they may sign
    in instead (/viewer)."""
    viewer_id = grant["viewer_account_id"]
    account = _table("viewer").get_item(
        Key={"viewer_account_id": viewer_id},
        ConsistentRead=True).get("Item") or {}
    entry = _known_device(viewer_id, account, _device_from_headers(headers))
    if entry is None:
        print("[device-needed] viewer=%s presented=%s" % (
            viewer_id[:8], bool(_device_from_headers(headers))))
        raise DeviceNeeded(grant, bool(account.get("registered")))
    return account, entry


def _issue_device(viewer_id, user_agent):
    """A new device token for this recipient, once their emailed code has
    been spent. Six months, not renewed. Expired entries are dropped, and past
    ten the oldest goes, so the list cannot grow without end."""
    at = rules.now()
    account = _table("viewer").get_item(
        Key={"viewer_account_id": viewer_id},
        ConsistentRead=True).get("Item") or {}
    devices = {k: v for k, v in (account.get("devices") or {}).items()
               if rules.parse(v["expires_at"]) > at}
    while len(devices) >= DEVICE_CAP:
        oldest = min(devices, key=lambda k: devices[k]["created_at"])
        del devices[oldest]

    device_id = uuid.uuid4().hex[:16]
    secret = secrets.token_urlsafe(32)
    ends = rules.add_months(at, DEVICE_MONTHS)
    devices[device_id] = {"hash": _device_hash(viewer_id, secret),
                          "created_at": rules.iso(at),
                          "expires_at": rules.iso(ends),
                          "user_agent": (user_agent or "")[:120]}
    _table("viewer").update_item(
        Key={"viewer_account_id": viewer_id},
        UpdateExpression="SET devices = :d",
        ExpressionAttributeValues={":d": devices})
    print("[device-verified] viewer=%s devices=%d" % (viewer_id[:8],
                                                      len(devices)))
    return {"device_token": "%s.%s" % (device_id, secret),
            "expires_at": rules.iso(ends)}


def _fresh(entry):
    """A device verified within the last fifteen minutes: as good a proof of
    the inbox as a registration code sent just now."""
    return bool(entry) and (rules.now() - rules.parse(entry["created_at"])) \
        .total_seconds() <= DEVICE_FRESH_MINUTES * 60


# --- registering -------------------------------------------------------------

def _register(grant, body, device=None):
    """The emailed code, a password, then the authenticator. Nothing is
    marked registered until the authenticator's first code is right
    (_confirm).

    THE EMAILED CODE COMES FIRST, before Cognito is touched at all. The link
    is not proof of who holds it; the code, sent to the recipient's own
    address by _send_email_code, is. Without it nobody can create this user
    or set its password - which also closes resetting a registration that
    was started and not finished, since that is the same two calls.

    OR A FRESH DEVICE. A browser whose device code was entered in the last
    fifteen minutes has just proved the same inbox, and is not made to prove
    it twice (decision of 7 October 2026). Any other needs the code."""
    if body.get("accept_terms") is not True:
        raise ValueError("Registering means accepting the terms and privacy "
                         "policy.")
    password = str(body.get("password") or "")
    if not password:
        raise ValueError("Choose a password.")
    if not _password_ok(password):
        raise ValueError(_PASSWORD_RULE)

    account = _account(grant["viewer_account_id"])
    if account.get("registered"):
        raise PermissionError("You have already registered. Sign in instead.")

    if not _fresh(device):
        # Nothing presented at all: the screen thought this browser was fresh
        # and the fifteen minutes ran out while the form was open. Said as
        # such, so the screen asks for a code rather than reporting a wrong
        # one.
        if not str(body.get("email_code") or "").strip():
            raise CodeRequired()
        _spend_email_code(grant["viewer_account_id"], "register",
                          body.get("email_code"))

    email = grant["recipient_email"]
    # THE ADDRESS IS VERIFIED by the code just spent, which only its inbox
    # could supply. Cognito sends nothing.
    restarted = False
    try:
        _cognito.admin_create_user(
            UserPoolId=VIEWER_POOL_ID, Username=email,
            UserAttributes=[{"Name": "email", "Value": email},
                            {"Name": "email_verified", "Value": "true"}],
            MessageAction="SUPPRESS")
    except ClientError as exc:
        # An earlier registration that never finished its MFA setup. The
        # account item says not registered, so the user is theirs to finish.
        # The key issued below REPLACES the one that attempt issued, and the
        # screen says so: an authenticator entry from before now makes codes
        # that will never match.
        if _code(exc) != "UsernameExistsException":
            raise
        restarted = True

    try:
        # THE PASSWORD IS NEVER STORED. It passes through here once, to the
        # pool, as signup's does (CLAUDE.md, Signing up).
        _cognito.admin_set_user_password(
            UserPoolId=VIEWER_POOL_ID, Username=email, Password=password,
            Permanent=True)
    except ClientError as exc:
        if _code(exc) == "InvalidPasswordException":
            raise ValueError(_PASSWORD_RULE)
        raise

    started = _cognito.admin_initiate_auth(
        UserPoolId=VIEWER_POOL_ID, ClientId=VIEWER_CLIENT_ID,
        AuthFlow="ADMIN_USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": email, "PASSWORD": password})
    if started.get("ChallengeName") != "MFA_SETUP":
        print("[register-unexpected-challenge] %s" %
              started.get("ChallengeName"))
        raise RuntimeError("registration could not set up MFA")

    associated = _cognito.associate_software_token(
        Session=started["Session"])
    secret = associated["SecretCode"]
    label = urllib.parse.quote("ARQEDIA:%s" % email)
    otpauth = "otpauth://totp/%s?secret=%s&issuer=ARQEDIA" % (label, secret)
    return {"session": associated["Session"], "secret_code": secret,
            "otpauth": otpauth, "qr_svg": _setup_qr(otpauth),
            "restarted": restarted}


# What the authenticator step says, one sentence per cause
# (fix/viewer-mfa-setup-timeout). All three used to read "check the time on
# your device", so a session that had simply timed out - the live failure of
# 7 October, a first code 3 minutes 15 seconds after a 3-minute session - sent
# the person off to fix a clock that was right.
MFA_SESSION_EXPIRED = ("This step timed out. Setting up the authenticator has "
                       "to be finished within 15 minutes. Start again and "
                       "we'll email you a new code.")
MFA_CODE_MISMATCH = ("That code didn't match. Check the key was added exactly "
                     "as shown and enter the next code your app shows. If it "
                     "keeps failing, check your device sets its clock "
                     "automatically.")
MFA_SETUP_FAILED = ("Something went wrong setting up the authenticator. Start "
                    "again.")

# Cognito's error code -> (the sentence, whether the person must start again).
# A wrong code can be retried in the same session; an expired or broken one
# cannot, and the screen offers Start again rather than another try.
MFA_SETUP_ERRORS = {
    "NotAuthorizedException": (MFA_SESSION_EXPIRED, True),
    "CodeMismatchException": (MFA_CODE_MISMATCH, False),
    "EnableSoftwareTokenMFAException": (MFA_CODE_MISMATCH, False),
}


class MfaSetupRestart(Exception):
    """The authenticator setup cannot go on in this session. 400, with
    restart: true, so the screen leads back to a new emailed code."""


def _setup_refused(exc, step):
    """Cognito refused the authenticator setup. Logged by its own error code -
    the reason the 7 October failure took a timing table to diagnose is that
    nothing said which error it was - then answered with the sentence for
    that cause."""
    code = _code(exc)
    print("[mfa-setup-refused] step=%s code=%s" % (step, code))
    message, restart = MFA_SETUP_ERRORS.get(code, (MFA_SETUP_FAILED, True))
    if restart:
        raise MfaSetupRestart(message)
    raise ValueError(message)


def _setup_qr(otpauth):
    """The authenticator setup link as a QR code, SVG, beside the typed key
    rather than instead of it - somebody may be setting up on a device with no
    camera.

    reportlab's own QR generator, already in the layer for the PDFs: no new
    dependency, and the secret goes nowhere it does not already go. Built
    from the same otpauth link the typed key comes from, so the two cannot
    disagree. None if it cannot be drawn: the typed key still works, and a
    missing picture must not stop a registration."""
    try:
        from reportlab.graphics import renderSVG
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing

        widget = QrCodeWidget(otpauth, barLevel="M")
        x0, y0, x1, y1 = widget.getBounds()
        size = 200
        drawing = Drawing(size, size, transform=[
            size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
        drawing.add(widget)
        return renderSVG.drawToString(drawing)
    except Exception as exc:  # noqa: BLE001 - the typed key still works
        print("[mfa-qr-not-drawn] %r" % exc)
        return None


def _confirm(grant, body):
    """The first code from the authenticator. Right, and the viewer is
    registered: every grant they hold is recomputed to six months from its
    own send, unless the tenant set its date (section 6, settled 1 October
    2026)."""
    if body.get("accept_terms") is not True:
        raise ValueError("Registering means accepting the terms and privacy "
                         "policy.")
    email = grant["recipient_email"]
    try:
        verified = _cognito.verify_software_token(
            Session=str(body.get("session") or ""),
            UserCode=str(body.get("code") or "").strip(),
            FriendlyDeviceName="ARQEDIA viewer")
    except ClientError as exc:
        _setup_refused(exc, "verify")
    if verified.get("Status") != "SUCCESS":
        print("[mfa-setup-refused] step=verify status=%s"
              % verified.get("Status"))
        raise ValueError(MFA_CODE_MISMATCH)

    try:
        signed_in = _cognito.admin_respond_to_auth_challenge(
            UserPoolId=VIEWER_POOL_ID, ClientId=VIEWER_CLIENT_ID,
            ChallengeName="MFA_SETUP",
            ChallengeResponses={"USERNAME": email},
            Session=verified["Session"])
    except ClientError as exc:
        _setup_refused(exc, "respond")
    _cognito.admin_set_user_mfa_preference(
        UserPoolId=VIEWER_POOL_ID, Username=email,
        SoftwareTokenMfaSettings={"Enabled": True, "PreferredMfa": True})

    user = _cognito.admin_get_user(UserPoolId=VIEWER_POOL_ID, Username=email)
    sub = next((a["Value"] for a in user.get("UserAttributes", [])
                if a["Name"] == "sub"), None)

    at = rules.iso(rules.now())
    # One unticked box, whatever the jurisdiction, until counsel says which
    # default applies where (section 7.1, open). Unticked is never wrong.
    opted = body.get("marketing_opt_in") is True
    names = {"#r": "registered"}
    values = {":y": True, ":at": at, ":sub": sub, ":opt": opted,
              ":email": email}
    update = ("SET #r = :y, registered_at = :at, terms_accepted_at = :at, "
              "cognito_sub = :sub, marketing_opt_in = :opt, email = :email, "
              "verified_at = if_not_exists(verified_at, :at), "
              "created_at = if_not_exists(created_at, :at)")
    if opted:
        update += ", marketing_opt_in_at = :at"
    _table("viewer").update_item(
        Key={"viewer_account_id": grant["viewer_account_id"]},
        UpdateExpression=update, ExpressionAttributeNames=names,
        ExpressionAttributeValues=values)

    # THE SAME ADDRESS IN BOTH POOLS: a tenant user, linked at signup, now
    # registering as a viewer too. Flagged, not resolved - which one a sign-in
    # reaches is deferred (feature/viewer-tenant-integration).
    if _account(grant["viewer_account_id"]).get("customer_sub"):
        print("[both-pools] viewer=%s registered while linked to a tenant user"
              % grant["viewer_account_id"][:8])

    extended = _extend(grant["viewer_account_id"])
    result = signed_in["AuthenticationResult"]
    print("[viewer-registered] viewer=%s grants=%d" % (
        grant["viewer_account_id"][:8], extended))
    return {"id_token": result["IdToken"],
            "expires_in": result.get("ExpiresIn"),
            "extended": extended,
            "expires_at": _plain(_grant(grant["grant_id"]) or {}).get(
                "expires_at")}


def _extend(viewer_id):
    """Every grant this viewer holds, six months from its own send - not from
    registering. A grant sent five months ago gets one more month. A date the
    tenant chose is left alone, and so is a revoked grant."""
    changed, start = 0, None
    while True:
        kwargs = {"IndexName": "viewer-index",
                  "KeyConditionExpression": "viewer_account_id = :v",
                  "ExpressionAttributeValues": {":v": viewer_id}}
        if start:
            kwargs["ExclusiveStartKey"] = start
        page = _table("grant").query(**kwargs)
        for g in page.get("Items", []):
            if g.get("status") != rules.ACTIVE or g.get("revoked") \
                    or g.get("expiry_set_by_tenant"):
                continue
            ends = rules.expires_at(rules.parse(g["sent_at"]), True)
            _table("grant").update_item(
                Key={"grant_id": g["grant_id"]},
                UpdateExpression="SET expires_at = :e",
                ConditionExpression="expiry_set_by_tenant = :no",
                ExpressionAttributeValues={":e": rules.iso(ends),
                                           ":no": False})
            changed += 1
        start = page.get("LastEvaluatedKey")
        if not start:
            return changed


# --- signing in --------------------------------------------------------------

def _sign_in(body):
    email = rules.normalise_email(body.get("email"))
    try:
        started = _cognito.admin_initiate_auth(
            UserPoolId=VIEWER_POOL_ID, ClientId=VIEWER_CLIENT_ID,
            AuthFlow="ADMIN_USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email,
                            "PASSWORD": str(body.get("password") or "")})
    except ClientError as exc:
        if _code(exc) in ("NotAuthorizedException", "UserNotFoundException"):
            raise PermissionError(SIGN_IN_FAILED)
        raise
    challenge = started.get("ChallengeName")
    if challenge == "MFA_SETUP":
        raise PermissionError("Registration was not finished. Open the link "
                              "you were sent and register again.")
    if challenge != "SOFTWARE_TOKEN_MFA":
        print("[sign-in-unexpected-challenge] %s" % challenge)
        raise PermissionError(SIGN_IN_FAILED)
    return {"session": started["Session"]}


def _sign_in_mfa(body):
    email = rules.normalise_email(body.get("email"))
    try:
        done = _cognito.admin_respond_to_auth_challenge(
            UserPoolId=VIEWER_POOL_ID, ClientId=VIEWER_CLIENT_ID,
            ChallengeName="SOFTWARE_TOKEN_MFA",
            ChallengeResponses={"USERNAME": email,
                                "SOFTWARE_TOKEN_MFA_CODE":
                                    str(body.get("code") or "").strip()},
            Session=str(body.get("session") or ""))
    except ClientError as exc:
        if _code(exc) in ("CodeMismatchException", "NotAuthorizedException",
                          "ExpiredCodeException"):
            raise ValueError(CODE_FAILED)
        raise
    result = done["AuthenticationResult"]
    return {"id_token": result["IdToken"],
            "expires_in": result.get("ExpiresIn")}


def _mine(viewer_id):
    """Everything shared with this viewer, from every tenant. Each tenant
    sees only its own grants; this person sees all of theirs, and nothing
    here says one tenant's name to another (section 3)."""
    out, start = [], None
    at = rules.now()
    while True:
        kwargs = {"IndexName": "viewer-index",
                  "KeyConditionExpression": "viewer_account_id = :v",
                  "ExpressionAttributeValues": {":v": viewer_id},
                  "ScanIndexForward": False}
        if start:
            kwargs["ExclusiveStartKey"] = start
        page = _table("grant").query(**kwargs)
        for g in page.get("Items", []):
            if g.get("status") != rules.ACTIVE or g.get("revoked"):
                continue
            g = _plain(g)
            out.append({
                "grant_id": g["grant_id"],
                "memo_label": g.get("memo_label"),
                "subject": g.get("subject"),
                "tenant_name": g.get("tenant_name"),
                "sent_at": g.get("sent_at"),
                "expires_at": g.get("expires_at"),
                "expired": rules.parse(g["expires_at"]) <= at})
        start = page.get("LastEvaluatedKey")
        if not start:
            return {"shares": out}


# --- the trial prompt --------------------------------------------------------

def _trial_prompt_due(account):
    """Whether a signed-in viewer is asked "Want to try ARQEDIA yourself?".

    Never once they are a linked tenant: they already are. Otherwise asked
    when it has never been answered, and again 30 days after the last answer
    - "Yes" included, since a "Yes" that never became a signup is the same
    person, still a viewer, a month on."""
    if account.get("customer_sub"):
        return False
    answered = account.get("trial_prompt_answered_at")
    if not answered:
        return True
    return (rules.now() - rules.parse(answered)).days >= TRIAL_PROMPT_DAYS


def _answer_trial_prompt(viewer_id, body):
    answer = str(body.get("answer") or "")
    if answer not in TRIAL_ANSWERS:
        raise ValueError("Answer yes or not_now.")
    at = rules.now()
    _table("viewer").update_item(
        Key={"viewer_account_id": viewer_id},
        UpdateExpression="SET trial_prompt_answer = :a, "
                         "trial_prompt_answered_at = :at",
        ConditionExpression="attribute_exists(viewer_account_id)",
        ExpressionAttributeValues={":a": answer, ":at": rules.iso(at)})
    return {"answer": answer,
            "ask_again_after": rules.iso(
                at + datetime.timedelta(days=TRIAL_PROMPT_DAYS))}


# --- a tenant, shared with ---------------------------------------------------
#
# THE LINK IS ON THE VIEWER ACCOUNT (decision of 9 October 2026): customer_sub,
# customer_tenant_id, linked_at, linked_via. The signup function writes it
# when an account is made for an address that already has a viewer account;
# this writes it on the first visit where signup's write is missing - a viewer
# account made after the tenant signed up, or a signup whose link write
# failed. Either way it names ONE customer user, and only that user's token
# is answered.

def _linked_viewer(claims):
    """The viewer account id this tenant user is linked to, or None."""
    email = rules.normalise_email(claims.get("email"))
    sub = str(claims.get("sub") or "")
    if not email or not sub:
        return None
    viewer_id = rules.viewer_account_id(email)
    account = _table("viewer").get_item(
        Key={"viewer_account_id": viewer_id},
        ConsistentRead=True).get("Item")
    if not account:
        return None
    held = account.get("customer_sub")
    if held:
        return viewer_id if held == sub else None

    # Not linked yet. Only on an address the customer pool says is verified:
    # every account the signup function makes is, and an unverified one has
    # not shown it owns the inbox the shares went to.
    if str(claims.get("email_verified") or "").lower() != "true":
        return None
    try:
        _table("viewer").update_item(
            Key={"viewer_account_id": viewer_id},
            UpdateExpression="SET customer_sub = :s, customer_tenant_id = :t, "
                             "linked_at = :at, linked_via = :via",
            ConditionExpression="attribute_exists(viewer_account_id) AND "
                                "attribute_not_exists(customer_sub)",
            ExpressionAttributeValues={
                ":s": sub, ":t": str(claims.get("custom:tenant_id") or ""),
                ":at": rules.iso(rules.now()), ":via": "first-visit"})
    except ClientError as exc:
        if _code(exc) != "ConditionalCheckFailedException":
            raise
        # Linked by somebody else between the read and the write: answer by
        # whatever is there now.
        again = _account(viewer_id).get("customer_sub")
        return viewer_id if again == sub else None
    print("[viewer-linked] viewer=%s via=first-visit" % viewer_id[:8])
    if account.get("registered"):
        print("[both-pools] viewer=%s linked while registered" % viewer_id[:8])
    return viewer_id


# --- dispatch ----------------------------------------------------------------

def lambda_handler(event, context):
    if event.get("action") == "log":
        return _write_log(event)

    started = time.time()
    reply = _dispatch(event, context)
    # Route and status. Never the grant id in full, never the token, never
    # the address.
    print("[viewer] route=%s status=%s ms=%.0f" % (
        event.get("routeKey", "-"), (reply or {}).get("statusCode"),
        (time.time() - started) * 1000))
    return reply


def _dispatch(event, context):
    route = event.get("routeKey", "")
    params = event.get("pathParameters") or {}
    grant_id = urllib.parse.unquote(params.get("grant_id") or "")
    token = rules.token_from_header(event.get("headers"))
    try:
        body = json.loads(event.get("body") or "{}")
    except ValueError:
        return _reply(400, {"error": "that request could not be read"})

    claims = (((event.get("requestContext") or {}).get("authorizer") or {})
              .get("jwt") or {}).get("claims") or {}
    # A customer token carries the tenant; a viewer's never does. The gateway
    # already puts each pool's token on its own routes - this holds the line
    # again here, so a route bound to the wrong authorizer still refuses.
    tenant_token = bool(claims.get("custom:tenant_id"))
    signed_in = rules.viewer_account_id(claims["email"]) \
        if claims.get("email") and not tenant_token else None

    try:
        if route in ("GET /view/{grant_id}", "POST /view/{grant_id}/download",
                     "POST /view/{grant_id}/verify/code",
                     "POST /view/{grant_id}/verify",
                     "POST /view/{grant_id}/register/code",
                     "POST /view/{grant_id}/register",
                     "POST /view/{grant_id}/register/confirm"):
            grant, refused = _authorised(grant_id, token=token or "")
            if refused:
                return refused

            # READING AND DOWNLOADING TAKE THE LINK AND A VERIFIED DEVICE -
            # the same rule for both, so there is no weaker way to the same
            # memorandum (fix/share-link-possession-read).
            if route == "GET /view/{grant_id}":
                account, device = _require_device(grant, event.get("headers"))
                _arrived(grant)
                _record(context, event, grant, "view")
                return _reply(200, _page(grant, account, device))
            if route == "POST /view/{grant_id}/download":
                _require_device(grant, event.get("headers"))
                _arrived(grant)
                # Recorded once the copy exists, not before: a download that
                # failed is not one somebody took.
                copy = _download(grant)
                _record(context, event, grant, "download")
                return _reply(200, copy)

            # Verifying this browser: a code to the recipient's own inbox,
            # then a device token for it. The link holder gets the token only
            # by entering what that inbox received.
            if route == "POST /view/{grant_id}/verify/code":
                _arrived(grant)
                return _reply(200, _send_email_code(grant, "device"))
            if route == "POST /view/{grant_id}/verify":
                _spend_email_code(grant["viewer_account_id"], "device",
                                  body.get("code"))
                _arrived(grant)
                agent = ((event.get("requestContext") or {}).get("http")
                         or {}).get("userAgent")
                return _reply(200, _issue_device(grant["viewer_account_id"],
                                                 agent))

            if route == "POST /view/{grant_id}/register/code":
                _arrived(grant)
                if _account(grant["viewer_account_id"]).get("registered"):
                    raise PermissionError(
                        "You have already registered. Sign in instead.")
                return _reply(200, _send_email_code(grant, "register"))
            if route == "POST /view/{grant_id}/register":
                _arrived(grant)
                # A verified device is optional here: fresh, it stands in for
                # the emailed code; otherwise the code is required as before.
                viewer_id = grant["viewer_account_id"]
                device = _known_device(
                    viewer_id, _table("viewer").get_item(
                        Key={"viewer_account_id": viewer_id},
                        ConsistentRead=True).get("Item") or {},
                    _device_from_headers(event.get("headers")))
                return _reply(200, _register(grant, body, device))
            return _reply(200, _confirm(grant, body))

        if route == "POST /viewer/sign-in":
            return _reply(200, _sign_in(body))
        if route == "POST /viewer/sign-in/mfa":
            return _reply(200, _sign_in_mfa(body))

        # A tenant, shared with: the customer pool's token, answered only
        # for the viewer account linked to this exact user.
        if route in ("GET /me/shared", "GET /me/shared/{grant_id}",
                     "POST /me/shared/{grant_id}/download"):
            if not tenant_token:
                return _reply(403, {"error": "not signed in"})
            linked = _linked_viewer(claims)
            if route == "GET /me/shared":
                if linked is None:
                    return _reply(200, {"linked": False, "shares": []})
                return _reply(200, dict(_mine(linked), linked=True))
            if linked is None:
                return _reply(404, {"error": LINK_DEAD})
            grant, refused = _authorised(grant_id, viewer_id=linked)
            if refused:
                return refused
            if route == "GET /me/shared/{grant_id}":
                _record(context, event, grant, "view")
                return _reply(200, _page(grant))
            copy = _download(grant)
            _record(context, event, grant, "download")
            return _reply(200, copy)

        # Signed in. The gateway's viewer-pool authorizer has verified the
        # token; with no email in it there is nobody to answer for.
        if signed_in is None:
            return _reply(403, {"error": "not signed in"})

        if route == "GET /viewer/shares":
            mine = _mine(signed_in)
            mine["trial_prompt"] = _trial_prompt_due(_account(signed_in))
            return _reply(200, mine)
        if route == "POST /viewer/trial-prompt":
            return _reply(200, _answer_trial_prompt(signed_in, body))

        if route in ("GET /viewer/shares/{grant_id}",
                     "POST /viewer/shares/{grant_id}/download"):
            grant, refused = _authorised(grant_id, viewer_id=signed_in)
            if refused:
                return refused
            if route == "GET /viewer/shares/{grant_id}":
                _record(context, event, grant, "view")
                return _reply(200, _page(grant))
            copy = _download(grant)
            _record(context, event, grant, "download")
            return _reply(200, copy)

        return _reply(404, {"error": "unknown route"})

    except DeviceNeeded as exc:
        return _reply(401, {"error": str(exc), "device_required": True,
                            "sent_to": exc.sent_to,
                            "registered": exc.registered})
    except CodeRequired:
        return _reply(400, {"error": "Confirm it's you again: ask for a "
                                     "code.", "code_required": True})
    except EmailNotSent:
        return _reply(502, {"error": EMAIL_CODE_NOT_SENT})
    except MfaSetupRestart as exc:
        return _reply(400, {"error": str(exc), "restart": True})
    except PermissionError as exc:
        return _reply(403, {"error": str(exc)})
    except ValueError as exc:
        return _reply(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - never leak internals
        print("[viewer-error] route=%s %r" % (route, exc))
        return _reply(500, {"error": "Something went wrong. Try again."})
