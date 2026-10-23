# ARQEDIA — Backlog Item

## PACK-02 · Offerings: what ARQEDIA offers is a workspace

| | |
|---|---|
| Status | Shape agreed in chat 23 October 2026; nothing built. Two items open (below). |
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
   offers now.
6. **A new offering starts empty**, with no facts, document types or
   memoranda. It is built by hand, or from a report uploaded and read by the
   proposer and structured from there — the same two routes a client has.

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
4. `forked_from_workspace_id` set to Trade Finance on client workspaces per
   item 5 — which ones is open item A.

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
starts from a forked base. An empty offering is the first case with
nothing to match. To be exercised before item 6 is called built.

### Open

- **A.** Tenant 2's "AR FINANCING" and tenant 5's "REAL ESTATE" hold the
  Trade Finance vocabulary. Linked to Trade Finance like the rest (what
  they hold), or left unlinked until re-forked from their own offering?
- **B.** A client's own-report routes ("from scratch", "from a report you
  already write") also fork a base. Proposed: the base of the offering
  chosen on the same screen. To confirm.

### Sequence

1. Migration 044, written and tested on a copy of the rows; held.
2. Registry and API, with tests. Layer rebuilt.
3. Curator screens: offerings, Add an offering, offer per offering.
4. Client screens: choose an offering, Catalogue scoped. `web/` with it.
5. Apply; 044 out of held and applied; walk both tenants signed in.

One branch per step, stopping at the end of each for review.
