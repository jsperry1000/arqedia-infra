"""
paddle_api.py - the calls made to Paddle.

  create_checkout_transaction  POST  /transactions
  charge_topup                 POST  /subscriptions/{id}/charge
  change_plan                  PATCH /subscriptions/{id}
  cancel_subscription          POST  /subscriptions/{id}/cancel
  payment_method_transaction   GET   /subscriptions/{id}/update-payment-method-transaction
  resume_subscription          POST  /subscriptions/{id}/resume
  renewal_outcome              GET   /transactions
  list_transactions            GET   /transactions
  invoice_pdf_url              GET   /transactions/{id}/invoice

cancel_subscription is not reached from any route. Account deletion calls it
(docs/runbooks/cancel_subscription.py, step 3 of the deletion runbook).

PROPOSED: the standard library (urllib), not the Paddle SDK. The decision
record names no client for outbound calls; the webhook side already avoids the
SDK (item 5), and three calls do not justify a layer.

The API key is read from Secrets Manager once per container and never logged.
Nothing here logs a request or a response.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import boto3

_secrets = boto3.client("secretsmanager")

API_BASE = os.environ["PADDLE_API_BASE"]
API_KEY_SECRET_ARN = os.environ["PADDLE_API_KEY_SECRET_ARN"]

# plan.plan_key to Paddle price id, from config/paddle/sandbox.json through
# Terraform.
PLAN_PRICES = {
    "base": os.environ["PADDLE_PRICE_BASE"],
    "business": os.environ["PADDLE_PRICE_BUSINESS"],
}
TOPUP_PRICE = os.environ["PADDLE_PRICE_TOPUP"]

# PROPOSED. The API Lambda allows 30 seconds, and a charge collects payment
# before it answers.
TIMEOUT_SECONDS = 20

_key = None


class PaddleError(Exception):
    """Paddle answered with an error. The code is Paddle's own, for the log
    and the reply; nothing else of the response is kept."""

    def __init__(self, status, code):
        self.status = status
        self.code = code
        super().__init__("Paddle refused the request (%s %s)" % (status, code))


def _api_key():
    global _key
    if _key is None:
        _key = _secrets.get_secret_value(
            SecretId=API_KEY_SECRET_ARN)["SecretString"]
    return _key


def _request(method, path, body=None):
    # A body only where one is given: the two reads send none. Every write
    # passes one, so what they send is unchanged.
    request = urllib.request.Request(
        API_BASE + path, method=method,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + _api_key(),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            error = json.loads(exc.read().decode("utf-8")).get("error") or {}
        except ValueError:
            error = {}
        # Not chained: the original carries the request, and the request
        # carries the key.
        raise PaddleError(exc.code, error.get("code")) from None


def create_checkout_transaction(tenant_id, plan_key):
    """A transaction for one plan, carrying the tenant. Paddle copies its
    custom_data to the subscription it creates, and from the subscription to
    every renewal, upgrade and charge after it.

    The tenant is an argument from the caller's token. There is no parameter
    through which a request body could supply one (decision record item 7)."""
    body = {
        "items": [{"price_id": PLAN_PRICES[plan_key], "quantity": 1}],
        "custom_data": {"tenant_id": tenant_id},
    }
    return _request("POST", "/transactions", body)["data"]["id"]


def charge_topup(subscription_id, increments):
    """Bill the stored card now. The purchased bucket is granted by the
    transaction.completed webhook, never here (decision record item 6)."""
    _request("POST", "/subscriptions/%s/charge"
             % urllib.parse.quote(subscription_id, safe=""), {
                 "effective_from": "immediately",
                 "items": [{"price_id": TOPUP_PRICE,
                            "quantity": int(increments)}],
                 "on_payment_failure": "prevent_change",
             })


def change_plan(subscription_id, plan_key):
    """Replace the plan. prorated_immediately bills the difference now;
    prevent_change leaves the subscription as it was if that payment fails.
    The items list is the whole subscription: the plan is its only item."""
    _request("PATCH", "/subscriptions/%s"
             % urllib.parse.quote(subscription_id, safe=""), {
                 "items": [{"price_id": PLAN_PRICES[plan_key], "quantity": 1}],
                 "proration_billing_mode": "prorated_immediately",
                 "on_payment_failure": "prevent_change",
             })


def cancel_subscription(subscription_id):
    """Cancel now, not at the end of the period: the tenant is being deleted
    and nothing should bill it again. Paddle cannot reinstate a cancelled
    subscription. Answers Paddle's status for it, which is "canceled".

    The subscription row is moved by the subscription.updated webhook that
    follows, never here."""
    return _request("POST", "/subscriptions/%s/cancel"
                    % urllib.parse.quote(subscription_id, safe=""), {
                        "effective_from": "immediately",
                    })["data"]["status"]


def payment_method_transaction(subscription_id):
    """A transaction for the browser to open, where the customer enters a new
    payment method. Paddle offers it for an active or past_due subscription
    only, never a paused one.

    Active: a new zero-value transaction, origin
    subscription_payment_method_change, which the processor records and
    grants nothing for. Past due: the overdue renewal itself (origin
    subscription_recurring), paid on the new method, so its credit arrives as
    any renewal's does.

    A GET that creates a transaction in the active case - Paddle's own
    choice of verb, and why the route of ours in front of it is a POST."""
    return _request("GET", "/subscriptions/%s/update-payment-method-transaction"
                    % urllib.parse.quote(subscription_id, safe=""))["data"]["id"]


def resume_subscription(subscription_id):
    """Resume a paused subscription now. Paddle starts a new billing period
    and charges the stored method at once, in a subscription_recurring
    transaction whose webhook grants the period's credit. If that charge
    fails the subscription becomes past_due, where the payment method can be
    changed.

    Answers when the new period starts, which is how renewal_outcome finds
    the charge: Paddle has not made it yet when this returns (verified 24
    October 2026 - the transaction appeared 0.4 seconds after the answer).

    The subscription row is moved by the webhooks that follow, never here."""
    data = _request("POST", "/subscriptions/%s/resume"
                    % urllib.parse.quote(subscription_id, safe=""), {
                        "effective_from": "immediately",
                        "on_resume": "start_new_billing_period",
                    })["data"]
    return (data.get("current_billing_period") or {}).get("starts_at")


# A payment attempt that has ended without the money: Paddle's own words.
FAILED_PAYMENTS = ("error", "dropped", "canceled")


def renewal_outcome(subscription_id, period_start):
    """Whether the renewal charge for the period starting at period_start
    has been paid: "paid", "failed", or None while it does not exist or has
    no answer yet.

    MATCHED BY ITS PERIOD, never the newest. The renewal transaction's
    billing_period.starts_at is the very instant the resume answered with,
    and the newest renewal when the resume returns is the previous one.

    Read from Paddle, not from our tables. Paddle has the answer within a
    second; the webhooks that carry it here have taken eighteen."""
    found = _request("GET", "/transactions?" + urllib.parse.urlencode({
        "subscription_id": subscription_id,
        "origin": "subscription_recurring",
        "order_by": "created_at[DESC]",
        "per_page": 5,
    })).get("data") or []
    for transaction in found:
        if (transaction.get("billing_period") or {}).get(
                "starts_at") != period_start:
            continue
        status = transaction.get("status")
        payments = transaction.get("payments") or []
        # Newest attempt first, as Paddle lists them.
        latest = (payments[0].get("status") if payments else None)
        if status in ("paid", "completed") or latest == "captured":
            return "paid"
        if status == "past_due" or latest in FAILED_PAYMENTS:
            return "failed"
        return None
    return None


# What the invoice list shows. draft and ready are checkouts nobody finished
# and billed is a manually-collected invoice, which nothing here creates.
INVOICE_STATUSES = ("completed", "paid", "past_due", "canceled")

# Paddle's own maximum for listing transactions, and its default.
PER_PAGE = 30


def list_transactions(customer_id, subscription_id, after=None, ids=None):
    """One page of a customer's transactions on one subscription, newest
    billed first. Answers Paddle's response as it came: data, and
    meta.pagination with has_more and next.

    ids narrows it to named transactions, which is how one is checked to be
    this customer's before its PDF is asked for."""
    params = {
        "customer_id": customer_id,
        "subscription_id": subscription_id,
        "status": ",".join(INVOICE_STATUSES),
        "order_by": "billed_at[DESC]",
        "per_page": PER_PAGE,
    }
    if after:
        params["after"] = after
    if ids:
        params["id"] = ",".join(ids)
    return _request("GET", "/transactions?" + urllib.parse.urlencode(params))


def invoice_pdf_url(transaction_id):
    """A link to the invoice PDF. Paddle's link expires after an hour, so it
    is asked for on the click and never kept."""
    return _request("GET", "/transactions/%s/invoice"
                    % urllib.parse.quote(transaction_id, safe=""))["data"]["url"]
