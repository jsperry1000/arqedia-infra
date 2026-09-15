"""
signup/app.py - the only door.

A separate function from the API, deliberately, for two reasons.

The pool stays admin-create-only. If Cognito accepted registrations directly,
anyone could call it and skip every control below - the domain rule, the
disposable list, the rate limit - and end up with an account carrying no
tenant, signed in to an application that cannot answer a single request about
them. There is one way in and the controls are on it.

And this function holds Cognito administrative permissions. The API does not
and must not: a defect in any of its fifty routes would otherwise be a defect
that can create users.

Routes, all unauthenticated:

  POST /signup             run the checks, send a code, create nothing
  POST /signup/verify      check the code, create the tenant and the user
  POST /invitations/accept take a seat on a tenant somebody else owns

Nothing exists until the code comes back. That is what stops a throwaway
address taking a trial.

Accepting an invitation is here rather than in the API for the same reason
signing up is: the person has no token, because they have no account. It is
also the only other thing in the product that creates a Cognito user, and
those permissions live in exactly one function.
"""

import hashlib
import json
import os
import re
import secrets
import time
import datetime

import boto3
from botocore.exceptions import ClientError

_rds = boto3.client("rds-data")
_idp = boto3.client("cognito-idp")
_ses = boto3.client("ses")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]
USER_POOL_ID = os.environ["USER_POOL_ID"]
SENDER = os.environ["SENDER"]

# The trial, from the wallet specification. Thirty days, full use, $5.00 of
# metered credit, no card.
TRIAL_DAYS = 30

# A code lives fifteen minutes and may be got wrong five times. Both are
# deliberately short: a code that lives an hour is a code somebody else can
# use, and unlimited attempts on six digits is not a control at all.
CODE_MINUTES = 15
MAX_ATTEMPTS = 5

# Rate limits, per hour. The domain rule does most of the work; these stop a
# script rather than a person.
MAX_PER_IP_HOUR = 5
MAX_PER_DOMAIN_HOUR = 3

# Addresses that exist to be thrown away. A short list held here and a longer
# one behind a service are both defensible; a stale list is worse than none,
# because it reads as working. See ONB-01.
DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "yopmail.com",
    "tempmail.com", "temp-mail.org", "throwawaymail.com", "sharklasers.com",
    "getnada.com", "trashmail.com", "dispostable.com", "maildrop.cc",
    "fakeinbox.com", "mintemail.com", "mohmal.com", "spamgourmet.com",
}

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- plumbing, matching lambda/api/app.py ----------------------------------

def _sql(statement, params=None):
    """Data API call, retrying while the cluster wakes from zero capacity."""
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


def _reply(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _client_ip(event):
    """Recorded, never decided upon.

    Blocking on an address fails in both directions: a VPN defeats it in
    seconds, while a shared office connection blocks strangers who have
    nothing to do with each other. It is kept so that when an abuse flag
    fires a person can see nine attempts came from one connection.
    """
    return (event.get("requestContext", {})
                 .get("http", {})
                 .get("sourceIp"))


def _record(domain, email, ip, outcome, detail=None):
    _sql(
        """
        INSERT INTO signup_attempt
          (email_domain, email_hash, ip, outcome, detail)
        VALUES (:d, :h, :ip, :o, :detail)
        """,
        [_p("d", domain), _p("h", _sha(email)), _p("ip", ip),
         _p("o", outcome), _p("detail", detail)],
    )


# --- the checks ------------------------------------------------------------

def _refuse(domain, email, ip, outcome, message, detail=None):
    _record(domain, email, ip, outcome, detail)
    return _reply(400, {"error": message})


def _checks(email, domain, ip):
    """In the order that costs least. Returns a reply to send, or None."""

    if domain in DISPOSABLE:
        return _refuse(domain, email, ip, "disposable",
                       "That address will not last long enough to be useful. "
                       "Use your work address.")

    # One trial per email domain. A second person from a firm that already has
    # a tenant is not turned away - they are told to ask for a seat, which is
    # what they wanted.
    taken = _sql(
        "SELECT tenant_id, multi_allowed FROM tenant_domain WHERE domain = :d",
        [_p("d", domain)],
    ).get("records", [])
    if taken and not _col(taken[0], 1):
        return _refuse(domain, email, ip, "domain_taken",
                       f"{domain} already has an ARQEDIA workspace. Ask an "
                       f"administrator there to invite you to a seat.")

    hour = "DATE_SUB(NOW(), INTERVAL 1 HOUR)"

    per_domain = _sql(
        f"SELECT COUNT(*) FROM signup_attempt "
        f"WHERE email_domain = :d AND created_at > {hour}",
        [_p("d", domain)],
    )["records"][0]
    if _col(per_domain, 0) >= MAX_PER_DOMAIN_HOUR:
        return _refuse(domain, email, ip, "rate_limited",
                       "Too many attempts. Try again in an hour.",
                       "domain")

    if ip:
        per_ip = _sql(
            f"SELECT COUNT(*) FROM signup_attempt "
            f"WHERE ip = :ip AND created_at > {hour}",
            [_p("ip", ip)],
        )["records"][0]
        if _col(per_ip, 0) >= MAX_PER_IP_HOUR:
            return _refuse(domain, email, ip, "rate_limited",
                           "Too many attempts. Try again in an hour.", "ip")

    return None


# --- POST /signup ----------------------------------------------------------

def begin(event, body):
    email = (body.get("email") or "").strip().lower()
    if not EMAIL.match(email):
        return _reply(400, {"error": "That does not look like an email address."})

    domain = email.split("@", 1)[1]
    ip = _client_ip(event)

    refused = _checks(email, domain, ip)
    if refused:
        return refused

    # An address that already has an account is told to sign in, and no code
    # is sent. Telling somebody their address is already registered is not a
    # disclosure worth protecting: they can learn the same from the sign-in
    # screen, and hiding it makes the product feel broken.
    try:
        _idp.admin_get_user(UserPoolId=USER_POOL_ID, Username=email)
        return _refuse(domain, email, ip, "exists",
                       "That address already has an account. Sign in instead.")
    except _idp.exceptions.UserNotFoundException:
        pass

    code = f"{secrets.randbelow(1000000):06d}"
    expires = (datetime.datetime.utcnow()
               + datetime.timedelta(minutes=CODE_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

    # One row per address, replaced on a second attempt: asking for the code
    # again should send a new one rather than leave two valid.
    _sql(
        """
        INSERT INTO pending_signup
          (email, email_domain, code_hash, org_name, jurisdiction, region,
           pack, second_admin, ip, expires_at)
        VALUES (:e, :d, :c, :org, :j, :r, :pack, :second, :ip, :exp)
        ON DUPLICATE KEY UPDATE
          code_hash = VALUES(code_hash), attempts = 0,
          org_name = VALUES(org_name), jurisdiction = VALUES(jurisdiction),
          region = VALUES(region), pack = VALUES(pack),
          second_admin = VALUES(second_admin), ip = VALUES(ip),
          expires_at = VALUES(expires_at)
        """,
        [_p("e", email), _p("d", domain), _p("c", _sha(code)),
         _p("org", body.get("org_name")), _p("j", body.get("jurisdiction")),
         _p("r", body.get("region")), _p("pack", body.get("pack")),
         _p("second", body.get("second_admin")), _p("ip", ip),
         _p("exp", expires)],
    )

    _ses.send_email(
        Source=SENDER,
        Destination={"ToAddresses": [email]},
        Message={
            "Subject": {"Data": "Your ARQEDIA code"},
            "Body": {"Text": {"Data":
                f"Your code is {code}.\n\n"
                f"It lasts {CODE_MINUTES} minutes. If you did not ask for it, "
                f"nothing has been created and you can ignore this."}},
        },
    )

    _record(domain, email, ip, "code_sent")
    return _reply(200, {"sent": True, "expires_in": CODE_MINUTES * 60})


# --- POST /signup/verify ---------------------------------------------------

def verify(event, body):
    """The code is right, so make everything - in an order that cannot leave
    a Cognito user without a tenant.

    Tenant row first. If Cognito then refuses, the row is removed. The reverse
    order would leave an account that can sign in to an application which
    cannot answer a single request about it, and no way to tell from the
    outside that anything is wrong.
    """
    email = (body.get("email") or "").strip().lower()
    code = (body.get("code") or "").strip()
    password = body.get("password") or ""
    ip = _client_ip(event)

    rows = _sql(
        """
        SELECT pending_id, email_domain, code_hash, attempts, org_name,
               jurisdiction, region, pack, second_admin, expires_at
        FROM pending_signup WHERE email = :e
        """,
        [_p("e", email)],
    ).get("records", [])
    if not rows:
        return _reply(400, {"error": "Start again - that signup has expired."})

    r = rows[0]
    pending_id = _col(r, 0)
    domain = _col(r, 1)

    if _col(r, 3) >= MAX_ATTEMPTS:
        return _refuse(domain, email, ip, "too_many_codes",
                       "Too many wrong codes. Start again.")

    if str(_col(r, 9)) < datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"):
        return _refuse(domain, email, ip, "code_expired",
                       "That code has expired. Ask for another.")

    if _sha(code) != _col(r, 2):
        _sql("UPDATE pending_signup SET attempts = attempts + 1 "
             "WHERE pending_id = :id", [_p("id", pending_id)])
        return _reply(400, {"error": "That code is not right."})

    # The domain rule is checked again. Two people at one firm can reach this
    # point together, and the first to arrive takes the tenant.
    taken = _sql(
        "SELECT tenant_id, multi_allowed FROM tenant_domain WHERE domain = :d",
        [_p("d", domain)],
    ).get("records", [])
    if taken and not _col(taken[0], 1):
        return _refuse(domain, email, ip, "domain_taken",
                       f"{domain} already has an ARQEDIA workspace. Ask an "
                       f"administrator there to invite you to a seat.")

    org = _col(r, 4) or domain
    jurisdiction = _col(r, 5)
    region = _col(r, 6) or "us-east-2"
    pack = _col(r, 7)
    trial_ends = (datetime.datetime.utcnow()
                  + datetime.timedelta(days=TRIAL_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    _sql(
        """
        INSERT INTO tenant
          (name, region, jurisdiction, plan, trial_ends_at, forked_pack,
           signup_ip)
        VALUES (:name, :region, :j, 'base', :trial, :pack, :ip)
        """,
        [_p("name", org), _p("region", region), _p("j", jurisdiction),
         _p("trial", trial_ends), _p("pack", pack), _p("ip", ip)],
    )
    tenant_id = _sql("SELECT LAST_INSERT_ID()")["records"][0]
    tenant_id = _col(tenant_id, 0)

    try:
        _sql(
            "INSERT INTO tenant_domain (domain, tenant_id) VALUES (:d, :t)",
            [_p("d", domain), _p("t", tenant_id)],
        )

        # SUPPRESS: no invitation email. The person is standing in front of
        # the screen and is about to set their own password, so an email
        # carrying a temporary one would be noise and a second credential.
        _idp.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": body.get("person_name") or email},
                {"Name": "custom:tenant_id", "Value": str(tenant_id)},
                {"Name": "custom:role", "Value": "admin"},
            ],
        )
        _idp.admin_set_user_password(
            UserPoolId=USER_POOL_ID, Username=email,
            Password=password, Permanent=True,
        )
    except Exception as exc:
        # Nothing half-made survives this handler.
        _sql("DELETE FROM tenant_domain WHERE tenant_id = :t",
             [_p("t", tenant_id)])
        _sql("DELETE FROM tenant WHERE tenant_id = :t", [_p("t", tenant_id)])
        try:
            _idp.admin_delete_user(UserPoolId=USER_POOL_ID, Username=email)
        except Exception:
            pass
        _record(domain, email, ip, "failed", str(exc)[:200])
        return _reply(500, {"error": "The account could not be created. "
                                     "Nothing was charged and nothing was kept."})

    _sql("DELETE FROM pending_signup WHERE pending_id = :id",
         [_p("id", pending_id)])
    _record(domain, email, ip, "created", f"tenant {tenant_id}")

    # The pack is recorded, not forked here. First run forks it, which is
    # where a person can see what they are getting and change their mind.
    return _reply(200, {
        "tenant_id": tenant_id,
        "trial_ends_at": trial_ends,
        "pack": pack,
    })


# --- POST /invitations/accept ---------------------------------------------

def accept(event, body):
    """Turn a valid invitation into a seat and an account.

    The seat is counted at this moment, not when the invitation was sent. An
    invitation issued while a seat was free can still fail because somebody
    else accepted first - which is the correct answer, and the message says
    so rather than failing obscurely.

    Seat first, then the Cognito user, and the seat is given back if the user
    cannot be made. The reverse order leaves somebody able to sign in to a
    workspace that does not list them.
    """
    email = (body.get("email") or "").strip().lower()
    token = (body.get("token") or "").strip()
    password = body.get("password") or ""
    ip = _client_ip(event)

    if not email or not token:
        return _reply(400, {"error": "That invitation link is incomplete."})
    domain = email.split("@", 1)[1] if "@" in email else ""

    rows = _sql(
        """
        SELECT invitation_id, tenant_id, role, token_hash, expires_at,
               invited_by
        FROM seat_invitation
        WHERE email = :e AND revoked_at IS NULL
        """,
        [_p("e", email)],
    ).get("records", [])
    if not rows:
        return _reply(400, {"error": "That invitation is no longer open."})

    r = rows[0]
    invitation_id, tenant_id, role = _col(r, 0), _col(r, 1), _col(r, 2)

    if _sha(token) != _col(r, 3):
        return _reply(400, {"error": "That invitation link is not valid."})
    if str(_col(r, 4)) < datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"):
        return _reply(400, {"error": "That invitation has expired. Ask the "
                                     "person who sent it for another."})

    # How many the plan buys, and how many are taken. Kept in step with
    # lambda/api/seats.py: "business" is what tenant.plan holds for the Small
    # Business plan, whatever the specification calls it.
    plan_rows = _sql("SELECT plan FROM tenant WHERE tenant_id = :t",
                     [_p("t", tenant_id)]).get("records", [])
    plan = ((_col(plan_rows[0], 0) if plan_rows else "base") or "base").strip().lower()
    bought = {"base": 2, "business": 5, "small_business": 5}.get(plan, 2)

    taken = _col(_sql("SELECT COUNT(*) FROM seat WHERE tenant_id = :t",
                      [_p("t", tenant_id)])["records"][0], 0)
    if taken >= bought:
        return _reply(409, {"error": "Every seat in that workspace is taken. "
                                     "Ask an administrator to free one, then "
                                     "open this link again."})

    _sql(
        "INSERT INTO seat (tenant_id, email, role, invited_by) "
        "VALUES (:t, :e, :r, :by)",
        [_p("t", tenant_id), _p("e", email), _p("r", role),
         _p("by", _col(r, 5))],
    )

    try:
        _idp.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            MessageAction="SUPPRESS",
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": body.get("person_name") or email},
                {"Name": "custom:tenant_id", "Value": str(tenant_id)},
                {"Name": "custom:role", "Value": role},
            ],
        )
        _idp.admin_set_user_password(
            UserPoolId=USER_POOL_ID, Username=email,
            Password=password, Permanent=True,
        )
    except Exception as exc:
        _sql("DELETE FROM seat WHERE tenant_id = :t AND email = :e",
             [_p("t", tenant_id), _p("e", email)])
        try:
            _idp.admin_delete_user(UserPoolId=USER_POOL_ID, Username=email)
        except Exception:
            pass
        _record(domain, email, ip, "invite_failed", str(exc)[:200])
        return _reply(500, {"error": "The account could not be created. "
                                     "Nothing was kept, and the invitation is "
                                     "still open."})

    _sql("DELETE FROM seat_invitation WHERE invitation_id = :i",
         [_p("i", invitation_id)])
    _record(domain, email, ip, "seat_taken", f"tenant {tenant_id}")

    return _reply(200, {"tenant_id": tenant_id, "role": role, "email": email})


def lambda_handler(event, context):
    route = event.get("routeKey", "")
    try:
        body = json.loads(event.get("body") or "{}")
    except ValueError:
        return _reply(400, {"error": "Malformed request."})

    try:
        if route == "POST /signup":
            return begin(event, body)
        if route == "POST /signup/verify":
            return verify(event, body)
        if route == "POST /invitations/accept":
            return accept(event, body)
        return _reply(404, {"error": "No such route."})
    except Exception as exc:  # noqa: BLE001 - nothing may escape to the client
        print("signup failed:", repr(exc))
        return _reply(500, {"error": "Something went wrong. Nothing was created."})
