# Wallet & Entitlement Gate — Spec v1.0

**DD SaaS product · greenfield · branch `feature/wallet-entitlement`**
Supersedes the inline v0.1–v0.3 drafts.

---

## 0. Status of every claim here

Every number and rule below came from this session's decisions. Nothing is
inherited from the eBL build, which is out of scope by instruction. Two items
are **PROPOSED** rather than decided and are marked as such: the database
engine (§3) and the text-layer floor (§5.2).

---

## 1. Scope

**Owns:** money buckets, expiry, quoting, the debit transaction, top-up, and the
single pre-flight decision every billable action passes through.

**Does not own:** subscription charges and invoices (delegated to the payments
interface, §6), the classifier, the pipeline, or the meaning of a share beyond
its count.

---

## 2. Settled economics

| Plan | Price/mo | Seats | Monthly credit | Shares/mo | Top-up increment |
|---|---|---|---|---|---|
| Base | $25 | 2 | $5.00 | 5 | $10 |
| Small Business | $65 | 5 | $15.00 | unlimited | $25 |
| Enterprise | negotiated | n | n | n | $5 × seats |

Billable events: `document_filed` $0.25 · `memo_generated` $1.00 ·
`provider_call` (phase 2, price TBD).

Trial: 30 days, seats free, $5.00 metered credit, expiring at `trial_ends_at`.

> **Corrected 22 September 2026.** The trial is **14 days**, not 30. It was
> changed by the Paddle decision record of 16 September
> (`paddle_subscription_decisions_2026-09-16.md`, "Trial is 14 days in all
> cases (was 30, Wallet §2)") and `signup.TRIAL_DAYS` has said 14 since. The
> line above is left standing because it is what this document said; the
> published figure now lives in `config/plans.json` as `trial_days`, which
> the marketing site and the application both render at build.
Trial-generated memos remain downloadable after expiry.

Seats are a fixed plan attribute. Adding a seat is a plan change, not a
proration.

---

## 3. Data model

**Aurora MySQL Serverless v2, minimum capacity 0 ACU, on a new cluster.**

*New cluster, not new tables on the existing one.* The eBL database holds
identified borrower material governed by the Client and Viewer Acknowledgements;
third-party tenant data cannot share that cluster. This is a contract
constraint, not a hygiene preference. It also makes the regulated stack a
Terraform scope parameter rather than a rewrite.

*MySQL, not Postgres.* The existing stack is MySQL and the team knows it.
Nothing in this model needs Postgres — `provider_entitlements` becomes a join
table rather than an array, which is the only difference.

*Minimum 0 ACU.* A 0.5 ACU floor bills ~$44/month of idle compute, which is
nearly two Base subscriptions burned before any tenant does anything. At 0 ACU
the instance pauses after a configurable idle window (300s–1 day, default 300s)
and instance capacity is not billed while paused. Resume on first connection is
roughly 15 seconds — acceptable for a document-upload product.

Two account-state checks before this is final, neither of which I can read:
whether the current engine version supports auto-pause (an upgrade may be
needed), and whether anything in the design will hold a persistent connection —
a pooler or an always-on health check defeats auto-pause and restores the floor.

```sql
plan                  plan_id PK, name, seat_count, monthly_price_cents,
                      monthly_credit_cents,
                      share_allowance INT NULL,        -- NULL = unlimited
                      active TINYINT(1)

plan_provider         plan_id FK, provider_code       -- join table, replaces the array
                      PK (plan_id, provider_code)

subscription          tenant_id PK, plan_id FK, status, billing_anchor_day,
                      trial_ends_at, payment_method_ref, created_at
                      -- status ∈ (trial, active, closed). 'capped' is NOT stored.

bucket                bucket_id PK, tenant_id FK,
                      kind,                            -- credit | cash
                      granted_cents BIGINT, granted_at, expires_at
                      INDEX (tenant_id, expires_at)    -- drives spend order

ledger_entry          entry_id PK, tenant_id FK, bucket_id FK,
                      event_type, event_ref, amount_cents BIGINT, created_at,
                      UNIQUE KEY (tenant_id, event_ref)   -- idempotency
                      INDEX (bucket_id)                   -- drives the SUM

price_book            event_type, unit_price_cents, effective_from
                      -- versioned; settled history never reprices

share_grant           grant_id PK, tenant_id FK, memo_id, viewer_account_id,
                      created_at, expires_at, revoked_at, first_opened_at
```

**MySQL notes.** All money is `BIGINT` cents — never a float, never `DECIMAL`
arithmetic in application code. Enum-like columns (`kind`, `status`,
`event_type`) are `VARCHAR` with a lookup table rather than MySQL `ENUM`, so
adding an event type is an insert and not a schema change. InnoDB throughout,
since the debit transaction depends on row-level locking.

**No materialised balance.** A bucket's remaining value is
`granted_cents − SUM(ledger_entry.amount_cents)` for that bucket, computed on
read. At ~100 events per tenant per month this is free, and with no cached
column there is no drift and no reconciliation job. Add the column later as an
optimisation if volume ever justifies it.

**No hold tables.** Charging happens at commit, in the same transaction as the
filing insert, so there is no window to reserve against. Concurrency is handled
by `SELECT ... FOR UPDATE` on the tenant's bucket rows under InnoDB's default
REPEATABLE READ, which serialises two concurrent debits against the same
balance.

---

## 4. Money rules

- **Two bucket kinds, one table.** Credit is granted monthly by the plan and
  expires at the billing anniversary, forfeiting any remainder. Cash is
  purchased and expires 30 days from its own purchase date. Each cash purchase
  is its own bucket with its own clock.
- **Spend order: soonest expiry first**, tie-broken by oldest `granted_at`.
  This single rule subsumes "credit before cash" — credit normally expires
  first, but a cash tranche maturing sooner is correctly burned first rather
  than stranded.
- **Available balance** is the sum of unexpired buckets. `capped` is derived
  from `available == 0`; it is never written to a column.
- **Ledger is append-only and monotonic.** No negative entries, no credits, no
  reversals — unreadable material is blocked before filing (§5.2), so there is
  nothing to refund.

---

## 5. The commit path

### 5.1 Sequence

```
upload file → classifier proposes parts → review screen (quote) → FILE ALL
                                                                     │
                                              ┌──────────────────────┘
                                              ▼
                          BEGIN
                            SELECT buckets FOR UPDATE
                            recompute available
                            debit N × $0.25 across buckets in spend order
                            insert filed parts
                          COMMIT
```

Memo generation is the same transaction shape with one $1.00 unit.

If available has fallen since the quote was rendered, the transaction files
`affordable_count` parts and leaves the rest in staging. Nothing is
half-processed: unfiled parts are an unaccepted proposal, not orphaned rows.

### 5.2 The quote

The wallet requires only this from the classifier — it does not care how the
part list is produced:

```
proposal {
  parts: [ { part_id, proposed_class, readable: bool, reason?: string } ],
  total_cents,          // readable parts only
  available_cents,
  affordable_count
}
```

Rendered to the operator before any money moves:

```
18 parts proposed          $4.50
Available                  $2.00   (credit $2.00, exp 28 Sep)
Fileable now                  8    · 10 remain in staging
```

**Readability is a gate condition, not a billing condition.** A part whose
extractable characters per page fall below a floor is marked
`readable: false`, reason `no_text_layer`, excluded from `total_cents`, and
cannot be filed. The operator is told to OCR it and resubmit. **PROPOSED:** the
floor itself is a tuning number to be set against test files during build.

---

## 6. Payments — interface, implementation deferred

No processor is named. The wallet depends only on this interface; a concrete
adapter is written when a processor is chosen, and verified against that
processor's live documentation at that time.

```
PaymentProvider
  attach_method(tenant_id)                  → payment_method_ref
  charge(payment_method_ref, cents, ref)    → Charged | Declined(reason)
  detach_method(payment_method_ref)         → void
```

Requirements the adapter must satisfy, stated now so the choice can be tested
against them:

1. **Card on file without a standing mandate.** Every charge is triggered by an
   explicit click; nothing is ever charged unprompted.
2. **Idempotency on `ref`**, so a retried top-up cannot double-charge.
3. **Subscription billing** for the monthly plan fee, separate from the
   click-triggered metered top-ups.
4. **No card data touches our infrastructure.**

---

## 7. Top-up

- **Soft prompt at ≤ $5.00** — persistent, non-blocking, states the balance in
  memos remaining. Most conversions should land here, before anyone is stopped.
- **Hard block at $0.00** — `capped`.
- **Consent per charge.** One click buys one increment ($5 × seats). There is no
  velocity limit and no spend ceiling because the click is the ceiling.

---

## 8. The gate

One function. Called before any billable work and before any model call.

```
gate(tenant_id, action, job_spec?) → Allow | Deny(reason, remedy)
```

| Action | trial | active | capped | closed |
|---|---|---|---|---|
| file parts / generate memo / provider call | balance | balance | deny | deny |
| read existing | allow | allow | allow | deny |
| download existing | allow | allow | allow | deny |
| create share | allowance | allowance | deny | deny |
| edit config | allow | allow | allow | deny |
| delete document | deny | deny | deny | deny |
| delete account | allow | allow | allow | allow |

`balance` = the debit transaction succeeds for at least one unit.
`allowance` = plan share counter not exhausted (NULL = unlimited), with a rate
limit applied regardless.

`Deny` carries a `remedy` so the UI renders the top-up prompt from the gate's
response rather than reimplementing the rule anywhere.

**Trial expiry needs no transition logic.** The trial credit bucket expires,
available reaches zero, `capped` falls out of the derivation. Checkout sets
`status = active` and grants the first monthly credit bucket.

**Share viewers** hold a non-consuming entitlement scoped to one rendered memo.
No config, no upload, no generation, no seat charge. Grants are revocable and
expiring, and `first_opened_at` is the marketing signal.

---

## 9. Deletion

Per-document deletion is denied in every state — the ledger must stay
reconcilable against filed artifacts. Account deletion is permitted in every
state and scrubs tenant rows, storage prefix, derived artifacts, and revokes
every outstanding share grant.

**Flagged, unresolved:** denying per-document deletion may collide with
statutory erasure rights in some tenant jurisdictions. Legal question, not an
engineering one.

---

## 10. Open

1. **Aurora engine version** (§3) — confirm the current version supports
   auto-pause, or plan an upgrade. Account state; needs a live read.
2. **Persistent connections** (§3) — confirm nothing in the design holds one,
   or the 0 ACU floor is theoretical.
3. **Text-layer floor** (§5.2) — tuning number, set during build against test
   files.
4. **Processor choice** (§6) — deferred by decision; adapter written on
   selection.
5. **Provider call pricing** (§2) — phase 2.

Items 1 and 2 are account state and gate the cost model. Items 3–5 do not block
the design.
