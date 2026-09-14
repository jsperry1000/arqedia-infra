# ARQEDIA — Handoff, 13 September 2026

A UI day. Five branches merged, the deploy path established, and the MVP work
list written and settled. Supersedes nothing; the 9 September handoff still
holds for anything not mentioned here.

---

## Read this first

**Confirm the live state before trusting any of the below.**

```powershell
git checkout main; git pull --prune; git branch -vv; git status -sb
terraform plan -detailed-exitcode
```

Two things this session learned the hard way and that are worth keeping:

- **Merges are squashed.** A merged branch shows as unmerged locally, because
  the commit ids do not survive. Prove it with `git diff --stat main <branch>`
  before deleting, then `-D`.
- **Two deploy paths, not one.** The front end: build in `ui/`, whose `outDir`
  is `../web`, commit `web/` with the source, merge to main, and the workflow
  syncs `web/` to S3 and invalidates CloudFront. The Lambdas: `terraform apply`.
  The workflow never touches `lambda/`.

---

## Merged today

| Branch | What |
|---|---|
| `br-01-brand-light` | A fourth tenant colour, `brand_light`. Migration 013, both SELECTs, `_col(r, 6)`, `palette_for` reading a fourth key |
| `ux-routing` | Five URL routes replace the four state flags in `App.tsx`. `react-router-dom`, already in `package.json` |
| `ux-shell` | Left rail, pinned configuration bar, place held in the query string |
| `ux-entry` | One Back pill everywhere, the report chooser, what publishing covers |
| `ux-surfaces` | The fourth swatch in Settings, chooser corrections, section pills, bound facts first, growing prompt box, delete guards |

**Migration 013 was applied to dev only.** Nothing in the repository records
that. It is written down in ENV-01 and nowhere else.

---

## Decisions settled

| | | |
|---|---|---|
| D1 | Routing | A URL per surface. There was no router; one was added first |
| D2 | Rail side | Left |
| D3 | Numbering | One global scheme for every memorandum, a field on the configuration |
| D4 | Publish wording | The screen says publishing applies across all memoranda at once |
| D5 | Derive from an existing report | In the MVP |
| D6 | Brand colours | BR-01 before any pill work |
| D7 | Live updates | Polling |
| — | Light default | `#C7E4F8`, used by both the UI and the PDF where a tenant has set nothing. Where a mid is set and a light is not, the existing mix toward white stands |

---

## Backlog added today

All are in `ARQEDIA_backlog_UX01_mvp_ui_worklist.md` unless noted.

| | | |
|---|---|---|
| UX-15 | Switching memorandum must not lose an open edit | **Closed**, verified |
| UX-16 | One Back pill on every screen | **Merged** on `ux-entry` |
| UX-17 | The report chooser lists memoranda, not proposals | **Closed** |
| UX-18 | Resume a proposal inside the proposer | **Closed**, then superseded by UX-21 |
| UX-19 | An account menu on the tenant name, carrying Sign out | Open |
| UX-20 | The open-section panel: tint only the bound facts, canvas colour, and pin them while the unbound list scrolls | Open |
| UX-21 | The proposer is a first cut, not a second editor. Accept writes to the draft and opens the configuration editor | Open |
| ENV-01 | One environment, and three things that will not follow `var.environment` | Parked. Own document |

---

## Open, and not on a branch

- **`ux-progress`** carries UX-21, UX-20, UX-11, UX-12, UX-14 and UX-19. The
  prompt is written. Confirm whether the branch exists before starting.
- **UX-07, numbering.** Held back deliberately. It adds a field the registry
  does not have, and that is agreed against the schema before it is written.
  It is the only registry change left in the MVP.
- **`change_impact` does not exist.** Specified in `config_editors_spec_v1.md`
  §8, not built. No delete confirmation carries a reference count, and the
  agent said so rather than inventing an endpoint.
- **The memo editor's wide mode may run under the 200px rail.** Flagged twice
  by the agent, never confirmed on screen.
- **Back picks up a changed tenant colour only after a reload.**
- **A dead `.shell header .settings` rule in `index.css`.**
- **Thirteen untracked documents** in `docs/`, including `CLAUDE.md` sitting
  in `docs/` rather than the repository root, and three backlog files
  duplicated across `docs/HANDOFF/` and `docs/backlog-items/`, one with a
  ` (1)` suffix. On no branch and in no backup.

---

## Working practices earned today

- **`CLAUDE.md` at the root.** Claude Code reads it at the start of every
  session, so the Rules of Engagement apply without being restated. It is
  currently in the wrong place.
- **One branch, one session.** Context is re-sent every turn, so a session
  that has read `Configure.tsx` carries it until the session ends. Close it
  when the branch is pushed.
- **Point at files rather than asking it to search.** A `Select-String` run in
  the terminal costs nothing and does the same hunting.
- **Commit messages go to a file.** Anything long enough to be useful exceeds
  the agent's inline command limit. `git commit -F msg.txt`.
- **Say "report and stop."** Merging stays with a person who has looked at the
  rendered screen.

---

## Test accounts

`https://d2pco7fhb5wnod.cloudfront.net`

`joeschmoe1000@gmail.com` / `Arqedia-Test-2026!` — tenant 2, TESTCO B, base plan.

`sperry@vmac.com` — tenant 1, TESTCO A, business plan. Password not known to
this session.

`q.ps1` is in the repository root; a new terminal needs
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; . .\q.ps1`.
