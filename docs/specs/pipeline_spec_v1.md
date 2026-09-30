# Pipeline — Spec v1.0

**DD SaaS product · greenfield · design spec**
Component 4 of 9. Reads *Config Registry v1.0*. Gated and charged by
*Wallet & Entitlement Gate v1.0*.

---

## 0. Status of every claim here

Every rule below is a decision made for this product. Items awaiting a decision
from you are collected in §9. **§8 is the important section** — it contains two
unbounded cost exposures created by decisions already taken, and both need a
call before build.

---

## 1. Scope

**Owns:** everything between a file arriving and a rendered memo — staging,
classification, the part proposal, readability, filing, extraction dispatch,
value persistence, composition, render.

**Does not own:** config (registry), editors, money rules (wallet), sharing,
external data providers.

---

## 2. The six stages

```
1  UPLOAD          file → tenant staging prefix              free
2  CLASSIFY        propose parts, types, readability         free  ⚠ §8.1
3  REVIEW          quote shown, operator confirms            free
4  FILE            charge $0.25/part, commit                  BILLED
5  EXTRACT         run mapped schemas, persist values        free  ⚠ §8.2
6  COMPOSE         bind to template, render PDF/DOCX          BILLED $1.00
```

Stages 1–3 are free and reversible. Stage 4 is the commitment point: money
moves, and everything after it is included. This boundary is the whole billing
model and it must not drift.

---

## 3. Revision pinning

At stage 4 the job reads `current_revision(tenant_id)` once and carries that
`revision_id` through stages 5 and 6. It never re-reads.

A publish landing mid-job must not change the rules under work that has already
been quoted and charged. Extracted values are stamped with the revision that
produced them; a memo records the revision it composed under. That pair is what
makes a March memo reproducible in September.

---

## 4. Stages 1–3: upload, classify, review

**Upload** writes to the tenant's staging prefix. Nothing is charged and nothing
is visible to the rest of the product.

**Classify** does three things per uploaded file:

- **Split** — detect document boundaries within a combined file and propose
  parts. One 47 MB PDF may be 18 documents.
- **Type** — propose a `document_type` per part, matched against the tenant's
  own types using the descriptions authored in the editor (*Config Editors*
  §3). This is why those descriptions are functional, not decorative.
- **Readability** — extractable characters per page against a floor. Below it,
  the part is marked `no_text_layer` and cannot be filed. The operator is told
  to OCR and resubmit.

**Review** shows the proposal with the quote (*Wallet* §5.2). Readable parts
only are priced. The operator may correct proposed types, merge or split parts,
and drop parts before confirming.

**Everything here is a proposal, not data.** A tenant who never confirms has
created nothing and owes nothing. Parts left unfiled stay in staging until a
retention sweep.

---

## 5. Stage 4: filing and the charge

One transaction (*Wallet* §5.1): lock buckets, debit N × $0.25, insert the filed
parts, pin the revision, commit. If balance has moved since the quote, file
`affordable_count` parts and leave the rest in staging.

Filed parts move from the staging prefix to the tenant's document prefix. A
filed document is immutable — corrections are a new filing, not an edit.

---

## 6. Stage 5: extraction

For each filed part, the pipeline resolves its `document_type` to the set of
schemas mapped to it under the pinned revision, and runs each one.

- **Dispatch** is by `handler_code` on the schema. **The handler list is
  deferred to the build phase by decision.** The pipeline requires only that
  dispatch is by a validated code and that a handler receives the document, the
  field list, and the extraction prompt, and returns typed values.
- **Persistence** is `(document_id, field_id, value, row_ordinal, revision_id)`.
  Values bind by stable `field_id`, never by label. `row_ordinal` is 0 for
  ordinary fields and the row index for fields in a repeating group
  (*Registry* §3.2a); a handler returns rows for a group rather than
  independent lists.
- **Failure is per schema, not per document.** One schema returning nothing
  leaves the others' values intact. Nothing is refunded — the readability gate
  at stage 2 exists precisely so that the common cause of total failure is
  caught before money moves.
- **Retries** are idempotent on `(document_id, schema_id, revision_id)`.
  Extraction is free at this stage, so a retry costs the tenant nothing and
  costs us inference.

---

## 7. Stage 6: composition

The tenant picks a template and a set of filed documents.

- **Bind** — for each section, gather values for its bound `field_id`s across
  the selected documents.
- **Coverage report before generating** — which sections will be fully
  populated, partially populated, or empty. Shown *before* the $1.00 is
  charged, so nobody pays for a memo that was always going to be half empty.
- **Narrate** — each section's narrative prompt turns bound values into prose.
- **Render** — PDF, DOCX, or both, per the template.
- **Regeneration is a new memo at $1.00.** Memos are immutable artifacts, and
  a memo already shared must not change under the viewer.

**Values may predate the pinned revision.** A document filed under revision 3
and composed under revision 7 binds fine as long as the field IDs still exist.
Where they do not, the section shows as uncovered in the coverage report.

---

## 8. Cost controls — settled

Both exposures below follow from decisions already made. Both are now bounded.

### 8.1 Classification allowance

Stage 2 is inference, is not charged, and runs before any commitment. A tenant
can upload continuously and never file. That is rational behaviour for someone
on a $5 credit who wants to know what is in a pile of files, not abuse.

**Settled — a daily classification allowance, implemented as a fourth wallet
bucket kind (`classify`).** Granted at first use each day, expiring at end of
day, non-rolling. It debits at a notional per-part price, sealed off from real
balance in both directions exactly as the test bucket is (*Wallet* §4).

Displayed to the tenant as documents remaining today, never as dollars — the
notional price is internal.

| Plan | Daily allowance | Parts/day at $0.05 notional |
|---|---|---|
| Base | $5.00 | 100 |
| Small Business | $15.00 | 300 |
| Enterprise | negotiated | — |

**The $0.05 notional is a placeholder.** It must be set from measured token cost
per classification during build, not assumed. The allowance figures move with it.

### 8.2 Publish-time ceilings

$0.25 files one part, which then runs **every schema mapped to its document
type**. $1.00 buys one memo, whose every section is a narrative call. Inference
scales with fan-out; revenue does not.

**Settled — two ceilings enforced at publish validation, carried as columns on
the plan row.** Checked once at configuration rather than repeatedly at runtime,
and presented in the editors as a plan feature rather than a runtime surprise.

| Plan | Schemas per document type | Sections per template |
|---|---|---|
| Base | 3 | 12 |
| Small Business | 5 | 25 |
| Enterprise | 10 (default, negotiable) | 50 (default, negotiable) |

Rationale: a document type genuinely feeding more than two or three schemas is
usually a configuration mistake — most often the overlap case in *Config
Editors* §4. A due diligence memo of more than twelve sections is unusual at the
Base tier and normal at the top of Small Business. The ceilings are set to bind
on outliers, not on ordinary use.

**On downgrade**, a configuration exceeding the new plan's ceilings cannot
publish until trimmed. The currently published revision keeps running
unchanged — non-destructive, consistent with the rest of the design. The plan
change screen states which objects exceed the new ceilings before confirming.

---

## 9. Open

1. **Handler list** (§6) — held for build phase, per prior decision.
2. **Classification notional price** (§8.1) — placeholder $0.05; must be set
   from measured token cost during build.
3. **Text-layer floor** (§4) — tuning number, set during build against test
   files. Carried from *Wallet* §10.
4. **Staging retention** (§4) — how long unfiled parts survive before sweep.

**Settled:** classification allowance (§8.1); publish-time fan-out ceilings
(§8.2).

All four remaining items are build-phase measurements, not design decisions.
This component is closed and buildable.
