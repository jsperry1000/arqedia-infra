# ARQEDIA — Handoff, 9 September 2026

Written at the end of a long session. Supersedes nothing; the 7 September
handoff still holds for anything not mentioned here.

---

## Read this first

**Confirm the live state before trusting any of the below.** Several branches
were merged during the session and at least one delivery was not saved. Start
with:

```powershell
git checkout main; git pull --prune; git branch -a; git status -sb
q "SELECT tenant_id, name, active_revision FROM tenant ORDER BY tenant_id"
```

---

## Delivered but NOT saved or pushed

**`ui/src/Review.tsx`** — the filed document list grouped by document type,
one type open at a time with a count on each heading, and the values count made
a link into what was read. `tsc` clean, delivered to outputs, never saved. If
the next session wants it, ask for the current `Review.tsx` and re-apply rather
than using the delivered copy, which will be stale.

**Four backlog documents were written and never committed:**

| | |
|---|---|
| `ARQEDIA_config_consistency_review.md` | the ten findings from reading the config path end to end |
| `ARQEDIA_backlog_BR01_fourth_brand_colour.md` | the palette needs a light, the pill borrows the mid |
| `ARQEDIA_backlog_UNI01_shared_screens_on_hold.md` | why the two config screens cannot be further shared |
| `ARQEDIA_backlog_AUD01_fact_to_files.md` | walking from a fact to the files it was read from |

`OCR-01` and the 7 September handoff **were** committed.

---

## What was built this session

**Configuration screen, substantially rebuilt.**

- Parts renamed: Report sections, Facts included in sections, The document
  types.
- All three fact lists group by the group the documents sit in. A fact held by
  two groups appears under both; one in no document keeps a place of its own.
- Facts included in sections and The document types collapse, one group open at
  a time, each shut heading carrying a count. **A section's own field list does
  not collapse** - that is the working list and needs the whole vocabulary
  visible.
- Search on a section's field list and on the document types.
- A memorandum can be duplicated with its sections and bindings.
- Sections and columns can be reordered by typing a position.
- The section form and document form are drawers: close on a click outside,
  Escape or Cancel, each asking before an unsaved change is lost.
- A field card shows the documents it is found in; the count opens that list
  above the card, and closing returns to the card.

**Extraction.** A table's citations are now asked for per ROW rather than per
table. Measured before and after: table columns without a citation fell from
roughly a quarter to 1.3%.

**OCR-01 closed.** A file holding a scanned page no longer splits; the
collector uses the same envelope name as everything else; it has ListBucket so
a missing object says so; a stalled document can be set aside from the screen.

**The save-what-was-sent class closed.** Every upsert in `editor.py` was read;
four kept a `sort_order` the caller had not sent. All now keep what the row had.

---

## Two working practices that were earned the hard way

**Never write CSS from reasoning.** Four attempts at one grouped layout, each
worse than the last, until the user supplied the rule. The failures were: a
wrapping grid holes; a column flow splits a group; flex without a floor
squeezes; and a scroll on the inner element is confined to that element. What
finally worked was letting the label set the column - `max-content`, `nowrap` -
and having the OUTER box scroll. **Render it and look at it, or ask.**

**Drawer stacking follows document order.** There are no z-indexes. A drawer
opened from another must render AFTER it in the component, and must not sit
inside a collapsible part or it renders nothing when that part is shut. Two
separate faults this session came from exactly that.

---

## Next, in order

1. **Save the four backlog documents** and the Review.tsx work, or discard them
   deliberately.
2. **Review screen, items 3 to 5** - Ready to file as a drawer; search and
   counts on the memoranda list; a path from a document's values into the
   configuration, which needs the AUD-01 decision first.
3. **TPL-01, the starter packs.** The tooling is now there: duplicate a
   memorandum, reorder its sections, group the facts, read any fact without
   losing your place. What remains is credit judgement about which sections a
   Credit pack and a Deal Sheet carry - the user's work, not engineering.
4. **UNI-01** - the saving-model decision, which unblocks sharing the last two
   components between the two configuration screens.
5. **CF-01, TPL-01, UI-03, BR-01** and the rest of the standing backlog.

---

## Test accounts

`https://d2pco7fhb5wnod.cloudfront.net`

`joeschmoe1000@gmail.com` / `Arqedia-Test-2026!` — tenant 2, TESTCO B, base
plan, revision 32 at last check.

`sperry@vmac.com` — tenant 1, TESTCO A, business plan, revision 36. Password
not known to this session.

`q.ps1` is in the repository root; a new terminal needs
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; . .\q.ps1`.
