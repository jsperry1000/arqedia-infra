# ARQEDIA — Paddle go-live list

**6 November 2026 · dev is prod (ENV-01, decided 6 November) · live Paddle
account underway**

Supersedes `ARQEDIA_paddle_go_live_build_list.md` (26 October), which is kept
as it was. Built from that list, `HANDOFF/ARQEDIA_HANDOFF_paddle_2026-10-26.md`,
`prompts/ARQEDIA_paddle_go_live_cc_prompts.md`, the legal handoff of 27
October, `main` to #471, the dev database and AWS read today, and Paddle's
go-live checklist read today through `paddle-docs`.

Sections run in order. Inside a section, order does not matter unless it says
so. **Owner:** *You* is the dashboard, a decision, `terraform apply` or a
merge. *CC* is Claude Code on a branch.

---

## 0. Done since 26 October

| Item | Where | Read today |
|---|---|---|
| ENV-01: live on the `arqedia-dev` stack, re-pointed | ENV-01 backlog, 6 Nov | — |
| "Plus tax" beside every price; trial and top-up terms stated (old stage 5) | #460, 4 Nov | — |
| Failure-queue alarm and a `needs_review` alarm, emailing `info@arqedia.com` (old stage 9) | #459, 4 Nov | Topic `arqedia-dev-ops-alerts` has a confirmed email subscription; `paddle-processor-failed` and `paddle-needs-review` both `OK`, one action each |
| Solo plan added: $8/month, 1 seat; Base raised to 3 seats | #422; migration 050 | Applied 29 Oct. The plan table holds solo 800, base 2500, business 6500. The 050 header still says "not applied" |
| Terms, Privacy and Refund Policy pages; `info@arqedia.com` in every site footer | #417; migration 049 | `/terms`, `/privacy`, `/refunds` and `/pricing/` return 200. The homepage carries the contact address and does not link the legal pages, as decided |
| Webhook receiver decodes a base64-encoded body | `lambda/paddle_webhook/app.py:57`, since #150 | Code read only. See 4.5 |

---

## 1. Live account — You, underway

- [ ] Business verification. What has been submitted, and its status, is not
      recorded anywhere in the repository; please give it.
- [ ] **Website approval for both `arqedia.com` and `app.arqedia.com`.**
      Checkout opens on `app.`. Paddle: "`app.example.com` needs its own
      approval even if `example.com` is approved." (The 26 October list named
      `arqedia.com` only.)
- [ ] Payout details: Business account > Payouts > Payout settings.
- [ ] Default payment link, once `app.arqedia.com` is approved: Checkout >
      Checkout configuration. Paddle also uses it in its own emails for a
      payment-method update. See 4.6.

## 2. Live account settings — You

Paddle keeps live and sandbox settings separate. Read both and mirror them.

- [ ] Payment methods at checkout.
- [ ] Sales tax mode. Prices are tax-exclusive, decided 19 September.
- [ ] Balance currency.
- [ ] Retain: dunning settings, and the cancellation flow. Neither has been
      considered for ARQEDIA. **Proposed.**

## 3. Live catalogue — You, in the dashboard

Paddle settles the price-editing question that blocked this stage: "Editing
a price only changes it for new purchases; existing subscriptions keep the
version they were created with" (go-live checklist). That is from the docs,
not from Paddle support.

| Product name | Amount (USD cents) | Billing | Quantity |
|---|---|---|---|
| ARQEDIA Solo | 800 | month | 1 |
| ARQEDIA Base | 2500 | month | 1 |
| ARQEDIA Small Business | 6500 | month | 1 |
| ARQEDIA Top-up | 500 | one_time | 1–50, "number of $5 increments" |

Names must match `config/plans.json` `paddle_price_name`. Amounts match the
plan table, read today. Each product's sandbox→live ID mapping goes into
`config/paddle/live.json` (4.1).

## 4. Code before cutover — CC, needs no live account

- [ ] **4.1 One switch between sandbox and live.** `paddle.tf:72` reads
      `sandbox.json` and `paddle.tf:82` fixes `sandbox-api.paddle.com`. One
      variable chooses both, plus `config/paddle/live.json`, with a refusal at
      plan time if the IDs carry the wrong prefix. The file's IDs come from
      you after stage 3.
- [ ] **4.2 Checkout at first sign-in** (old stage 6). Still not built.
      `billing.py:287` stamps `checkout_offered_at`; nothing in `ui/src` reads
      `signup_intent` or `checkout_offered_at`.
- [ ] **4.3 Monthly-credit cap across a resumed period** (old stage 7).
      Unverified. Tenant 5, four $65.00 grants, 19–25 October. A query
      settles it.
- [ ] **4.4 Build refusals.** One test each, confirming the build refuses a
      `live_` token built for `sandbox` and a `test_` token built for
      `production`.
- [ ] **4.5 Webhook body encoding against the real gateway** (old stage 8).
      The handler takes both shapes. That API Gateway sends one or the other
      has never been read from a real CloudWatch entry.
- [ ] **4.6 The default payment link page.** Paddle opens it with a `_ptxn`
      parameter, including from its payment-method emails. Whether
      `app.arqedia.com` opens checkout from `_ptxn` has not been checked.
- [ ] **4.7 `pwCustomer` to Paddle.js** for Retain. Named in the 21 October
      readiness report and in Paddle's checklist; nothing in `ui/src` passes
      it. **Proposed**; goes with 2's Retain decision.

## 5. Decide before cutover — You

- [ ] **Dev's existing tenants.** They and their sandbox subscription IDs
      stay in what becomes the production database. Once the API points at
      live, every Paddle call for them fails. What happens to them is not
      decided.
- [ ] **Who holds the live credentials, and where.** The 26 October handoff
      records sandbox keys pasted into chats and command lines. The standing
      rule: you type or paste them, never into chat, a command line, a commit
      or a report.
- [ ] **Testing after cutover.** No sandbox environment remains in the app.
      Whether that is accepted, or met another way, is not decided.

## 6. Cutover — You, one sitting, in this order

Until 6.6 has run, the secrets, the Lambdas and the bundle disagree, so do
not leave it half done.

1. [ ] Live API key, same permissions as sandbox, into the existing
       `arqedia-dev/paddle/*` secret, through the console's Plaintext tab.
2. [ ] Live notification destination at the existing `/paddle/webhook` URL,
       with the same five events as sandbox. Its `pdl_ntfset_` secret goes into
       the existing webhook secret. **Create it once.** Recreating it rotates
       the secret.
3. [ ] Merge 4.1 with `live.json`, then `terraform apply` with the switch set
       to live.
4. [ ] `ui/.env`: the `live_` token and `production`. Build, then commit
       `web/` with the change.
5. [ ] Merge, which deploys the app.
6. [ ] Confirm the deployed state by reading it, never from the absence of an
       error:
       - the Lambdas' API base;
       - the bundle's token prefix (grep `web/assets`);
       - the secret prefixes, by length and prefix only.

## 7. First real payment — You, walked; CC reads it through

Paddle's checklist suggests a 100% discount code for the checkout, so there
is nothing to refund. A top-up is a charge against the stored card, so a
discount code may not reach it. It is a real $5, refunded by adjustment.

- [ ] One checkout, read through to `subscription` and a `monthly_credit`
      bucket.
- [ ] One top-up, read through to a `purchased` bucket, then refunded.
- [ ] One plan change, then a scheduled cancel and an immediate cancel.
- [ ] Tax added as expected in the first real customer's jurisdiction.
- [ ] The discount archived and the test subscription cancelled.

---

## Not required before live

- **Annual pricing.** No longer blocked (3), and nothing depends on it.
- **PAY-01:** whether Paddle's amounts belong in our database.
- **Paddle data on the staff console** (16.12).
- **The price-check test** against `plans.json`, which no workflow runs (17.9).
- **Housekeeping:** pre-038 credit figures in the test fixtures, and the 050
  header.
- **Webhook IP allowlist** from `https://api.paddle.com/ips`, recommended by
  Paddle. **Proposed.**
- **Legal pages and verification.** They are reachable but unlinked from the
  homepage, by decision. Whether Paddle's reviewer accepts that is not known
  until review.
