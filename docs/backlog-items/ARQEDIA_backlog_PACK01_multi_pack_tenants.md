# ARQEDIA — Backlog Item

## PACK-01 · Multi-workspace tenants

| | |
|---|---|
| Status | Shape settled against the live schema; four schema blockers resolved. Ready for Prompt 2. |
| Priority | Decide before further config-registry work locks in single-partition assumptions |
| Type | Architecture — schema migration + Config Registry + Config Editors + Pipeline + Identity & Seats + Wallet & Entitlement |
| Raised | 21 October 2026, from chat |
| Updated | 22 October 2026 — CC read the live schema under Prompt 1; the spec's object model was never built, this document is rewritten against what's actually live |
| Status, 23 October 2026 | Built, deployed and walked on dev. See "Where it stands" directly below; the sections after it are the record as it was written and are left as they were. |

---

### Where it stands — 23 October 2026

Read from `main`, `schema_migration` and the deployed Lambdas on dev, not
from the record below. Everything the record leaves "in progress", "not
deployed" or "awaiting" has since landed.

**Migrations, all applied on dev:** 040 (22 Oct 18:04), 042 (22 Oct 23:14),
043 (22 Oct 23:31, out of `held/`), then PACK-02's 044-047 and 048
(`config_field`'s schema index given `workspace_id`, 23 Oct 17:10).

**Prompts 3 and 4: merged and deployed together.** #352
(`feature/pack01-workspace-scope`) was squash-merged as `b90821b`, so the
"second commit hash" under Open no longer exists to be found. #353
(`feature/pack01-workspace-ui`), #354 (043 out of `held/`) and #357
followed. The deploy order under Prompt 4 was the one used.

**The Open items below, answered:**

- **Ownership check on an explicit `?workspace=`** — answered in code.
  `config.workspace` refuses any number that is not one of the token's
  tenant's live workspaces (400, "this account has no workspace N"), before
  anything is read; a member is further refused one not assigned to them
  (403, PACK-02 C). A memo, document or share named by its own number is
  answered "not found" when its workspace is not the caller's to reach or
  has been deleted (`_outside_assignment`).
- **Second commit hash on #352** — moot; squash-merged as above.
- **Share history by workspace** — built, #371 (G11).
- **Three-way "Add a workspace"** — built in #353 (one of ours, from
  scratch, or from a report, each named first); PACK-02 added which of our
  offerings "one of ours" comes from (#368).
- **Enterprise workspace-count ceiling** — settled and built (#376,
  migration 046): Base 1, Small Business 5, Enterprise a per-tenant number
  in `tenant.workspace_limit`, no limit until it is set. A downgrade below
  the workspaces held is refused.
- **Still open, unchanged:** schema/section ceilings per workspace or
  aggregated across a tenant's workspaces (settled item 3), and the billing
  unit (settled item 5).

**Settled items, as built:**

1. Document scope at upload — built: the storage key carries the workspace
   (`tenants/<t>/w/<w>/docs/…`), and classification reads that workspace's
   document types only. Since #380 (G8), nothing is uploaded or filed into
   a workspace with nothing published.
2. No cross-workspace document reuse — as settled; nothing was built for
   it.
3. Workspace count by plan — built, as above.
4. Seats and workspaces — built as PACK-02 C (#372-#375, migration 045): an
   administrator sees every workspace; a member only those assigned, at
   least one.

**Beyond this item, in PACK-02:** offerings (a workspace of tenant 0's is
what a client starts from), and deleting a workspace (hidden for six
months, then removed; restorable until then — #377, migration 047). The
removal after six months is not built. See
`ARQEDIA_backlog_PACK02_workspace_offerings.md`.

---

### Naming, settled

The new per-tenant industry partition is called a **workspace** — not a
"pack." Live, "pack" already means something else: the starter-template
bundle a brand-new tenant forks from (KYC/AML, Vendor, Credit File),
referenced by `config_revision.pack_key`, `pack_offer`, `forked_pack`,
`pending_signup.pack`, `fork_base`/`fork_template`. None of that naming
changes. "Workspace" is the new, separate concept: one industry-scoped
slice of a tenant's own config (Trade Finance, Real Estate, Private Credit
Corporate, Accounts Receivable Financing).

### Observation

A tenant working more than one industry has no way to hold more than one
fact set today. They either run one oversized config mixing every
industry's categories/document types/schemas/templates, or open a second
tenant (separate login, billing, users) to get a second fact set.

### What's actually live — corrected 22 October 2026

`config_registry_spec_v1.md` §4's model — `category`, `document_type`,
`schema_def`, `template`, a separate `registry_revision` — **was never
built.** This document originally assumed it was; it wasn't. CC read
migrations 001–039 in full against the live dev database and found:

- Migration 008 built nine `config_*` tables instead, each keyed by
  `(tenant_id, revision, <natural key>)`.
- The real anchor is `config_revision(tenant_id, revision)`. Every config
  row hangs off that pair — there is no single foreign key to retarget.
- The database has exactly one foreign key in total (`fk_subscription_plan`;
  migration 026: *"Nothing in this schema has one"*). Adding a second FK is
  a deliberate choice, not a given.
- Four runtime tables also carry `(tenant_id, revision)` and assume it's
  unique per tenant: `document.config_revision`, `extracted_value.config_revision`,
  `memo.config_revision`, `memo_rewrite.config_revision` — plus
  `tenant.active_revision` and `pack_offer(tenant_id, revision)`.
- The draft is hardcoded as `revision 0`. One `(tenant_id, revision)` pair
  per tenant means one draft per tenant, full stop, under the current key
  shape.

### Why partitioning by tag-inside-one-registry still doesn't work

Unchanged reasoning, now anchored to the real tables: tagging config rows
by industry inside the existing single `(tenant_id, revision)` series would
still mean one draft, one publish, one coverage-validation run shared
across every industry the tenant runs — a Real Estate edit sitting in the
same publish as Trade Finance, and a broken binding in one blocking the
other. Partitioning avoids this by giving each workspace its own
`(tenant_id, workspace_id, revision)` series instead.

### Settled shape — the real fix, not the lightweight alternative

CC offered a cheaper alternative (keep `(tenant_id, revision)` as-is, add a
nullable `pack_id` only to `config_revision`, no other table touched). **Not
chosen.** The decision is to do the real fix everywhere:

- New `workspace` table: `workspace_id`, `tenant_id`, `name`,
  `forked_from_workspace_id`, `forked_from_revision_id` (an `INT` revision
  number — no `revision_id` exists to reference), `created_at`.
- `workspace_id` goes into the primary key of all nine `config_*` tables
  (built in migration 008) **and** the four runtime tables listed above —
  not just a nullable column on `config_revision`. Every existing row in
  all thirteen tables is backfilled with a `workspace_id`.
- Revision numbers stay **one shared counter per tenant**, not per
  workspace — CC's original recommendation, confirmed. `(tenant_id,
  workspace_id, revision)` identifies a revision; the counter generating
  the next `revision` value is tenant-wide, not reset per workspace.
- **No foreign key** from `config_revision.workspace_id` (or any of the
  other twelve tables' `workspace_id`) to `workspace.workspace_id`,
  consistent with the schema's existing one-FK-total posture.
- `tenant.active_revision` is kept as a compatibility copy for older
  readers, the same pattern already used for `tenant.plan`. The live
  selected revision moves to `workspace.active_revision`, one per
  workspace.

### The six existing tenants

Live tenant IDs: `0, 1, 2, 5, 9, 10`. (Tenant `0` is the reserved tenant
holding the starter packs themselves — unrelated to this change.) Each of
the other five gets exactly one `workspace` row created by the backfill,
carrying their entire existing config forward unchanged. **Settled name for
all of them: `"Trade Finance"`** — that is what their live config already
does. Real Estate, Private Credit Corporate, and Accounts Receivable
Financing are added later as new, separate workspaces, not derived from the
backfill.

`forked_from_workspace_id` / `forked_from_revision_id` for the backfilled
rows: populated only where `config_revision.forked_from` already names a
starter pack (e.g. `pack:0:1`) — use that. Everywhere else, left `NULL`
rather than guessed; `tenant.forked_pack` is `NULL` for every live tenant,
so there's nothing to backfill from there.

### `?workspace=` resolution rule — settled 22 October 2026

Decided directly between you and CC, in Prompt 3's in-session question panel —
not something written into this backlog or the prompts doc beforehand. CC
proposed two options; you picked CC's recommendation:

- **Chosen:** no `?workspace=` named and the tenant has exactly one workspace
  → use it. No `?workspace=` named and the tenant has several → refuse,
  "choose a workspace." Tenant with no workspace of its own (tenant 0, the
  starter-pack tenant) → resolves to workspace 0.
- **Declined:** lowest-numbered workspace as a silent default (never
  refuses, but can misfile work against the wrong workspace without telling
  anyone).

### Three further CC design details

CC flagged these itself as its own design judgment, never put to you for a
decision beforehand.

1. **Transport — confirmed 22 October 2026.** `?workspace=<id>` travels as
   a query parameter on every route — GET and POST alike — not a body
   field or a header. CC's stated reason: both verbs carry it the same
   way, and it avoids an API Gateway CORS change.

   **Security review, 22 October 2026:** the transport location itself is
   low-risk — `workspace_id` is a partition selector, not a credential, so
   its presence in logs/history isn't a meaningful leak, and a query param
   is the *correct* choice for GET cache-key correctness (a header would
   need an explicit `Vary`). The real security question is not where
   `workspace_id` travels but whether every route independently verifies
   the resolved workspace belongs to the authenticated tenant (and, after
   Prompt 5, the authenticated seat) rather than trusting the number in the
   URL at face value — a bare integer in a query string is the classic IDOR
   shape if that check is missing on any handler. Folded into Prompt 4 as a
   confirm-only ask; CC's Prompt 4 report (below) does not yet answer it —
   still open.

2. **Legacy-row fallback — confirmed 22 October 2026.** `config.workspace_of`
   treats a document, memo, or config row still sitting at `workspace 0` as
   belonging to the tenant's one workspace, under the same
   one/several/refuse logic as the resolution rule above. This is a
   transition shim for rows the still-deployed old code writes before this
   branch ships — once a tenant has a second workspace, a row still stuck
   at `0` becomes unreadable until reassigned.

3. **Unresolvable upload — superseded 22 October 2026, see Prompt 4's
   report below.** Originally recorded as "resolves at upload-signing time,
   travels to the normalizer as S3 metadata." Prompt 4's work found the
   actual live mechanism (from the still-undeployed Prompt 3 branch) signs
   a **workspace header** on the upload link instead — one the upload
   screen never sends back, which would reject every upload once deployed.
   The real, now-current mechanism: the workspace is encoded directly in
   the **S3 storage key** (`tenants/<t>/w/<w>/docs/…`), not a header or
   metadata field. The normalizer reads both the old and new key layouts
   for compatibility. Refusal-row behavior on an unresolvable workspace is
   unchanged.

### Prompt 3 — done, 22 October 2026

Branch `feature/pack01-workspace-scope`, PR **#352** (confirmed 22 October
2026 — this is the PR number referenced in Prompt 4's report). Commits
`a0b6cd6` and a second commit (CC's transcript truncated its hash twice —
still outstanding, get the exact hash before merge). 832 tests pass,
including new tests for the resolution rule and fork-as-workspace; 172
existing tests updated for new function signatures; two test failures
caught during the work were fixed. All five tenants (1, 2, 5, 9, 10)
verified side-by-side against `main`'s code on dev, read-only — revisions,
memo labels, extracted-value row counts and publish-validation identical,
plus a rolled-back test publish per tenant confirmed draft/revision-in-use
unchanged afterward.

**#352 is merged to `main` but NOT deployed** (confirmed via Prompt 4's
report, 22 October 2026) — every Lambda is still on the 20 October build,
layer 47. A statement in the Prompt 4 text ("that refusal is live now") was
wrong — merging is not deploying, and this was asserted without checking
live state. Corrected; future prompts will check deployed state rather
than infer it from a merge decision.

**#352 cannot deploy alone.** Its upload-link signing sends a workspace
header the current (pre-Prompt-4) upload screen never echoes back, so S3
rejects every upload if #352 ships by itself. Prompt 4's branch
(`feature/pack01-workspace-ui`) fixes this by moving the workspace into the
storage key instead (see "Three further CC design details," item 3,
above) — #352 and the UI branch must deploy together.

**Tenant 1 split-state, found and fixed in this pass:** tenant 1 was edited
and republished to revision 46 through the still-deployed old code (which
doesn't know about workspaces) after migration 040 ran. That left 759 rows
at `workspace 0` and set only `tenant.active_revision` to 46, leaving
`workspace.active_revision` at 45 — a real split between the tenant-level
and workspace-level revision-in-use pointers. CC re-ran 040's backfill (759
rows fixed, none outside tenant 0 left at workspace 0) and added a new
third step to migration 041 to copy `tenant.active_revision` onto
`workspace.active_revision` per tenant. Both statements were already run
by hand against dev to validate the retry; `schema_migration` currently
under-reports dev's true state until 041 is applied as a whole.

**Housekeeping, non-blocking:** several stale local branches
(`feature/memo-update`, `fix/copy-review-critical`, `generate-refund`,
`ocr-split-parts`) differ from `main` but don't touch `registry.py`,
`config.py`, or `editor.py` — not touched by this work, flagged for
separate cleanup.

### Prompt 4 — in progress, 22 October 2026 (not deployed, UI unverified)

Branch `feature/pack01-workspace-ui`, commit `612c923`, PR open. Code
written and pushed; nothing deployed or applied; the screens have not been
clicked through in a browser.

**What changed:**

- **Selector:** one selector in the header, beside the account menu, built
  from that menu's existing classes (no new CSS). Shows when a tenant has
  more than one workspace, or for an administrator. Every request now
  carries the active workspace; switching reloads every screen, and an
  open engagement or memo returns to Home. The Configure surfaces show the
  workspace first in their bar, ahead of Document types.
- Members see every workspace for now — Prompt 5 (who may see which
  workspace) isn't built yet; expected, not a gap.
- **Get started:** asks "Name this workspace" (required, with an example
  as placeholder only) whenever pressing it will create one — a new
  tenant's first run, and "Add a workspace." The new workspace becomes
  active before any memorandum is taken into it. The Catalogue no longer
  forks a base on its own; an unconfigured tenant is sent to Get started.
  Configure's first-run screen has its own name field.

  **Correction to the Prompt 4 text itself:** it stated the unnamed-fork
  refusal was already live. It isn't — #352 (which added that refusal) is
  merged but not deployed. The Get started fix is on this branch regardless
  and will take effect once both branches deploy together.
- **Upload:** the engagement page reads "Uploading into [workspace]";
  classification runs only against that workspace's document types. The
  storage key is now `tenants/<t>/w/<w>/docs/…`; the normalizer reads both
  the old and new key layouts. No document reuse across workspaces — a
  document needed in two is uploaded twice, per the existing settled
  decision.
- **Lists:** engagements, documents, memos, and "Share a memo" show the
  active workspace's rows only. **Share history was not filtered** in this
  pass — flagged by CC, and you've asked for it to be fixed now, folded
  into this same branch (see follow-up instruction below).
- **Migration 042** (written, not applied) — new, not originally specified
  in Prompt 4: adds `engagement.workspace_id`, a unique key, and a
  backfill. Safe to apply under the code running today. Two departures
  from what CC originally offered, **both confirmed fine 22 October
  2026:**
  - `workspace_id` is `NOT NULL DEFAULT 0`, not nullable — a nullable
    column would let the unique key treat two same-named engagements in
    different NULL states as distinct, defeating the constraint.
  - The old one-name-per-tenant key is kept until after deploy, not
    dropped immediately.
- **Migration renumbering:** the old `041` is now
  `db/migrations/held/043_workspace_drafts.sql` — renumbered because it now
  depends on 042 (the new engagement key), and moved to `held/` because
  `migrate.ps1` applies every pending file in the migrations folder; left
  in place, it would apply ahead of the #352 + UI-branch deploy it must
  wait for. The script doesn't read subfolders, so it has to be moved back
  up by hand when due (deploy step 3 below).

**What CC verified:** 845 backend tests pass (13 new — storage key carries
the workspace with no header signed; normalizer reads both key layouts;
engagements made/found/listed within one workspace; "Share a memo" scoped
to the active workspace; another tenant's workspace is refused with
nothing read; `/settings` lists the workspaces). Arity check clean on every
changed call site. TypeScript compiles; 15 UI unit tests pass. Lint: 20
pre-existing problems in touched files, none on lines CC wrote. `web/`
rebuilt; the new bundle contains the selector and the name field.

**Not verified:** the screens have not been rendered or clicked through —
no credentials to sign in, and neither the API code nor migration 042 are
on dev yet, so nothing could be exercised against the real API. Not
walked: the header picker's look and placement, Get started and "Add a
workspace," and switching workspaces. A second workspace stays half-made
until `held/043` is applied — "Add a workspace" forks its base
successfully, but taking memoranda into it is refused because another
workspace still holds the tenant's only draft.

**Deploy order, from CC — supersedes the order recorded under Prompt 3:**

1. Apply migration 042.
2. Deploy #352 and `feature/pack01-workspace-ui` together: merge, run
   `build-layer.ps1`, `terraform apply`, confirm the deployed layer.
3. Move `held/043_workspace_drafts.sql` into `db/migrations/` and run
   `migrate.ps1`.
4. Walk the journeys signed out, on the real domain.

**Follow-ups sent to CC, 22 October 2026, both folded into
`feature/pack01-workspace-ui`:**

1. Filter Share history by workspace too — flagged as not done in CC's
   report.
2. A second gap CC found and asked about directly: as built, neither
   "create from scratch" nor "create from a report you already wrote"
   ever offers to start a new workspace — both land in whichever
   workspace is active, and the Catalogue's two create routes get
   overridden by Get started (which only offers the built-in memoranda)
   for an unconfigured tenant. Confirmed fix, now sent to CC: make "Add a
   workspace" a three-way choice (one of ours / from scratch / from a
   report), each asking for the workspace name first, then building the
   template into it; the Catalogue's two create routes offer "this
   workspace" or "a new workspace" once a tenant has more than one. Still
   blocked on `held/043` for a second workspace to actually take content,
   same as the existing known gap.

Awaiting CC's updated report on this branch with both folded in.

### Settled, from earlier chat (21–22 October 2026, still valid)

1. **Document scope at upload.** Classification runs only against the
   active workspace's document types. No cross-workspace classification,
   no routing logic. The tenant (or member) picks the workspace before
   upload; classification resolves document type within that workspace
   alone.

2. **Cross-workspace document reuse: none.** A document relevant to two
   workspaces is uploaded twice, once per workspace. No dedup, no shared
   document record, no merge logic.

3. **Workspace count, gated by plan.** Base plan: one workspace. Small
   Business plan: up to 5 workspaces. No change to `build_index.md`'s plan
   names — this adds a workspace-count ceiling column (Base = 1, Small
   Business = 5, Enterprise = not stated, flagged open below).
   **Still open beneath this:** whether `plan.max_schemas_per_type` /
   `plan.max_sections_per_template` apply per workspace or aggregated
   across a tenant's workspaces — not addressed by a workspace-count
   ceiling, remains unanswered.

4. **Seats/roles vs. workspaces.** A workspace is assigned to a member
   (not every member sees every workspace by default). An admin
   sees/has all workspaces regardless of assignment — a new access
   dimension for Identity & Seats, additive to the existing role model.

5. **Billing unit — left open, noted for later.** No billing mechanism
   proposed; dependency on Component 1 stands.

### Open

- **Schema/section ceilings per workspace vs. aggregate** (item 3) — not
  yet answered.
- **Enterprise workspace-count ceiling** (item 3) — not stated; Base and
  Small Business are now set.
- **Billing unit** (item 5) — explicitly deferred, not scoped.
- **Ownership check on explicit `?workspace=`** — folded into Prompt 4's
  text; CC's Prompt 4 report does not yet answer it. Still needs a direct
  answer from CC.
- **Second commit hash on `feature/pack01-workspace-scope` (#352)** — CC's
  report truncated it twice; get the exact hash before merging.
- **Share history filtering + three-way "Add a workspace"/Catalogue fix**
  — both sent to CC on `feature/pack01-workspace-ui`; awaiting the updated
  report.

### What this amends

The live schema directly: nine `config_*` tables (migration 008) + four
runtime tables (`document`, `extracted_value`, `memo`, `memo_rewrite`) +
`tenant.active_revision` / `pack_offer`, all gaining `workspace_id` in their
keys, plus `engagement.workspace_id` (migration 042). Also:
`config_registry_spec_v1.md` (its §4 object model is already stale against
live code — this doesn't make it more stale, just confirms the spec was
never the build), `config_editors_spec_v1.md` (workspace selector ahead of
Surface 1), `pipeline_spec_v1.md` (workspace resolved before document-type
classification; upload workspace carried in the S3 storage key, not a
header), `identity_seats_spec_v1.md` (workspace assignment per seat; admin
sees all), `wallet_entitlement_spec_v1.md` / `build_index.md` economics
table (workspace-count column).

### Not decided here

Whether this ships now or is sequenced behind other live work. This
document establishes the shape, now validated against the real schema, so
nothing downstream gets built against a single-workspace assumption that's
expensive to retrofit later.
