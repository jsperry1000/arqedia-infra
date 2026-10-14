# ARQEDIA — Free-form graphics in memos: questions for CC

## Status
Undesigned. Nothing in this area is built. This is a question set, not a spec — do not build from it.

## Requirement added 8 Oct 2026
UNDO-01 (backlog, status: proposed, not designed — see `ARQEDIA_backlog_UNDO01_undo_in_the_memo.md`) is now a requirement of this work, not a parallel item to work around. Any action taken is a mutation point UNDO-01 already enumerates: edit a block, add a paragraph, split a block at the caret, delete a block, accept/put-back a rewrite, discard changes. A graphic insert is a new mutation of the same kind and must be added to that list, not treated as exempt from it.

Three questions in UNDO-01 are unanswered and block design of both items together:
1. How far back undo goes — last act only, session stack, or working-copy-persisted stack.
2. Whether Discard is undoable.
3. Whether undo survives a reload (same question as #2 — whether history is stored).

Do not design the image block's mutation handling separately from this. Question 3 in the list below (block model / mutation list) is answered by whatever UNDO-01 decides, not independently of it.

## Context — corrected 8 Oct 2026 by CC, from code
Two factual errors in the original context below, left in place rather than deleted:
- Memos are **not** rendered with react-markdown. It's listed in `ui/package.json` but nothing in `ui/src` imports it. Every view goes through `MemoDocument`, using the project's own parser, `ui/src/memodoc.ts`.
- The editor is **not** single-block-kind. `memodoc.ts:40-57` defines seven kinds already: heading, para, quote, rule, list, table, raw. An image would be the eighth.

Original (superseded) context: Memo editing is currently text-only: one working-copy JSON (4 MiB cap), text blocks mutated via `replace` / `addParagraph` / `splitBlock` / `removeBlock` in `MemoReader.tsx` / `Memo.tsx`, rendered through `markdownOf` into the reader, editor preview, and rewrite screen. A separate PDF render path exists and has not been checked against non-text content (per UI-08). UNDO-01 is in parallel, proposed but not built, touching the same mutation points.

Request: ability to insert a free-form graphic (image supplied by the person — logo, diagram, photo) into a memo, possibly later extended to system-generated graphics (charts/sketches). Free-form first; both forms may eventually be wanted.

## Questions

1. **Storage.** The working copy can't hold an embedded image inline (size cap). Does a new asset store get added alongside the existing docs/review/curated buckets, with the working copy holding a reference only? Any constraint on where that store can live?

2. **Entry point.** Drag-drop, paste, or an explicit insert control — one to start, or more than one from day one?

3. **Block model.** The editor has one content type (text block). An image is a new block kind. Does it go into the editor's existing mutation list now, or is it deliberately built after UNDO-01 lands, to avoid two structural changes landing on the same code at once?

4. **Render parity.** `Memo.tsx` renders markdown through `react-markdown`; confirm whether `![]()` image syntax renders as-is or needs a plugin/style pass. The PDF path is separate and untested for any non-text content — does it need its own confirmation pass, or is PDF out of scope for a first build?

5. **Provenance.** Every other value in a memo carries a citation back to a source document (`revise` refuses saves citing documents outside the memo's sources). A free-form image has no source document and no citation. Confirm this is acceptable as an explicit exception, rather than something that should be reconciled with the citation rule.

6. **Scope boundary.** Confirm free-form only for this pass — no system-generated chart/sketch-to-image step included yet, even though it may be wanted later. If both are wanted together, say so now; it changes the shape of #1 and #3.

## CC's answers, 8 Oct 2026 (from code — no plan proposed, no code changed)

**1. Storage.** Working copy lives in the curated bucket under `tenants/{t}/working/memos/…`, capped at 4 MiB (`lambda/api/app.py:1966-1998`). Only `docs` and `review` accept browser uploads (`storage.tf:125`); `docs` must not hold images — a watcher classifies, files and charges anything landed there. A `brand` bucket already exists (`render.tf:13`) and the PDF renderer already reads the tenant logo from it via ReportLab's `ImageReader` (`lambda/render/app.py:974`). A new store would follow the same pattern: shared KMS key, tenant-prefixed keys, no public access, short-lived PUT-only upload links. Working copy holds a reference only. **Open: new bucket vs. a prefix inside curated — product owner's call, and it's a Terraform change.**

**2. Entry point.** **Open — product owner's call.** CC's recommendation: start with one explicit insert control; drag-drop and paste each carry their own handling problems.

**3. Block model.** **Open — product owner's call.** UNDO-01 is still backlog, three questions open (`docs/ARQEDIA_next_steps.md:74`). Both pieces touch the same mutation code. CC's recommendation: build images after UNDO-01 so the two structural changes don't collide.

**4. Rendering.**
- Browser: `![]()` will **not** render as an image — the parser has no image block or inline; expected result is a plain paragraph with the markdown visible as text. Not yet rendered to confirm.
- PDF: `lambda/render/app.py` has its own line parser with no image case either, but the library already draws images (the logo), so it's a parser addition, not a capability gap. Same file where UI-08 (tables unchecked on PDF path) is still open.
- Shared copies are stamped from the PDF output — leaving PDF out of a first build means shared memos lose the image.

**5. Provenance.** **Open — product owner's call, not technical.** One fact: the source-document check on save looks at citations only; an image with no citation won't trip it. An exception would be a new rule and should be written down next to the citation rule, not left implicit.

**6. Scope.** **Open — product owner's call.** If generated charts are wanted in the same pass: question 1 becomes "where does generated output live, and is it tied to a revision," and question 3 needs a block that carries data, not an image file.

## Product owner decisions, 8 Oct 2026

1. **Storage: prefix inside `curated`.** No new bucket.
2. **Entry point: drag-drop AND cut/paste, not explicit-control-only.** Overrides CC's recommendation — this is a report-generation tool, both are considered essential. Both carry their own handling problems per CC's note; those problems are now in scope, not deferred.
3. **Build order: UNDO-01 first, images after.** Confirmed as advised.
4. N/A — not a decision, confirmed as a build item regardless of sequencing.
5. **Provenance: exception confirmed.** Write it down next to the citation rule when built.
6. **Scope: free-form only.** No generated charts/sketches in this pass.

## Instruction
All five decisions above are settled. UNDO-01 (its three open questions) is still the blocking item — nothing here starts until that's designed. When UNDO-01 is resolved, build order is: (a) image block + prefix storage, drag-drop and paste entry, (b) browser parser pass, (c) PDF parser pass, (d) citation-exception rule written down. Do not propose an implementation plan or touch code until UNDO-01 is resolved.

## Review by CC, 8 Oct 2026 — corrections and new questions

Nothing above is changed; corrections are recorded here.

### Corrections

- **"Requirement added", item 3** says undo surviving a reload is "the same question as #2". It is not. `ARQEDIA_backlog_UNDO01_undo_in_the_memo.md` (§ Needed before any of it is designed) says it is the same question as whether the history is stored — the third option of item 1 (working-copy-persisted stack). Discard (item 2) is a separate question. UNDO-01 therefore has **two** open decisions, not three.
- **"Requirement added", mutation list** names six acts. UNDO-01 (§ What it has to cover) lists nine: edit a block (`replace`), add a paragraph (`addParagraph`), break a block at the caret (`splitBlock`), delete a block (`removeBlock`), drop a block emptied to nothing (`finish`), add or remove a table row (`replace`), accept a rewrite (`accept`), put back the original (`putBack`), discard changes (`discard`). The list here omits `finish` and table rows, and merges accept and put-back. UNDO-01's list is authoritative; image insert would be a tenth.
- **Decision 1 (prefix inside `curated`) still needs Terraform.** No new bucket, but browser uploads are allowed only to `docs` and `review` (`storage.tf:125-143`, `local.upload_buckets`). An image uploaded from the browser into `curated` needs `curated` added to that CORS configuration, plus a new signed-upload route in the API. Terraform changes are not automated (CLAUDE.md, What is not automated).
- **Decision 4 is unverified.** "`![]()` renders as a plain paragraph" was read from `memodoc.ts`, not observed in a rendered screen. It stands as expected behaviour until rendered.

### New questions

- **N1. Image lifetime.** An image is a file in `curated`, referenced from the working copy. If undo history is stored (UNDO-01 item 1, third option) or Discard is undoable (item 2), a deleted image can be restored, so its file cannot be removed while any working copy or history still references it. When is an image file deleted, and by what? Not covered by questions 1–6.
- **N2. Image in a saved revision.** Once a revision is saved, the memo is never overwritten. Is the image file then held for as long as that revision exists, and is it copied or referenced from the working-copy location?
- **N3. Account deletion.** Image files under the tenant's `curated` prefix must be on the account-deletion list beside `tenant_domain` and `share.purge_tenant` (CLAUDE.md, What is open). Confirm they are in scope for that list.
- **N4. Limits on an image.** Accepted file types and maximum size per image, and whether there is a limit per memo. None is stated.
- **N5. Pasted content that is not an image.** Paste is in scope (decision 2). When the clipboard holds rich text or HTML mixed with an image, what is inserted: the image only, the text only, or both?

## Questions to be answered — consolidated, 8 Oct 2026

Blocking (UNDO-01):
1. How far back undo goes: last act only, session stack, or working-copy-stored stack. (Answers reload survival.)
2. Whether Discard is undoable.

Graphics:
3. N1 — when and by what an image file is deleted.
4. N2 — image handling once a revision is saved.
5. N3 — image files on the account-deletion list.
6. N4 — file types and size limits.
7. N5 — what a mixed paste inserts.

Acknowledgement only:
8. Decision 1 needs a Terraform change (CORS on `curated`, upload route) — confirm accepted.

## Product owner decisions, 9 Oct 2026 — answers to the consolidated list

1. **Undo depth: stored history.** Kept with the working copy; survives a reload.
2. **Discard: undoable.**
3. **N1 — image deletion: garbage-collected on a sweep.**
4. **N2 — saved revision: the image is copied into the revision at save time.**
5. **N3 — account deletion: image files are added to the account-deletion list.**
6. **N4 — types and limits: PDF, JPEG, SVG, PNG. 10 MB per image, 50 MB total per memo.**
7. **N5 — mixed paste: the image wins.**
8. **Terraform (CORS on `curated`, signed-upload route): accepted.**

Recorded on branch `docs/graphics-insert-decisions`, separate from `fix/mobile-ui-batch`. Items 1 and 2 are also recorded in `docs/backlog-items/ARQEDIA_backlog_UNDO01_undo_in_the_memo.md`.

### Open after these decisions — flagged by CC, not decided

- **P1. PDF and SVG on both render paths are unverified.** The PDF renderer draws images through ReportLab's `ImageReader` (`lambda/render/app.py:974`), used today only for the logo. Whether it accepts a PDF or an SVG as an image, or needs another library in the layer, has not been checked against ReportLab's documentation. In the browser, PDF is not an image type an `<img>` element displays. Both must be confirmed before the parser passes (build order b, c).
- **P2. SVG can carry script.** An uploaded SVG shown to another person — a colleague, or a share recipient — is a security question as well as a rendering one. How an SVG is shown or converted is not decided.
- **P3. Stored history against the 4 MiB cap.** UNDO-01 (§ Stored shape) names the cap as the real risk of a stored history: whole-document steps, changed blocks only, or a cap on steps. Not decided. Images are references, so they do not add to it.
- **P4. The sweep.** Garbage collection needs a schedule and a rule for "unreferenced" covering working copies, their stored history and saved revisions. Not designed; a scheduled job is a Terraform change.

## Product owner decisions, 14 Oct 2026 — answers to P1–P4

1. **P1 — PDF/SVG render support: verify.** A task, not a decision. Confirm support on both paths (browser and `lambda/render/app.py`) before building on the assumption.
2. **P2 — SVG script: sanitize on upload.**
3. **P3 — stored undo history: the last 10 edits.**
4. **P4 — the sweep: match the existing sweep pattern.**

### Note on P4 — by CC, from code, 14 Oct 2026

There is no deletion sweep in the repository today, and no S3 lifecycle rule. The only scheduled job is the reconciliation in `reconcile.tf`: an EventBridge rule on `rate(15 minutes)` invoking a Lambda (`reconcile.tf:195-213`). It finds missing work and deletes nothing. "Match the existing sweep pattern" is read as that shape — an EventBridge schedule invoking a Lambda — unless the product owner names another.
