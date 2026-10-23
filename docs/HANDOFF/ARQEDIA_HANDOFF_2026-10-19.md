# ARQEDIA — Handoff, 19–20 Oct 2026

Status snapshot. Nothing here is new work — a consolidation of what's confirmed, shipped, and waiting on a decision. Supersedes the earlier counts in this doc's UX02 section (corrected below).

## UNDO-01 (memo editor undo)
- Design fully recorded: `docs/specs/undo_01_design_2026-10-14.md` (branch `design/undo-01`, merged main via PR #308/#309, docs only).
- **Verified NOT built**: `Memo.tsx`/`MemoReader.tsx` still call `setDraft` directly from 7 locations, no central recording function, no undo button, no history stack.
- What looks like undo today is the browser's native contentEditable Ctrl+Z — block-scoped only, doesn't survive closing a block or reload, doesn't cover memo-level actions. Expected; the design explicitly deferred binding Ctrl+Z for this reason.
- 5 settled decisions (unbuilt): one edit = everything typed into a block between open/close; no redo this pass; Discard keeps its confirm; undo is button-only, no Ctrl+Z binding; saving ends the undo history.
- 3 open design questions, still blocking: how far back undo goes; whether Discard is undoable; whether undo survives reload.
- **Decision still pending from you:** start UNDO-01 now, or keep the UX02 hold. The hold's original reason was avoiding collision with graphics-insert's structural changes to the same mutation code — nothing shipped since (19.2, 20.1, 20.2, pycache hygiene, 22.8) touches that code.

## Graphics-insert (freeform image insertion into memos)
- Fully designed, nothing built. Source of truth: `docs/ARQEDIA_graphics-insert-questions.md` (merged main via PR #305, docs only).
- Settled: storage = prefix inside `curated` (no new bucket); entry point = drag-drop AND cut/paste; build order = after UNDO-01; provenance = explicit citation-exception; scope = freeform only, PNG/JPEG, 10MB/image, 50MB/memo; deletion = sweep; revision lifetime = copied at save; account deletion = added to sweep; mixed paste = image wins.
- Same UNDO-01 decision above governs both.

## UX02 worklist audit — complete, merged (corrected counts)
Full 51-row audit merged to main (#329, docs/ux02-audit-1019). Corrected counts: **16 built, 1 closed, 8 partly built, 24 not built, 2 decision-only → 32 open rows** (not 33 — earlier count was off by one).

- **22.13 correction:** extraction-cache-v2 *did* reach main by mistake (#280) and was reverted (#283) — not "never merged" as first recorded.
- **22.4** moves from partly-built to **built** — migration 038 confirmed applied (live 6 Oct), `monthly_credit_cents` reads correctly.
- **18.13** stays decision-only — migration 033's `sections_per_template` column exists but nothing enforces it.
- **Migrations:** schema_migration on dev lists 001–039 applied, no real gaps (003 has no file and never did — not a gap).

**Sizing (effort/impact grid):** done for 34 rows (the 32 open + 18.13 + 21.6, included since they're decided-but-unbuilt). Full table is in the merged worklist doc on main; several impacts carry CC's own flagged `?` uncertainty rather than a guess. Not duplicated here — see `docs/ARQEDIA_worklist_UX02_2026-09-20.md` on main.

## 22.8 — built, walked, confirmed
"Add a fact" (was "Add a field" in one place) now live in all four locations: Facts table, a section's fact list, the document type's drawer, and the fact detail panel (new — opens a blank unattached fact card, same pattern as the Facts tab). Merged via #335 (docs/ux02-22-8) and #336 (ui/add-a-fact, no-op — superseded by #335's version). **Walked on screen and confirmed working.** Labels intentionally left as "field" elsewhere (Edit field, New field, Delete this field, Filter fields, Save N fields, Field column heading) — scoped to only what was named.

## Housekeeping — done
- 19 stale worktrees removed (branches kept, nothing lost; one long-path folder cleanup needed for `mobile-preview`).
- `arqedia-generate-refund` worktree removed after confirming #336 made no file changes.
- Only `C:\Terraform\arqedia` (main) remains — **3 commits behind GitHub, needs a `git pull`** (left alone due to an untracked xlsx in that folder).
- **Pending:** CC asked to check which old *local* branches (no matching remote) are safe to delete vs. genuinely abandoned — not yet run.

## Still open — the two actual decisions pending from you
1. **UNDO-01 go/no-go** (unblocks graphics-insert too).
2. **20.4** — is the single AWS SDK auto-retry enough, or do you want deliberate retry-with-backoff logic built on purpose?

## Separately open (unprioritized backlog, surfaced not actioned)
- 20.3 (link charge to memo via entry_id column), 20.5 (confirmed built/walked, closeable), 19.3 (preselect plan on ended-trial screen), plus the remaining ~30 not-built/partly-built rows now sized in the worklist doc.

## Recently shipped and verified (context only)
- 19.2 (trial-ending banner), 20.1 (generation/update refund — real web/-build bug found and fixed), 20.2 (composition-crash refund — verified via live timeout test), `__pycache__` Terraform hygiene fix, 22.8 (above).
- Standing rule in `CLAUDE.md`: any branch touching `ui/src` must include its `web/` build in the same PR.
