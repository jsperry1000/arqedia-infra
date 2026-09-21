"""
cross_tenant.py - the queries that deliberately have no tenant clause.

EVERY OTHER MODULE IN THIS SYSTEM IS WRONG IF IT LOOKS LIKE THIS ONE. The
customer API reads the tenant from a verified token and from nowhere else,
and every statement it issues carries `tenant_id = :t`. That single rule is
the whole isolation model. This file breaks it on purpose, for the staff
console, and it is a separate file so that the break is visible in an import
line rather than buried in a WHERE clause somebody has to notice is missing.

It is named cross_tenant so that a `from cross_tenant import ...` in any
function that serves a customer is obvious in review. Nothing in lambda/api
imports this, and nothing here imports lambda/api - the two directories do
not share a line of code, which is Group 16's decision about what the staff
console may reuse: the database, and nothing else.

READ-ONLY, AND NOT BY CONVENTION ALONE. Every statement goes through _read,
which refuses anything that is not a SELECT before it reaches the Data API.
That is a real guard on this code, and it is NOT a guard on the credentials:
rds-data:ExecuteStatement outside a transaction autocommits, so the role
could write if somebody wrote a statement that got past the check. The
control that would survive a careless edit is a SELECT-only database user -
OBS-02 in the backlog - and it is not built.
"""

import os
import time

import boto3
from botocore.exceptions import ClientError

_rds = boto3.client("rds-data")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

# A page of signups. Bounded so one request cannot ask for the table.
SIGNUP_PAGE = 50
SIGNUP_PAGE_MAX = 200


class NotASelect(Exception):
    """Raised before anything reaches the database."""


def _read(statement, params=None):
    """One SELECT, with the cluster's resume retried.

    THE GUARD IS HERE, at the only door out of this module, rather than at
    each call site - a call site can be added without one."""
    if not statement.lstrip().upper().startswith("SELECT"):
        raise NotASelect(
            "the staff console reads; this module issues SELECT and nothing "
            "else: %r" % statement[:60])

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
    if isinstance(value, int) and not isinstance(value, bool):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _v(cell):
    if cell.get("isNull"):
        return None
    for key in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if key in cell:
            return cell[key]
    return None


def _records(result):
    return [[_v(c) for c in row] for row in result.get("records", [])]


# --- the three reads -------------------------------------------------------

# TWO PLANS, BOTH SHOWN. tenant.plan is a copy written from the subscription
# for readers that predate that table; subscription.plan_id is the plan. A
# staff screen that showed one of them would be the place where the copy
# having drifted from the original became invisible, so it shows both and
# lets a person see they disagree.
_TENANTS = """
SELECT t.tenant_id,
       t.name,
       t.plan,
       p.plan_key,
       s.status,
       (SELECT COUNT(*) FROM seat st WHERE st.tenant_id = t.tenant_id),
       t.created_at,
       t.trial_ends_at,
       t.active_revision
FROM tenant t
LEFT JOIN subscription s ON s.tenant_id = t.tenant_id
LEFT JOIN plan p ON p.plan_id = s.plan_id
ORDER BY t.tenant_id
"""

_SEATS = """
SELECT seat_id, email, role, invited_by, accepted_at
FROM seat
WHERE tenant_id = :t
ORDER BY accepted_at, seat_id
"""

# OPEN means neither revoked nor lapsed. A seat is reserved for seven days
# and then lapses, so an invitation past its date is not an outstanding one
# and counting it as such would overstate what a tenant has committed.
_INVITATIONS = """
SELECT invitation_id, email, role, invited_by, created_at, expires_at
FROM seat_invitation
WHERE tenant_id = :t
  AND revoked_at IS NULL
  AND expires_at > NOW()
ORDER BY created_at DESC
"""

_TENANT_NAME = "SELECT name FROM tenant WHERE tenant_id = :t"

# THE ADDRESS IS NOT HERE TO BE SHOWN. signup_attempt keeps a domain and a
# hash, never the address itself, so this screen reports who tried by domain
# and cannot report by person. That is the schema's decision, not this
# module's, and the hash is returned because it is what makes two attempts
# from one address recognisable as the same person.
_SIGNUPS = """
SELECT attempt_id, email_domain, email_hash, ip, outcome, detail, created_at
FROM signup_attempt
ORDER BY attempt_id DESC
LIMIT :limit OFFSET :offset
"""

_SIGNUP_COUNT = "SELECT COUNT(*) FROM signup_attempt"


def every_tenant():
    """Every tenant in the system. No clause, on purpose."""
    return [
        {
            "tenant_id": r[0],
            "name": r[1],
            "plan": r[2],
            "subscription_plan": r[3],
            "subscription_status": r[4],
            "seats": r[5],
            "created_at": r[6],
            "trial_ends_at": r[7],
            "active_revision": r[8],
        }
        for r in _records(_read(_TENANTS))
    ]


def tenant_name(tenant_id):
    """The tenant's name, or None where there is no such tenant.

    Asked separately so that a request for a tenant that does not exist is a
    404 rather than an empty seat list, which reads as "nobody has joined"."""
    rows = _records(_read(_TENANT_NAME, [_p("t", tenant_id)]))
    return rows[0][0] if rows else None


def seats_of(tenant_id):
    return [
        {
            "seat_id": r[0],
            "email": r[1],
            "role": r[2],
            "invited_by": r[3],
            "accepted_at": r[4],
        }
        for r in _records(_read(_SEATS, [_p("t", tenant_id)]))
    ]


def open_invitations_of(tenant_id):
    return [
        {
            "invitation_id": r[0],
            "email": r[1],
            "role": r[2],
            "invited_by": r[3],
            "created_at": r[4],
            "expires_at": r[5],
        }
        for r in _records(_read(_INVITATIONS, [_p("t", tenant_id)]))
    ]


def signup_attempts(limit, offset):
    rows = _records(_read(_SIGNUPS,
                          [_p("limit", limit), _p("offset", offset)]))
    return [
        {
            "attempt_id": r[0],
            "email_domain": r[1],
            "email_hash": r[2],
            "ip": r[3],
            "outcome": r[4],
            "detail": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def signup_count():
    rows = _records(_read(_SIGNUP_COUNT))
    return rows[0][0] if rows else 0
