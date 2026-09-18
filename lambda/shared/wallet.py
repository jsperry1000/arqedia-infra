"""
wallet.py - what a tenant has, and what becomes of it.

Self-contained on purpose. It opens its own Data API client rather than
importing helpers from app.py, because app.py imports this and the two would
otherwise refer to each other. The duplication is thirty lines and the
alternative is a circular import.

IN THE LAYER, NOT IN lambda/api. The collector refunds a document whose OCR
failed, and it is a different function; two copies of the money rules is how
they come to disagree. Everything with the docprocessing layer can now import
this, and IAM is what decides who may actually write - the api and collector
roles hold the four rds-data actions, nothing else does.

Three rules shape everything here.

THE LEDGER IS APPEND-ONLY. Nothing is updated, nothing is deleted. A balance
that can be edited is not a record of anything.

There IS now a reversal, and the reason the rule gave for having none has
gone. It read "unreadable material is blocked before filing rather than
charged and refunded" - and unreadable material is no longer blocked before
filing, which is the whole point of the unreadable-documents record of 18
September. So refund() exists. It still adds a row rather than editing one:
the charge and its reversal sit side by side, and nothing about the past
changes.

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

    A REFUND COUNTS AS PURCHASED. It is not granted credit - it is money the
    tenant already paid, coming back because we failed to deliver. Withholding
    it would leave money on the Account screen that cannot be spent, from the
    one tenant who has already had a payment problem (decision record, 18
    September, item 15).
    """
    only = " AND kind IN ('purchased', 'refund')" if purchased_only else ""
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
    # kind IN ('purchased', 'refund') for the same reason _live_buckets does:
    # a refund is money coming back, not credit being granted. The two must
    # agree, or the balance shown is not the balance that can be spent.
    only = " AND kind IN ('purchased', 'refund')" if purchased_only else ""
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


# --- giving it back --------------------------------------------------------

REFUND_DAYS = 30


def refund(tenant_id, document_id, charge_entry_id, email=None):
    """Give back what one document cost, once.

    WHY THIS EXISTS AT ALL. The ledger rule said there was nothing to refund
    because unreadable material was blocked before filing. It is not any
    more - a scan is accepted, charged and sent to OCR - so a read that fails
    has taken money for nothing (decision record, 18 September, item 14).

    ONCE, AND THE DATABASE IS WHAT SAYS SO. The key is
    'refund:<document_id>', against uq_idempotency (tenant_id,
    idempotency_key). Three different failures can call this for one document,
    and a redelivered Textract notification can call it twice for the same
    one; only the first writes. That is not a check anyone can forget.

    THE LEDGER ROW GOES FIRST. It carries the unique key, so it is the gate:
    if the bucket insert then fails, the transaction rolls back and a retry
    finds nothing and is clean. The other order would grant money and then
    discover it was a repeat.

    WHAT WAS PAID, NOT WHAT IT COSTS TODAY. unit_cents comes from the entry
    that charged for it, never from meter_price: a price changed in between
    would return the wrong sum, and there is no meter_price row for a refund
    for exactly that reason.

    A NEW BUCKET, NOT THE OLD ONE. The bucket that paid may have expired, and
    restoring spent_cents on an expired bucket restores nothing spendable. So
    the money comes back with thirty days of its own, and a trial refund may
    outlive the trial - accepted deliberately, because the alternative is
    returning money that dies before it can be used (item 15).

    Returns {"refunded": bool, "amount_cents": int, "repeated": bool}.
    refunded is False only where there is nothing to give back: a document
    that was never charged for, or whose charge cannot be traced.
    """
    if not charge_entry_id:
        # Filed before migration 026, or never charged for. Nothing to give
        # back and nothing to invent.
        return {"refunded": False, "amount_cents": 0, "repeated": False,
                "reason": "no charge recorded against this document"}

    paid = _sql(
        """
        SELECT unit_cents, event_type FROM wallet_ledger
        WHERE tenant_id = :t AND entry_id = :e
        """,
        [_p("t", tenant_id), _p("e", int(charge_entry_id))],
    ).get("records", [])
    if not paid:
        return {"refunded": False, "amount_cents": 0, "repeated": False,
                "reason": "the charge named by this document is not there"}

    unit = int(_col(paid[0], 0) or 0)
    if unit <= 0:
        return {"refunded": False, "amount_cents": 0, "repeated": False,
                "reason": "the charge was nothing"}

    key = "refund:%d" % int(document_id)

    tx = _rds.begin_transaction(
        resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
        database=DATABASE)["transactionId"]
    try:
        try:
            _sql(
                """
                INSERT INTO wallet_ledger
                  (tenant_id, event_type, quantity, unit_cents, amount_cents,
                   reference, idempotency_key, created_by)
                VALUES (:t, 'document_filed_refund', 1, :u, :a, :ref, :k, :by)
                """,
                # NEGATIVE. Nothing computes a balance from the ledger - that
                # comes from the buckets - so this is what a person reading it
                # months later sees, and they should see a reversal rather
                # than a second charge.
                [_p("t", tenant_id), _p("u", unit), _p("a", -unit),
                 _p("ref", "refund of entry %d, document %d"
                    % (int(charge_entry_id), int(document_id))),
                 _p("k", key), _p("by", email)],
                tx=tx,
            )
        except ClientError as exc:
            if _duplicate_key(exc):
                _rds.rollback_transaction(
                    resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                    transactionId=tx)
                return {"refunded": False, "amount_cents": unit,
                        "repeated": True}
            raise

        _sql(
            """
            INSERT INTO wallet_bucket
              (tenant_id, kind, granted_cents, expires_at, reference)
            VALUES (:t, 'refund', :c, DATE_ADD(NOW(), INTERVAL :d DAY), :ref)
            """,
            [_p("t", tenant_id), _p("c", unit), _p("d", REFUND_DAYS),
             _p("ref", str(int(charge_entry_id)))],
            tx=tx,
        )

        _rds.commit_transaction(resourceArn=CLUSTER_ARN,
                                secretArn=SECRET_ARN, transactionId=tx)
    except Exception:
        try:
            _rds.rollback_transaction(resourceArn=CLUSTER_ARN,
                                      secretArn=SECRET_ARN, transactionId=tx)
        except Exception:  # noqa: BLE001 - the original error is what matters
            pass
        raise

    return {"refunded": True, "amount_cents": unit, "repeated": False}


def _duplicate_key(exc):
    """A unique-key collision from the Data API, which reports it as a
    DatabaseErrorException carrying MySQL's 1062 rather than as a typed error.

    Matched on the constraint name as well as the code, so an unrelated
    duplicate elsewhere in the statement is not read as 'already refunded'."""
    text = str(exc)
    return ("Error code: 1062" in text or "Duplicate entry" in text) \
        and "uq_idempotency" in text


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
