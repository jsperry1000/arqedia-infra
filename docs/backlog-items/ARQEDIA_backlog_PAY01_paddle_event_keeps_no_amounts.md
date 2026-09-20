# PAY-01 — What Paddle charged cannot be answered from our database

**Raised 19 September 2026**, out of the first sandbox checkout. Noticed when
a simple question - was tax added on top? - could not be answered from any row
we hold.

---

## The problem

`paddle_event` records that an event happened and nothing about what it said:

    event_id  event_type  occurred_at  tenant_id  paddle_entity_id
    needs_review  received_at

No payload, no amount, no currency, no tax, no fee. The processor logs an
outcome - `outcome=credit-granted` - and deliberately logs no figures. The
`wallet_bucket` row carries the transaction ID as its reference, which is a
pointer rather than an amount: it says the $5.00 monthly credit came from
transaction `txn_...`, not that the tenant was charged $26.65 for it.

So on 19 September the first real checkout completed, everything worked, and
these were the facts about the money:

    charged              25.00   pre-tax
    tax at 6.6%           1.65   added on top
    total paid           26.65
    Paddle's fee          1.83
    net to ARQEDIA       23.17

**Not one of those figures exists anywhere in ARQEDIA.** Every one came from
the Paddle dashboard, by hand, for transaction
`txn_01m2x7kdkdrxjese1q6ekkb4rf`.

## Why it matters more than it looks

- **Support.** "What was I charged on the 19th?" cannot be answered without
  logging in to Paddle. The tenant's own Invoices tab is still mocked, so
  there is nothing to show them either.
- **Reconciliation.** The ledger is reconcilable against what was filed
  (Wallet section 4) and against nothing at all on the money coming in. A
  bucket granted for a payment that was later refunded looks identical to one
  granted for a payment that stood.
- **The fallback is not there.** Reading it from the Paddle API needs a key
  with `transaction.read`. The key behind the sandbox MCP connection does not
  have it - `transactions.get`, `subscriptions.get` and `subscriptions.list`
  all answer "You aren't permitted to perform this request" - so on the day
  this was asked, neither our database nor our tooling could say.

## What would close it

**PROPOSED, all of it.** None of this is in the decision record and none of it
has been agreed.

- **Keep the amounts on `paddle_event`**: `currency_code`, `subtotal_cents`,
  `tax_cents`, `total_cents`, `fee_cents`, `earnings_cents`, each nullable
  because not every event type carries them. A migration and a few lines in
  the processor, which already has the payload in its hand.
- **Or keep the raw payload** in a `JSON` column and read figures out of it
  later. Cheaper to write and worse to query; it also stores whatever Paddle
  chooses to send, which is a privacy decision rather than a schema one -
  `include_sensitive_fields` is currently `false` on the destination, and that
  should stay a deliberate setting rather than an accident of storing
  everything.
- **Decide which**, because doing both is how two sources of truth start.

The second is what makes the first possible retrospectively: without a stored
payload, the fifteen events already received cannot be backfilled from
anything except the Paddle API.

## What to decide first

**Whether the amounts belong to us at all.** Paddle is the merchant of record:
it holds the invoice, it holds the tax determination, and it is the legal
record of the sale. Copying its figures into our database means keeping two
records that can disagree - after a refund, an adjustment or a currency
conversion - and the one a person reads would be ours.

The honest middle is probably: **keep enough to answer "what happened and when"
and link out to Paddle for the document**. That is a decision, not an
implementation, and it has not been made.

## Not in scope

The Invoices tab, which is mocked and stays mocked on this branch (decision
record item 8). It is the obvious consumer of whatever this produces, and it
is the reason to decide this before building that.

## Done when

- A completed checkout leaves enough in our own tables to say what was
  charged, in what currency, and how much of it was tax.
- The wider question above is answered, or recorded as deliberately deferred
  with a reason.
- The first sandbox checkout of 19 September is either backfilled or recorded
  as unbackfillable.
