# ARQEDIA

Read this at the start of every session. The Rules of Engagement below apply to
every response and every commit, without being restated.

---

## Rules of Engagement

- Rules of Engagement are printed in full at the head of every response, not
  summarised.
- Schema-faithful. Where something is missing from the schema, flag it as
  proposed rather than inventing it.
- Additive and non-destructive. Nothing already recorded is overwritten or
  discarded.
- Two-LTV discipline: Bill of Exchange value is the invoiced amount, not marked
  to market.
- Confirm before build. Decisions that are hard to reverse are put to me before
  code is written.
- Concise.
- No assumptions about architecture or intent. Ask rather than infer.
- No fabrication.
- No hallucination.
- No rabbit-holing. Surface when a line of work has stopped being productive.
- Simple question, simple answer. Analysis only when asked for it.
- One path. No if-then branching in instructions.
- Read or ask for live state. Never infer it from naming.
- Review prior chat and context before answering.
- Separate branches, commit periodically.
- Working directory `c:\terraform\arqedia`, Terraform and Docker.
- Web-search third-party capabilities rather than assuming them.
- A short push summary on every push.
- Never edit a document, schema or file without first reading it in full.

---

## Working practices earned the hard way

**Never write CSS from reasoning.** Four attempts at one grouped layout, each
worse than the last, until the rule was supplied. What worked was letting the
label set the column — `max-content`, `nowrap` — and having the OUTER box
scroll. Render it and look at it, or ask.

**Drawer stacking follows document order.** There are no z-indexes. A drawer
opened from another must render AFTER it in the component, and must not sit
inside a collapsible part or it renders nothing when that part is shut.

**Keep what the row had.** Every upsert keeps fields the caller did not send.
A caller that omits `sort_order` must not zero it.

**`.tf` and `.py` are LF.** `.gitattributes` enforces it. A checkout that
writes CRLF into a heredoc or a Lambda source makes Terraform plan the resource
as changed on every single run, for ever, and applying does not fix it. A
resource that plans as changed with no code difference is line endings, not
code.

**A CSS class carrying `display` beats the `hidden` attribute.** A modal styled
`display: flex` is open on load unless `[hidden]` is given its own rule.

**Specificity inside the header.** `.shell header a` sets the pale blue that
suits navy. A panel inside the header must be selected through `.shell header`
or its text renders light on white.

**Verify by querying, never by the absence of an error.** A migration that
printed no error had not run. A build whose hash did not change may or may not
contain the new source. Ask the database or grep the bundle.

---

## The product, in one paragraph

A tenant holds one configuration — document types, facts and their wording, and
memoranda with their sections and bindings. That configuration is uniform across
every engagement. An engagement holds documents. A document is read once, at
filing, against the revision live at that moment, and never read again. A
memorandum is layout over facts already held, composed on demand. One Publish
covers the whole configuration, not a single memorandum.

---

## Settled decisions

These were argued and decided. They are not open, and code that contradicts one
is wrong even where it is locally sensible.

### Brand and colour

**A tenant's four colours appear on rendered output only** — a memorandum and
anything shared. The application itself wears ARQEDIA's palette, whoever is
signed in. No `--tenant-*` variable appears in the chrome; `style.palette_for`
resolves them at render time and nowhere else.

**One token file.** `ui/src/tokens.css` is the only place in either codebase
that declares a colour, a typeface or a radius. The application imports it from
`index.css`; the marketing site imports the same file. A value that is needed
and missing is added there, never redeclared.

**One mark.** `/brand/logo-deep.svg` and `/brand/logo-white.svg` at the
repository root. Both surfaces reference them by relative path; there is no
copy. The current pair are placeholders and say so in their own source.

**Gold is the act that costs money.** `--gold` appears on the generate control
and nowhere else. It is the only signal of its kind the product has.

### Reading and citation

**Read once, at filing, and never again.** This is what makes a memorandum from
March reproduce in September. Everything downstream — grouping, binding,
section order, wording of a fact's label — may change freely and reaches
memoranda built from documents filed months ago.

**Page-level citation is built.** `extracted_value` carries `locator_kind`,
`locator_index`, `char_start`, `char_end` and `cell_range`; `claim` and
`claim_evidence` bind a rendered sentence to the values behind it. EV-01 is
closed. The marketing site states page-level citation because the product does
it.

**A revision is an integer on an append-only series.** A memorandum names the
revision that wrote it. Two generated a fortnight apart under different
revisions are not the same document and say so.

### Money

**The ledger is append-only.** Nothing is updated, nothing deleted. There are
no reversals, because unreadable material is blocked before filing rather than
charged and refunded.

**Debit on the click.** The price is shown and accepted before anything is
filed. Every charge carries an idempotency key minted where the click happens;
a retry is refused as a repeat.

**A charge is all or nothing**, in a transaction. `rds-data:BeginTransaction`,
`CommitTransaction` and `RollbackTransaction` are separate IAM actions from
`ExecuteStatement` and all four are needed.

**Buckets, not a balance.** Spent soonest-expiry first, then oldest. "Credit
before cash unless a cash tranche matures sooner" is not a rule in code — it
falls out of that ordering.

**Prices are data.** `meter_price`, with `tenant_id IS NULL` as the standard
price. Enterprise is negotiated and a negotiated price must not be a release.
An unpriced event refuses; it never charges nothing.

**A short proposal is a number, not an error.** Money for eight of eighteen
shows "fileable now 8" and offers to set the rest aside.

### Signing up and seats

**One door.** The Cognito pool stays admin-create-only. `POST /signup` is the
only way an account comes into being, and the `arqedia-dev-signup` function is
the only thing in the system holding Cognito admin permissions. Enabling
self-registration would let anyone skip every control.

**Nothing is created until the emailed code comes back.** Every check runs on
the last click, before the code is sent, so a refusal never costs a wait.

**The password is never stored.** The browser holds it and sends it with the
code, once, when there is something to set it on.

**One trial per email domain**, with `tenant_domain.multi_allowed` as the lift
for a holding company or a consultant. The lift exists from the same day the
rule does.

**An IP address is a signal, never a gate.** Recorded on `signup_attempt` and
`tenant`, surfaced on abuse review, used only for a rate limit. Blocking on it
fails in both directions. It is personal data in the EU and the UK and needs a
retention limit.

**A seat is taken on acceptance.** An invitation reserves one for seven days
and lapses. Otherwise a firm that paid for five seats can use three.

**The last administrator cannot be removed or demoted.** A tenant with none
cannot change its own plan, card, brand or seats.

**An address outside the tenant's own domain is allowed and marked.** Outside
counsel and consultants are a real case; forbidding it makes the workaround a
shared login. The abusive case looks identical, so it is surfaced to the
administrator who would have to explain it.

**Two roles.** A Member uploads, files, generates, configures, publishes and
shares. An Administrator additionally changes the plan, the card, the brand and
the seats. Anything finer is a permission system and nobody has asked for one.

### Documents coming in

**A folder name is provenance.** Recorded and displayed; the classifier never
reads it. Letting it hint would put a counterparty's filing habits into our
classification, and two tenants would get different results from the same
document.

**A linked external source is detected, never synchronised.** A change upstream
is reported and nothing is filed without a click. Filing costs money and changes
what the next memorandum says; neither should happen because a counterparty
saved a file.

**File sources are an abstraction with an adapter per provider**, separate from
`provider_abstraction_spec_v1.md`. A screening provider returns facts; a file
source returns bytes and holds a long-lived credential.

---

## What is mocked, and where the fakes live

`ui/src/mock.tsx` holds every invented figure. **Delete a block from it the
moment the endpoint behind it is real** — an exported fake balance or a fake
list of colleagues is a trap, and the next screen that needs one finds it there
and never learns it was not real.

Mocked today: **Subscription** (no endpoint), **Sharing**, **the Viewer**.
Live: the wallet balance and ledger, seats, signing up.

Every inert control says "not connected yet" on click rather than failing
quietly, and every mocked screen carries the marker at the top of its own tab.

---

## What is open

- **SES production access** in `us-east-2`, and a verified sender. It gates the
  signup code and the invitation email. Everything either side of the send
  works.
- **Forking the chosen packs at first run.** `tenant.forked_pack` records one or
  two; first run still forks whatever is first in the list.
- **Paddle** (16 Sep 2026): one-off charges against a stored card are supported
  through the subscription charge API. The subscription screen is being
  connected to Paddle sandbox on `feature/paddle-subscription`.
- **Trial vetting**, `frontend_onboarding_spec_v1.md` §11. Self-serve sanctions
  tooling at $25 with no check on the buyer. Probably needs counsel.
- **Starter packs** validated by somebody who writes these memoranda.
- **`signup_attempt.ip` retention**, and the privacy-policy wording for it.
- **Does CI build the app.** `web/` is committed output; the marketing site
  builds in CI. Either bring them into line or record why not.
- **Seat counts as data.** `PLAN_SEATS` is a map in `seats.py`. It belongs in a
  `plan` table the way `meter_price` holds prices.
- **Recipient registration to download** a shared memorandum: gate it as a lead
  source, leave it open, or let the sender choose.
- **`docs/HANDOFF/` and `docs/backlog-items/`** hold duplicates of four backlog
  items, including a `(1)` copy of HONE01.

---

## Current work

`docs/ARQEDIA_backlog_UX01_mvp_ui_worklist.md` is the specification for the UI
work to MVP. Its decisions are settled; its branch order is not to be
rearranged. Work one branch at a time and stop at the end of each for review.

---

## What is not automated

- Merging to main. A human looks at the rendered screen first.
- Anything touching Terraform or the registry schema, including the numbering
  field in UX-07.
- New decisions. Ask; do not choose.
