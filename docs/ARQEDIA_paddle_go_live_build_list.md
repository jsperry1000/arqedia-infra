# ARQEDIA — Paddle, what is left before live

**26 October 2026 · sandbox only; no live Paddle account exists**

**Superseded 6 November 2026** by `ARQEDIA_paddle_go_live_list_2026-11-06.md`.
Kept as it was.

Sequential. Each stage depends on the one above it.

---

## 1. Decide the environment question (ENV-01)

- Decide whether live is a second Terraform stack or the same one re-pointed.
  Everything below inherits the answer, so nothing else should start first.
- Read `versions.tf` and the S3 backend key before deciding. A fixed state key
  means applying with `environment = "prod"` overwrites dev's state.
- Decide how migrations are recorded per environment. Nothing in the repository
  says which environment received which migration.

**Decided 6 November 2026: the same stack, re-pointed.** No second stack. One
cluster, so `schema_migration` is the migrations record. What happens to dev's
existing tenants and sandbox subscription IDs is not settled. See ENV-01,
"Decided, 6 November 2026".

## 2. Open the live Paddle account

- Submit the business for Paddle's verification. It takes days, so it starts
  before anything that depends on it.
- Approve `arqedia.com` as a checkout domain on the live account.
- Set the live default payment link, without which checkout refuses to open.

## 3. Build the live catalogue

- Create the live products and prices: Base, Small Business, and the $5
  one-time top-up.
- Write `config/paddle/live.json` with the live IDs, mirroring `sandbox.json`.
- Settle first, because it changes the catalogue: whether editing a Paddle
  price's amount re-prices existing subscribers, or whether they keep the price
  they bought. Two documentation searches found nothing; ask Paddle support.

## 4. Wire the live credentials

- Create the live API key with the same permissions as sandbox, and put it in
  Secrets Manager for the live stack.
- Create the live notification destination, and store its `pdl_ntfset_` secret.
  Subscribe the same five events sandbox uses.
- Build the front end with `VITE_PADDLE_TOKEN` set to the `live_` token and
  `VITE_PADDLE_ENVIRONMENT` to production. The build already refuses a
  mismatched pair.
- Decide who holds live credentials and where. Sandbox keys were pasted into
  chats and command lines more than once.

## 5. Finish the customer-facing copy

- Put "plus tax" beside every price on the pricing page and the Account screen.
  Prices are tax-exclusive and the customer pays more than the number shown.
- Say on the pricing page what the trial is: 14 days, $5 of metered credit, no
  card.
- Say what a top-up is: $5 increments, charged on a click, expiring 30 days
  from purchase.

## 6. Build checkout at first sign-in

- The decision of 17 September: a `subscribe` signup opens checkout once at
  first sign-in. `GET /billing/subscription` already returns `signup_plan`,
  `signup_intent` and `checkout_offered_at`; nothing reads them.
- Without it, somebody who chose Subscribe on the pricing page lands on a trial
  and has to find the Account screen themselves.

## 7. Prove the cap across a resumed period

- Tenant 5 was granted $65.00 of monthly credit four times between 19 and 25
  October, three of them on one day. Either the cap held and each grant had its
  own expiry, or it did not.
- One query settles it. It matters only because the same path with real money
  would hand out credit nobody paid for.

## 8. Verify the webhook signature against the real gateway

- The signature is computed over the raw body. API Gateway may base64-encode
  it, and that has never been confirmed either way (decision record §3).
- Sandbox works, which is evidence but not proof that live will.

## 9. Watch what fails

- The failure-queue alarm has no notification target. A failed event means a
  customer paid and received nothing, and today it would sit silently.
- Nothing reads `needs_review`. Four events carry it. With real money, an
  unmatched charge is money received and unaccounted for.

## 10. Go live, then watch the first real payment

- Run one real checkout, one top-up and one plan change, and read them through
  to the buckets, as was done on sandbox on 19–20 September.
- Confirm tax is added as expected in the first real customer's jurisdiction.

---

## Not required before live

- **Annual pricing.** Blocked on the price-editing question in stage 3, and
  nothing depends on it.
- **PAY-01**, whether Paddle's amounts belong in our database. Invoices now
  read live from Paddle, which is a working answer whether or not it is
  recorded as the decision.
- **Paddle data on the staff console** (16.12).
- **The price-check test** that compares `plans.json` against Paddle, which no
  workflow runs (17.9).
- **Housekeeping:** eight migration headers that say "not applied" when they
  are, and test fixtures carrying the pre-038 credit figures.
