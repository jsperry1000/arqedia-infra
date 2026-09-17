"""
wallet.py - what a tenant has, and what becomes of it.

Self-contained on purpose. It opens its own Data API client rather than
importing helpers from app.py, because app.py imports this and the two would
otherwise refer to each other. The duplication is thirty lines and the
alternative is a circular import.

Three rules shape everything here.

THE LEDGER IS APPEND-ONLY. Nothing is updated, nothing is deleted. A balance
that can be edited is not a record of anything. There is no reversal because
unreadable material is blocked before filing rather than charged and refunded.

A CHARGE IS ALL OR NOTHING. Every charge runs in a transaction. A tenant is
never left having paid for part of something, and a bucket is never debited
without the allocation that says why.

DEBIT ON THE CLICK. The price is shown and accepted before anything is filed.
Somebody who has accepted a price should not later find the work ran and the
money did not.
"""

import os
import time
import boto3
from botocore.exceptions import ClientError

_rds = boto3.client("rds-data")

CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]


class InsufficientFunds(Exception):
    """Not enough to cover the whole charge. Nothing was debited."""

    def __init__(self, needed_cents, available_cents, purchased_only=False):
        self.needed_cents = needed_cents
        self.available_cents = available_cents
        # True when only purchased cash could be spent (decision record items
        # 12 and 13, as amended), so the refusal can say why.
        self.purchased_only = purchased_only
        super().__init__(
            f"needs {needed_cents} cents, has {available_cents}")


class Unpriced(Exception):
    """No price for that event. An unpriced event refuses; it never charges
    nothing, because charging nothing is how a free-of-charge bug ships."""


# --- plumbing --------------------------------------------------------------

def _sql(statement, params=None, tx=None):
    """Data API call, retrying while the cluster wakes from zero capacity."""
    kwargs = dict(resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                  database=DATABASE, sql=statement, parameters=params or [])
    if tx:
        kwargs["transactionId"] = tx
    for _ in range(12):
        try:
            return _rds.execute_statement(**kwargs)
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


def _money(cents):
    return f"${cents / 100:,.2f}"


# --- standing --------------------------------------------------------------
#
# Derived on every charge, never stored (Wallet section 4).
#
#   trial           no subscription row - the tenant has not checked out
#   active          a subscription in good standing
#   purchased_only  payment has failed (past_due), or the subscription was
#                   cancelled and its paid period is over. Filing and
#                   generating may spend unexpired purchased cash and nothing
#                   else - not monthly credit, not trial credit (decision
#                   record items 12 and 13, as amended). Every other action
#                   follows capped.
#
# capped is not a fourth answer: it is available = 0, which charge refuses as
# InsufficientFunds in every standing.

TRIAL = "trial"
ACTIVE = "active"
PURCHASED_ONLY = "purchased_only"


def classify_standing(has_subscription, paddle_status, period_over):
    if not has_subscription:
        return TRIAL
    if paddle_status == "past_due":
        return PURCHASED_ONLY
    if paddle_status == "canceled" and period_over:
        return PURCHASED_ONLY
    # Paused is treated as past_due (decision record, amendment of 17
    # September 2026, PROPOSED).
    if paddle_status == "paused":
        return PURCHASED_ONLY
    return ACTIVE


def standing(tenant_id):
    # PROPOSED: a cancelled subscription with no period end is over.
    rows = _sql(
        """
        SELECT paddle_status,
               current_period_ends_at IS NULL OR current_period_ends_at <= NOW()
        FROM subscription WHERE tenant_id = :t
        """,
        [_p("t", tenant_id)],
    ).get("records", [])
    if not rows:
        return TRIAL
    return classify_standing(True, _col(rows[0], 0), bool(_col(rows[0], 1)))


# --- what things cost ------------------------------------------------------

def unit_price(tenant_id, event_type):
    """The tenant's own price where one is set, the standard price otherwise.

    Enterprise is negotiated, and a negotiated price must not be a release."""
    rows = _sql(
        """
        SELECT unit_cents FROM meter_price
        WHERE event_type = :e AND (tenant_id = :t OR tenant_id IS NULL)
        ORDER BY tenant_id IS NULL
        LIMIT 1
        """,
        [_p("e", event_type), _p("t", tenant_id)],
    ).get("records", [])
    if not rows:
        raise Unpriced(event_type)
    return _col(rows[0], 0)


def quote(tenant_id, event_type, quantity=1):
    """What this would cost and whether it can be afforded. Charges nothing.

    This is what the review screen shows before anybody commits to filing."""
    unit = unit_price(tenant_id, event_type)
    total = unit * quantity
    only = standing(tenant_id) == PURCHASED_ONLY
    have = available(tenant_id, purchased_only=only)
    return {
        "event_type": event_type,
        "quantity": quantity,
        "unit_cents": unit,
        "total_cents": total,
        "available_cents": have,
        "affordable": total <= have,
        # What the person can do now, rather than only what they cannot. A
        # proposal of eighteen with money for eight should file eight.
        "affordable_count": min(quantity, have // unit) if unit else 0,
        # PROPOSED: returned so a screen can say only purchased credit counts.
        "purchased_only": only,
    }


# --- what is left ----------------------------------------------------------

def _live_buckets(tenant_id, tx=None, purchased_only=False):
    """Unexpired buckets with something left, in spend order.

    Soonest expiry first, then oldest. "Credit before cash, unless a cash
    tranche matures sooner" is not a rule in code - it falls out of this
    ordering, which is why it is the only ordering.

    purchased_only narrows it to purchased cash, for a tenant whose payment
    has failed or whose cancelled subscription has run out.
    """
    only = " AND kind = 'purchased'" if purchased_only else ""
    return _sql(
        """
        SELECT bucket_id, granted_cents - spent_cents AS remaining
        FROM wallet_bucket
        WHERE tenant_id = :t
          AND expires_at > NOW()
          AND granted_cents > spent_cents%s
        ORDER BY expires_at ASC, created_at ASC
        """ % only,
        [_p("t", tenant_id)], tx=tx,
    ).get("records", [])


def available(tenant_id, purchased_only=False):
    only = " AND kind = 'purchased'" if purchased_only else ""
    rows = _sql(
        """
        SELECT COALESCE(SUM(granted_cents - spent_cents), 0)
        FROM wallet_bucket
        WHERE tenant_id = :t AND expires_at > NOW()%s
        """ % only,
        [_p("t", tenant_id)],
    )["records"][0]
    return int(_col(rows, 0) or 0)


def balance(tenant_id):
    """The balance, and what it is made of.

    Expired buckets are shown rather than hidden. Somebody whose credit ran
    out on the 28th should be able to see that, not merely find themselves
    poorer than they remember.
    """
    rows = _sql(
        """
        SELECT bucket_id, kind, granted_cents, spent_cents,
               expires_at, created_at, reference,
               expires_at <= NOW() AS expired
        FROM wallet_bucket
        WHERE tenant_id = :t
        ORDER BY expires_at DESC
        """,
        [_p("t", tenant_id)],
    ).get("records", [])

    buckets = [{
        "bucket_id": _col(r, 0),
        "kind": _col(r, 1),
        "granted_cents": _col(r, 2),
        "spent_cents": _col(r, 3),
        "remaining_cents": _col(r, 2) - _col(r, 3),
        "expires_at": _col(r, 4),
        "created_at": _col(r, 5),
        "reference": _col(r, 6),
        "expired": bool(_col(r, 7)),
    } for r in rows]

    live = sum(b["remaining_cents"] for b in buckets if not b["expired"])

    out = {"available_cents": live, "available": _money(live),
           "buckets": buckets, "prices": {}}
    for event in ("document_filed", "memo_generated"):
        try:
            out["prices"][event] = unit_price(tenant_id, event)
        except Unpriced:
            pass
    return out


def ledger(tenant_id, limit=50):
    rows = _sql(
        """
        SELECT entry_id, event_type, quantity, unit_cents, amount_cents,
               reference, created_by, created_at
        FROM wallet_ledger
        WHERE tenant_id = :t
        ORDER BY entry_id DESC
        LIMIT :n
        """,
        [_p("t", tenant_id), _p("n", int(limit))],
    ).get("records", [])
    return [{
        "entry_id": _col(r, 0),
        "event_type": _col(r, 1),
        "quantity": _col(r, 2),
        "unit_cents": _col(r, 3),
        "amount_cents": _col(r, 4),
        "amount": _money(_col(r, 4)),
        "reference": _col(r, 5),
        "created_by": _col(r, 6),
        "created_at": _col(r, 7),
    } for r in rows]


# --- granting --------------------------------------------------------------

def grant(tenant_id, kind, cents, days, reference=None):
    """Put money in. Used by signup, by the monthly cycle, and by a top-up."""
    _sql(
        """
        INSERT INTO wallet_bucket
          (tenant_id, kind, granted_cents, expires_at, reference)
        VALUES (:t, :k, :c, DATE_ADD(NOW(), INTERVAL :d DAY), :ref)
        """,
        [_p("t", tenant_id), _p("k", kind), _p("c", int(cents)),
         _p("d", int(days)), _p("ref", reference)],
    )
    return balance(tenant_id)


# --- charging --------------------------------------------------------------

def charge(tenant_id, email, event_type, quantity, reference, idempotency_key):
    """Debit, all or nothing, once.

    The key is what makes this safe to call from a click. Filing eighteen
    documents is one click and eighteen charges; a retry, a double click or a
    stalled network must not charge twice, and the only place a duplicate can
    be refused reliably is the unique index on the ledger.

    Raises InsufficientFunds without debiting anything.

    What may be spent depends on standing: a tenant whose payment failed, or
    whose cancelled subscription has run out, spends purchased cash only.
    PROPOSED: standing is read before the transaction opens; a webhook landing
    in between changes the next charge, not this one.
    """
    unit = unit_price(tenant_id, event_type)
    total = unit * int(quantity)
    only = standing(tenant_id) == PURCHASED_ONLY

    # Already done. Return what was recorded rather than doing it again.
    seen = _sql(
        """
        SELECT entry_id, amount_cents FROM wallet_ledger
        WHERE tenant_id = :t AND idempotency_key = :k
        """,
        [_p("t", tenant_id), _p("k", idempotency_key)],
    ).get("records", [])
    if seen:
        return {"entry_id": _col(seen[0], 0),
                "amount_cents": _col(seen[0], 1),
                "repeated": True,
                "available_cents": available(tenant_id, purchased_only=only)}

    tx = _rds.begin_transaction(
        resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
        database=DATABASE)["transactionId"]

    try:
        buckets = _live_buckets(tenant_id, tx=tx, purchased_only=only)
        have = sum(_col(b, 1) for b in buckets)
        if have < total:
            _rds.rollback_transaction(resourceArn=CLUSTER_ARN,
                                      secretArn=SECRET_ARN, transactionId=tx)
            raise InsufficientFunds(total, have, only)

        _sql(
            """
            INSERT INTO wallet_ledger
              (tenant_id, event_type, quantity, unit_cents, amount_cents,
               reference, idempotency_key, created_by)
            VALUES (:t, :e, :q, :u, :a, :ref, :k, :by)
            """,
            [_p("t", tenant_id), _p("e", event_type), _p("q", int(quantity)),
             _p("u", unit), _p("a", total), _p("ref", reference),
             _p("k", idempotency_key), _p("by", email)],
            tx=tx,
        )
        entry_id = _col(_sql("SELECT LAST_INSERT_ID()", tx=tx)["records"][0], 0)

        # Take from each in turn until the charge is met. A charge that spans
        # two buckets leaves two allocations saying so.
        owing = total
        for b in buckets:
            if owing <= 0:
                break
            bucket_id, remaining = _col(b, 0), _col(b, 1)
            take = min(owing, remaining)

            _sql(
                "INSERT INTO wallet_allocation "
                "(entry_id, bucket_id, tenant_id, amount_cents) "
                "VALUES (:e, :b, :t, :a)",
                [_p("e", entry_id), _p("b", bucket_id),
                 _p("t", tenant_id), _p("a", take)],
                tx=tx,
            )
            # Guarded, so two charges racing cannot overspend a bucket: the
            # update matches no row if the money has gone in the meantime.
            _sql(
                "UPDATE wallet_bucket SET spent_cents = spent_cents + :a "
                "WHERE bucket_id = :b AND granted_cents - spent_cents >= :a",
                [_p("a", take), _p("b", bucket_id)],
                tx=tx,
            )
            owing -= take

        if owing > 0:
            _rds.rollback_transaction(resourceArn=CLUSTER_ARN,
                                      secretArn=SECRET_ARN, transactionId=tx)
            raise InsufficientFunds(total, total - owing, only)

        _rds.commit_transaction(resourceArn=CLUSTER_ARN,
                                secretArn=SECRET_ARN, transactionId=tx)
    except InsufficientFunds:
        raise
    except Exception:
        try:
            _rds.rollback_transaction(resourceArn=CLUSTER_ARN,
                                      secretArn=SECRET_ARN, transactionId=tx)
        except Exception:
            pass
        raise

    return {"entry_id": entry_id, "amount_cents": total,
            "repeated": False,
            "available_cents": available(tenant_id, purchased_only=only)}
