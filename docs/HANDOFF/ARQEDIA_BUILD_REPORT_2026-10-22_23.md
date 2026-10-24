# ARQEDIA — Build report, 22–24 October 2026

One working session, from 22 October 15:04 UTC to 24 October. It covers PACK-01
(multi-workspace tenants) through to deployment, all of PACK-02 (workspace
offerings, seat assignment, plan limits, deleting a workspace), and the defects
found by walking each one. This report records what was built, how it was
deployed, how it was verified, and what is still open. It does not replace
the backlog items. Where they differ, the backlog items and CLAUDE.md
take precedence.

Environment: dev only (`us-east-2`, profile `arqedia`). No production change.

---

## 1. Summary

| | |
|---|---|
| Pull requests merged | #351–#386 (36 numbers; 29 distinct changes, the rest repeat merges of the same branch) |
| Migrations written and applied on dev | 040, 042, 043, 044, 045, 046, 047, 048 (041 became 043; there is no 041) |
| Deployed layer | `arqedia-dev-docprocessing` version 51, created 2026-10-23 17:57 UTC |
| Tests | 969 pass on `main` at `d35d863` (881 → 969 over the session, plus the PACK-01 additions before that) |
| New API routes | 4 (`/workspaces`, delete code, delete, restore), listed in `api.tf` |
| New API module | `lambda/api/workspaces.py` |
| Walked on screen | Every PACK-02 step, as tenant 0, tenant 2 (admin and member), and tenant 5 |
| Defects found by walking and fixed | 9 (section 5) |
| Not in this session | #387 (AI Review for tenant 0), #388 (brand PNG lockups), #389 (memo identity in the PDF). They were merged the same evening from other branches and are not covered here. |

---

## 2. Work by pull request

### PACK-01: multi-workspace tenants (22 October)

**#351, migration 040: the workspace table.**
- Creates `workspace`.
- Widens the primary key of the nine `config_*` tables to include `workspace_id`. The old key stays as `uq_single_workspace`, so the code already deployed kept working.
- Adds `workspace_id` and an index to `document`, `extracted_value`, `memo` and `memo_rewrite`.
- Backfills one "Trade Finance" workspace per tenant, excluding tenant 0.
- No foreign key. No application code changed.
- Applied on dev 2026-10-22 18:04.

**#352: drafts, publishing and revisions scoped to a workspace.**
- Every read and write of a draft or revision now keys on `(tenant_id, workspace_id, revision)`.
- `config.load` caches on that triple.
- `config.workspace` resolves `?workspace=`. Without one, it falls back to the tenant's only workspace and refuses when there are several.
- Publishing still draws from one counter per tenant.
- `fork_base` creates a named workspace in one transaction.
- The workspace is recorded throughout:
  - Uploads carry it.
  - Documents, values, memos and Update rows record it.
  - Composition reads only the memo's own workspace's documents.
- Migration 041 was written here to drop `uq_single_workspace`. It also copies `tenant.active_revision` onto single-workspace tenants: on dev, tenant 1 had published 46 while its workspace still said 45.
- 34 files: `registry.py`, `editor.py`, `config.py`, five Lambdas and 20 test files.

**#353: the workspace UI.**
- **Workspace selector in the header.**
  - One selector for the whole app.
  - `call()` adds `?workspace=` to every request.
  - Configure shows the workspace name ahead of its parts.
- **Naming a workspace.**
  - Get started asks for a name before the first fork.
  - Administrators get "Add a workspace".
- **Engagements belong to a workspace** (migration 042).
  - The engagement, document and memo lists, and Share a memo, are scoped to the active workspace.
  - The workspace now travels in the S3 key. The signed metadata header it used before was never sent back by the screen.
- **Three ways to start a workspace:**
  - from one or more of our memoranda;
  - from a memorandum of your own, starting from scratch;
  - from a report you already write.
- **Catalogue routes:**
  - "Create from scratch" and "Create from a report" ask an administrator whether to build in this workspace or a new one.
  - A tenant with nothing configured is sent to Get started.
- **Migration 041** moved to `db/migrations/held/` and renumbered 043, so `migrate.ps1` would not apply it before the deploy it depends on.

**#354: 043 applied.**
- Applied after the workspace code was confirmed live on layer 48: the API, normalizer and composition matched `main` byte for byte.
- `uq_single_workspace` is off all nine config tables, and `uq_engagement_name` is off `engagement`.
- Applied 2026-10-22 23:31.

**#355 and #356: documents committed as they stood, not edited.**
- Handoff 19–20 October.
- Decisions of 20 October.
- PACK-01 backlog notes.
- The copy triage xlsx.

**#357: no open-draft note when adding a workspace.**
- "You have an open draft. Get started publishes it" was untrue there, because the new workspace has no draft.

### PACK-02: offerings (23 October morning)

**#358, #359, #360: backlog item.** `docs/backlog-items/ARQEDIA_backlog_PACK02_workspace_offerings.md`:
- What ARQEDIA offers is a workspace.
- Six settled decisions.
- A and B answered:
  - AR FINANCING (tenant 2) and REAL ESTATE (tenant 5) stay unlinked.
  - A report of the tenant's own starts from what the workspace holds.
- C raised: seat-to-workspace assignment.
- D's shape settled:
  - Hidden, then removed.
  - The last workspace is kept.
  - Counts, typed name and an emailed code.
  - Members reassigned.

**#361, migration 044: offering workspaces.**
- Tenant 0's configuration moves into workspace 12, "Trade Finance".
- `pack_offer` is keyed `(workspace_id, pack_key)`.
- Client workspaces 1–5 are linked to 12; workspaces 9 and 10 are unlinked.
- The data statements were dry-run in a rolled-back transaction before the migration was written.

**#362: offerings in the registry and the API.**
- **Registry:**
  - `offer` and `set_offer` work per offering.
  - `packs` returns one base per offering.
  - `fork_base(..., offering)` records `forked_from_workspace_id`.
  - `fork_template` and `template_packs` take memoranda from the workspace's own offering only.
  - `new_workspace` makes an empty workspace and its draft in one transaction.
- **API (no new routes):**
  - `POST /config/fork` takes `offering` and `empty`.
  - `GET /config/templates/available` takes `?offering=`.
- 876 tests.

**#363, #365, #366: 044 applied.**
- Applied 2026-10-23 11:28:09, after layer 49 was confirmed.
- Checked by query:
  - Workspace 12 is at revision 33.
  - No row of the fourteen tables is left at workspace 0.
  - All five `pack_offer` rows are at workspace 12.

**#364 and #367: curator screens.**
- The picker offers "Add an offering".
- Get started builds an empty offering, by hand or from a report.
- The Catalogue shows "What <offering> offers".
- An offering with nothing published says so.
- Fixed: Get started showed no error on the own-report routes, because the error was drawn inside the hidden memoranda list.

**#368: client screens, and two defects from the curator walk.**
- **Client screens:**
  - Get started asks which offering where there are several, and names it where there is one.
  - A report of the tenant's own makes an empty workspace; nothing is forked.
  - A workspace that came from no offering is told why no memoranda are offered.
- **Defect:** the header lost the picker after signing in on an open tab, because the role was read once, before the session existed.
- **Defect:** an empty workspace said "Live: revision 1", which is another workspace's revision. `GET /config` now answers `active_revision: null`.
- 878 tests.

**#369: an empty workspace is not a new tenant.**
- First run now means a tenant with no workspace.
- Get started no longer forks a second workspace when a memorandum is ticked inside an empty one.
- The Engagements note sends an empty workspace to Configure.

**#370, G1: say why the first screen is waiting.**
- Aurora takes up to 30 s to wake. After 3 s the shell now says it is starting up and why. Before, it showed only an ellipsis.

**#371, G11: Share history lists only the active workspace's shares.**
- Grants are filtered by the memo's workspace.
- The share allowance stays the tenant's.
- 881 tests.

### PACK-02 C: seats and workspaces (23 October)

**#372 and #373: an administrator assigns workspaces to member seats.**
- **Migration 045:**
  - `seat_workspace` and `seat_invitation_workspace`.
  - Existing members got every current workspace.
- **`seats.py`:**
  - Listing per seat and per invitation.
  - `invite()` requires at least one workspace for a member.
  - `set_workspaces`.
  - `set_role` keeps every workspace when an administrator is made a member.
  - `allowed_workspaces`.
- **Signup** acceptance copies the invitation's workspaces to the seat.
- **API, for a member:**
  - `?workspace=` must be one of the member's workspaces, or the API answers 403.
  - Without it, the API uses the member's only workspace.
  - A memo, document or share by number outside the member's workspaces is 404.
- **API, other:** `PUT /seats/{id}` changes the role only when the body names one.
- **Seats screen:**
  - A Workspaces column.
  - "Change" with ticks.
  - Ticks on the invite form.
- 901 tests.
- Applied 2026-10-23 13:56.

**#374: a member's seats screen is read-only.**
- Walking as a member (tenant 2) showed every seat control offered and then refused by the server.
- The viewer's role is now their own seat's.
- A member sees roles as text and their own workspaces, plus one line saying who changes seats.

**#375: a member with one workspace sees its name in the header.**
- Shown as text in place of the picker toggle.

### Plan limits (23 October)

**#376: how many workspaces a plan holds.**
- **Limits:**
  - Base 1, Small Business 5.
  - Enterprise is negotiated through `tenant.workspace_limit`; no limit until it is set.
  - Tenant 0 is exempt.
- **Migration 046:** `plan.workspace_count` and `tenant.workspace_limit`. Applied 2026-10-23 16:00.
- **Enforcement:**
  - `billing.require_workspace_room` runs before `POST /config/fork` (409).
  - A downgrade below the workspaces held is refused, as it is for seats.
- **Display:**
  - `/settings` carries `workspace_limit` and `workspaces_held`.
  - The plan table has a Workspaces row.
  - `config/plans.json` gains `workspace_count`.
  - The picker and "Add a workspace" say when the limit is reached.
- 917 tests.

### PACK-02 D: deleting a workspace (23 October)

**#377: an administrator deletes a workspace, and restores one.**
- **Migration 047:**
  - `workspace.deleted_at`, `deleted_by`, `remove_after` (six months).
  - Table `workspace_deletion`: the code is hashed, lasts 15 minutes, allows 5 tries and one request a minute.
  - Applied 2026-10-23 16:27.
- **`lambda/api/workspaces.py`:**
  - A listing with counts.
  - The emailed code.
  - Delete: the name is typed, the code is entered, and members who see only that workspace are moved.
  - Restore needs room on the plan.
- **Hiding:**
  - Hidden through `config.workspaces` (in the layer) and the seat queries (`_LIVE`).
  - The assignment rows are kept, so a restore gives back the same access.
  - A memo, document or share in a deleted workspace is 404 for everyone.
- **Shares** are suspended, not revoked. `share_rules.refusal` returns "suspended" (in the layer), and `share.py` suspends and lifts a workspace's grants.
- **Account management:** a Workspaces tab, for administrators only.
- 951 tests.

**#385: an offering nothing depends on may be deleted (amendment to D).**
- Tenant 0 may delete an offering only when:
  - no client workspace was started from it, deleted ones included;
  - it has no `pack_offer` row.
- Otherwise the delete is refused with the reason, both at the code and at the delete.
- The tab shows "N client workspaces use it" or "on offer" in place of Delete.
- 969 tests.

### Small items and fixes (23 October)

**#378: gold marks every act that charges, and nothing else.**
- 13 buttons are marked `.spend`; every other button is navy.
- CLAUDE.md is amended beside the settled line, which is kept.

**#379: plurals.** "1 fact" and "1 document type", in four places.

**#380, G8: nothing is uploaded or filed where nothing is published.**
- An empty workspace fell back to revision 1, which holds nothing there: a document was read against nothing and filing still charged.
- `POST /uploads` and `POST /engagements/{id}/file` now answer 400 before any row or charge is made.
- The engagement screen shows the reason, with a link to the Report Catalogue, in place of the upload box.
- 955 tests.

**#381, migration 048:**
- `idx_field_schema` becomes `(tenant_id, workspace_id, revision, schema_key)`.
- An index change only. Applied 2026-10-23 17:10.

**#382, PACK-01 backlog:** a dated "Where it stands — 23 October 2026" section, added beside the existing text.

**#383, Proposer:**
- **Defect:** headings were matched character for character, but a PDF's text layer puts tabs where the page shows spaces. On the Real Estate sample, 0 of 8 headings were found and 127 facts were proposed.
- `_find` now ignores case and treats any run of whitespace as one space. On the same sample, 8 of 8 headings are found and 85 facts proposed.
- Tick all / Untick all for each section and for all kept sections.
- The "heading not found" message is rewritten to say what it means.
- 961 tests.

**#384: duplicate names, and an empty workspace's first run.**
- `registry._workspace_name` refuses a name already used by a live workspace, ignoring case and spacing. A deleted workspace's name is free again.
- Configure's first-run screen inside an existing empty workspace now reopens that workspace's draft. Before, it made another workspace.
- 965 tests.

**#386: Catalogue.** The same gap as #384, in the Catalogue's `ensureDraft`. From an empty workspace, "Create from a report you already write → In <workspace>" now opens the report reader instead of Get started's "Add a memorandum".

---

## 3. Database state on dev, read 24 October 2026

**`schema_migration`:** 040 (22 Oct 18:04), 042 (23:14), 043 (23:31), 044 (23 Oct 11:28), 045 (13:56), 046 (16:00), 047 (16:27), 048 (17:10).

**`workspace`:**

| tenant | id | name | state |
|---|---|---|---|
| 0 | 12 | Trade Finance | live; 5 `pack_offer` rows; clients 1–5 forked from it |
| 0 | 13 | PACK-02 walkthrough | deleted 2026-10-23 18:22:05; removal due **2027-04-23** |
| 0 | 16 | REAL ESTATE | live; 2 `pack_offer` rows; tenant 5's workspace 18 forked from it |
| 1 | 1 | Trade Finance | from 12 |
| 2 | 2, 9 | Trade Finance (from 12), AR FINANCING | live |
| 5 | 3, 10, 14, 15, 18 | Trade Finance (from 12), REAL ESTATE, PACK-02 walkthrough – own report, New Workspace, ARQEDIA REAL ESTATE (from 16) | live |
| 9, 10 | 4, 5 | Trade Finance | from 12 |

**Other tables:**
- Workspace 17, a duplicate "REAL ESTATE" on tenant 0, was removed by hand after confirming that no row referenced it.
- `seat_workspace`: 3 rows.
- `plan.workspace_count`: base 1, business 5.

---

## 4. Deployment discipline followed

- **Order:** each migration that depended on code was held in `db/migrations/held/` until that code was confirmed deployed, then moved out in a PR of its own and applied (043, 044). Additive migrations (045–048) were applied before or with their code.
- **Layer:** every change under `lambda/shared/` was followed by `build-layer.ps1` before `terraform apply`. The deployed layer's version and contents were checked, not the local file (layers 48, 49, then up to 51).
- **`web/`:** every `ui/src` change carried its `web/` build in the same PR. Each push summary said so.
- **Verification:** every migration and deploy was checked by querying, not by the absence of an error.
- **Merges:** done by a human, from the push link (no gh CLI).

---

## 5. Defects found by walking, and their fixes

| # | Found | Fix |
|---|---|---|
| 1 | Header lost the workspace picker after signing in on an open tab | #368: role taken from the sign-in claims |
| 2 | Empty workspace said "Live: revision 1" | #368: `active_revision: null`, "nothing published" |
| 3 | Get started treated an empty workspace as a new tenant and would fork a second one | #369 |
| 4 | Own-report routes in Get started showed no error at all | #364 |
| 5 | A member was offered every seat control, and the server refused each | #374 |
| 6 | A member narrowed to one of several workspaces could not see which one | #375 |
| 7 | Upload and filing in an empty workspace read against nothing and still charged | #380 |
| 8 | Two offerings called REAL ESTATE; Configure's first run made a new workspace from an empty one | #384 |
| 9 | Catalogue sent an empty workspace to "Add a memorandum" | #386 |

The Proposer finding (#383: 0 of 8 headings, 127 facts) came from the user's report, not from a walk.

---

## 6. Incidents and process notes

- **Deploy not done.** The first check after "merged and applied" showed C was not deployed. The user re-applied. This is why each deploy is checked by query.
- **Repeat merges.** #372/#373, #363/#365/#366, #364/#367, #355/#356 and #358/#359/#360 carry the same change more than once. No harm, but they make the history longer.
- **Browser PUT not exercised.** A direct API call through the browser was blocked by the auto-mode classifier. That one path was recorded as unverified rather than assumed.
- **Wrong tenant in a test.** The browser session had switched tenant, so a downgrade test ran as tenant 2. The log confirmed it, and the test was redone as tenant 5.
- **`build-layer.ps1` stopped early when run with `2>&1`.** pip's warning halted it before the zip was made. It must be run without the redirect.
- **PowerShell and git.**
  - Quotes broke `git commit -m`; commit messages are now written to a file as UTF-8 without a BOM.
  - One BOM did reach a subject line. It was amended and force-pushed with lease, on an unmerged branch of my own only.
- **G8 broke 13 tests.** Placing the check inside the functions broke tests that use order-based fake databases, so it moved to the routes.
- **Email (D's deletion code):**
  - `admin@arqedia.com` bounced (550 5.4.1) because it did not exist in Microsoft 365. The user added the alias.
  - SES then refused the address from its **account suppression list**, where the hard bounce had put it. The entry was removed with `aws sesv2 delete-suppressed-destination`, and the next code was delivered at 18:20.
  - An apparent crash at 18:16:53 was the one-code-a-minute 409.
  - Confirmed: SES only sends. There are no receipt rules, MX points to Microsoft 365 (`mail_dns.tf`), and `info@` and `admin@` are M365 aliases. Mail to *@arqedia.com is not forwarded by SES.

---

## 7. Quality assessment

**Strong:**
- **Tests:**
  - Every server change carries tests: 969 on `main`, all passing.
  - New suites: `test_workspace_resolution`, `test_workspace_scope`, `test_offering_routes`, `test_seat_workspace`, `test_workspace_deletion`, `test_nothing_published`, `test_proposer_slicing`.
- **Isolation:**
  - Another tenant's workspace number → 400.
  - A member's unassigned workspace → 403.
  - Anything in a deleted or unassigned workspace → 404, by number, for memos, documents and shares.
- **Money:** nothing in an empty workspace can be charged (G8). The plan limit is checked before anything is made. Gold now marks charges only.
- **Reversibility:** a deleted workspace is restorable for six months, with its access and shares returned.
- **Walks:** every PACK-02 screen was walked as each role, and nine defects were fixed as a result.

**Weaker, or not exercised:**
- **UI tests:** there are 15 UI tests, and none cover the workspace screens. The screens are verified by walking only.
- **ESLint:** `App.tsx` still has the 8 findings it has on `main`.
- **Removal job:** the six-month removal after delete is not built (section 8). Until it is, "removed after six months" is a promise the system does not keep.
- **Suppression list:** a suppressed address fails silently. The only sign is the bounce email sent to sperry@ebl-finance.com.
- **Order-based test fakes:** several suites use them, and they break when the order of queries changes (see G8). They are worth replacing over time.

---

## 8. Open

| Item | State | Due or owner |
|---|---|---|
| **D removal job:** remove workspaces past `remove_after` | Not built | Before **2027-04-23** (workspace 13) |
| SES suppression fails silently: note under CLAUDE.md's open email items | Offered, not answered | User |
| Schema and section ceilings: per workspace or across the tenant | Undecided | User |
| Billing unit for workspaces | Undecided | User |
| Document groupings on a raw workspace | Parked by the user; part of developing tenant 0's packs | User |

---

*Compiled 24 October 2026 from `git log` of #351–#386, `schema_migration`, the
`workspace` and `pack_offer` tables on dev, the deployed layer listing, and a
full test run on `main` at `d35d863`.*
