# Config Registry — Spec v1.0

**DD SaaS product · greenfield · design spec**
Companion to *Wallet & Entitlement Gate v1.0*. Component 2 of 9.

---

## 0. Status of every claim here

Every rule below is a decision made for this product. Nothing is inherited from
the eBL build, which is out of scope by instruction. Items requiring a decision
from you are marked **OPEN** and collected in §9. One item is **PROPOSED**:
the editing role (§8).

---

## 1. Scope

**Owns:** the four configuration objects a tenant authors — categories,
document types, schemas, templates — plus the mapping between them, their
versioning, and the validation that runs before a version goes live.

**Does not own:** the editors themselves (component 3), extraction or
composition (component 4), or money (wallet spec).

**Why it comes first:** the three editors, the pipeline, and the share all read
from it. Its versioning rules decide whether a memo produced in March still
reproduces in September.

---

## 2. The four objects and the chain

```
category            "Corporate", "Financial", "KYC/AML"
   └── document_type    "Certificate of Incorporation", "Audited Accounts"
          └── schema         field set + extraction prompt
                 └── template     sections, each bound to fields
```

A fact reaches a memo through four links. A break at any link is silent — the
fact simply never appears. Making that silence visible is the main job of §5.

The `document_type → schema` link is **many-to-many**: one type can feed several
schemas, one schema can be fed by several types. This is where duplicates,
overlaps and zero-reads originate, and it is the only link that needs its own
editing surface.

---

## 3. Core decisions

**3.1 — Versioning is a whole-registry snapshot, not per-object.**

A memo depends on the entire chain across all four object kinds. Per-object
versions would require pinning a *set* of versions and resolving cross-object
references at each — a dependency-graph problem that gets worse with every
edit. A snapshot is a single integer.

So: one mutable **draft** per tenant, and an append-only series of immutable
**revisions**. Editors write the draft. Extraction and composition read a
revision, never the draft. Publishing copies draft → new revision.

**3.2a — Fields may repeat together as a row.**

Some information only means anything in pairs. A shareholder's name is
meaningless without the percentage beside it; a bank's name is meaningless
without knowing it is the bank rather than the auditor.

Fields sharing a `group_key` repeat as a unit. Extracted values carry a
`row_ordinal` saying which repetition they belong to, so the third name stays
attached to the third percentage. Templates bind a group as a table rather than
as loose fields.

Without this, two parallel lists of values have no reliable correspondence and a
memo can put the wrong percentage against the wrong shareholder with nothing
flagging it. It is trivial before any tenant data exists and cannot be
retrofitted afterwards.

**3.2 — Fields have stable IDs; names are display only.**

This is the highest-leverage decision in the document. A tenant renaming
"Reg. No." to "Registration Number" must not orphan two years of extracted
values. Identity lives in an immutable `field_id` minted at creation; the label
is mutable metadata. Rename is free. Delete is a genuine break, and is treated
as one (§6).

**3.3 — Validation runs at publish, not at save.**

A draft mid-edit is legitimately inconsistent — a schema exists before anything
routes to it. Blocking every save would make the editors unusable. Publish is
the gate: the full validator runs, and a failing draft cannot become a
revision.

**3.4 — Retirement falls out of snapshots.**

There is no "retired" flag. A document type absent from revision 12 but present
in revision 11 is retired going forward, and every document filed under
revision 11 still resolves against revision 11. Non-destructive by
construction, with no tombstone rows to maintain.

**3.5 — Fork copies, never references.**

Starter packs live in a reserved pack tenant. Forking deep-copies a pack
revision into the new tenant as its revision 1. Our subsequent edits to a pack
never reach a tenant who already forked it.

---

## 4. Data model

Aurora MySQL, same cluster as the wallet. `BIGINT` keys, `VARCHAR` +
lookup tables rather than MySQL `ENUM`, InnoDB.

```
registry_revision     revision_id PK, tenant_id FK, revision_no,
                      state,                    -- draft | published
                      published_at, published_by, forked_from_revision_id NULL,
                      UNIQUE KEY (tenant_id, revision_no)

category              category_id PK, revision_id FK, category_key,
                      label, sort_order

document_type         document_type_id PK, revision_id FK, category_id FK,
                      type_key, label, description

schema_def            schema_id PK, revision_id FK, schema_key, label,
                      extraction_prompt TEXT, handler_code

schema_field          schema_field_id PK, revision_id FK, schema_id FK,
                      field_id,                 -- STABLE across revisions
                      label, data_type, cardinality, required TINYINT(1),
                      group_key NULL,           -- fields sharing a key repeat as a row
                      sort_order

type_schema_map       revision_id FK, document_type_id FK, schema_id FK,
                      PK (revision_id, document_type_id, schema_id)

template              template_id PK, revision_id FK, template_key, label,
                      output_format            -- pdf | docx | both

template_section      section_id PK, revision_id FK, template_id FK,
                      heading, narrative_prompt TEXT, sort_order

section_binding       section_id FK, field_id,  -- binds by STABLE field_id
                      sort_order,
                      PK (section_id, field_id)

draft_lock            tenant_id PK, holder_seat_id FK,
                      acquired_at, last_heartbeat_at
                      -- one row per tenant, deleted on release
```

**Every object row carries `revision_id`.** Publishing duplicates every row
into the new revision. At the scale of one tenant's configuration — dozens of
types, tens of schemas, a handful of templates — this is a few hundred rows per
publish. Copy-on-publish is the whole versioning mechanism; there is no diffing
and no reconstruction.

**`field_id` is minted once and copied forward unchanged** through every
publish. `schema_field_id` is the row; `field_id` is the thing extracted values
and template bindings point at.

**Keys vs. IDs.** `category_key`, `type_key`, `schema_key` are tenant-authored
stable slugs used in exports and API responses. Row IDs are per-revision and
must never leak outside the registry.

---

## 5. Publish validation — the coverage surface

Six checks. All must pass; each returns the offending objects so the editor can
render them inline rather than showing a generic error.

| # | Check | Failure means |
|---|---|---|
| 1 | Every `document_type` maps to ≥ 1 schema | Uploads of this type extract nothing — a **zero-read** |
| 2 | Every `schema_def` is mapped from ≥ 1 type | An **orphaned schema** that can never be produced |
| 3 | Every `section_binding.field_id` resolves to a live `schema_field` | Template section renders permanently empty |
| 4 | Every `schema_def.handler_code` is a built handler | Extraction dispatch fails at runtime |
| 5 | Every `template` has ≥ 1 section with ≥ 1 binding | An empty deliverable |
| 6 | No two schemas mapped from the same type share a `field_id` | **Overlap** — two extractions write the same field, last one wins silently |
| 7 | No `document_type` maps to more than `plan.max_schemas_per_type` schemas | Extraction fan-out exceeds the plan ceiling (*Pipeline* §8.2) |
| 8 | No `template` holds more than `plan.max_sections_per_template` sections | Composition fan-out exceeds the plan ceiling (*Pipeline* §8.2) |

Check 6 is the one that has no analogue in a hand-built system and is worth the
effort: it catches the case where a tenant maps a document type to both a
"Corporate Details" and a "Company Identity" schema that both extract
registration number, and then cannot understand why the value flips.

**Check 3 is not sufficient on its own — CARRIED FORWARD FROM BUILD.** Publish
validation catches a broken binding only when someone publishes. The editors
must prevent the disconnect arising in the first place:

- A template naming a field the schemas do not define is a **blocking** error at
  save, not a warning at publish. The memo consequence is a confident false
  negative: the report states a fact was not provided when it was extracted
  under a different name. That is the worst output this product can produce.
- **Renaming a field must propagate to every template binding automatically.**
  Identity is the stable `field_id`, so a rename is a label change and nothing
  should break — but the editor must show which templates are affected before
  the rename is accepted.
- **Deleting a field must open every template that binds it** and require the
  binding be removed or repointed before the delete is accepted. A template
  cannot be left holding a reference to something that no longer exists.
- Schemas and templates are edited on separate screens but are **one chain**.
  The editors must make them flow from each other rather than allowing them to
  drift apart between publishes.

Observed in the Stage 1 build: the template still named placeholder field
identifiers after the field definitions were replaced, and the resulting memo
reported the entity's legal name and registration number as missing when both
had been extracted and cited.

**Warnings, not blocks:** a category with no types; a schema field bound by no
template; a template not reachable from any type. All legitimate mid-build,
none silently harmful.

**Checks 7 and 8 are plan-dependent** and are the only validation rules whose
outcome can change without the tenant editing anything. On downgrade, a
configuration that exceeded the new plan's ceilings cannot publish until
trimmed; the currently published revision keeps running unchanged. The plan
change screen names the offending objects before confirming.

---

## 6. What happens to already-extracted data

Extracted values are stored as `(document_id, field_id, value)` and tagged with
the revision that produced them. They are **never** re-extracted automatically.

Consequences, stated plainly because this is the part tenants will ask about:

- **Rename a field** — nothing happens. Identity is `field_id`. Old values keep
  binding. This is why §3.2 matters.
- **Add a field** — old documents have no value for it. Sections bound to it
  render as uncovered for those documents. Tenant may re-extract, paying $0.25
  per document, or accept the gap.
- **Delete a field** — old values become unreachable. They are not deleted;
  they simply stop being bound. Restoring the field by the same `field_id`
  restores them. Publish should warn with a count of affected values.
- **Change the extraction prompt** — old values stand. Only documents filed
  after the publish get the new prompt.

**Re-extraction is always a tenant-initiated, billable action.** No config edit
ever silently spends a tenant's balance — that rule is absolute, and it is why
automatic re-extraction was rejected.

---

## 7. Starter packs

A reserved pack tenant holds published revisions of each pack. **Settled
initial set: KYC/AML, Vendor Onboarding, Credit File.**

Fork is: deep-copy the pack revision into the target tenant as revision 1,
minting fresh row IDs but **preserving `field_id` values**. Preserving them
means a tenant who forks the KYC pack, and later imports something exported
from another KYC-pack tenant, has bindings that line up. That interoperability
is free if we do it now and impossible to retrofit.

`forked_from_revision_id` is retained for support and for telling a tenant that
their pack has a newer upstream version. Upgrade is a manual, opt-in operation,
not a push.

---

## 7A. Export and import

A tenant may export their **entire configuration** — categories, document
types, schemas including extraction prompts, templates, and the mapping — as a
single portable file, and import it into another account.

- **Format:** JSON, carrying `field_id` values verbatim. Preserving them is what
  makes an import bind correctly against extracted values, and what lets two
  tenants forked from the same pack exchange config.
- **Export is always available**, in every entitlement state including `capped`.
  A tenant locked out for non-payment can still take their own IP with them.
  It is the single exception to `capped` being read-only, and withholding it
  would be indefensible.
- **Import lands in the draft**, never directly as a published revision, and is
  therefore blocked in `capped` along with all other config editing.
- **Import is all-or-nothing** and replaces the draft. Merging two
  configurations is a genuinely hard problem — conflicting `field_id`s, colliding
  keys — and is out of scope.
- **What export does not contain:** documents, extracted values, memos, share
  grants, or ledger history. Configuration only.

---

## 7B. Deletion

**Account deletion scrubs everything.** Config, all revisions, documents,
extracted values, memos, share grants, storage prefix. Irreversible. No
archive, no recovery path.

Consequences of the simple rule, all of them good:

- No retention period to defend.
- No identity-verification vendor to select or build.
- No statutory erasure exposure from holding a closed account's data.
- No conflict with the wallet spec.

**Export (§7A) is therefore the only way a tenant preserves their
configuration.** The deletion flow must offer export before confirming, and the
confirmation must state plainly that nothing survives. That prompt is the whole
mitigation and it is not optional.

Ledger history is retained for the statutory accounting period. It is financial
record, not tenant data, and is out of scope for deletion.

---

## 8. Interfaces

```
Registry
  get_draft(tenant_id)                      → Draft
  publish(tenant_id, actor)                 → Revision | ValidationFailure[]
  get_revision(tenant_id, revision_no)      → Revision   (immutable)
  current_revision(tenant_id)               → Revision
  fork_pack(tenant_id, pack_key, actor)     → Revision
  validate(tenant_id)                       → ValidationFailure[]   -- dry run
  export_config(tenant_id, revision_no?)    → ConfigBundle (JSON)
  import_config(tenant_id, bundle, actor)   → Draft | ImportFailure[]
  acquire_lock(tenant_id, actor, force?)    → Lock | LockHeld(holder, since)
  heartbeat_lock(tenant_id, actor)          → Lock | LockLost
  release_lock(tenant_id, actor)            → void
```

The pipeline calls `current_revision` once at the start of a job and carries the
`revision_id` through filing, extraction and composition. It never re-reads
mid-job — a publish landing mid-run must not change the rules under a job that
already quoted and charged.

**Settled — `admin` is a seat role.** Every seat is `admin` or `member`. At
least one admin per tenant at all times; the last admin cannot be demoted or
removed. Admin-only actions: publish, fork, import, plan change, top-up,
account deletion. Members upload, generate, share, and read config without
editing it.

**Consequence worth noting:** on a 2-seat Base plan, one of only two users
carries every destructive action. Losing that person locks the tenant out of
publishing and paying. A second admin should be encouraged at signup, and
support needs a documented path for admin recovery on a 2-seat account.

**Settled — the draft takes an exclusive lock.** One admin edits at a time.

- **Acquire** on opening any editor. A second admin gets read-only view of the
  draft plus who holds the lock and since when.
- **Heartbeat** while the editor is open. **PROPOSED:** 60-second interval,
  15-minute idle expiry — tuning numbers, not decisions.
- **Release** on explicit exit, on publish, or on expiry.
- **Takeover** is permitted once the lock has expired, with a confirmation
  naming the current holder. Unpublished draft changes are preserved, not
  discarded — the lock governs who may write, not whose work survives.

The takeover path is not optional. On a 2-seat Base plan a stale lock held by
the other admin is a total editing lockout, and there is no third person to
resolve it.

---

## 9. Open

**Settled since v1.0 draft:** starter packs (three), admin role (seat-level),
export/import (full config including prompts), account deletion scrubs
everything, draft locking (exclusive lock with expiry and takeover).

Remaining:

1. **Handler set** — §4's `handler_code` validates against a list of built
   extraction handlers defined by component 4. Held for the build phase by
   decision; registry needs no change when it lands.
2. **Lock timing** (§8) — heartbeat interval and idle expiry are proposed
   numbers, tuned during build.

This component is otherwise closed.
