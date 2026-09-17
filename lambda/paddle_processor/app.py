"""
paddle_processor - applies a verified Paddle event.

Invoked asynchronously by the receiver, which has already checked the
signature. One event, one transaction: paddle_event is written first, and what
the event changes is written in the same transaction. A failure leaves nothing
behind, so the retry starts clean.

NEVER LOG THE EVENT OR ITS PAYLOAD. It carries the customer's email address.
What is logged is the event id, its type and the outcome.

Any error is raised. Lambda retries twice, then its failure record goes to the
failure queue (paddle.tf), where it waits to be replayed.

What an event does - docs/specs/paddle_subscription_decisions_2026-09-16.md:

  subscription.created / .updated      the subscription row; tenant.plan as a copy
  transaction.completed, a plan price  a monthly_credit bucket
  transaction.completed, a plan change the monthly_credit difference, on an upgrade (item 16)
  transaction.completed, a top-up      a purchased bucket
  adjustment, refund or chargeback     recorded for review, nothing else (item 15)
  anything else                        recorded only

The tenant comes from custom_data.tenant_id and nowhere else (item 7). An event
that would change something for a tenant this database does not hold is
recorded for review and changes nothing.
"""

import datetime
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

_rds = boto3.client("rds-data")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]

# Price id to plan.plan_key. The price ids come from config/paddle/sandbox.json
# through Terraform.
PLAN_PRICES = {
    os.environ["PADDLE_PRICE_BASE"]: "base",
    os.environ["PADDLE_PRICE_BUSINESS"]: "business",
}
TOPUP_PRICE = os.environ["PADDLE_PRICE_TOPUP"]

# A top-up is a flat $5 increment; quantity is the number of increments
# (decision record section 1). Cash expires 30 days from purchase (Wallet 4).
TOPUP_INCREMENT_CENTS = 500
TOPUP_EXPIRY_DAYS = 30

# PROPOSED. The origins that pay for a whole period of a plan. A plan change
# (subscription_update) is not a new period: it grants only the difference,
# on an upgrade (item 16). A payment method change grants nothing.
PLAN_GRANT_ORIGINS = {"api", "web", "subscription_recurring"}

# PROPOSED. chargeback_warning is included: Paddle creates it ahead of a
# chargeback, and review should start then.
REVIEW_ACTIONS = {"refund", "chargeback", "chargeback_warning"}

SUBSCRIPTION_EVENTS = {"subscription.created", "subscription.updated"}


# --- reading an event ------------------------------------------------------

_STAMP = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(?:Z|[+-]00:00)?$")


def db_time(value):
    """A timestamp as a DATETIME(6) literal with exactly six fractional digits,
    so two of them compare correctly as strings. Paddle sends up to nine
    digits; the database holds six."""
    m = _STAMP.match(value or "")
    if not m:
        raise ValueError("unrecognised timestamp")
    fraction = (m.group(3) or "").ljust(6, "0")[:6]
    return "%s %s.%s" % (m.group(1), m.group(2), fraction)


def plus_days(stamp, days):
    moment = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.%f")
    return (moment + datetime.timedelta(days=days)).strftime(
        "%Y-%m-%d %H:%M:%S.%f")


def tenant_ref(data):
    """custom_data.tenant_id, set by our own server on the transaction. Nothing
    else names a tenant."""
    custom = data.get("custom_data")
    raw = custom.get("tenant_id") if isinstance(custom, dict) else None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.isascii() and raw.isdigit():
        return int(raw)
    return None


def plan_of(items):
    """The plan a list of items is for, or None when it names none or more
    than one."""
    keys = {PLAN_PRICES[(i.get("price") or {}).get("id")]
            for i in items or []
            if (i.get("price") or {}).get("id") in PLAN_PRICES}
    return keys.pop() if len(keys) == 1 else None


def topup_quantity(items):
    return sum(int(i.get("quantity") or 0) for i in items or []
               if (i.get("price") or {}).get("id") == TOPUP_PRICE)


# --- applying an event -----------------------------------------------------

def apply(event, store):
    """Record the event and apply it. Returns the outcome, which is logged."""
    event_id = event["event_id"]
    event_type = event["event_type"]
    occurred_at = db_time(event["occurred_at"])
    data = event.get("data") or {}

    tenant_id = tenant_ref(data)
    if tenant_id is not None and not store.tenant_exists(tenant_id):
        tenant_id = None

    is_subscription = event_type in SUBSCRIPTION_EVENTS
    is_transaction = event_type == "transaction.completed"
    is_adjustment = event_type in ("adjustment.created", "adjustment.updated")

    plan = plan_of(data.get("items")) if (is_subscription or is_transaction) else None
    period = data.get("billing_period") or {}
    grants_credit = (is_transaction and plan is not None
                     and data.get("origin") in PLAN_GRANT_ORIGINS)
    increments = (topup_quantity(data.get("items"))
                  if is_transaction and data.get("origin") == "subscription_charge"
                  else 0)

    # Item 16. A plan change pays the difference in monthly credit. The new
    # plan is the one the transaction is for. The old plan is read from the
    # subscription row, which may already have moved: Paddle does not deliver
    # in order, so subscription.updated can land before this transaction. So,
    # in this order (PROPOSED):
    #   the row already shows the new plan  previous_plan_id (migration 020)
    #   otherwise                           the row's plan_id
    #
    # Read without a lock: subscription events lock paddle_event then
    # subscription, and taking them in the other order here could deadlock
    # the two.
    is_plan_change = is_transaction and data.get("origin") == "subscription_update"
    new_plan = plan if is_plan_change else None
    old_plan = change_expires = None
    if is_plan_change and tenant_id is not None:
        row_plan, previous_plan, row_period_end = store.current_plan(tenant_id)
        old_plan = previous_plan if row_plan == new_plan else row_plan
        # PROPOSED: the transaction's own period, else the subscription's.
        change_expires = (db_time(period["ends_at"]) if period.get("ends_at")
                          else row_period_end)

    changes_something = (is_subscription or grants_credit or increments > 0
                         or is_plan_change)

    # Decided before anything is written, so the event is recorded once with
    # the flag it deserves.
    needs_review = (
        (is_adjustment and data.get("action") in REVIEW_ACTIONS)
        or (changes_something and tenant_id is None)
        # PROPOSED: a subscription naming no known plan price.
        or (is_subscription and plan is None)
        # PROPOSED: a plan transaction with no period cannot say when its
        # credit expires.
        or (grants_credit and not period.get("ends_at"))
        # PROPOSED: a plan change whose plans cannot be placed. The items name
        # no single plan; or neither the previous plan nor the current one
        # gives a plan other than the new one - no subscription row, or a row
        # already showing the new plan with no previous plan recorded. A known
        # old plan that is higher is a downgrade, not a review: it grants
        # nothing (item 16).
        or (is_plan_change and (new_plan is None or old_plan is None
                                or old_plan == new_plan))
        # PROPOSED: no period to expire the upgrade credit at.
        or (is_plan_change and change_expires is None)
    )

    if not store.insert_event(event_id, event_type, occurred_at, tenant_id,
                              data.get("id"), needs_review):
        return "duplicate"
    if needs_review:
        return "review"

    if is_subscription:
        return _apply_subscription(store, tenant_id, plan, data, occurred_at)

    outcomes = []
    if grants_credit:
        outcomes.append(_grant_credit(store, tenant_id, plan, data["id"],
                                      db_time(period["ends_at"])))
    if increments > 0:
        outcomes.append(_grant_topup(store, event_id, tenant_id, data["id"],
                                     increments, occurred_at))
    if is_plan_change:
        outcomes.append(_grant_upgrade(store, tenant_id, old_plan, new_plan,
                                       data["id"], change_expires))
    return ",".join(outcomes) or "recorded"


def _apply_subscription(store, tenant_id, plan, data, occurred_at):
    """Paddle does not deliver in order. An update older than the last one
    applied is recorded and skipped."""
    last = store.subscription_event_at(tenant_id)
    if last is not None and last >= occurred_at:
        return "stale"

    current = data.get("current_billing_period") or {}
    # current_billing_period is null for a paused or cancelled subscription.
    # The store keeps what the row had rather than blanking the period end
    # that item 13 counts from. PROPOSED.
    ends_at = db_time(current["ends_at"]) if current.get("ends_at") else None
    # PROPOSED: the anchor day is the day of the month the period starts.
    anchor = (int(db_time(current["starts_at"])[8:10])
              if current.get("starts_at") else None)

    store.upsert_subscription(
        tenant_id=tenant_id, plan_key=plan,
        paddle_subscription_id=data["id"],
        paddle_customer_id=data.get("customer_id"),
        paddle_status=data.get("status"),
        current_period_ends_at=ends_at,
        billing_anchor_day=anchor,
        paddle_event_at=occurred_at)
    # A copy for readers that predate the subscription table. plan_id decides.
    store.copy_plan_to_tenant(tenant_id, plan)
    return "applied"


def _grant_credit(store, tenant_id, plan, transaction_id, expires_at):
    if store.bucket_exists(tenant_id, "monthly_credit", transaction_id):
        return "credit-reference-exists"
    store.grant(tenant_id, "monthly_credit", store.monthly_credit_cents(plan),
                expires_at, transaction_id)
    return "credit-granted"


def _grant_upgrade(store, tenant_id, old_plan, new_plan, transaction_id,
                   expires_at):
    """Item 16, as amended 17 September 2026. On an upgrade only. A downgrade
    grants nothing and takes nothing back: the ledger is append-only (Wallet
    section 4). The transaction id is the reference, so the same transaction
    delivered twice - once before and once after subscription.updated -
    grants once.

    Capped: monthly credit granted in one billing period never exceeds the
    current plan's monthly credit. The grant is the new plan's monthly credit
    less every unexpired monthly_credit bucket - the period's own grant and
    any earlier upgrade - so upgrade, downgrade, upgrade again pays the
    difference once. Unexpired stands for "this period": monthly credit
    expires at the period end, so an earlier period's has gone. expires_at
    is only where the new bucket expires; it does not choose what is
    counted, so a period end that differs by a second still counts."""
    if (store.monthly_credit_cents(new_plan)
            <= store.monthly_credit_cents(old_plan)):
        return "downgrade-no-grant"
    if store.bucket_exists(tenant_id, "monthly_credit", transaction_id):
        return "upgrade-reference-exists"
    grant = (store.monthly_credit_cents(new_plan)
             - store.monthly_credit_granted(tenant_id))
    if grant <= 0:
        return "upgrade-capped"
    store.grant(tenant_id, "monthly_credit", grant, expires_at,
                transaction_id)
    return "upgrade-credit-granted"


def _grant_topup(store, event_id, tenant_id, transaction_id, increments,
                 occurred_at):
    if store.bucket_exists(tenant_id, "purchased", transaction_id):
        return "topup-reference-exists"
    store.grant(tenant_id, "purchased", TOPUP_INCREMENT_CENTS * increments,
                plus_days(occurred_at, TOPUP_EXPIRY_DAYS), transaction_id)
    # PROPOSED matching. The charge API returns no transaction id and takes no
    # reference of ours, so the oldest unmatched request for this tenant with
    # the same number of increments is taken. The cash is granted whether or
    # not a request matches - it was paid for - and an unmatched one is
    # flagged for a person to look at.
    #
    # Two same-size requests from one tenant can swap: each transaction may be
    # recorded against the other's request. That changes only which requester
    # is recorded, not the credit - the amount and the tenant are the same.
    if not store.match_topup(tenant_id, increments, transaction_id):
        store.flag_review(event_id)
        return "topup-granted-unmatched"
    return "topup-granted"


# --- the database ----------------------------------------------------------

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


def _call(fn, **kwargs):
    """A Data API call, retried while the cluster wakes from zero capacity."""
    for _ in range(12):
        try:
            return fn(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN, **kwargs)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in (
                "DatabaseResumingException", "ThrottlingException"
            ):
                time.sleep(3)
                continue
            raise
    raise RuntimeError("cluster did not resume")


class DataApiStore:
    """One transaction per event. Committed when the event is applied, rolled
    back when anything raises."""

    def __enter__(self):
        self.tx = _call(_rds.begin_transaction, database=DATABASE)["transactionId"]
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            _call(_rds.commit_transaction, transactionId=self.tx)
        else:
            try:
                _call(_rds.rollback_transaction, transactionId=self.tx)
            except Exception:  # noqa: BLE001 - the original error is what matters
                pass
        return False

    def _sql(self, statement, params=None):
        return _call(_rds.execute_statement, database=DATABASE,
                     transactionId=self.tx, sql=statement,
                     parameters=params or []).get("records", [])

    def tenant_exists(self, tenant_id):
        return bool(self._sql("SELECT tenant_id FROM tenant WHERE tenant_id = :t",
                              [_p("t", tenant_id)]))

    def insert_event(self, event_id, event_type, occurred_at, tenant_id,
                     entity_id, needs_review):
        """False when the event is already recorded. The row is locked first,
        so two deliveries racing each other cannot both apply: the loser hits
        the primary key, raises, and its retry finds the row."""
        if self._sql("SELECT event_id FROM paddle_event WHERE event_id = :e "
                     "FOR UPDATE", [_p("e", event_id)]):
            return False
        self._sql(
            """
            INSERT INTO paddle_event
              (event_id, event_type, occurred_at, tenant_id, paddle_entity_id,
               needs_review)
            VALUES (:e, :type, :at, :t, :entity, :review)
            """,
            [_p("e", event_id), _p("type", event_type), _p("at", occurred_at),
             _p("t", tenant_id), _p("entity", entity_id),
             _p("review", 1 if needs_review else 0)])
        return True

    def flag_review(self, event_id):
        self._sql("UPDATE paddle_event SET needs_review = 1 WHERE event_id = :e",
                  [_p("e", event_id)])

    def subscription_event_at(self, tenant_id):
        """None when the tenant has no subscription row. The row is locked for
        the rest of the transaction."""
        rows = self._sql("SELECT paddle_event_at FROM subscription "
                         "WHERE tenant_id = :t FOR UPDATE", [_p("t", tenant_id)])
        if not rows:
            return None
        value = _col(rows[0], 0)
        return db_time(value) if value else ""

    def _plan(self, plan_key):
        rows = self._sql("SELECT plan_id, monthly_credit_cents FROM plan "
                         "WHERE plan_key = :k", [_p("k", plan_key)])
        if not rows:
            raise LookupError("no plan row for a known price")
        return _col(rows[0], 0), _col(rows[0], 1)

    def monthly_credit_cents(self, plan_key):
        return self._plan(plan_key)[1]

    def current_plan(self, tenant_id):
        """The plan key, the previous plan key and the period end the
        subscription row holds now, or (None, None, None) when there is no
        row."""
        rows = self._sql(
            "SELECT p.plan_key, pp.plan_key, s.current_period_ends_at "
            "FROM subscription s "
            "JOIN plan p ON p.plan_id = s.plan_id "
            "LEFT JOIN plan pp ON pp.plan_id = s.previous_plan_id "
            "WHERE s.tenant_id = :t",
            [_p("t", tenant_id)])
        if not rows:
            return None, None, None
        ends = _col(rows[0], 2)
        return (_col(rows[0], 0), _col(rows[0], 1),
                db_time(ends) if ends else None)

    def monthly_credit_granted(self, tenant_id):
        """Unexpired monthly credit granted to the tenant, spent or not.
        Granted is what the cap counts: spending credit does not make room
        for more. NOW() is the database's clock at apply time, not the
        event's: a failed event replayed after the period has ended counts
        the next period's buckets."""
        rows = self._sql(
            "SELECT COALESCE(SUM(granted_cents), 0) FROM wallet_bucket "
            "WHERE tenant_id = :t AND kind = 'monthly_credit' "
            "AND expires_at > NOW()",
            [_p("t", tenant_id)])
        return int(_col(rows[0], 0) or 0)

    def upsert_subscription(self, tenant_id, plan_key, paddle_subscription_id,
                            paddle_customer_id, paddle_status,
                            current_period_ends_at, billing_anchor_day,
                            paddle_event_at):
        """status is set to active on the first write and never changed here.
        payment_method_ref and trial_ends_at are not written. A NULL from Paddle
        keeps what the row had.

        previous_plan_id (migration 020) is the plan the row had before this
        write changed plan_id, and is kept when the plan does not change. It
        is assigned BEFORE plan_id: MySQL evaluates the assignments left to
        right, so subscription.plan_id still reads the old value there.
        PROPOSED, and unverified until it runs against dev."""
        plan_id = self._plan(plan_key)[0]
        self._sql(
            """
            INSERT INTO subscription
              (tenant_id, plan_id, status, billing_anchor_day,
               paddle_customer_id, paddle_subscription_id, paddle_status,
               current_period_ends_at, paddle_event_at)
            VALUES
              (:t, :plan, 'active', :anchor, :customer, :sub, :pstatus, :ends, :at)
            AS new
            ON DUPLICATE KEY UPDATE
              previous_plan_id       = IF(new.plan_id <> subscription.plan_id,
                                          subscription.plan_id,
                                          subscription.previous_plan_id),
              plan_id                = new.plan_id,
              billing_anchor_day     = COALESCE(new.billing_anchor_day, subscription.billing_anchor_day),
              paddle_customer_id     = COALESCE(new.paddle_customer_id, subscription.paddle_customer_id),
              paddle_subscription_id = new.paddle_subscription_id,
              paddle_status          = new.paddle_status,
              current_period_ends_at = COALESCE(new.current_period_ends_at, subscription.current_period_ends_at),
              paddle_event_at        = new.paddle_event_at
            """,
            [_p("t", tenant_id), _p("plan", plan_id),
             _p("anchor", billing_anchor_day), _p("customer", paddle_customer_id),
             _p("sub", paddle_subscription_id), _p("pstatus", paddle_status),
             _p("ends", current_period_ends_at), _p("at", paddle_event_at)])

    def copy_plan_to_tenant(self, tenant_id, plan_key):
        # tenant.plan is a copy for existing readers; subscription.plan_id is
        # the plan (CLAUDE.md, Money).
        self._sql("UPDATE tenant SET plan = :k WHERE tenant_id = :t",
                  [_p("k", plan_key), _p("t", tenant_id)])

    def bucket_exists(self, tenant_id, kind, reference):
        return bool(self._sql(
            "SELECT bucket_id FROM wallet_bucket WHERE tenant_id = :t "
            "AND kind = :k AND reference = :r LIMIT 1",
            [_p("t", tenant_id), _p("k", kind), _p("r", reference)]))

    def grant(self, tenant_id, kind, cents, expires_at, reference):
        self._sql(
            """
            INSERT INTO wallet_bucket
              (tenant_id, kind, granted_cents, expires_at, reference)
            VALUES (:t, :k, :c, :exp, :ref)
            """,
            [_p("t", tenant_id), _p("k", kind), _p("c", int(cents)),
             _p("exp", expires_at), _p("ref", reference)])

    def match_topup(self, tenant_id, increments, transaction_id):
        rows = self._sql(
            """
            SELECT request_id FROM topup_request
            WHERE tenant_id = :t AND increments = :n
              AND paddle_transaction_id IS NULL
            ORDER BY created_at, request_id
            LIMIT 1
            FOR UPDATE
            """,
            [_p("t", tenant_id), _p("n", int(increments))])
        if not rows:
            return False
        self._sql("UPDATE topup_request SET paddle_transaction_id = :x "
                  "WHERE request_id = :id",
                  [_p("x", transaction_id), _p("id", _col(rows[0], 0))])
        return True


def lambda_handler(event, context):
    event_id = event.get("event_id")
    event_type = event.get("event_type")
    try:
        with DataApiStore() as store:
            outcome = apply(event, store)
    except Exception:
        # The exception is raised for Lambda to retry. Only the id and type
        # are logged here; the payload never is.
        print("[paddle-processor] event=%s type=%s outcome=error"
              % (event_id, event_type))
        raise
    print("[paddle-processor] event=%s type=%s outcome=%s"
          % (event_id, event_type, outcome))
    return {"outcome": outcome}
