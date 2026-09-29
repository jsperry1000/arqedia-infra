# Config Editors & Mapping Join — Spec v1.0

**DD SaaS product · greenfield · design spec**
Component 3 of 9. Reads and writes *Config Registry v1.0*. Gated by
*Wallet & Entitlement Gate v1.0*.

---

## 0. Status of every claim here

Every rule below is a decision made for this product. Items requiring a decision
from you are marked **OPEN** and collected in §9. Nothing in this component
remains PROPOSED.

---

## 1. Scope

**Owns:** the four authoring surfaces a tenant configures the product through,
the live validation shown inside them, and the publish flow.

**Does not own:** storage or versioning (registry), extraction (component 4),
visual design system, or money.

**Why it matters commercially:** this is the product. The extraction engine is
identical for every tenant; what they are paying for is the ability to shape it.
If these four surfaces are confusing, there is no product — only a generic
document reader.

---

## 2. Core decisions

**2.1 — Four editors, one draft, one Publish.**

A persistent bar sits across all four surfaces: draft status, live issue count,
lock holder, and the Publish button. A tenant never publishes "a template" —
they publish their configuration. This follows directly from registry §3.1 and
must be visible, or they will not understand why a template change did nothing.

**2.2 — Validation is live and advisory; publish is the only block.**

The registry's `validate()` dry run runs on every save and renders inline
against the offending object. Issues do not prevent saving. Publish refuses
while any blocking issue stands. Tenants build in an invalid state constantly —
a schema exists before anything maps to it — so blocking saves would make the
editors unusable.

**2.3 — Nobody starts from a blank page.**

First run is fork-a-pack, not an empty editor. The three packs are the onboarding
flow. A blank-slate builder is the single most reliable way to lose a self-serve
tenant in the first ten minutes.

**2.4 — Members see everything, change nothing.**

Every surface renders read-only for `member` seats. Config is not secret from
the people using it; a member needs to understand why a memo section is empty.

**2.5 — Plain language throughout, no internal identifiers.**

Tenants never see `handler_code`, `field_id`, `revision_id`, or the word
"schema" if a better one exists. Keys are auto-derived from labels and shown
only in export and API contexts.

---

## 3. Surface 1 — Categories & document types

The simplest surface, and the one tenants touch first after forking.

- Two-level list: categories, each holding document types. Drag to reorder,
  drag to move a type between categories.
- Each type carries a label and a description. **The description is not
  decorative** — it is what the classifier uses to recognise the type, so the
  field is labelled to say so, with an example.
- Removing a type shows what it will break before confirming: how many mappings
  reference it, and how many previously filed documents used it. Removal is
  draft-only until publish, and old documents keep resolving against old
  revisions (registry §3.4). The confirmation says so plainly, because "delete"
  reads as destruction and here it is not.

---

## 4. Surface 2 — The mapping join

**The centrepiece. Built as a matrix, not a form.**

Document types down the left, schemas across the top, a checkbox at each
intersection. Margin counts on both axes. This is the only display that makes
the three failure modes visible at a glance:

| Failure | How it appears |
|---|---|
| Zero-read | An empty **row** — a document type that extracts nothing |
| Orphan schema | An empty **column** — a schema nothing can produce |
| Overlap | A flagged **cell pair** — two schemas on one row sharing a field |

Overlap is field-level, not cell-level, so it needs its own treatment: hovering
a row lists every field the row's mapped schemas produce, with duplicates
highlighted. This is the failure that is effectively impossible to find by hand,
and finding it is the strongest single argument for the matrix.

At tenant scale — dozens of types, tens of schemas — the matrix fits on a
screen with filtering by category. It does not need to scale further.

---

## 5. Surface 3 — The schema editor

### 5.1 Shape

A schema is a name, a handler, an ordered field list, and an extraction prompt.

### 5.2 Fields

Each field: label, data type, cardinality, required flag.

**Settled — eight data types.**

| Type | Holds | DD example |
|---|---|---|
| Text | Free text | Business description |
| Number | Plain numeric | Number of employees |
| Date | A calendar date | Incorporation date |
| Currency amount | Value plus currency code | Share capital, turnover |
| Boolean | Yes/no | Audited? |
| Entity name | An organisation or person | Registered name, UBO name |
| Address | A structured address | Registered office |
| Identifier | A registration-style code | Company number, LEI, tax ID |

The last three are deliberately not Text. Each is treated differently
downstream — name matching for screening, address normalisation, format
validation on identifiers — and the provider abstraction (component 6) needs
them typed to bind against. Collapsing them into Text now means adding the
distinction back later against live tenant configurations, which is not
practical.

The list is deliberately short. A longer one pushes tenants into schema design
they did not sign up for, and every type carries extraction logic and template
rendering behind it.

**Tenants supply names; we supply types.** A KYC schema might hold "Registered
Name" as an Entity name and "Company Number" as an Identifier. Starter packs
ship with sensible names already in place, which is where most tenants will
leave them.

**Fields can be grouped into a repeating row.** The editor presents this as
"these fields repeat together" — shareholder name, percentage and role captured
as one line. A group renders as a table in both the editor and the memo. This is
how ownership tables, service providers and trade counterparties are captured;
without it they degrade into unrelated parallel lists.

`field_id` is minted on creation and never shown. Renaming a label is free and
the UI should say so — otherwise tenants avoid renaming out of fear, and live
with bad labels forever.

### 5.3 The extraction prompt

The hardest surface in the product, because tenants are not prompt engineers.

- **The prompt is scaffolded from the field list**, generated automatically and
  fully editable. A tenant who never opens it still gets a working schema.
- **Editing is optional and framed as tuning**, not as a required step.
- **Test run** against a document the tenant has already filed, showing extracted
  values against the field list. Without this, prompt authoring is blind and
  tenants will ship bad schemas and blame the product.

**Settled — test runs are free against a $1.00 daily allowance per tenant.**

Implemented as a wallet bucket of kind `test`: granted 100 cents, expiring at
end of day, non-rolling. Test runs debit it at the normal $0.25, so four runs a
day. Exhausting it blocks further test runs until reset; it does not spill over
into real balance, and real balance can never be spent on testing. Reusing the
bucket mechanism means no separate counter, no new debit path, and the same
idempotency guarantees.

The exposure is bounded and known: $1.00 of notional per tenant per day, which
is our inference cost only, with no revenue against it. Cheap insurance against
tenants shipping untested schemas and blaming the product.

### 5.4 Handler

Presented as a plain-language choice about document shape, not a technical
setting. The list is defined by component 4 and held for the build phase. The
editor requires only that the choice validates against that list, and that
changing it warns when the current field set is incompatible.

---

## 6. Surface 4 — The template editor

- **Sections** are ordered, each with a heading, a narrative prompt, and a set
  of bound fields.
- **Binding picker shows provenance.** Each selectable field displays which
  document types can actually supply it under the current mapping. A field no
  mapped type produces is shown but marked unreachable. Without this the tenant
  binds fields that can never populate and discovers it only in a finished memo.
- **Coverage preview** per section: which fields are bound, which are
  unreachable, which sections are empty.
- **Bindings cannot drift from the schemas — CARRIED FORWARD FROM BUILD.**
  Saving a template that names an undefined field is blocked, not warned.
  Renaming a field propagates to bindings and shows which templates are
  affected. Deleting a field opens every template that binds it and requires
  the binding be resolved first. See *Config Registry* §5.
- **Narrative prompt** governs how bound values become prose. Scaffolded like
  the extraction prompt, editable, optional.
- **Output format** per template: PDF, DOCX, or both.

---

## 6A. Deriving a template from the tenant's existing memo

**The tenant uploads a memo they already write, and the system proposes a
template that mirrors it.** This is the strongest onboarding moment in the
product — the answer to "will it produce what we already produce" stops being a
promise and becomes something they can see in five minutes.

**It works against a forked pack, not from nothing.** The pack supplies a field
vocabulary; the uploaded memo supplies structure and voice. The system
reconciles the two.

**What is proposed:**

| Derived from the memo | Result |
|---|---|
| Headings and order | Template sections, in their order |
| Prose in each section | A narrative prompt capturing their house voice |
| Facts referenced in the prose | Bindings to pack fields where recognisable |
| Facts with no matching pack field | Proposed new fields, flagged for review |

**Sections are reliable; field bindings are inference.** A finished memo
contains values, not field definitions — "incorporated in Jersey on 4 March
2019 under number 12345" implies three fields, and recognising that is
judgement, not parsing. The review screen must present bindings as proposals to
confirm, never as settled, or a tenant inherits confident mistakes.

**The uploaded memo is processed for structure and discarded.** It is not filed,
not charged, and its values never enter the tenant's extracted data. It contains
real counterparty material about a third party who has no relationship with us,
and there is no reason to keep it.

**It lands in the draft**, subject to the same publish validation as anything
else (*Registry* §5).

**Plan ceilings will bite here, and the flow must handle it gracefully.** A
tenant's real memo may run to eighteen sections against Base's twelve. That is a
legitimate upgrade conversation presented at exactly the right moment — the
screen should say which sections exceed the plan and offer both trimming and
upgrading. It must not read as an error.

**Billing — free, three per month.** Reading a full memo and deriving structure
is a large-context call and costs us more than an ordinary extraction. It is
also the single highest-value moment in onboarding, and charging for it there
would be self-defeating. Capped rather than unlimited because the cost is real.

---

## 7. Cross-cutting

**Publish flow.** Publish opens a summary: what changed since the last revision,
blocking issues, non-blocking warnings, and a count of previously extracted
values affected by any field deletion (registry §6). Confirm to publish; the
draft becomes revision N+1.

**Lock state.** The persistent bar shows the holder and elapsed time. A second
admin sees read-only plus a Take Over control, enabled only after expiry, naming
the current holder in the confirmation (registry §8).

**Capped state.** All four surfaces render read-only, with export still
available and a top-up prompt in place of Publish (wallet §8).

**Empty and error states.** Every blocking issue links directly to the object
that caused it. A publish failure that says "3 issues" without navigation is a
support ticket.

---

## 8. Interfaces

The editors are a client over the registry interface. They add nothing to it
except:

```
Editors
  preview_extraction(tenant_id, schema_id, document_id)  → FieldValue[]
  change_impact(tenant_id)                               → ChangeSummary
  derive_template(tenant_id, uploaded_memo)              → ProposedTemplate
```

`change_impact` powers both the publish summary and the removal confirmations.
`preview_extraction` is §5.3's test run and is the only editor operation that
touches inference.

---

## 9. Open

1. **Handler list** (§5.4) — held for build phase, per prior decision. The only
   item genuinely awaiting a decision.

**Settled:** test-run billing — free against a $1.00 daily allowance (§5.3);
field data types — eight, fixed (§5.2); overlap treatment — detect, block,
explain (§4); repeating field groups (§5.2); derive-template-from-memo, free,
three per month (§6A).

**Closed with caveat — guided overlap resolution.** §4 detects overlap by field
ID intersection, blocks at publish, and names the two schemas and the shared
field. That is complete behaviour and nothing is waiting on it.

A one-click fix — *"Company Number is produced by both Company Identity and
Corporate Details; remove it from which?"* — is a post-launch enhancement, not a
design gap. It is deferred because the right affordance depends on which of the
three valid fixes tenants actually reach for: unmap a schema, remove the field
from one schema, or split into two distinct fields. Offering only one of those
pushes tenants toward it even when another was correct. Adding it later touches
no data model and no validation logic; it is UI over information already
computed.

This component is otherwise closed and buildable.
