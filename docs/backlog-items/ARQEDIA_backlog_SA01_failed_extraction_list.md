# ARQEDIA — Backlog Item

## SA-01 · Set aside is two different acts wearing one flag

| | |
|---|---|
| Status | **Parked by decision, 21 September 2026.** Approved in shape, not built |
| Priority | After the failed-extraction work settles |
| Type | Schema, API, review screen |
| Raised | 21 September 2026 |

---

### Where it stands

`document.active` carries one bit and two meanings, and `deactivated_by` /
`deactivated_at` record who flipped it without recording which of the two they
meant (`db/migrations/006_authorship_and_revisions.sql:21-23`).

The two acts are:

- **Deselected for the memorandum.** "This document is real and readable, and
  I do not want the next memorandum drawing on it." An editorial choice, made
  and unmade freely, and the tick in the filed table is exactly right for it.
- **Set aside.** "Nothing further will happen to this on its own." A read that
  stalled, or — since migration 029 — an extraction that failed. It is not an
  editorial choice; it is an acknowledgement, and it should not read as one.

Both go through `POST /documents/{document_id}/active`
(`lambda/api/app.py:2117`, handler at `:778`), and both land as `active = 0`.
So a document set aside because its extraction failed is indistinguishable, in
the schema and on the screen, from one a person deliberately left out of the
memorandum. An administrator reviewing what a tenant excluded cannot tell the
difference, and neither can a report.

The failed rows are real and present: 51 in COCOA-EMPIRE alone now render
"extraction failed" (`ui/src/Review.tsx:961`), each with the values it managed
to write before it stopped.

---

### Decided, 21 September 2026 — parked, not built

**1. Set aside is kept apart from deselected-for-memo.** Two acts, two
records. `active` keeps its one meaning — whether the next memorandum draws on
this document — and set-aside becomes its own thing rather than a second
tenant of the same flag.

**2. PROPOSED, not in the schema:** two columns on `document`.

```
set_aside_by    -- who acknowledged it
set_aside_at    -- when
```

Neither exists today; confirmed against `information_schema.COLUMNS` on dev,
which returns nothing for `set_aside%`. They are proposed here and are **not**
a rename of `deactivated_by` / `deactivated_at`, which keep their own meaning
for the editorial act. Whether set-aside also implies `active = 0`, and
whether the two states can be held at once, is part of what is parked.

**3. PROPOSED, not built:** a route of its own.

```
POST /documents/{document_id}/set-aside
```

Separate from `POST /documents/{document_id}/active` rather than a flag on it,
for the same reason migration 025 gave for keeping `refusal_code` apart from
`type_reason`: one endpoint cannot carry two meanings without a caller
eventually sending the wrong one. Role treatment follows the existing path —
no guard, a Member's act — unless a decision says otherwise.

**4. Failed extractions move behind a link.** They do not belong in the main
filed list, where they read as ordinary documents that happen to have failed.
They sit behind:

> **Review failed extractions?**

So the filed list is what the engagement holds, and the failures are a thing a
person goes and looks at deliberately. The x added on 21 September stays where
it is until this lands.

---

### What this does not change

`showInactive` keeps its default of `true` (`ui/src/Review.tsx:98`) and its
label "Show set aside" (`:875`). Moving the failures behind a link is not the
same as hiding set-aside rows, and the two must not be confused when this is
built.

Nothing already recorded is rewritten. The 102 rows migration 029 marked keep
their `extraction_error`, their null `extracted_at` and the values they wrote
before stopping, whatever is decided here.

---

### Why it is parked

The failed-extraction work went in on 21 September and has not been seen by
anybody working an engagement. What a person actually does with 51 failed rows
— acknowledge them one at a time, in bulk, or not at all — decides the shape of
the route and of the screen, and guessing it now would build the wrong thing
twice.

---

### Not in scope

Anything retrospective. No existing `active = 0` row is to be reclassified as
set-aside: nothing recorded says which of the two acts it was, and inventing
an answer is worse than the ambiguity.
