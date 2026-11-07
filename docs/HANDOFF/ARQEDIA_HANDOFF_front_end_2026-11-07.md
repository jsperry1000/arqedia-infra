# ARQEDIA — Front end handoff, 7 November 2026

Status snapshot for a new chat. Covers one session, 6–7 November 2026: the
first sign-in walk, workspace renaming, the staff console's tenant standing,
and a clean-up of test tenants. Everything here is on **dev** (us-east-2,
account 667523685221), which is also production for now (ENV-01).

---

## 1. State at handoff

| PR | Branch | State |
|---|---|---|
| #473 | `feature/workspace-rename` | merged |
| #474 | `feature/onboarding-steps` | merged |
| #475 | `feature/onboarding-steps` (second PR) | merged — duplicates #476's change, harmless |
| #476 | `feature/setup-only-redirect` | merged |
| — | `feature/staff-standing` | **pushed, not merged.** Its Lambda is already deployed |

`main` at `9b1760c` builds, passes 91 tests, and its committed `web/` matches
its source (rebuilt and compared, 7 November).

Live changes made this session, each verified by querying afterwards:

- **Migration 054** applied: `memo.workspace_name VARCHAR(128) NULL`.
- **`terraform apply`, 6 November**: route `PUT /workspaces/{workspace_id}`
  added; `arqedia-dev-api` and `arqedia-dev-render` redeployed. Deployed code
  hashes matched the plan; one memo read through the deployed API returned 200.
- **`terraform apply`, 7 November**: `arqedia-dev-admin` redeployed. Its
  `GET /tenants` answered 200 with the new `standing` field.
- **Tenants 13–17 deleted** (dev sign-up tries). See §5.

---

## 2. First sign-in as step panels (#474, #476)

`ui/src/FirstRun.tsx`, switched in from `WelcomeView` in `Welcome.tsx`.
Draft copy from `ui/src/assets/Draft copy.docx` (the user's; not committed).

One panel at a time, each bordered in `--deep`, Next at its foot:

- **I** Welcome / How ARQEDIA works, with the backbone diagram
  (`ui/src/assets/backbone.png`, taken from the .docx; header labels
  re-lettered bold in Arial Bold). Panel I is 988px wide, 30% over 760.
- **II** Engagements and segregation of data. Button "Next – get started".
- **III A** How to start: ARQEDIA configuration → C; from scratch or from a
  report → B.
- **III B** Create a workspace (own configuration only). Next creates an empty
  workspace and opens Configure, as the old form did.
- **III C** ARQEDIA workspaces, several allowed, counts read live.
- **III D** Report templates under each chosen workspace. Next forks each
  workspace, takes its ticked templates, publishes. In reverse order, so the
  first chosen is left active. A second press after a failure makes nothing
  twice.

Every other arrival at `/welcome` (Add a workspace, the Catalogue's routes, an
offering) keeps the old single form.

**The shell (`App.tsx`, `setupOnly`)**: an administrator whose tenant holds no
workspace is sent to `/welcome` from every route — rail, Home, the mark,
Account management. Lifted the moment `adopt()` sets an active workspace, so
the hand-off to Configure is not sent back. Members are not held. Only on a
workspace read that answered.

---

## 3. Workspace renaming (#473)

- `PUT /workspaces/{workspace_id}` in `lambda/api/workspaces.py` (`rename`).
  Administrator only; refused for tenant 0's offerings; refused where another
  **live** workspace of the tenant has the name, case-folded; 128 characters.
- UI: "Rename <name>" under the rail's list (active workspace, in place), and
  Rename beside each row in Account management → Workspaces.
- **Old memos keep the old name.** Renaming first stamps the old name into
  `memo.workspace_name` on every memo of the workspace still NULL, then
  renames. `get_memo` and the renderer read `COALESCE(m.workspace_name,
  w.name)`; `revise_memo` copies the parent's value. Composition was not
  touched. At handoff all 199 memos are NULL — no rename has happened yet.
- **Restore** of a deleted workspace whose name a live one now holds comes
  back as `<name>-restored` (then `-restored-2`…) and the screen says so.

---

## 4. Staff console: Standing (`feature/staff-standing`, not merged)

Why a trial showed as "base": sign-up writes `tenant.plan = 'base'` for every
tenant and leaves the plan to the subscription; a trial is having none. The
view showed only the plan copy and the subscription. Not a billing fault —
`wallet.standing` already treats them as trials.

`lambda/admin/cross_tenant.py` now returns `standing`, restating
`wallet.classify_standing` in SQL on `paddle_status` (the staff console shares
no code with the API): trial, trial_ended, active, payment_failed, paused,
cancelled, and `arqedia` for tenant 0. `admin/src/App.tsx` adds a Standing
column and renames "Status" to "Paddle status". **Lambda deployed; the
console updates when the branch merges** (CI builds `admin/`).

---

## 5. Tenants 13–17 deleted

Sausage Maker, jsp, joeschmo, stubb, genevetrader. Removed: every Aurora row
(5,203 config rows, 6 workspaces, 1 engagement, 5 seats, 5 terms
acceptances, 5 trial buckets, 5 tenants), 56 `signup_attempt` rows, 5 users in
`arqedia-dev-users`, one proposal file in the review bucket. Nothing in
documents, memos, shares, DynamoDB, ledger, Paddle or `tenant_domain`.

**Kept on purpose:** the five `signup_allow` entries, so the same addresses
can sign up again; `stub4491@gmail.com`'s viewer account (separate pool, not
part of the tenant).

No deletion procedure was written down; this one was done by hand. The open
item on account deletion in CLAUDE.md still stands.

---

## 6. Decisions made this session

Not yet in CLAUDE.md's settled decisions. Each was the user's call:

1. First sign-in is step panels I–III D, as above; at first sign-in only.
2. **Amends 22 October** ("a name is never filled in"): at first sign-in each
   ARQEDIA workspace is created under its ARQEDIA name.
3. Step C keeps to the plan's workspace limit; the upgrade is a note, not a
   link (see 7).
4. Dropped from the first-run copy: what a filing costs, getting facts right
   before upload, a second administrator.
5. A tenant with no workspace reaches nothing but the steps. A workspace that
   exists with nothing published is not held.
6. Workspaces are renamable by an administrator, from the rail and from
   Account management; never an ARQEDIA offering; no duplicate live names.
7. A memorandum keeps the workspace name it was generated under.
8. A restored workspace whose name is taken comes back `-restored`.

---

## 7. Open, and unverified

**Not seen rendered** (CLAUDE.md: render it and look):

- The step-panel border width (3px placeholder) and panel I at 988px.
- The rail's rename box (`.rail-rename`).
- The staff Standing column.

**Not exercised end to end:**

- A real rename, and an old memo then still showing the old name — on screen
  and in the PDF.
- A restore whose name is taken.
- Step D creating several workspaces in one press, and the step C limit note.
  The trial's workspace limit was never looked up.

**Loose ends:**

- Panel D still says "you come back to this screen from Template Catalogue".
  With nothing reachable but the steps, that sentence is now inaccurate.
- `ui/src/assets/Draft copy.docx` (and Word's `~$aft copy.docx` lock file)
  sit untracked in `ui/src/assets/`.
- `docs/HANDOFF/ARQEDIA_HANDOFF_paddle_2026-10-26.md` and
  `docs/backlog-items/ARQEDIA_HANDOFF_legal_2026-10-27.md` are untracked too.
- `App.tsx` carries six lint errors; `main` had the same six before this work.

---

## 8. Local development

The UI runs locally against the deployed dev backend; there is no local
backend. `ui/.env` already holds the sandbox Paddle pair and
`VITE_SITE_URL`.

```
cd C:\terraform\arqedia\ui
npm run dev
```

It serves on 5173 (5174, 5175 if taken — the three origins the API accepts).
Started from Claude Code, the server was killed three times for low memory
while idle, and stale copies held ports; start it from a terminal of your
own. Signing up locally creates real tenants, sends real codes, and is
limited to one trial per email domain — use an address on `signup_allow` or a
fresh domain.

Staff console sign-in: `info@ebl-finance.com`, the only user in
`arqedia-dev-staff`, with an authenticator.
