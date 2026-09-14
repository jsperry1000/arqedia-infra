# ARQEDIA — Handoff, 12 September 2026

Everything below is merged on `main` and live in dev. Written at the end of a
session that ran from section rewrite through to the PDF's citations. The next
session is UI/UX fine-tuning.

---

## What shipped

| PR | |
|---|---|
| #118 | `012_memo_rewrite.sql`; composition's rewrite entry point |
| #119 | API routes for rewrites; `revise` records accepted rewrites |
| #120 | Rewrite mode on the memo screen |
| #121 | The working copy: unsaved work kept on the server |
| #122, #123 | The memo head pinned under the site header |
| #124 | The memo read as a document: real tables, citations put away |
| #125 | Editing in the document, a block at a time |
| #126 | An edit taken as it is typed, not when the block closes |
| #127 | Delete a block; drop one emptied to nothing |
| #128 | Add a paragraph; break a block at the caret |
| #129 | Put a row in mid-table, and take one out |
| #130 | One mark per run of citations in the PDF |

### 1 · Section rewrite

A person writes a prompt under any `##` section and presses Go. The model
rewrites each prompted section; the result appears beside what it would
replace, to accept or discard; accepted sections are saved as a new revision
recording which sections the model wrote and at whose prompt.

Rules the build holds to, for whoever changes it:

- The model sees only the section's current text and the prompt. It cannot
  add a fact.
- Citations are masked and restored with composition's own functions, and
  dropped ones are counted on the row.
- The heading is removed before the call and restored after; the model never
  writes it.
- A section over 40,000 characters, or a reply that used all 4,096 output
  tokens, is refused rather than saved incomplete.
- A failure is written to the row and never retried by Lambda, so no model
  call is spent twice.
- Nothing about a memo changes until `revise` is called with the accepted
  rewrite ids. A rewrite already accepted into one revision is never moved.

Free by decision. Every row carries `tokens_in`, `tokens_out` and `model_id`,
including discarded and failed rewrites, so the cost per tenant is recorded.

Verified live: memo 95 is revision 2 of memo 94, carrying rewrites 3 and 4.

### 2 · The working copy

Prompts typed, rewrites accepted and hand edits are kept per memo per person,
in the curated bucket under `tenants/<t>/working/memos/<memo>/`, keyed by a
hash of the person's address. Kept after a pause in typing and on leaving;
reopened where it was left; cleared when a revision is saved. Two routes,
`GET` and `PUT /memos/{memo_id}/working`. No schema change: the API stores the
object opaque and the screen owns its shape.

### 3 · The memo as a document

`memodoc.ts` parses the stored markdown into blocks and writes them back. Two
rules hold it together: every block keeps the source it was parsed from, so a
block nobody edits is written back character for character; and nothing is
inferred. All 745 lines of memo 96 round-trip byte for byte.

`react-markdown` is gone from the memo screen, and with it the underscore
escaping, the `[object Object]` guard and the one-line table repair. The
repair moved into the parser, where it no longer alters the stored text.

All 23 tables in memo 96 draw as tables. Citations are put away by default:
each run collapses to one mark carrying its count, with a Sources control on
every block.

### 4 · Editing in the document

Every block carries an Edit control and opens where it sits. Citations are
locked marks inside the editor. Bold and italic only; pasted content
contributes text and nothing else. Tables are edited cell by cell, with
per-row controls to insert above and delete. A thin "+" between blocks starts
a paragraph; Enter breaks a block at the caret. Delete removes a block and
names how many references go with it; a block emptied to nothing is dropped
when closed.

There is no markdown on screen anywhere. The second pane, the textarea and
the scroll sync are gone.

### 5 · The PDF

A run of citations takes one superscript number rather than one each, and the
References entry lists every source behind that statement. On memo 96, 847
citations become 421 marks; References grows from 146 entries to 163.

---

## Two bugs worth remembering

**Edits that sometimes did not take (#126).** The block was read out only when
it closed, and that read hung off React's unmount, which runs after the
element has left the page. Most of the time it worked. Now the block is read
on every change, on blur, on Enter and on close. The same class of timing bug
came back twice more: the empty-block check had to wait for the render after
Done, and rows had to be keyed by position *and* count or an inserted row
shifted the table while the text stayed put.

**Parsing on every keystroke.** The document was re-parsed on each key, 745
lines and 119,000 characters. Memoised on the markdown.

---

## Open, in the order I would take them

1. **UI/UX fine-tuning.** The next session. Known from screenshots: Done sits
   below the block rather than where Edit was, and the rule under a paragraph
   crowds the Sources control.
2. **UNDO-01.** Nothing can be undone, and everything commits as it is typed.
   Discard changes destroys an hour of work on one confirmation.
3. **Save does not warn about citations an edit removed.** Delete asks; typing
   over a citation mark does not. This was point 4 of the editing design and
   is the one part not built.
4. **RW-01's follow-ups**, principally: a Go in progress is not shown again
   after a reload, and the screen gives up after five minutes where the
   function runs for ten.
5. **HONE-01.** Keep a rewrite prompt into the section's prompt, so the next
   memo starts where this one ended.
6. **UI-01, UI-02, UI-03, CF-01, BR-01, AUD01** and the rest of the standing
   backlog.

## Backlog documents written this session

`UNDO-01`, `HONE-01` and `RW-01` are current. `UI-08` and `UI-09` were
written earlier in the session and are now **stale**: UI-08 describes tables
rendering as pipes, which #124 fixed, and UI-09 describes a side-by-side
rich-text editor, which #125 replaced with editing in the document. Neither
should be committed as written.

## Left on record

- `memo_rewrite` rows 1 and 2 on tenant 2 are test data, marked
  `prompted_by` = `stage-2-test` and `stage-3-test`. Row 1 names memo 0, which
  does not exist. Both unaccepted and harmless.
- `docs/HANDOFF/ARQEDIA_HANDOFF_2026-09-09.md` is still untracked.

## Not verified

- The PDF after #130. The change is tested against the citation machinery but
  nobody has opened the rendered file and looked at the opening sentence or
  its References entry.
- Typing behaviour in a browser beyond the one flaky case that was reported
  and fixed.
