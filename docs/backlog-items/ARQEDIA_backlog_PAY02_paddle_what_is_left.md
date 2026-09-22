# ARQEDIA — Backlog Item

## PAY-02 · What is left on the Paddle integration

| | |
|---|---|
| Status | Raised. The money paths work; the surfaces around them do not |
| Priority | Before the first paying tenant |
| Type | Front end, API routes, Paddle catalogue, migrations |
| Raised | 20 September 2026 |

---

### What is done, so it is not reopened by mistake

All three money paths are proven against dev, not asserted from tests:

- **Checkout.** Sandbox payment, subscription row, webhook, monthly credit
  granted. Three seconds end to end.
- **Top-up.** Request recorded, card charged, purchased bucket granted at 30
  days, `topup_request.paddle_transaction_id` matched back.
- **Plan change.** Base → Small Business granted $10.00, capped at Small
  Business's $15.00 for the period, nothing flagged. The deployed zip was
  verified byte-for-byte against `HEAD`.

Tax is confirmed added on top: $25.00 pre-tax, 6.6% tax, $26.65 paid.

---

### Not built

- **"Update card" during `past_due`.** The button is drawn and inert. It needs
  a route calling Paddle's `GET /subscriptions/{id}/update-payment-method-transaction`.
  Nothing in `paddle_api.py` calls it. Until then, Paddle's own dunning emails
  carry a link that works.
- **First-sign-in checkout.** The 17 September amendment: a `subscribe` signup
  opens checkout once at first sign-in. `GET /billing/subscription` already
  returns `signup_plan`, `signup_intent` and `checkout_offered_at`; nothing
  reads them. It belongs in `App.tsx` at sign-in, not on the Account tab.
- **The pricing page.** Public marketing site, two tiers, Trial and Subscribe
  per plan, `?plan=&intent=` carried through signup. Copy still needs the $5
  flat top-up, the 14-day trial, and "plus tax" beside every price.
- **Annual pricing.** $240 Base and $624 Small Business, monthly × 12 less 20%.
  Needs the prices created in Paddle, and a `plan` table migration holding
  `annual_price_cents` and the annual price id. Blocked on the question below.

---

### Open questions

- **Editing a Paddle price's amount.** Whether it re-prices existing
  subscribers at renewal, or whether they keep the price they bought. Two
  documentation searches found nothing. This blocks the annual migration:
  getting it wrong re-prices people who already paid. Ask Paddle support if the
  docs stay silent.
- **PAY-01.** `paddle_event` keeps no amounts, so what Paddle actually charged
  cannot be answered from our database. The prior question is whether those
  figures belong to us at all when Paddle is the merchant of record.
  - The Paddle **customer credit balance** falls inside this. Tenant 5 holds
    ~$26.57 there after an upgrade-then-downgrade, invisible to our screens,
    and it silently paid for a later top-up. Nothing is wrong; nothing is shown.
- **BLD-01.** Three `archive_file` blocks exclude `__pycache__`; eight do not.
  Test runs then produce phantom Terraform changes, which on 19 September
  nearly hid an unmerged signup deployment.

---

### Recorded, not repaired

The two plan changes of 19 September (`txn_…y67818`, `txn_…gag9zv`) stay
flagged `needs_review` and ungranted. No replay path was built.

`needs_review` is written and nothing reads it — no screen, no alarm, no
report. Three events now carry it. That is OBS-03's argument, made concrete.

---

### Elsewhere, and not this item

A scanned PDF with no text layer is refused silently by the normalizer: no
document row, no message, and the Review screen polls for ten minutes before
giving up. Being handled separately.
