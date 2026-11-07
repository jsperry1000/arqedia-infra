# ARQEDIA — Paddle handoff, 26 October 2026

Status snapshot for a new chat. Everything below is **sandbox only**. No live
Paddle account exists. Nothing here is new work — a consolidation of what was
decided, built, proven, and left open across the Paddle integration chat that
ran 16 September to 26 October 2026.

Two companion docs carry the forward plan and should be read with this one:
`ARQEDIA_paddle_go_live_build_list.md` (what is missing, in dependency order)
and `ARQEDIA_paddle_go_live_cc_prompts.md` (the same work as Claude Code
prompts, reordered so the account-independent work runs first).

---

## 1. Processor choice — settled

Paddle Billing, as merchant of record. Polar and Stripe were both examined
when flexibility was questioned; Paddle was confirmed sufficient and the
question is closed. The decisive capability was a one-off charge against a
stored card, triggered by an explicit click — which Paddle supports, and which
the top-up model depends on.

Prices are **tax-exclusive**. Paddle adds tax at checkout; a US checkout on 20
September was observed at 6.6% on top of the listed amount. This is confirmed
from a real transaction, not from documentation.

---

## 2. Decision record — authored, in the repo

`specs/paddle_subscription_decisions_2026-09-16.md`. Fifteen approved items
plus item 16, with two amendments. The ones that constrain future work:

- **1** — API key and webhook secret live in AWS Secrets Manager, values set
  outside Terraform so they never reach state. The Paddle client-side token
  (`test_`/`live_`) is public by Paddle's own documentation and ships in the
  bundle.
- **2** — charge at checkout; no Paddle trial period. Our trial is our own.
- **3** — a plan is a row, not code.
- **4** — receiver and processor are separate Lambdas.
- **5** — HMAC with the Python standard library, no Paddle SDK in the receiver.
- **6** — grants come only from `transaction.completed`. `checkout.completed`
  and `checkout.closed` are cues to re-read our server, never to grant.
- **7** — the tenant reference is set server-side on the transaction, never
  accepted from the browser.
- **9** — leftover trial credit is kept, not cleared, on subscribing.
- **10** — a top-up is refused when there is no subscription.
- **11** — `subscription` is its own table.
- **12 / 13, as amended** — unexpired purchased cash remains spendable while
  `past_due` and after cancellation. The original drafting took it away; that
  was rejected on the grounds that the customer paid cash for it.
- **14** — a downgrade is refused when seats are in use above the lower plan.
- **15** — refunds are recorded, not reversed out of buckets.
- **16** — a mid-cycle upgrade grants the difference in monthly credit, capped.
  A downgrade grants nothing and reclaims nothing.

§3 of that document holds the open items; the live ones are repeated in §8
below.

---

## 3. Sandbox catalogue and its mapping

Three products and prices created in the sandbox dashboard: **Base $25/mo**,
**Small Business $65/mo**, and a **$5 one-time top-up**. Mapped into the
existing repository at `config/paddle/sandbox.json` — not a separate Paddle
repository, by decision. Amounts are strings in the lowest denomination.

Monthly credit equals the plan fee's credit figure per migration 038: $5.00 on
Base, $15.00 on Small Business.

---

## 4. The Paddle MCP server in Claude Code

Working, as `paddle-sb`, connected. This took several attempts and the failure
mode is worth recording because it will recur on the live key:

- The key kept landing as placeholder text (`NEW_KEY`, `PASTE_KEY_HERE`) or,
  once, as an entire PowerShell command line — the stored secret's prefix read
  `powershel`, length 109, instead of `pdl_sdbx_`, length 69.
- Fixed by removing the stale `-s local` entry and re-adding at `--scope user`
  with the key typed in place before pressing Enter.
- **There is no separate Claude Code key.** It is the same Paddle sandbox API
  key. That was not said plainly early enough and cost time.

The same command-line-instead-of-key mistake also reached Secrets Manager and
produced `authentication_malformed` on `POST /billing/checkout`. Fixed through
the AWS console's Plaintext tab. Two API keys were in existence at one point
and were reduced to one.

**Standing rule from all of this:** credentials are typed or pasted by you,
never put into chat, a command line, a commit, or a report.

---

## 5. What is built

**Webhook path.** Receiver Lambda on an unauthenticated route
(`POST /paddle/webhook`, `authorization_type = "NONE"`), verifying
HMAC-SHA256 over `ts:rawBody` with the standard library, then async-invoking a
processor Lambda. The processor runs one Data API transaction per event,
de-dupes on `event_id`, and orders by `occurred_at`. An SQS queue is the
on-failure destination; `reserved_concurrent_executions` is 1 on the processor
and 5 on the receiver; two retries. A CloudWatch alarm watches the failure
queue. The replay procedure is in `paddle.tf`'s header comment.

**Wallet.** Buckets (`trial`, `monthly_credit`, `purchased`, `daily_test`),
append-only ledger, balance derived on read, spend soonest-expiry-first,
`capped` derived and never stored.

**Migrations.** 018 (`plan`, `subscription`, `paddle_event`, `topup_request`),
019 (signup intent), 020 (`previous_plan_id`), 027 (signup allowlist), 038
(monthly credit equals the plan's credit figure).

**Front end.** `ui/src/paddle.ts` (new), with `ui/src/api.ts` and
`ui/src/Account.tsx` wired to the live endpoints. The mock `SUBSCRIPTION` and
`PLANS` objects were deleted from `ui/src/mock.tsx`. The client-side token
comes from build-time env — `VITE_PADDLE_TOKEN` and `VITE_PADDLE_ENVIRONMENT`,
declared in `ui/.env.example` and `ui/src/vite-env.d.ts`, validated in
`ui/vite.config.ts` so a mismatched pair cannot ship. Checkout is branded to
the mid brand colours, replacing Paddle's default green.

**Signup.** `TRIAL_DAYS = 14`. Plan and intent are validated at signup and
stored on `pending_signup`, then copied to the tenant at verify. The
invite-only allowlist and the `FREE_MAIL` guard merged as #174.

---

## 6. What was proven end to end on sandbox

- **Webhook delivery** — simulator event 17 September; real checkout 19
  September.
- **Checkout** — a real sandbox subscription created and read through to a
  `monthly_credit` bucket.
- **Tax** — added on top, 6.6% observed, read off the Paddle transaction
  detail.
- **Top-up** — charged on a click and matched to its `topup_request` row. A
  repeat is detected by the duplicate-key path:
  `DatabaseErrorException` carrying `Error code: 1062` and `uq_idempotency` is
  treated as a repeat, not an error. A $15 `purchased` bucket was confirmed on
  the balance screen.
- **Plan change** — proven after the fix in §7.

---

## 7. The plan-change credit bug — found, fixed, proven

A proration transaction carries **two items**: the new plan at quantity +1 and
the old plan at quantity −1. The processor had been reading the plan off the
items without regard to sign, so an upgrade could be read as the wrong plan.

Diagnosed from the real payloads, not from reading the code. Fixed in
`lambda/paddle_processor/app.py` by splitting the question in two:

```python
def plan_of(items):
    """The plan the items are FOR: the plan price at positive quantity."""
    return _one(_plan_keys(items, taken_away=False))

def plan_removed(items):
    """The plan the items TAKE AWAY: the plan price at negative quantity."""
    return _one(_plan_keys(items, taken_away=True))
```

`_plan_keys(items, taken_away)` treats a missing quantity as positive.
`monthly_credit_granted(tenant_id)` sums unexpired monthly credit
(`WHERE expires_at > NOW()`) and is what `_grant_upgrade` caps against.

**Proven on dev:** an upgrade granted $10.00 and capped at $15.00. The
deployed zip was verified byte-for-byte against HEAD, so the behaviour
observed was the behaviour in the branch.

A downgrade grants nothing and reclaims nothing, per item 16. Paddle shows its
own credit on the downgrade; we do not mirror it into buckets, and the question
of refunding cash to the card on a downgrade was raised and left where item 15
leaves it — recorded, not reversed.

---

## 8. Open — Paddle

**Blocking the live catalogue.** Whether editing a Paddle price's amount
re-prices existing subscribers, or whether they keep the price they bought.
Two documentation searches found nothing; it needs Paddle support. It gates
annual pricing, and it should be answered before the live prices are created —
getting it wrong re-prices people who have already paid.

**Needs a decision from you.** ENV-01: whether live is a second Terraform
stack or the same one re-pointed, and how migrations are recorded per
environment. Nothing in the repository says which environment received which
migration. Every other stage inherits this answer, which is why it is first on
the build list.

**Not built.**

- Checkout at first sign-in. The decision of 17 September stands;
  `GET /billing/subscription` already returns `signup_plan`, `signup_intent`
  and `checkout_offered_at`, and nothing reads them. Somebody who chose
  Subscribe on the pricing page lands on a trial and has to find the Account
  screen themselves.
- "Plus tax" beside every price, and the trial and top-up terms stated in
  customer-facing copy. Every number on screen today is less than the customer
  pays.

**Unverified.**

- Whether the monthly-credit cap holds across a resumed period. Tenant 5 was
  granted $65.00 four times between 19 and 25 October, three on one day.
  Either each grant had its own expiry and the cap held, or it did not. One
  query settles it; it matters because the same path with real money hands out
  credit nobody paid for.
- The webhook signature against the real gateway body encoding. API Gateway
  may base64-encode the body and this has never been confirmed either way
  (decision record §3). Sandbox works, which is evidence and not proof.

**Silent failures.**

- The SQS failure-queue alarm has no notification target. A failed event means
  a customer paid and received nothing, and today it would sit unnoticed.
- Nothing reads `needs_review`. Four events carry it. With real money, an
  unmatched charge is money received and unaccounted for.

**Not required before live.** Annual pricing (blocked above). PAY-01, whether
Paddle's amounts belong in our database — invoices now read live from Paddle,
which is a working answer whether or not it is recorded as the decision.
Paddle data on the staff console (16.12). The price-check test comparing
`plans.json` against Paddle, which no workflow runs (17.9). Eight migration
headers that say "not applied" when they are, and test fixtures carrying the
pre-038 credit figures.

---

## 9. Done alongside, and worth knowing

**Signup is testable stem to stern.** Cloudflare Email Routing provides a
catch-all on `deus-ex.co`; SES was already in production (not sandbox) in
`us-east-2`. AWS-native alternatives were examined and Cloudflare was chosen
because the domains were stagnant anyway. The Cloudflare activity log showing
"Dropped" was the expected state for an unrouted address, not a fault.

**Upload was broken and is fixed.** The presigned S3 PUT was blocked by CORS
because the docs bucket's `AllowedOrigins` did not include
`app.arqedia.com`. Fixed on three buckets. Two wrong guesses preceded the
browser console showing the actual cause — payload size, then API Gateway.
The lesson stands: read the console before theorising.

**A misdiagnosis to not repeat.** A stacking `setInterval` loop was diagnosed
here and disproved by Claude Code: there is one interval, correctly guarded,
and 36 invocations a minute is one poll every 5 seconds. The real cause was a
scanned PDF silently refused by the normalizer. OCR is being handled in a
separate chat.

**BLD-01 raised.** A one-line change produced a five-change Terraform plan,
from `__pycache__` written by Docker test runs plus `signup` deployed from the
unmerged `signup-allowlist` branch. `archive_file` now carries
`excludes = ["__pycache__"]`. The habit to keep: when the plan shows more than
you changed, find out why before applying.

**Branches cleaned,** local and remote. Note for next time: squash merges
rewrite commit SHAs, so a local branch cannot be diffed against main to prove
it was merged — three attempts failed before that was accepted. `main` is not
hard-reset locally.

**PAY-02 written** — `ARQEDIA_backlog_PAY02_paddle_what_is_left.md`, in the
ENV-01 house format.

---

## 10. Standing constraints for whoever picks this up

- `terraform apply` and `db/migrate.ps1` stay with you. Claude Code never runs
  either.
- Never edit a document, schema or file without reading it in full first.
- Credentials are never pasted into chat or a command line.
- Read or ask for live state. Never infer it from naming.
- Separate branches, commit periodically, a short push summary on every push.
- Advisory chats have no access to the repo, AWS, or Paddle. Claude Code runs
  locally against `C:\terraform\arqedia`; its output is pasted back for review,
  and prompts are written here to be pasted forward.
