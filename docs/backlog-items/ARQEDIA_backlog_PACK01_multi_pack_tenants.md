# ARQEDIA — Backlog Item

## PACK-01 · Multi-workspace tenants

| | |
|---|---|
| Status | Shape settled against the live schema; four schema blockers resolved. Ready for Prompt 2. |
| Priority | Decide before further config-registry work locks in single-partition assumptions |
| Type | Architecture — schema migration + Config Registry + Config Editors + Pipeline + Identity & Seats + Wallet & Entitlement |
| Raised | 21 October 2026, from chat |
| Updated | 22 October 2026 — CC read the live schema under Prompt 1; the spec's object model was never built, this document is rewritten against what's actually live |

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

- **Draft identity confirmed resolved** by the real-fix decision above — a
  workspace's own `(tenant_id, workspace_id, 0)` is its draft, no collision
  across a tenant's workspaces. No longer a blocker.
- **Schema/section ceilings per workspace vs. aggregate** (item 3) — not
  yet answered.
- **Enterprise workspace-count ceiling** (item 3) — not stated; Base and
  Small Business are now set.
- **Billing unit** (item 5) — explicitly deferred, not scoped.

### What this amends

The live schema directly: nine `config_*` tables (migration 008) + four
runtime tables (`document`, `extracted_value`, `memo`, `memo_rewrite`) +
`tenant.active_revision` / `pack_offer`, all gaining `workspace_id` in their
keys. Also: `config_registry_spec_v1.md` (its §4 object model is already
stale against live code — this doesn't make it more stale, just confirms
the spec was never the build), `config_editors_spec_v1.md` (workspace
selector ahead of Surface 1), `pipeline_spec_v1.md` (workspace resolved
before document-type classification), `identity_seats_spec_v1.md`
(workspace assignment per seat; admin sees all), `wallet_entitlement_spec_v1.md`
/ `build_index.md` economics table (workspace-count column).

### Not decided here

Whether this ships now or is sequenced behind other live work. This
document establishes the shape, now validated against the real schema, so
nothing downstream gets built against a single-workspace assumption that's
expensive to retrofit later.
