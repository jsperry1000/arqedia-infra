"""
app.py - the staff console's API. ARQEDIA's own people, reading.

THREE ROUTES, ALL GET, NOTHING WRITES:

    GET /tenants               every tenant, its plan, its seat count, when
                               it was created
    GET /tenants/{id}/seats    that tenant's seats and its open invitations
    GET /signups               signup_attempt, newest first, paged

WHO REACHES IT. The gateway verifies the token before this code runs, and
the authorizer in admin_api.tf names the STAFF pool's client as its audience
and the staff pool as its issuer. A customer's token is issued by a different
pool and carries a different audience, so it fails at the gateway and never
arrives - there is no code path here that could be persuaded to accept one.
The issuer is checked again below, against STAFF_POOL_ISSUER, because a
second reading of the same claim costs nothing and a misconfigured authorizer
is a silent failure otherwise.

NO TENANT COMES FROM THE TOKEN. This is the one API in the system where the
caller is not a tenant and the reads are not scoped to one. Every such read
lives in cross_tenant.py, named so that an import of it anywhere near the
customer path is impossible to miss.

NOTHING IS IMPORTED FROM lambda/api. Not a helper, not a dispatcher, not a
response shape. The staff console shares the database with the customer path
and nothing else, so a change to one cannot reach the other by accident.
"""

import json
import os

import cross_tenant

STAFF_POOL_ISSUER = os.environ["STAFF_POOL_ISSUER"]


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def _claims(event):
    return ((event.get("requestContext") or {})
            .get("authorizer", {})
            .get("jwt", {})
            .get("claims", {})) or {}


def _int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _paging(event):
    """limit and offset, both bounded.

    A limit larger than the maximum is clamped rather than refused: a staff
    screen asking for too much should get a page, not an error it has to
    handle."""
    query = event.get("queryStringParameters") or {}
    limit = _int(query.get("limit"), cross_tenant.SIGNUP_PAGE)
    limit = max(1, min(limit, cross_tenant.SIGNUP_PAGE_MAX))
    offset = max(0, _int(query.get("offset"), 0))
    return limit, offset


def _tenants(event):
    return _response(200, {"tenants": cross_tenant.every_tenant()})


def _seats(event):
    raw = (event.get("pathParameters") or {}).get("id")
    tenant_id = _int(raw, None)
    if tenant_id is None:
        return _response(400, {"error": "tenant id must be a number"})

    name = cross_tenant.tenant_name(tenant_id)
    if name is None:
        return _response(404, {"error": "no tenant %d" % tenant_id})

    return _response(200, {
        "tenant_id": tenant_id,
        "name": name,
        "seats": cross_tenant.seats_of(tenant_id),
        "invitations": cross_tenant.open_invitations_of(tenant_id),
    })


def _signups(event):
    limit, offset = _paging(event)
    attempts = cross_tenant.signup_attempts(limit, offset)
    total = cross_tenant.signup_count()
    return _response(200, {
        "attempts": attempts,
        "limit": limit,
        "offset": offset,
        "total": total,
        # None rather than a page past the end, so a caller stops without
        # having to compare two numbers itself.
        "next_offset": offset + limit if offset + limit < total else None,
    })


# Route key exactly as the gateway sends it. A key that is not here is a 404
# from this function, which should be unreachable: the gateway holds the same
# list and refuses anything else first.
ROUTES = {
    "GET /tenants": _tenants,
    "GET /tenants/{id}/seats": _seats,
    "GET /signups": _signups,
}


def lambda_handler(event, context):
    route = event.get("routeKey") or ""

    # The gateway has already verified the signature, the expiry and the
    # audience. This is the same claim read twice: if the authorizer were
    # ever pointed at another pool, every request would fail here rather than
    # quietly succeed.
    issuer = _claims(event).get("iss")
    if issuer != STAFF_POOL_ISSUER:
        print("[admin-refused] route=%s issuer=%r" % (route, issuer))
        return _response(403, {"error": "not a staff token"})

    handler = ROUTES.get(route)
    if handler is None:
        return _response(404, {"error": "no route %s" % route})

    print("[admin] route=%s sub=%s" % (route, _claims(event).get("sub")))
    return handler(event)
