# ARQEDIA — Backlog Item

## PACK-02 · Offerings: what ARQEDIA offers is a workspace

| | |
|---|---|
| Status | Steps 1-5 built and deployed on dev (#361-#371). C deployed and walked (#372-#375, migration 045). Plan limits built on a branch (migration 046). D decided, not built. |
| Depends on | PACK-01 (migrations 040, 042, 043; #352, #353, #354), all merged and applied on dev |
| Type | Architecture — schema migration + Config Registry + API + Get started + Catalogue + curator screens |
| Raised | 23 October 2026, from chat |

---

### The use case

admin@arqedia.com (tenant 0) builds what clients are offered. Today that is
one base and a list of memoranda over it. It should be several **offerings**
— Trade Finance, Real Estate, Private Credit Corporate, Accounts Receivable
Financing — each partitioned like a client's workspace: its own document
types, categories, facts and memoranda. A client adds a workspace by taking
an offering.

### What is live — read 23 October 2026

- Tenant 0 has **no `workspace` row**. Its whole configuration is at
  `workspace_id = 0`: 34 revisions, active revision 33, 130 templates. No
  documents.
- `pack_offer` has **no `workspace_id`**. Its primary key is `pack_key`
  alone; five rows, all tenant 0 revision 33: `base` and four templates.
  PACK-01 listed `pack_offer` as gaining `workspace_id`; migration 040 did
  not include it.
- `registry.set_offer` replaces the whole offer: `DELETE FROM pack_offer`,
  then inserts. One offer, by construction.
- `registry.fork_base` refuses tenant 0, and forks "the base" by key
  (`pack_key = 'base'`). Every client workspace starts from the same
  vocabulary, whatever it is named.
- Every client workspace's `forked_from_workspace_id` is NULL ("the pack
  tenant's configuration is in no workspace"). `forked_from_revision_id` is
  set: 1, 9, 25 or 33.
- Two client workspaces are already named for another industry and were
  forked from revision 33, the Trade Finance configuration: tenant 2's
  workspace 9 "AR FINANCING" and tenant 5's workspace 10 "REAL ESTATE".

### Settled, 23 October 2026

1. **An offering is one of tenant 0's workspaces**, published and drafted
   on its own as PACK-01 already allows.
2. **A client takes the offering's base plus the memoranda they tick** —
   Get started as it works today, scoped to one offering.
3. **Tenant 0's existing configuration becomes the first offering, named
   Trade Finance.** Real Estate, Private Credit Corporate and AR Financing
   are made as their own.
4. **No memorandum from another offering.** A client workspace's Catalogue
   offers only the memoranda of the offering it was forked from. The facts
   are partitioned; a memorandum from another offering binds facts that
   workspace does not hold.
5. **Today's client workspaces are linked to Trade Finance**
   (`forked_from_workspace_id`), so their Catalogue keeps offering what it
   offers now. **Except** tenant 2's workspace 9 "AR FINANCING" and tenant
   5's workspace 10 "REAL ESTATE", which are **left unlinked** (open item A,
   answered 23 October 2026): their Catalogue offers no memoranda of ours
   until they are linked or re-forked from their own offering.
6. **A new offering starts empty**, with no facts, document types or
   memoranda. It is built by hand, or from a report uploaded and read by the
   proposer and structured from there — the same two routes a client has.
7. **A client's own report starts from whatever the workspace holds when
   they start it** (open item B, answered 23 October 2026). No offering's
   base is forked for it. In an existing workspace that is its own facts and
   document types; a workspace made for an own report holds nothing, and is
   built by hand or from the report — as a new offering is in item 6.

### Proposed — not yet confirmed

**Migration 044**, written and held in `db/migrations/held/` until the code
below is merged and the layer deployed — the 043 pattern. Moving tenant 0's
rows out of workspace 0 breaks every reader that still looks for them there.

1. One `workspace` row for tenant 0: "Trade Finance", `active_revision` 33.
2. Tenant 0's rows in the nine `config_*` tables moved from `workspace_id`
   0 to that workspace. The four runtime tables hold nothing for tenant 0
   (to be re-counted in the migration's own check).
3. `pack_offer` gains `workspace_id BIGINT NOT NULL`, backfilled to that
   workspace; primary key becomes `(workspace_id, pack_key)`, so each
   offering has its own `base`.
4. `forked_from_workspace_id` set to Trade Finance on every client
   workspace except tenant 2's 9 and tenant 5's 10 (item 5), named by id in
   the migration rather than matched by name.

**Registry.**

- `_offer`, `offer`, `packs`, `template_packs` take the offering's
  workspace. `template_packs` for a client workspace reads its
  `forked_from_workspace_id`.
- `set_offer(workspace, ...)` replaces that offering's rows only. Its
  checks — published, holds facts, no memorandum binding a fact the
  revision does not define — are unchanged.
- `fork_base(tenant, email, name, offering)` forks the named offering's
  base and records `forked_from_workspace_id`. The tenant-0 refusal stays.
- `new_offering(name, email)` — tenant 0 only: an empty workspace and its
  draft. No published revision until the curator publishes one, so it is
  not offerable until then (`set_offer` already refuses a revision with no
  facts).

- `new_workspace(tenant, email, name)` — a client's empty workspace, for
  an own report (item 7). The same act as `new_offering`, for any tenant
  but 0; one function may serve both.

**API.** A list of offerings for Get started: name, its base's counts,
its offered memoranda. The fork route takes the offering. A curator route
to make an offering.

**Screens.**

- Get started (Add a workspace): **choose the offering first**, then the
  name, then the route; "With one or more of our memoranda" lists that
  offering's only.
- Catalogue: the active workspace's offering's memoranda only.
- Curator: the workspace picker PACK-01 built, "Add an offering" (empty;
  build or read a report), and the offer set per offering.

**Unverified.** Accepting a proposal into a workspace with **no facts at
all**. Today's proposer matches a report against facts the tenant already
holds and proposes new ones beside them; every route into it so far
starts from a forked base. An empty workspace — a new offering, or a
client's own-report workspace — is the first case with nothing to match.
To be exercised before items 6 and 7 are called built.

### Also raised, 23 October 2026 — seats and deleting a workspace

**C. An administrator assigns workspaces to member seats.** Already
settled under PACK-01 (its item 4: a workspace is assigned to a member, an
administrator sees all). **Settled 23 October 2026, all asked in-session:**

- Table `seat_workspace(tenant_id, seat_id, workspace_id)`: approved as
  proposed (migration 045, with `assigned_by` and `assigned_at`).
- An invitation's workspaces wait in a second table,
  `seat_invitation_workspace(invitation_id, workspace_id)`, and are copied
  to the seat when the invitation is accepted.
- Existing members get every workspace their tenant holds when this ships.
- A member's invitation names at least one workspace; an administrator's
  names none.
- An administrator made a member keeps every current workspace.
- A new workspace is assigned to no member.

Built on `feature/pack02-seat-workspaces`. Unprompted choices made in the
build: a member asking for a memo, document or share in a workspace not
theirs is answered "not found", as another tenant's number is; the invite
form starts with the workspace in use ticked; a member's own seat edit
needs at least one workspace.

**Workspace count by plan (PACK-01 settled 3), settled 23 October 2026:**
Base 1, Small Business 5, Enterprise **to be negotiated** - a per-tenant
number set when negotiated, **no limit until it is set**. A downgrade to a
plan that holds fewer workspaces than the tenant has is **refused**, as a
seat downgrade already is; nothing is deleted for the tenant. On the day
this ships no Base client holds more than one (read on dev: tenants 1, 9,
10 hold one each), so nothing is deleted then either; had one, the extras
were to be deleted and Trade Finance kept. Tenant 0 is exempt (proposed, not
asked): its workspaces are offerings. Not built.

**Settled further, 23 October 2026, all asked in-session:** Enterprise's
negotiated number is `tenant.workspace_limit`, read only on Enterprise;
tenant 0 is exempt; the limit is shown in the app only, and joins the
pricing page when the site is redone before launch. Built on
`feature/pack02-workspace-limit`: migration 046 (`plan.workspace_count`,
`tenant.workspace_limit`), `billing.workspace_limit` and
`require_workspace_room` before `POST /config/fork`, the downgrade refusal,
a Workspaces row on the plan table, and the picker and Add a workspace
saying so at the limit. A hidden workspace (D) is not yet counted apart.

**D. An administrator deletes a workspace from the tenant**, with
sufficient warnings and steps. This is the first delete in the product and
sits against "additive and non-destructive" and "read once, never again",
so its shape was asked rather than proposed:

- What it removes: its configuration and revisions, engagements,
  documents and their S3 objects, extracted values, claims, memos and
  rewrites, and its shares (grants, access log, `shares/` PDFs — the
  per-workspace counterpart of `share.purge_tenant`, which nothing calls).
- What it never touches: `wallet_ledger` and its buckets. Charges stay
  charged; nothing is refunded by deleting.
- **Settled 23 October 2026:**
  - **Hidden, then removed.** Hidden at once and restorable for a period,
    then removed for good. **The period is six months** (set 23 October
    2026; 30 days had been proposed).
  - **The last workspace cannot be deleted.** Removing everything is
    account deletion, a separate act.
  - **Steps:** the counts it holds shown (engagements, documents, memos,
    active shares), its name typed, and a code emailed to the
    administrator entered before it goes. The administrator is recorded.
  - **Members are reassigned on delete.** Deleting asks which workspace
    the members assigned only to this one move to. Depends on C.
- The written manual procedure for account deletion (What is open, 20
  October 2026) is the same list for a whole tenant; one should be built
  from the other.

### Sequence

1. Migration 044, written and tested on a copy of the rows; held.
2. Registry and API, with tests. Layer rebuilt.
3. Curator screens: offerings, Add an offering, offer per offering.
4. Client screens: choose an offering, Catalogue scoped. `web/` with it.
5. Apply; 044 out of held and applied; walk both tenants signed in.
6. C: seat-to-workspace assignment.
7. D: deleting a workspace.

One branch per step, stopping at the end of each for review.
