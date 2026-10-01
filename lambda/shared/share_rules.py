"""
share_rules.py - the rules a share lives by, for both of its halves.

The API sends, lists and revokes (lambda/api/share.py); the viewer function
serves a recipient (lambda/share_viewer/app.py). Both need to agree on what a
grant is called, who a recipient is, when access ends and whether a request
may see a memorandum. Written once, in the layer, because two copies of an
access rule is a hole the first time one of them changes.

PURE. Nothing here touches AWS. Every function takes what it needs and
returns an answer, so the rules can be read and tested on their own.

share_viewer_spec_v1, as amended 1 October 2026:

  verified    the recipient has only opened the link: 2 weeks from send
  registered  password, MFA and our terms: 6 months from that grant's own
              send - not from registering (UX02 12.5, settled 1 October)
  tenant-set  an expiry the tenant chose is a ceiling, and registering
              never moves it
"""

import datetime
import hashlib
import hmac
import os
import re
import secrets

VERIFIED_DAYS = 14
REGISTERED_MONTHS = 6

# 20 shares a day per tenant, every plan (share_viewer_spec section 9, settled
# 1 October 2026). Re-sending counts: it sends an email.
DAILY_LIMIT = 20

PENDING = "pending"
ACTIVE = "active"

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- names -----------------------------------------------------------------

def table(name):
    """A table's name, from the environment, read when it is needed. As
    mail.sender: a missing one fails the route that uses it, not every route
    in the function at import."""
    variable = {
        "grant": "SHARE_GRANT_TABLE",
        "viewer": "VIEWER_ACCOUNT_TABLE",
        "log": "SHARE_ACCESS_LOG_TABLE",
        "usage": "SHARE_USAGE_TABLE",
    }[name]
    value = os.environ.get(variable)
    if not value:
        raise RuntimeError("%s is not set" % variable)
    return value


def normalise_email(address):
    return str(address or "").strip().lower()


def valid_email(address):
    return bool(_EMAIL.match(normalise_email(address)))


def viewer_account_id(address):
    """Who a recipient is, before they have done anything.

    Derived from the address rather than minted, because the grant has to
    name its recipient at send and the account is not made until they open
    the link. The first 32 hex characters of sha256 of the lower-cased
    address: the address itself is not the key, so it does not appear in
    every index and every log line that names a grant."""
    digest = hashlib.sha256(normalise_email(address).encode("utf-8"))
    return digest.hexdigest()[:32]


def grant_id(memo_id, viewer_id):
    """One memorandum, one recipient. The key is the uniqueness rule."""
    return "%d#%s" % (int(memo_id), viewer_id)


def split_grant_id(value):
    """(memo_id, viewer_account_id), or None for anything malformed."""
    text = str(value or "")
    if "#" not in text:
        return None
    memo, viewer = text.split("#", 1)
    if not memo.isdigit() or not re.match(r"^[0-9a-f]{32}$", viewer):
        return None
    return int(memo), viewer


def object_prefix(tenant_id, memo_id, viewer_id):
    """Where a grant's PDFs live in the curated bucket. Under shares/ - the
    only prefix the viewer function may read or write."""
    return "shares/%d/%d/%s/" % (int(tenant_id), int(memo_id), viewer_id)


# --- the link --------------------------------------------------------------

def new_token():
    """The secret in a share link. 256 bits, URL-safe."""
    return secrets.token_urlsafe(32)


def token_matches(presented, held):
    """Constant time, so a wrong guess learns nothing from how long it took."""
    if not presented or not held:
        return False
    return hmac.compare_digest(str(presented).encode("utf-8"),
                               str(held).encode("utf-8"))


def token_from_header(headers):
    """The link token, from "Authorization: Share <token>".

    In a header rather than the path or the query string, so it is in no
    access log - the gateway's logs record the path. The browser takes it
    from the link's #fragment, which the browser never sends anywhere."""
    for key, value in (headers or {}).items():
        if key.lower() == "authorization":
            text = str(value or "").strip()
            if text.lower().startswith("share "):
                return text[6:].strip()
    return None


# --- time ------------------------------------------------------------------

def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def iso(moment):
    """2026-10-01T14:03:22Z. Sortable as a string, which is what lets the
    tenant index order by it."""
    return moment.astimezone(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def parse(text):
    return datetime.datetime.strptime(
        text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def add_months(moment, months):
    """Calendar months, the day clamped to the end of a shorter month: 31
    August plus six months is 28 or 29 February, not 3 March."""
    month = moment.month - 1 + months
    year = moment.year + month // 12
    month = month % 12 + 1
    for day in (moment.day, 30, 29, 28):
        try:
            return moment.replace(year=year, month=month, day=day)
        except ValueError:
            continue
    raise ValueError("no such date")


def expires_at(sent_at, registered, tenant_expiry=None):
    """When a grant ends.

    A date the tenant chose wins, whatever the recipient does - it is a
    deliberate limit, and registering must not lengthen it (section 6).
    Otherwise two weeks from send, or six calendar months from send once the
    recipient has registered."""
    if tenant_expiry is not None:
        return tenant_expiry
    if registered:
        return add_months(sent_at, REGISTERED_MONTHS)
    return sent_at + datetime.timedelta(days=VERIFIED_DAYS)


# --- may this request see it -----------------------------------------------

def refusal(grant, at, token=None, viewer_id=None):
    """Why a request may not see this grant, or None where it may.

    Exactly one of token and viewer_id is given: a link carries the token, a
    signed-in registered viewer carries their account id. Every reason a
    request is refused reads the same to the person making it - a link that
    does not work - so nothing here tells a guesser which part was wrong.
    The reason is for the log."""
    if not grant:
        return "no-grant"
    if token is not None:
        if not token_matches(token, grant.get("link_token")):
            return "bad-token"
    elif viewer_id is not None:
        if grant.get("viewer_account_id") != viewer_id:
            return "not-yours"
    else:
        return "no-credential"
    if grant.get("status") != ACTIVE:
        return "not-active"
    if grant.get("revoked"):
        return "revoked"
    if not grant.get("expires_at") or parse(grant["expires_at"]) <= at:
        return "expired"
    return None
