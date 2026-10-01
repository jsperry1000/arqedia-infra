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
                 request after it is refused.
  Signed in      a registered viewer's token from the viewer pool, on the
                 /viewer/shares routes. The gateway verifies it; this checks
                 the grant names the same person.

EVERY REFUSAL READS THE SAME. A wrong token, a revoked grant, an expired one
and one that never existed all say the link does not work. The log says
which; the person does not learn which part of a guess was wrong.

Routes:
  GET  /view/{grant_id}                     the memorandum, by its link
  POST /view/{grant_id}/download            a copy stamped with this moment
  POST /view/{grant_id}/register            a password, then MFA setup
  POST /view/{grant_id}/register/confirm    the authenticator's first code
  POST /viewer/sign-in                      a registered viewer, password
  POST /viewer/sign-in/mfa                  ... and the code
  GET  /viewer/shares                       everything shared with them
  GET  /viewer/shares/{grant_id}            one of them, signed in
  POST /viewer/shares/{grant_id}/download   a copy of it, signed in
"""

import hashlib
import json
import os
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


def _page(grant):
    """What the viewer page shows around the memorandum."""
    g = _plain(grant)
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


# --- registering -------------------------------------------------------------

def _register(grant, body):
    """A password, then the authenticator. Nothing is marked registered until
    the first code is right (_confirm)."""
    if body.get("accept_terms") is not True:
        raise ValueError("Registering means accepting the terms and privacy "
                         "policy.")
    password = str(body.get("password") or "")
    if not password:
        raise ValueError("Choose a password.")

    account = _account(grant["viewer_account_id"])
    if account.get("registered"):
        raise PermissionError("You have already registered. Sign in instead.")

    email = grant["recipient_email"]
    # THE ADDRESS IS VERIFIED: the person holds a link that was sent to it
    # and to nobody else. Cognito sends nothing.
    try:
        _cognito.admin_create_user(
            UserPoolId=VIEWER_POOL_ID, Username=email,
            UserAttributes=[{"Name": "email", "Value": email},
                            {"Name": "email_verified", "Value": "true"}],
            MessageAction="SUPPRESS")
    except ClientError as exc:
        # An earlier registration that never finished its MFA setup. The
        # account item says not registered, so the user is theirs to finish.
        if _code(exc) != "UsernameExistsException":
            raise

    try:
        # THE PASSWORD IS NEVER STORED. It passes through here once, to the
        # pool, as signup's does (CLAUDE.md, Signing up).
        _cognito.admin_set_user_password(
            UserPoolId=VIEWER_POOL_ID, Username=email, Password=password,
            Permanent=True)
    except ClientError as exc:
        if _code(exc) == "InvalidPasswordException":
            raise ValueError("That password is not accepted: at least 12 "
                             "characters, with upper case, lower case and a "
                             "number.")
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
    return {"session": associated["Session"], "secret_code": secret,
            "otpauth": "otpauth://totp/%s?secret=%s&issuer=ARQEDIA"
                       % (label, secret)}


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
        if _code(exc) in ("CodeMismatchException", "EnableSoftwareTokenMFAException",
                          "NotAuthorizedException"):
            raise ValueError(CODE_FAILED)
        raise
    if verified.get("Status") != "SUCCESS":
        raise ValueError(CODE_FAILED)

    signed_in = _cognito.admin_respond_to_auth_challenge(
        UserPoolId=VIEWER_POOL_ID, ClientId=VIEWER_CLIENT_ID,
        ChallengeName="MFA_SETUP",
        ChallengeResponses={"USERNAME": email},
        Session=verified["Session"])
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
    signed_in = rules.viewer_account_id(claims["email"]) \
        if claims.get("email") else None

    try:
        if route in ("GET /view/{grant_id}", "POST /view/{grant_id}/download",
                     "POST /view/{grant_id}/register",
                     "POST /view/{grant_id}/register/confirm"):
            grant, refused = _authorised(grant_id, token=token or "")
            if refused:
                return refused

            if route == "GET /view/{grant_id}":
                _arrived(grant)
                _record(context, event, grant, "view")
                return _reply(200, _page(grant))
            if route == "POST /view/{grant_id}/download":
                _arrived(grant)
                # Recorded once the copy exists, not before: a download that
                # failed is not one somebody took.
                copy = _download(grant)
                _record(context, event, grant, "download")
                return _reply(200, copy)
            if route == "POST /view/{grant_id}/register":
                _arrived(grant)
                return _reply(200, _register(grant, body))
            return _reply(200, _confirm(grant, body))

        if route == "POST /viewer/sign-in":
            return _reply(200, _sign_in(body))
        if route == "POST /viewer/sign-in/mfa":
            return _reply(200, _sign_in_mfa(body))

        # Signed in. The gateway's viewer-pool authorizer has verified the
        # token; with no email in it there is nobody to answer for.
        if signed_in is None:
            return _reply(403, {"error": "not signed in"})

        if route == "GET /viewer/shares":
            return _reply(200, _mine(signed_in))

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

    except PermissionError as exc:
        return _reply(403, {"error": str(exc)})
    except ValueError as exc:
        return _reply(400, {"error": str(exc)})
    except Exception as exc:  # noqa: BLE001 - never leak internals
        print("[viewer-error] route=%s %r" % (route, exc))
        return _reply(500, {"error": "Something went wrong. Try again."})
