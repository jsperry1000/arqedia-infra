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

# The trial. Fourteen days in all cases, full use, $5.00 of metered credit, no
# card (decision record, amendment of 17 September 2026; was thirty, Wallet
# section 2).
TRIAL_DAYS = 14

# The $5.00, granted when the tenant is made. Not lazily, on the first look at
# the balance: the signup screen promises it, so it must be true from the
# moment the account exists, not from the moment somebody checks. Without it a
# new tenant cannot file a single document.
TRIAL_CENTS = 500

# A code lives fifteen minutes and may be got wrong five times. Both are
# deliberately short: a code that lives an hour is a code somebody else can
# use, and unlimited attempts on six digits is not a control at all.
CODE_MINUTES = 15
MAX_ATTEMPTS = 5

# Rate limits, per hour. The domain rule does most of the work; these stop a
# script rather than a person.
MAX_PER_IP_HOUR = 5
MAX_PER_DOMAIN_HOUR = 3

# What somebody came to do (decision record, amendment of 17 September 2026).
INTENTS = {"trial", "subscribe"}

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

def _retrying(call):
    """Retry while the cluster wakes from zero capacity."""
    for _ in range(12):
        try:
            return call()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in (
                "DatabaseResumingException", "ThrottlingException"
            ):
                time.sleep(3)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _sql(statement, params=None, tx=None):
    """Data API call. With tx, the statement joins that transaction."""
    extra = {"transactionId": tx} if tx else {}
    return _retrying(lambda: _rds.execute_statement(
        resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
        database=DATABASE, sql=statement, parameters=params or [], **extra))


def _begin():
    return _retrying(lambda: _rds.begin_transaction(
        resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
        database=DATABASE))["transactionId"]


def _commit(tx):
    _rds.commit_transaction(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                            transactionId=tx)


def _rollback(tx):
    _rds.rollback_transaction(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                              transactionId=tx)


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

NOT_INVITED = ("ARQEDIA is not open for signup yet. If you have been invited, "
               "use the link in your invitation.")


def _invited(email):
    """Whether this address may create an account at all.

    THE ONLY GATE ON WHO. Everything else in _checks is about abuse volume or
    duplication - a disposable domain, one trial per domain, two rate limits -
    and none of them asks who somebody is. Until this, anyone with a real
    mailbox on an unclaimed domain got a tenant, a trial and $5.00 of credit.

    FAILS SHUT. An empty table refuses everyone. A lookup that cannot reach
    the database raises, and the handler answers 500 rather than letting
    somebody through - the failure mode of a gate must be closed.

    The address arrives lowercased from begin/verify, and signup_allow is
    _ci, so a lookup matches whatever case was stored. Both, deliberately:
    either alone would work until somebody changed the other."""
    rows = _sql(
        "SELECT email FROM signup_allow WHERE email = :e",
        [_p("e", email)],
    ).get("records", [])
    return bool(rows)


def _refuse(domain, email, ip, outcome, message, detail=None):
    _record(domain, email, ip, outcome, detail)
    return _reply(400, {"error": message})


def _checks(email, domain, ip):
    """In the order that costs least. Returns a reply to send, or None."""

    # FIRST, before anything that reveals the state of the system. An
    # uninvited address costs one primary-key lookup and learns nothing about
    # which domains are taken.
    invited = _invited(email)
    if not invited:
        return _refuse(domain, email, ip, "not_invited", NOT_INVITED)

    if domain in DISPOSABLE:
        return _refuse(domain, email, ip, "disposable",
                       "That address will not last long enough to be useful. "
                       "Use your work address.")

    # One trial per email domain. A second person from a firm that already has
    # a tenant is not turned away - they are told to ask for a seat, which is
    # what they wanted.
    #
    # NOT APPLIED TO AN INVITED ADDRESS. The rule exists to stop a firm taking
    # a second free trial by signing up twice; the allowlist already decides
    # who may sign up, one address at a time, so a second decision by domain
    # would overrule a decision already made deliberately. Two of the four
    # seeded addresses are at domains that are already claimed.
    #
    # The disposable list and both rate limits still apply: those are about
    # abuse, and an invitation is not a licence to hammer the endpoint.
    if not invited:
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

def _plan_and_intent(body):
    """The plan and intent the pricing page sent, checked, or a sentence
    saying what is wrong with them.

    PROPOSED: both absent is allowed and stored as NULL. That is a signup from
    a screen that does not ask - today's - and NULL says exactly that. Present
    and wrong is refused."""
    plan = body.get("plan")
    intent = body.get("intent")
    if intent is not None and (not isinstance(intent, str)
                               or intent not in INTENTS):
        return None, None, "Choose a trial or a subscription."
    # Against the plan rows, not a list held here: a plan is a row (Plans
    # section 1), and one made inactive stops being offered.
    if plan is not None and (not isinstance(plan, str) or not _sql(
            "SELECT 1 FROM plan WHERE plan_key = :k AND active = 1",
            [_p("k", plan)]).get("records")):
        return None, None, "Choose Base or Small Business."
    # PROPOSED: subscribing needs a plan to subscribe to.
    if intent == "subscribe" and plan is None:
        return None, None, "Choose a plan to subscribe to."
    return plan, intent, None


def begin(event, body):
    email = (body.get("email") or "").strip().lower()
    if not EMAIL.match(email):
        return _reply(400, {"error": "That does not look like an email address."})

    # Refused before the checks, and not recorded as an attempt, as a
    # malformed address is not. PROPOSED.
    plan, intent, problem = _plan_and_intent(body)
    if problem:
        return _reply(400, {"error": problem})

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
    #
    # The plan and intent are held here, server-side, so a code opened on
    # another device still knows what was chosen on the pricing page
    # (amendment of 17 September 2026). The verifying browser is not trusted
    # to remember them.
    _sql(
        """
        INSERT INTO pending_signup
          (email, email_domain, code_hash, org_name, jurisdiction, region,
           pack, plan, intent, second_admin, ip, expires_at)
        VALUES (:e, :d, :c, :org, :j, :r, :pack, :plan, :intent, :second, :ip,
                :exp)
        ON DUPLICATE KEY UPDATE
          code_hash = VALUES(code_hash), attempts = 0,
          org_name = VALUES(org_name), jurisdiction = VALUES(jurisdiction),
          region = VALUES(region), pack = VALUES(pack),
          plan = VALUES(plan), intent = VALUES(intent),
          second_admin = VALUES(second_admin), ip = VALUES(ip),
          expires_at = VALUES(expires_at)
        """,
        [_p("e", email), _p("d", domain), _p("c", _sha(code)),
         _p("org", body.get("org_name")), _p("j", body.get("jurisdiction")),
         _p("r", body.get("region")), _p("pack", body.get("pack")),
         _p("plan", plan), _p("intent", intent),
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
    a Cognito user without a tenant, or a tenant half made.

    ONE TRANSACTION. The tenant row, its domain claim, the founding
    administrator's seat and the trial bucket are written inside it, then the
    Cognito user is made, and only then does it commit. If Cognito refuses, the
    transaction rolls back and there is nothing to delete. If the commit fails
    after Cognito succeeded, the user this call created is deleted. Nothing is
    ever deleted by an id read back from the database.

    THE ID COMES FROM THE INSERT. It used to be a separate
    `SELECT LAST_INSERT_ID()`, which is per connection; the Data API does not
    promise the same connection between calls, so on dev it returned 0. The
    domain claim, the Cognito user's custom:tenant_id and the rollback all
    used that 0 - the pack tenant. generatedFields carries the id on the
    insert's own response, as it already does in the API, the normalizer and
    composition, and an id that is missing or not above zero stops everything
    before another row is written.
    """
    email = (body.get("email") or "").strip().lower()
    code = (body.get("code") or "").strip()
    password = body.get("password") or ""
    ip = _client_ip(event)

    rows = _sql(
        """
        SELECT pending_id, email_domain, code_hash, attempts, org_name,
               jurisdiction, region, pack, second_admin, expires_at,
               plan, intent
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

    # CHECKED AGAIN HERE, not only in begin(). A pending_signup row lives
    # fifteen minutes, so one created before an address was removed from the
    # allowlist - or before the allowlist existed at all - could otherwise be
    # verified afterwards. The window is small and closing it costs one query.
    invited = _invited(email)
    if not invited:
        return _refuse(domain, email, ip, "not_invited", NOT_INVITED)

    # The domain rule is checked again. Two people at one firm can reach this
    # point together, and the first to arrive takes the tenant. An invited
    # address is past it, for the reason given in _checks.
    if not invited:
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
    # Appended after expires_at so no earlier index moves. What was asked for,
    # not the plan: tenant.plan stays 'base' and subscription.plan_id decides
    # once Paddle reports a payment (CLAUDE.md, Money).
    signup_plan = _col(r, 10)
    signup_intent = _col(r, 11)
    trial_ends = (datetime.datetime.utcnow()
                  + datetime.timedelta(days=TRIAL_DAYS)).strftime("%Y-%m-%d %H:%M:%S")

    # forked_pack IS NO LONGER WRITTEN (TPL-02). Signup stopped asking which
    # memorandum somebody wants - Get started asks it, against the memoranda
    # that exist. Nobody chooses here, so there is nothing honest to record,
    # and a column NULL for every new tenant would drive a pre-tick that never
    # fires: dead code wearing the face of live code.
    #
    # The column stays. Dropping it is a destructive migration for no gain, and
    # the rows already in it record something that was true when it was asked.
    # `pack` is still selected above and still accepted by begin(), which
    # stores it on pending_signup: the field is part of the request contract
    # and removing it from the SELECT would shift every index after it.
    tx = _begin()
    user_made = False
    try:
        created = _sql(
            """
            INSERT INTO tenant
              (name, region, jurisdiction, plan, trial_ends_at, signup_ip,
               signup_plan, signup_intent)
            VALUES (:name, :region, :j, 'base', :trial, :ip, :sp, :si)
            """,
            [_p("name", org), _p("region", region), _p("j", jurisdiction),
             _p("trial", trial_ends), _p("ip", ip),
             _p("sp", signup_plan), _p("si", signup_intent)],
            tx=tx,
        )
        tenant_id = (created.get("generatedFields") or [{}])[0].get("longValue")
        # Tenant 0 is the pack tenant. An id that is missing, zero or negative
        # is refused here, before it can become a domain claim, a seat, a
        # bucket or a Cognito attribute.
        if not isinstance(tenant_id, int) or tenant_id <= 0:
            raise RuntimeError(f"tenant insert returned no usable id: {tenant_id!r}")

        # THE CLAIM IS TAKEN ONLY IF IT IS FREE.
        #
        # An invited address is past the domain rule above, so it can reach
        # here with the domain already claimed - gmail.com is held by tenant
        # 0. A bare INSERT would hit the primary key and roll the whole
        # transaction back, AFTER the code was verified, answering 500 and
        # naming nothing.
        #
        # NOT "INSERT IGNORE". MySQL's own manual: "With IGNORE, invalid
        # values are adjusted to the closest values and inserted; warnings are
        # produced but the statement does not abort." It downgrades data
        # conversions, over-length strings and illegal dates as well as
        # duplicate keys - so it would silently write a TRUNCATED domain
        # rather than fail, and we would never know. A gate that hides the
        # thing it was put there to catch is worse than no gate.
        #
        # So: look, then write. The existing row is never updated, never
        # replaced, and keeps its own created_at and multi_allowed.
        held = _sql(
            "SELECT tenant_id FROM tenant_domain WHERE domain = :d",
            [_p("d", domain)],
            tx=tx,
        ).get("records", [])
        if held:
            # The new tenant has NO domain claim, and therefore no home_domain
            # on its Seats screen, so no colleague is marked as outside the
            # firm. Accepted deliberately; recorded in the handoff.
            print("[claim-held] domain=%s new_tenant=%s held_by=%s" % (
                domain, tenant_id, _col(held[0], 0)))
        else:
            _sql(
                "INSERT INTO tenant_domain (domain, tenant_id) VALUES (:d, :t)",
                [_p("d", domain), _p("t", tenant_id)],
                tx=tx,
            )

        # The founding administrator holds a seat like anybody else. Without
        # one the seats screen counts nobody and the last-administrator rule
        # has nobody to protect.
        _sql(
            "INSERT INTO seat (tenant_id, email, role, invited_by) "
            "VALUES (:t, :e, 'admin', NULL)",
            [_p("t", tenant_id), _p("e", email)],
            tx=tx,
        )

        # The trial credit, expiring with the trial. Kept in step with
        # wallet.grant in lambda/shared/wallet.py, which this function cannot
        # import: it has no layer. No ledger row, as grant writes none - the
        # ledger records charges, and this is money put in.
        _sql(
            """
            INSERT INTO wallet_bucket
              (tenant_id, kind, granted_cents, expires_at, reference)
            VALUES (:t, 'trial', :c, :exp, 'granted at signup')
            """,
            [_p("t", tenant_id), _p("c", TRIAL_CENTS), _p("exp", trial_ends)],
            tx=tx,
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
        user_made = True
        _idp.admin_set_user_password(
            UserPoolId=USER_POOL_ID, Username=email,
            Password=password, Permanent=True,
        )

        _commit(tx)
    except Exception as exc:
        # Nothing half-made survives this handler, and nothing is deleted by
        # an id: the rows were never committed, so rolling back removes them.
        try:
            _rollback(tx)
        except Exception:
            pass
        # Only a user this call made. begin() refuses an address that already
        # has one, but a user made by somebody else in between is not ours.
        if user_made:
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

    # Nothing about memoranda comes back, because nothing was chosen here. Get
    # started is where they are picked, and it reads what we ship rather than
    # what an account once said it wanted.
    return _reply(200, {
        "tenant_id": tenant_id,
        "trial_ends_at": trial_ends,
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

    # Tenant 0 is ARQEDIA's own workspace: it holds what every tenant forks
    # from, and a seat there decides what all of them are offered. An
    # invitation is how a customer's colleague joins, and it is not the way
    # somebody gets in here. The seat is made by hand instead.
    #
    # Checked before the token, because a token that matches does not make
    # the destination right, and refused as an invitation that is not open -
    # which is what it is.
    if not isinstance(tenant_id, int) or tenant_id <= 0:
        return _refuse(domain, email, ip, "invite_refused",
                       "That invitation names the ARQEDIA workspace, which "
                       "nobody joins by invitation. Ask for a seat to be "
                       "created.")

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
