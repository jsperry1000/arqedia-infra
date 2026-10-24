"""
billing.py - paying for a plan, changing it, topping up, the invoices,
changing the payment method and resuming a paused subscription.

Self-contained, as wallet.py and seats.py are: app.py imports this.

Nothing here grants money. Paddle's webhooks do that, through the processor,
once a payment has completed (decision record item 6). What happens here is
asking Paddle to take one.
"""

import os
import re
import time
import urllib.parse

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
    """Every active plan, with everything the two surfaces show about one.

    workspace_count arrived with migration 046 (PACK-02): how many workspaces
    the plan holds, NULL for no limit, as the three limits below are.

    THE THREE LIMITS ARRIVED WITH MIGRATION 033 (18.5). Field sets per
    document type, sections per template and the daily classification
    allowance were sold on the pricing page and held nowhere - so the
    application could not show them at all, and the page that sold them was
    the only record. They are columns now, and this is what puts them on the
    screen a tenant actually pays from.

    NULL IS NOT ZERO in any of the three. A plan that has not been given a
    limit has not been given one; a plan limited to zero sections could render
    no memorandum. The screen shows a dash for null rather than a number.

    ENTERPRISE IS NOT HERE, and cannot be: seat_count, monthly_price_cents and
    monthly_credit_cents are NOT NULL, so a row for it could only exist by
    inventing three numbers, and a negotiated price must not be a release
    (CLAUDE.md, Money). This is also what decides what may be bought - see
    _known_plan - so a row would make it purchasable at a made-up price. Its
    column on the plan table is the marketing page's words, held in
    ui/src/upgrade.tsx beside the address it already keeps."""
    rows = _sql(
        """
        SELECT plan_key, name, seat_count, monthly_price_cents,
               monthly_credit_cents, share_allowance,
               field_sets_per_type, sections_per_template,
               daily_classification_cents, workspace_count
        FROM plan WHERE active = 1 ORDER BY monthly_price_cents
        """).get("records", [])
    return [{"plan_key": _col(r, 0), "name": _col(r, 1),
             "seat_count": _col(r, 2), "monthly_price_cents": _col(r, 3),
             "monthly_credit_cents": _col(r, 4),
             "share_allowance": _col(r, 5),
             "field_sets_per_type": _col(r, 6),
             "sections_per_template": _col(r, 7),
             "daily_classification_cents": _col(r, 8),
             "workspace_count": _col(r, 9)} for r in rows]


def _plan(plan_key):
    return next((p for p in _plans() if p["plan_key"] == plan_key), None)


def _subscription(tenant_id):
    rows = _sql(
        """
        SELECT s.paddle_subscription_id, s.paddle_status,
               s.current_period_ends_at, p.plan_key, s.paddle_customer_id
        FROM subscription s JOIN plan p ON p.plan_id = s.plan_id
        WHERE s.tenant_id = :t
        """,
        [_p("t", tenant_id)]).get("records", [])
    if not rows:
        return None
    r = rows[0]
    return {"paddle_subscription_id": _col(r, 0), "paddle_status": _col(r, 1),
            "current_period_ends_at": _col(r, 2), "plan_key": _col(r, 3),
            "paddle_customer_id": _col(r, 4)}


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
        # WHAT A TOP-UP INCREMENT COSTS, from the constant that charges it
        # (18.5). top_up() multiplies by exactly this, so the confirmation the
        # browser shows and the amount the card is billed cannot disagree -
        # which they could while the figure was written down again as
        # TOPUP_CENTS in Account.tsx.
        #
        # ON THIS ENDPOINT RATHER THAN ON /wallet, deliberately. The constant
        # lives in billing, and the alternative was moving it into wallet.py -
        # which ships in the docprocessing layer, so every deploy of it needs
        # build-layer.ps1 first or the Lambdas keep whatever the layer had
        # (CLAUDE.md). A number on the wrong endpoint is a smaller price than
        # a layer nobody remembers to rebuild. The Balance tab reads it here;
        # topping up needs an active subscription in any case, so it is the
        # same subsystem.
        "topup_increment_cents": TOPUP_INCREMENT_CENTS,
    }


# --- how many workspaces ---------------------------------------------------

def workspaces_held(tenant_id):
    # A deleted workspace is not counted (PACK-02 D, settled 23 October
    # 2026): deleting one makes room at once. Restoring it asks for room.
    rows = _sql("SELECT COUNT(*) FROM workspace "
                "WHERE tenant_id = :t AND deleted_at IS NULL",
                [_p("t", tenant_id)]).get("records", [])
    return int(_col(rows[0], 0)) if rows else 0


def workspace_limit(tenant_id):
    """How many workspaces this tenant may hold, or None for no limit
    (PACK-02, settled 23 October 2026).

    TENANT 0 HAS NO LIMIT: its workspaces are the offerings.

    THE SUBSCRIPTION'S PLAN DECIDES, as it does seats (seats.seats_bought).
    On a trial there is no subscription, and tenant.plan is read through the
    plan table instead. ENTERPRISE has no plan row: tenant.workspace_limit is
    its negotiated number, and NULL there is no limit until one is set. A
    plan string nothing recognises gets the smallest active plan's, as an
    unknown plan's seats do."""
    if tenant_id == 0:
        return None
    rows = _sql(
        "SELECT p.workspace_count FROM subscription s "
        "JOIN plan p ON p.plan_id = s.plan_id WHERE s.tenant_id = :t",
        [_p("t", tenant_id)]).get("records", [])
    if rows:
        return _col(rows[0], 0)

    rows = _sql("SELECT plan, workspace_limit FROM tenant WHERE tenant_id = :t",
                [_p("t", tenant_id)]).get("records", [])
    plan = ((_col(rows[0], 0) if rows else None) or "base")
    key = plan.strip().lower().replace(" ", "_")
    if key == "enterprise":
        return _col(rows[0], 1)

    rows = _sql("SELECT workspace_count FROM plan "
                "WHERE plan_key = :k AND active = 1",
                [_p("k", key)]).get("records", [])
    if rows:
        return _col(rows[0], 0)
    rows = _sql("SELECT workspace_count FROM plan WHERE active = 1 "
                "ORDER BY monthly_price_cents LIMIT 1").get("records", [])
    return _col(rows[0], 0) if rows else None


def require_workspace_room(tenant_id):
    """Refuses a new workspace at the limit. Asked before one is made, by
    the one route that makes them (POST /config/fork)."""
    allowed = workspace_limit(tenant_id)
    if allowed is None:
        return
    count = workspaces_held(tenant_id)
    if count >= allowed:
        raise Refused(
            "Your plan holds %d workspace%s, and %s in use. A bigger plan is "
            "how a tenant gets more." % (
                allowed, "" if allowed == 1 else "s",
                "it is" if count == 1 else "all %d are" % count))


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

    # The same refusal for workspaces (PACK-02, settled 23 October 2026):
    # nothing is deleted for the tenant to make a downgrade fit.
    count = workspaces_held(tenant_id)
    allowed = plan.get("workspace_count")
    if allowed is not None and count > allowed:
        raise Refused(
            "This tenant holds %d workspaces, and %s holds %d. Delete %s "
            "under Account management, Workspaces, first."
            % (count, plan["name"], allowed,
               "one" if count - allowed == 1 else "%d" % (count - allowed)))

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


# --- the payment method ----------------------------------------------------
#
# Paddle holds the card; nothing of it is kept here. What this hands the
# browser is a transaction to open in Paddle's overlay, where the new method
# is entered (amendment of 18 September 2026).

def payment_method(tenant_id, role):
    """A Paddle transaction for changing the payment method. The browser
    opens it with Paddle.Checkout.open({transactionId}).

    Active or past_due only, because that is all Paddle offers it for. A
    paused subscription resumes instead (resume, below)."""
    _require_admin(role)
    sub = _subscription(tenant_id)
    if not sub or sub["paddle_status"] not in ("active", "past_due"):
        raise Refused("There is no subscription whose payment method can be "
                      "changed.")
    return {"transaction_id": paddle_api.payment_method_transaction(
                sub["paddle_subscription_id"]),
            "status": sub["paddle_status"]}


def resume(tenant_id, role):
    """Resume a paused subscription. Paddle charges the stored method now
    for a new billing period; the webhooks move the status and grant the
    credit, so this answers 202 and the screen polls.

    NO IDEMPOTENCY KEY OF OURS. A second resume finds the subscription no
    longer paused and Paddle refuses it, so a repeat cannot charge twice;
    the row says paused until the webhook lands, so a repeat inside that
    window reaches Paddle and comes back as its refusal."""
    _require_admin(role)
    sub = _subscription(tenant_id)
    if not sub or sub["paddle_status"] != "paused":
        raise Refused("There is no paused subscription to resume.")
    paddle_api.resume_subscription(sub["paddle_subscription_id"])
    return {"requested": True}


# --- invoices --------------------------------------------------------------
#
# PADDLE IS THE RECORD. Nothing here stores an invoice: each read asks Paddle,
# one page of 30 at a time, with no cache. A 429 from Paddle is a PaddleError
# like any other, answered as the dispatcher's 502, and not retried.

_TRANSACTION = re.compile(r"^txn_[a-z\d]{26}$")


def _transaction_id(value, what):
    """A Paddle transaction id from the query string, or ValueError. It goes
    into Paddle's address, so nothing else is let through."""
    value = str(value or "").strip()
    if not _TRANSACTION.match(value):
        raise ValueError("That is not %s." % what)
    return value


def _when(value):
    """Paddle's RFC 3339 time as the API's other times are written -
    "2026-10-16 14:24:44", UTC - which is what the screen reads."""
    return value[:19].replace("T", " ") if value else None


def _invoice(transaction, names):
    """One row of the list, from one Paddle transaction."""
    totals = (transaction.get("details") or {}).get("totals") or {}
    amount = int(totals.get("grand_total") or 0)
    # What it was for: the plan or plans it bills, or a top-up. A plan
    # change carries the plan moved from at negative quantity, which is not
    # what was bought.
    what = []
    for item in transaction.get("items") or []:
        price = (item.get("price") or {}).get("id")
        quantity = item.get("quantity")
        if isinstance(quantity, int) and quantity < 0:
            continue
        name = names.get(price)
        if name and name not in what:
            what.append(name)
    return {
        "transaction_id": transaction.get("id"),
        # A cancelled transaction was never billed; when it was made is the
        # only date it has.
        "billed_at": _when(transaction.get("billed_at")
                           or transaction.get("created_at")),
        "what": ", ".join(what) or None,
        "amount_cents": amount,
        "currency": transaction.get("currency_code"),
        "status": transaction.get("status"),
        "invoice_number": transaction.get("invoice_number"),
        # Paddle makes a PDF for an automatically-collected transaction once
        # it is completed, and never for one of zero value.
        "has_pdf": transaction.get("status") == "completed" and amount > 0,
    }


def invoices(tenant_id, role, query):
    """The tenant's invoices from Paddle, newest first, one page at a time;
    or, with ?pdf=<transaction>, a link to that one's PDF. None where the PDF
    asked for is not this tenant's, which the route answers as 404.

    ADMINISTRATOR ONLY (decided 24 October 2026). An invoice carries the
    billing address and tax details, which is more than the plan and periods
    GET /billing/subscription shows to any seat."""
    _require_admin(role)
    query = query or {}
    asked = query.get("pdf")

    sub = _subscription(tenant_id)
    # A trial, tenant 0, or a subscription whose customer the webhooks have
    # not yet recorded: nothing to ask Paddle about.
    if not sub or not sub["paddle_customer_id"]:
        return None if asked else {"invoices": [], "has_more": False,
                                   "after": None}

    # BY CUSTOMER AND SUBSCRIPTION, BOTH (decided 24 October 2026). Paddle
    # keeps one customer per email address, so somebody who checks out two
    # tenants with one address is one customer, and the customer alone would
    # show each tenant the other's invoices. The subscription is this
    # tenant's own.
    #
    # THE GAP, ACCEPTED: subscription has one row per tenant, and a fresh
    # checkout after a cancellation overwrites paddle_subscription_id on it.
    # A tenant that cancels and subscribes again sees only the new
    # subscription's invoices here. The earlier ones are not lost - Paddle
    # holds them, and paddle_event.paddle_entity_id records the old
    # subscription's id - they are just not listed.
    customer = sub["paddle_customer_id"]
    subscription = sub["paddle_subscription_id"]

    if asked:
        wanted = _transaction_id(asked, "an invoice")
        found = paddle_api.list_transactions(customer, subscription,
                                             ids=[wanted]).get("data") or []
        if not found:
            return None
        if not _invoice(found[0], {})["has_pdf"]:
            raise Refused("Paddle has no PDF for this one.")
        return {"url": paddle_api.invoice_pdf_url(wanted)}

    after = query.get("after")
    page = paddle_api.list_transactions(
        customer, subscription,
        after=_transaction_id(after, "a page of invoices") if after else None)

    plans = {p["plan_key"]: p["name"] for p in _plans()}
    names = {price: plans[key] for key, price in
             paddle_api.PLAN_PRICES.items() if key in plans}
    names[paddle_api.TOPUP_PRICE] = "Top-up"

    rows = [_invoice(t, names) for t in page.get("data") or []]
    pagination = (page.get("meta") or {}).get("pagination") or {}
    more = bool(pagination.get("has_more"))
    # The cursor is in Paddle's own next link: the last transaction's id.
    cursor = urllib.parse.parse_qs(urllib.parse.urlsplit(
        pagination.get("next") or "").query).get("after", [None])[0]
    return {"invoices": rows, "has_more": more,
            "after": cursor if more else None}
