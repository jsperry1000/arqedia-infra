# ARQEDIA — Working practice: several Claude Code sessions

**Adopted 21 September 2026.** Every session reads this before its first
command, and again whenever it is unsure whose change it is looking at.

---

## Why

Three sessions share one repository and one Terraform state. In one afternoon
that produced three collisions: two sessions mixing staged changes and two
migration 029s in one folder; an apply from a branch whose base had moved,
which overwrote UX-17.3 on dev; and a second writer merging and pushing inside
another session's worktree mid-step.

Worktrees separate files. They do not separate deploys: every worktree applies
to the same stack, `-target` pulls in dependencies, and the last apply wins.

## The four rules

**1 · One session, one worktree, one branch.**

| Session | Worktree | Works on |
|---|---|---|
| EXTRACTION FIX | `c:\terraform\arqedia-extraction` | its own branch |
| COMPOSITION ERRORS | `c:\terraform\arqedia-subject` | `feature/subj-01-engagement-subject`, then its next branch |
| FRONT END | `c:\terraform\arqedia-frontend` | its own branch |

`c:\terraform\arqedia` holds `main` only. No session develops there.

Every prompt opens with the session's path. A session that finds a change it
did not make - staged files, `MERGE_HEAD`, a commit it does not recognise -
stops and reports. It does not continue, tidy up or commit it.

**2 · Branches never deploy.** Terraform apply and migrations run only:

- from `main`, up to date with `origin/main`, fetched immediately before the
  plan;
- in `c:\terraform\arqedia`;
- by the one session the user names when approving that apply.

Because `main` contains everything merged, an apply from it cannot regress
another session's work. The cost, accepted: nothing is tried on dev before it
is merged.

**3 · One merge at a time.** After any merge to `main`, every other branch
merges `main` in and rebuilds `web/` before its own PR is merged. `web/` is
resolved by rebuilding from merged source, never by picking a side.

**4 · This note is the reference.** A change to the rules is a commit to this
file, approved by the user.

## Standing checks

- `git fetch --prune` and `git worktree list` before any merge, plan or apply.
- Clear `__pycache__` under `lambda/` before any plan; `archive_file` has no
  excludes (BLD-01).
- Before `npm run build`, normalise to LF: `brand/logo-deep.svg`,
  `brand/logo-white.svg`, `ui/src/index.css`, `ui/src/tokens.css`,
  `ui/index.html`. Confirm `git status` shows no change to them (DRIFT-01).
- Plan to a saved file and apply that file. Stop if the plan lists anything not
  approved.
- A short push summary on every push.
