# ARQEDIA — Backlog Item

## UNDO-01 · Nothing can be undone

| | |
|---|---|
| Status | Proposed. Not designed. Decisions pending |
| Priority | High. Work can be destroyed with no way back |
| Type | Front end, with a stored-shape change if undo is to survive a reload |
| Raised | 12 September 2026 |
| Depends on | The working copy (#121) and in-place editing (#125–#128) |

---

### The need

A person revising a memorandum makes a long series of small changes: a
sentence here, a table row there, a rewrite accepted, a paragraph deleted.
Every one of them is final the moment it is made. There is no step back.

This matters more here than in most software because of how the screen works.
Nothing has a Save button any more. An edit commits as it is typed - a pause
of four hundred milliseconds, a click elsewhere, closing the block - and the
working copy is written to the server a second and a half later. That was a
deliberate fix: edits were being lost when they only committed on close
(#126). The cost of making them reliable is that they are also immediate, and
immediate with no undo means a mistake is permanent as soon as it is made.

The browser's own undo does not fill the gap. Ctrl+Z works inside one open
block, on the text typed since it opened, and nothing else. It cannot undo:

- deleting a block, which asks first but is final on Yes
- an edit to a block that has since been closed
- accepting a rewrite, or putting back the original
- adding or removing a table row
- adding a paragraph
- Discard changes, which throws away every unsaved change at once

The last is the worst case: one click, one confirmation, and an hour of
revision is gone. The confirmation names what will be lost, but a person who
clicks through it has no recourse.

What limits the damage today is that the memo itself is never overwritten. A
revision is a new memo and the original is untouched, so the worst case is
losing unsaved work rather than corrupting a record. That is the difference
between an annoyance and a disaster, and it should stay true whatever undo
does.

### What it has to cover

Every act that changes the working copy, in one list - these are the
mutation points in `MemoReader.tsx` and `Memo.tsx`:

| Act | Where |
|---|---|
| Edit a block | `replace` |
| Add a paragraph | `addParagraph` |
| Break a block at the caret | `splitBlock` |
| Delete a block | `removeBlock` |
| Drop a block emptied to nothing | `finish` |
| Add or remove a table row | `replace` |
| Accept a rewrite | `accept` |
| Put back the original | `putBack` |
| Discard changes | `discard` |

Anything not on that list is not undoable and should be seen not to be.

### Shape, unproposed

Two questions decide the design, and both are for the product owner rather
than for the build.

**1. How far back does it go?** Three answers, in increasing cost:

- *The last act only.* A single Undo, offered where the act happened. Cheap,
  covers the misclick, does not cover a wrong turn ten minutes ago.
- *The session.* A stack held in the page. Covers a working session; empty
  after a reload or a move to another memo.
- *The working copy.* A stack kept on the server beside the text, so undo
  survives a reload, a closed tab and another machine. This is the only one
  that matches how the working copy already behaves, and the only one that
  changes what is stored.

**2. Is Discard undoable?** It is the most destructive act and the easiest to
do by accident. Making it undoable means keeping the discarded copy rather
than clearing it, which is a stored-shape question, not a screen one.

### Severity of the change

**Front end: moderate, and structural rather than cosmetic.** The screen
currently holds the memo text as one string in `draft` and every act rewrites
it. Undo needs each act to record what the text was before it, which means
routing every mutation through one place rather than each calling
`onChange` directly. That is a refactor of the nine functions above, not an
addition beside them. It is well bounded - they are all in two files - but it
touches the code paths that were the subject of two bug fixes this week
(#126, #128), and those fixes are about timing rather than logic, so the
refactor must not disturb the order in which commits land.

**Back end: none, unless undo is to survive a reload.** The working copy is an
opaque JSON object the API stores and returns without interpreting, so the
screen can add a history to it without any change to `app.py`, to a route, or
to the database. The API's only constraint is the 4 MiB limit on one copy.

**Stored shape: the real risk, and the reason this is not a small job.** A
memorandum is a hundred thousand characters. Keeping twenty previous versions
of it as whole strings is two million characters, which is inside the 4 MiB
limit but not comfortably, and a longer memo would pass it. The options are to
cap the history at a handful of steps, to keep changed blocks rather than
whole documents, or to keep the history in the page and accept that it is lost
on reload. Choosing wrongly here means either a limit that is hit in real use
or a stored copy that fails to save - and a copy that fails to save is the
failure mode the working copy exists to prevent.

### Risks

**To the person's work, if it is built carelessly.** An undo that restores
stale text over a newer edit is worse than no undo. The dangerous case is
specific: a rewrite is still running when undo is pressed, it finishes
afterwards, and it is accepted into a document that has moved underneath it.
Undo must either refuse while anything is out or be defined against what is
there at the time.

**To the citation record.** `revise` refuses a save whose citations name
documents that are not sources of this memo. Text restored by undo has to be
text this screen produced, never text reconstructed from a parse, or a save
can be refused with no way for the person to see why.

**To the caret.** Every act commits as it is typed. An undo that replaces the
document while a block is open would re-render that block underneath the
caret, which is exactly the failure the editor was built to avoid: the content
is written into the element once and read out afterwards. Undo must close the
open block first, or be refused while one is open.

**To the working copy's reliability.** The copy is written after a pause and
on leaving, and a failure to write it is reported to the person. A history
stored beside the text makes every write larger and therefore slower and more
likely to fail. If the history is stored, the text must be written even when
the history cannot be.

**To the screen, mildly.** Undo needs somewhere to live - the head beside
Save, most likely, where it is visible and away from the block controls. The
head is already carrying Go, Save, Rewrite, Close and the PDF, and is pinned
under the site header, so this is a crowding question rather than a design
one.

### What would not change

- The memo itself is never overwritten. Undo operates on unsaved work only,
  and a saved revision is undone by opening the previous memo, which is
  already possible and always has been.
- The rewrite record. A `memo_rewrite` row is written when a rewrite is
  started and is never removed; undoing an acceptance means the revision does
  not carry it, not that it never happened.

### Needed before any of it is designed

- How far back it goes, of the three above.
- Whether Discard is undoable.
- Whether undo survives a reload, which is the same question as whether the
  history is stored.
