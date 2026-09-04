# CFG-04 — Build outline, corrected against the code

Supersedes the uncorrected outline. Phase 0 is done: `lambda/shared/config.py`,
`lambda/shared/editor.py` and `lambda/api/app.py` read in full.

---

## What phase 0 found

**Everything CFG-04 needs to write already exists.** No new writer, no new
table, no migration. Accepting a proposal is a sequence of calls that are
already there:

| To create | Call |
|---|---|
| A group | `editor.save_category` |
| A document type | `editor.save_document_type` |
| A field | `editor.save_field` |
| Where a field is found | `editor.set_field_documents` |
| A memorandum | `editor.save_template` |
| A section | `editor.save_section` |
| What a section renders | `editor.set_section_fields` |

**Keys mint themselves.** `_slug` builds a key from the label, once, and it
never follows the label afterwards. CFG-04 sends labels and lets the editor
mint. It must not invent keys.

**The schema builds itself.** A field's schema is derived from the set of
document types it is found in — `set_field_documents` finds or creates it. So
proposing "this fact is looked for in these documents" is the whole job; the
grouping underneath is not CFG-04's business.

**The order of the accept is fixed, and not by preference.**
`set_section_fields` refuses a field that does not exist yet — deliberately,
because a section bound to a missing field reports facts as absent when they
were extracted. So:

1. categories
2. document types
3. fields
4. `set_field_documents` for each field
5. the memorandum
6. sections
7. `set_section_fields` for each section

A field created at step 3 sits in schema `unrouted` until step 4. That is a
legitimate half-configured state, not an error.

**A draft has to be open.** Every editor call raises "no draft is open" against
anything but revision 0. CFG-04 either opens one first or refuses.

**It is an admin act.** Every config route calls `_require_admin`. This one too.

**Correction to something I said earlier in the session.** I said
`context_sections` had to go in by SQL. That is wrong: `save_section` accepts
`context_sections` in its body and writes it. CFG-02 is a front-end gap only.
The API has been able to do it all along.

---

## The one thing that does not exist

**A way to put a file in front of us that is not a document.**

`POST /uploads` signs a link into the docs bucket under
`tenants/{id}/docs/{engagement}/`. Anything landing there is picked up,
classified, and filed. That is exactly what must not happen to a sample.

So CFG-04 needs its own upload path to somewhere nothing watches, and the file
is deleted once the proposal is built. This is the only new plumbing in the
feature.

---

## Phase 1 · The reader

A new route — `POST /config/draft/propose` — that takes the sample and returns,
as data and nothing more:

- sections: heading and order
- per section, the facts it appears to report
- for each fact, whether an existing field looks like the same thing
- document types the memorandum names or implies
- a suggested group for each new type
- for each fact, the document types it should be sought in

Nothing is written. The sample is deleted after the read. Not filed, not
classified, not extracted from, not cited, not charged.

Every section is proposed as fact-rendering — `kind` defaults to `extract`,
which is already what `save_section` does. Guessing which sections the model
should write waits for CFG-02.

**Verify:** run it against the Manty credit memorandum. Thirteen sections, and
the facts under Borrower Overview and Financial Analysis should match fields
the tenant already holds. If it cannot find those, stop — the screens after it
are worthless.

---

## Phase 2 · The proposal screen

A third way to start on Configure. Route one — use one of ours — stays hidden
until the starter packs exist.

Shows what phase 1 returned, in the existing dropdowns and tick lists. He can
change anything. Nothing reaches the draft.

**Verify:** change everything on it, reload, confirm the draft is untouched.

---

## Phase 3 · The acknowledgement step

**Every new field** — he acknowledges name, what it is, and shape. We write the
description; he confirms it says what he means.

**Every new document type** — the same, for its description.
`save_document_type` already records why: the classifier reads it, and without
it the same document was classified differently as a PDF and as a Word file.

**Where his wording matches a field he holds** — shown as new, with our
suggestion beside it. He picks. We never make the match.

Acknowledge, then accept.

**Verify:** nothing accepts unacknowledged; declining a match creates the new
field rather than binding the old one.

---

## Phase 4 · Accept

Runs the seven steps above through the existing editor calls. Additive — it
creates, it does not remove.

**Verify:** accept, read the draft, publish, generate, and confirm the sections
appear in his order with the right facts under them.

---

## Phase 5 · Say when it matters

One line on the screen: do this before uploading. A field created afterwards is
empty on everything already filed, and the only remedy is filing again at
$0.25 a document.

---

## Still open

- **b.** Whether we guess which sections the model composes. Needs CFG-02's
  screen, not its API.
- **c.** What formats he can drop. The sample is a PDF with selectable text.
