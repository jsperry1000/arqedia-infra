"""
billing.py - paying for a plan, changing it, and topping up.

Self-contained, as wallet.py and seats.py are: app.py imports this.

Nothing here grants money. Paddle's webhooks do that, through the processor,
once a payment has completed (decision record item 6). What happens here is
asking Paddle to take one.
"""

import os
import time

import boto3
from botocore.exceptions import ClientError

import paddle_api
import seats
import wallet

_rds = boto3.client("rds-data")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

TOPUP_INCREMENT_CENTS = 500
# 50 is a placeholder (decision record section 1), and the Paddle price's own
# maximum.
MAX_INCREMENTS = 50


class Refused(Exception):
    """Understood, and not possible in this state. 409."""


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


def _require_admin(role):
    # The same sentence the seat routes use, so the refusal names what was
    # refused.
    if role != "admin":
        raise PermissionError(
            "only an administrator may change seats, the plan or the card")


# --- reading ---------------------------------------------------------------

def _plans():
    rows = _sql(
        """
        SELECT plan_key, name, seat_count, monthly_price_cents,
               monthly_credit_cents, share_allowance
        FROM plan WHERE active = 1 ORDER BY monthly_price_cents
        """).get("records", [])
    return [{"plan_key": _col(r, 0), "name": _col(r, 1),
             "seat_count": _col(r, 2), "monthly_price_cents": _col(r, 3),
             "monthly_credit_cents": _col(r, 4),
             "share_allowance": _col(r, 5)} for r in rows]


def _plan(plan_key):
    return next((p for p in _plans() if p["plan_key"] == plan_key), None)


def _subscription(tenant_id):
    rows = _sql(
        """
        SELECT s.paddle_subscription_id, s.paddle_status,
               s.current_period_ends_at, p.plan_key
        FROM subscription s JOIN plan p ON p.plan_id = s.plan_id
        WHERE s.tenant_id = :t
        """,
        [_p("t", tenant_id)]).get("records", [])
    if not rows:
        return None
    r = rows[0]
    return {"paddle_subscription_id": _col(r, 0), "paddle_status": _col(r, 1),
            "current_period_ends_at": _col(r, 2), "plan_key": _col(r, 3)}


def _known_plan(body):
    plan_key = (body or {}).get("plan")
    if plan_key not in paddle_api.PLAN_PRICES or _plan(plan_key) is None:
        raise ValueError("Choose Base or Small Business.")
    return plan_key


def subscription_view(tenant_id):
    """What the Account screen reads, and what first sign-in decides on: a
    subscribe signup with no subscription and no checkout offered yet opens
    checkout for signup_plan (amendment of 17 September 2026)."""
    sub = _subscription(tenant_id)
    found = _sql(
        """
        SELECT trial_ends_at, signup_plan, signup_intent, checkout_offered_at
        FROM tenant WHERE tenant_id = :t
        """,
        [_p("t", tenant_id)]).get("records", [])
    t = found[0] if found else None
    return {
        "standing": wallet.standing(tenant_id),
        "plan": sub["plan_key"] if sub else None,
        "trial_ends_at": _col(t, 0) if t else None,
        "current_period_ends_at": sub["current_period_ends_at"] if sub else None,
        "paddle_status": sub["paddle_status"] if sub else None,
        # PROPOSED: returned so the app can make the first-sign-in decision.
        "signup_plan": _col(t, 1) if t else None,
        "signup_intent": _col(t, 2) if t else None,
        "checkout_offered_at": _col(t, 3) if t else None,
        "plans": _plans(),
    }


# --- checkout --------------------------------------------------------------

def checkout(tenant_id, role, body):
    """A Paddle transaction for the chosen plan. The browser opens it with
    Paddle.Checkout.open({transactionId}).

    tenant_id is the token's (app.caller). Nothing in the body names a tenant
    and nothing in the body is read for one (decision record item 7)."""
    _require_admin(role)
    plan_key = _known_plan(body)

    sub = _subscription(tenant_id)
    # PROPOSED: a cancelled subscription may check out again; anything else
    # changes plan instead.
    if sub and sub["paddle_status"] != "canceled":
        raise Refused("This workspace already has a subscription. "
                      "Change the plan instead.")

    transaction_id = paddle_api.create_checkout_transaction(tenant_id, plan_key)

    # Amendment of 17 September 2026: the first-sign-in checkout opens once.
    # Set when a transaction is created, not when it is paid, and only the
    # first time - IS NULL keeps it. A transaction Paddle refused raised above
    # and sets nothing.
    _sql(
        """
        UPDATE tenant SET checkout_offered_at = NOW()
        WHERE tenant_id = :t AND checkout_offered_at IS NULL
        """,
        [_p("t", tenant_id)])

    return {"transaction_id": transaction_id}


# --- changing plan ---------------------------------------------------------

def change_plan(tenant_id, email, role, body):
    """Upgrade or downgrade. Paddle bills the difference now; the webhooks
    move the plan and grant any credit (item 16). Refused when more seats are
    taken or reserved than the target plan has (item 14)."""
    _require_admin(role)
    target = _known_plan(body)

    sub = _subscription(tenant_id)
    # Paddle refuses a change while past_due; so does this, with a sentence.
    if not sub or sub["paddle_status"] != "active":
        raise Refused("There is no active subscription to change.")
    if sub["plan_key"] == target:
        raise Refused("This workspace is already on that plan.")

    plan = _plan(target)
    state = seats.listing(tenant_id, email)
    held = state["taken"] + state["reserved"]
    if held > plan["seat_count"]:
        raise Refused(
            "%d seats are taken or reserved, and %s has %d. Remove seats or "
            "revoke invitations first." % (held, plan["name"],
                                           plan["seat_count"]))

    paddle_api.change_plan(sub["paddle_subscription_id"], target)
    return {"requested": True, "plan": target}


# --- topping up ------------------------------------------------------------

def _duplicate_idempotency_key(exc):
    """The Data API's refusal of a second topup_request for one key.

    Seen on dev, 17 September 2026: DatabaseErrorException, "Duplicate entry
    '4-...' for key 'topup_request.uq_idempotency'; Error code: 1062;
    SQLState: 23000". Matched on MySQL's error number and the index name, so
    a duplicate on any other key is not mistaken for a repeat."""
    error = getattr(exc, "response", {}).get("Error", {})
    message = error.get("Message") or ""
    return (error.get("Code") == "DatabaseErrorException"
            and "Error code: 1062" in message and "uq_idempotency" in message)


def top_up(tenant_id, email, role, body):
    """Buy purchased credit in $5 increments, on the stored card.

    The request is recorded before Paddle is called, and the idempotency key
    is what refuses a repeat: Paddle takes no key of ours. The credit arrives
    with the transaction.completed webhook."""
    _require_admin(role)
    body = body or {}

    increments = body.get("increments")
    if (isinstance(increments, bool) or not isinstance(increments, int)
            or not 1 <= increments <= MAX_INCREMENTS):
        raise ValueError("A top-up is 1 to %d increments of $5."
                         % MAX_INCREMENTS)
    key = str(body.get("idempotency_key") or "").strip()[:64]
    if not key:
        raise ValueError("A top-up needs an idempotency key.")

    sub = _subscription(tenant_id)
    if not sub or sub["paddle_status"] != "active":
        raise Refused("Subscribe first.")

    # The insert IS the check. uq_idempotency refuses a second row for the
    # same key, so two clicks racing each other cannot both get past it and
    # both charge - which a SELECT before the INSERT would allow.
    try:
        _sql(
            """
            INSERT INTO topup_request
              (tenant_id, idempotency_key, increments, requested_by)
            VALUES (:t, :k, :n, :by)
            """,
            [_p("t", tenant_id), _p("k", key), _p("n", increments),
             _p("by", email)])
    except ClientError as exc:
        if not _duplicate_idempotency_key(exc):
            raise
        # PROPOSED: a repeat is answered, not charged.
        return {"repeated": True, "increments": increments,
                "amount_cents": TOPUP_INCREMENT_CENTS * increments}

    # PROPOSED: a charge Paddle refuses leaves this request unmatched. Nothing
    # is granted for it, and it is visible beside the requests that were.
    paddle_api.charge_topup(sub["paddle_subscription_id"], increments)
    return {"requested": True, "increments": increments,
            "amount_cents": TOPUP_INCREMENT_CENTS * increments}
