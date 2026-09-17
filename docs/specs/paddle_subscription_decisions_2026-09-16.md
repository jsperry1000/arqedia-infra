# Paddle Subscription — Decision Record

**16 September 2026 · branch `feature/paddle-subscription`**
Additive to *Wallet & Entitlement Gate v1.0*, *Plans & Starter Packs v1.0* and
*Identity & Seats v1.0*. Those specs are not edited; where this record differs,
this record applies from this date.

---

## 1. Supersedes

| Spec wording | Now |
|---|---|
| Wallet §6 — "No processor is named" | Paddle (merchant of record). Sandbox catalog in `config/paddle/sandbox.json` |
| Wallet §2, §7 — top-up $10 / $25 / $5 × seats | Flat $5 increment per tenant. One Paddle one-time price, quantity = number of increments (1–50; 50 is a placeholder) |
| Wallet §6 req. 1 — card on file, no standing mandate | Met by `POST /subscriptions/{id}/charge`, `effective_from: immediately` |
| CLAUDE.md — secrets in environment variables | Paddle API key and webhook secret in AWS Secrets Manager, values set outside Terraform, read by Lambda at start-up |

The sanctions-underwriting question to Paddle is dropped.

---

## 2. Approved

1. **Secrets.** AWS Secrets Manager: API key and webhook secret. Paddle client-side token (`test_`, public by Paddle's documentation) in front-end config.
2. **Checkout during trial.** Charges at checkout. No Paddle trial period on plan prices. Checkout sets the tenant active and grants the first monthly credit (Wallet §8).
3. **Plan data.** A plan table, per Plans §1 "a plan is a row, not an enum". Holds monthly credit ($5 Base, $15 Small Business) and seat count.
4. **Webhooks.** Receiver Lambda (unauthenticated route, signature verified) invokes a processor Lambda asynchronously. Receiver never touches the database.
5. **Signature verification.** HMAC-SHA256 of `ts:rawBody` with the Python standard library. No Paddle SDK.
6. **Bucket grants.** Only from `transaction.completed` webhooks, referenced by Paddle transaction ID. Never from an API success response. Events de-duplicated on `event_id`, ordered by `occurred_at`.
7. **Tenant reference.** Set server-side on a Paddle transaction; never taken from the browser.
8. **Out of scope on this branch.** Invoices and "Close this account" stay mocked and inert.
9. **Leftover trial credit.** Kept until its own expiry; spend order (soonest expiry first) uses it first.
10. **Top-up with no subscription.** Refused: "Subscribe first". The charge API requires a subscription.
11. **Subscription data.** Separate `subscription` table, per Wallet §3, not columns on `tenant`.
12. **Payment failed (`past_due`).** Read-only (`capped`) until Paddle reports active.
13. **Cancelled.** Read-only (`capped`) from the end of the paid period; `closed` only on account deletion.
14. **Downgrade with more seats than the target plan.** Refused until seats fit the target plan.
15. **Refund or chargeback.** Event recorded; no bucket or ledger change (Wallet §4, append-only); flagged for manual review.
16. **Mid-cycle upgrade.** On transaction.completed with origin subscription_update to a higher plan, grant monthly_credit = new plan monthly_credit_cents minus old plan monthly_credit_cents, expiring at the current billing period end, reference = transaction ID. Downgrade grants nothing and reclaims nothing (Wallet §4, append-only).

### Amendment — 16 September 2026

**13 is amended.** After a cancellation passes the end of the paid period, the
tenant can still spend unexpired purchased (top-up) cash to file documents and
generate memos. Everything else follows `capped` in Wallet §8 as written. No new
top-ups: a cancelled subscription cannot be charged (item 10). Cash still expires
30 days from purchase (Wallet §4).

**12 is amended.** While a payment has failed (`past_due`), the tenant can still spend unexpired purchased (top-up) cash to file documents and generate memos, until it is used up or expires. Everything else follows `capped` in Wallet §8. No new top-ups while `past_due`: Paddle refuses the charge API in that state.

### Amendment — 17 September 2026

- **Trial length.** Trial is 14 days in all cases (was 30, Wallet §2). $5 metered cap unchanged.
- **Subscribe is always available.** Pricing page (Start 14-day trial and Subscribe per plan) and in-app in every state. During `past_due` the button is "Update card". PROPOSED.
- **Subscribe from the pricing page.** Runs signup with the chosen plan, then opens checkout after sign-in; tenant reference stays server-side (item 7). PROPOSED.
- **The chosen plan survives a cross-device verify.** It is stored server-side on `pending_signup` at begin and copied to the tenant at verify. On first sign-in, if `signup_intent` = subscribe, no subscription row exists and `checkout_offered_at` is NULL, the app opens checkout for `signup_plan`. `checkout_offered_at` is set when that checkout transaction is created, so it opens once. PROPOSED.
- **Conversion tracking.** `tenant.signup_intent` (trial / subscribe) distinguishes direct subscribers from trial conversions. PROPOSED.

---

## 3. Open

- Sandbox test checkout not yet run: tax added on top unconfirmed.
- API Gateway v2 body encoding: handler must hash exact raw bytes; unverified.
- Front-end config holds a sandbox-only token; one bundle cannot serve both environments (ENV-01).
- Live catalog and `config/paddle/live.json` do not exist.
- Failure-queue alarm has no notification target; failed events are visible only in the CloudWatch console.
