# ARQEDIA — Where things stand, and what comes next

**7 September 2026.** Written after three days on the configuration path.
Supersedes nothing; the 2 September backlog still holds for items not mentioned
here.

---

## What now works, proved end to end

A client-shaped tenant — TESTCO B, tenant 2 — was taken from an empty
configuration to a delivered memorandum without a hand-written statement at any
point except to clear one fault.

- A client drops a report of their own; it is read, and a configuration is
  proposed from it — sections, the facts each reports, the documents those come
  from, matched against what the tenant already holds.
- Decisions are kept as they are made, so a closed tab or a failed accept costs
  nothing.
- Accepting writes the whole configuration into the draft.
- 57 documents filed and extracted against the published revision.
- A memorandum generated that reads properly, renders its tables, and refuses
  to reconcile sources that disagree.

**That is the product working.** Everything below is refinement or repair.

---

## What was fixed on the way, and why it matters

Four faults reached production during these sessions, all in configuration:

- `save_field` set `group_key` on insert and not on update, so changing a
  field's shape left the registry reading a table as a single value, and
  extraction stopped on every document in the tenant.
- The front end minted its own column keys without the group prefix, so
  columns were read as facts in their own right.
- Accepting a proposal sent duplicate section bindings, failing on the last
  write after everything else had landed.
- Section order was never sent, so every section arrived at zero and the
  memorandum came out unreadable.

**All four would have published silently.** Validation now refuses three of
them outright. That is the single most valuable thing built this week and it is
worth extending rather than treating as done.

---

## Next, in order

### 1 · Prove what was built (half a day)

- Run the new Configure controls on the site: the position box, the field list,
  the used-by column.
- Regenerate a memorandum and confirm the section order holds.
- Nothing below is worth starting until these are known good.

### 2 · Share the two screens (two days, and it gets dearer every week)

`Configure.tsx` and `Propose.tsx` each implement the field card, the document
card, the column editor and both tick lists. They have already diverged once,
and only one of the two copies broke extraction.

- Extract the shared components. No behaviour change.
- Adopt them in `Configure`.
- Only then decide whether the section-first layout replaces the flat tables.

**Do not defer this again.** Every session adds a control to one screen and not
the other.

### 3 · The memorandum's credibility (one day, mostly configuration)

- **SC-02** — a screening asserted that never happened, because
  `f_screening_provider` is sought in correspondence. A fact asserting an act
  was performed belongs only in documents recording the act.
- **MEMO-01** — the lender's own people appearing in the subject's records,
  because `f_persons` reads correspondence.
- **CP-03** — citations without a page, which is also the root of the
  consolidation drops. Measure the share of `locator_kind = 'none'` first.

These three are what a credit officer notices.

### 4 · The starter packs — TPL-01 (a day of credit judgement)

Credit, KYC, lender over one shared vocabulary. The engineering is done and
proved. What is missing is the section list for each, which is your work rather
than engineering. Field identities must be shared across all three or importing
a pack into an existing tenant later matches nothing.

### 5 · Repairs that strand a person

- **OCR-01** (high) — a scanned part of a split file never leaves `reading`,
  and the interface has no way out. Give the collector `s3:ListBucket` whatever
  else is done, so the next occurrence reports what it means.
- **CFG-02** — a composed section cannot be authored: no control for
  `context_sections`. Smaller than the backlog says; the API has always
  accepted it.
- **CFG-03** — the editor accepts field bindings that will never render.

### 6 · Finish and polish

- **CF-01** — twenty financial fields extracted on every filing, bound to
  nothing, read by nobody. Also the three-period question the proposal screen
  surfaced.
- **UI-03** — show which revision a memo was written under. Recorded,
  displayed nowhere, and it is what makes reproducibility visible.
- **BR-01** — a fourth brand colour, so the pill stops borrowing the mid.
- Doubled citations in the memorandum body.

### 7 · Needs schema before it needs code

- Archiving and foldering engagements. There is no `engagement` table;
  the engagement lives only in an S3 key. Design it before building anything.

---

## Two working practices that earned their place

**Never edit a file from a copy in hand.** Two faults this week came from
editing a stale copy. Ask for the file, every time, however recently it was
seen.

**Render or run it before saying it works.** Four rounds went into a table
whose measurement was guessed at from screenshots; one log line found the cause
in seconds. Instrument first, then look.
