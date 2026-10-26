# UNDO-01 and graphics-insert — build plan

| | |
|---|---|
| Agreed | 26 October 2026, product owner |
| Designs | `docs/specs/undo_01_design_2026-10-14.md`, `docs/ARQEDIA_graphics-insert-questions.md` |
| Order | UNDO-01 built and merged first; then the five graphics branches, in order |

## Live state, 26 October 2026 (main `7b5e868`)

- **UNDO-01 not built.** `Memo.tsx` calls `setDraft` from seven places (load,
  `discard`, `accept`, `putBack`, three `onChange` wirings); no recording
  function, no history, no Undo control. The working copy is `version: 1`.
  `MemoReader.tsx` mutates through `replace`, `addParagraph`, `splitBlock`,
  `removeBlock` and `finish`, each ending in `onChange(markdown)`.
- **Graphics not built.** `memodoc.ts` has seven block kinds, no image.
  Browser uploads go to `docs` and `review` only (`storage.tf`,
  `local.upload_buckets`). The render parser has no image case.
- **Changed since 19 Oct: #389.** `get_memo` adds Number, Version and
  Workspace rows to `memo.markdown`; `revise_memo` strips them. Discard
  resets to `memo.markdown`, so they are inside Discard's step.

## UNDO-01 — `feature/undo-01`

Decisions as recorded: stored history with the working copy, survives a
reload; the last 10 edits; a step holds the changed blocks only; Discard
undoable, its confirm kept; one edit is everything typed into one block
between opening and closing it; no redo; button only, no Ctrl+Z binding;
Save ends the history.

- **`ui/src/undo.ts`, new.** Pure functions: diff two block-source lists
  into a step (common head and tail), undo a step against the current text
  with the `after` check, trim history to 10 and under the 4 MiB cap.
- **`Memo.tsx`.** `change(act, next)` replaces the six mutating `setDraft`
  calls (load stays direct); `accept`, `putBack`, `discard` go through it
  carrying `accepted_by`, `pending`, `prompts` as they were. Working copy
  `version: 2` with `history`; `version: 1` loads with none. A copy after
  Discard holds the original text and one step. Undo control beside Save,
  titled with the act it undoes, disabled with "Finish editing first" while
  a block is open and "Wait for the rewrite to finish" while one is out.
- **`MemoReader.tsx`.** `onChange(markdown, act)` names the act; mutation
  logic and commit timing (#126, #128) unchanged. **Proposed in this plan,
  not in the design:** `onOpenChange(id | null)`, so the screen can make
  one block's typing one edit and refuse undo while a block is open.
- **No** migration, Terraform, API or layer change. `web/` built in the PR.
- **Verified by** Vitest on `undo.ts`, then walked on the real domain: each
  of the nine acts undone; after a reload; after Discard; refused with a
  block open and with a rewrite out; an undone accept reappearing for
  accept; a memo near the cap keeping its text; undoing a Discard does not
  bring back the #389 Number/Version/Workspace rows as a change.

## Graphics-insert — after UNDO-01 is merged

Decided 26 Oct 2026:

- **Syntax.** `![alt](image:<key>)` on its own line.
- **Size.** A signed POST upload with a `content-length-range` condition,
  so S3 refuses an oversized file at upload. Mechanics confirmed against
  AWS's documentation before building.
- **Sweep.** Daily, with a 24-hour grace period for an uploaded file not
  yet referenced.

Branches, in order:

1. **`feature/graphics-storage`** — `curated` allowed for browser upload
   (CORS, POST); a signed-POST route to one key under
   `tenants/{t}/working/images/memos/{memo}/`, PNG/JPEG, 10 MB, 50 MB per
   memo; a signed read route; images copied into the revision at save
   (N2); API IAM on the prefix. Verified by a Python test of the save copy
   and a reviewed `terraform plan`.
2. **`feature/graphics-block`** — `image`, an eighth kind in `memodoc.ts`,
   lossless; `<img>` in `MemoReader` via the read route; drag-drop and
   paste (the image wins a mixed paste); insert is the tenth undoable act,
   step `"image"`. Verified by parse/serialize tests and walked: drag,
   paste, mixed paste, oversize, wrong type, undo an insert, reload.
3. **`feature/graphics-pdf`** — an image case in `lambda/render/app.py`
   through `ImageReader`; render IAM read on the prefix. Verified by a
   downloaded PDF and a shared copy, opened and looked at.
4. **`feature/graphics-sweep`** — EventBridge daily rule invoking a Lambda,
   the shape of `reconcile.tf`; deletes working-prefix files older than 24
   hours that no working copy's text or history references. Image files
   added to the account-deletion procedure. Verified by querying S3 after
   a run on a test memo.
5. **`docs/graphics-citation-exception`** — the image exception written
   next to the citation rule.
