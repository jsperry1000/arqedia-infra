# ARQEDIA — Implementation record

## TPL-02, steps 1 and 2 · Base and templates

| | |
|---|---|
| Specification | `docs/backlog-items/ARQEDIA_spec_TPL02_base_and_templates.md` |
| Branches | `tpl-base-split` (merged, 3f72c93, #141), `tpl-fork` |
| Written | 15 September 2026 |

What was found in the code, what was decided because of it, and what was
verified. Kept because the findings cost real reading and would otherwise have
to be rediscovered from scratch.

---

## Step 1 — migration 017

### What the code said

**Section bindings are separable by table, cleanly.**

- `config_section_field` holds section-to-fact bindings, keyed
  `(tenant_id, revision, template_key, section_key, field_key)`.
- **There is no document-type-to-fact table.** That relation is indirect:
  `config_field.schema_key` puts a fact in a schema, and `config_type_schema`
  maps a document type to schemas. "Which facts are sought in which document
  type" is the join of those two. The editor's `set_field_documents` works by
  finding or minting the schema fed by exactly that set of types.
- So the split is by table with no row-level filtering:
  - **Base** — `config_category`, `config_document_type`, `config_schema`,
    `config_type_schema`, `config_field`.
  - **Template** — `config_template`, `config_section`, `config_section_field`.
- `008` declares no foreign keys, so a template revision holding bindings whose
  `field_key` lives in another revision is structurally fine. The reference is
  by key and is only resolved when both are copied into one tenant revision.

**Several readers assume one revision is a whole configuration.** Recorded in
the specification under "What breaks when a revision is not whole".

**`packs()` ordering was the mapping, by accident.** It sorts by revision
descending, so `ensureDraft`'s `packs[0]` is the highest-numbered pack. Adding a
pack would silently change what every new tenant got.

### What was decided

| | |
|---|---|
| Ordering, in the window before step 2 | Base numbered highest, so `packs[0]` is the base — the thing first run should fork. Correct rather than merely tolerable |
| `pack_key` for the existing memorandum | `due-diligence`. Not `stage1-kyc`, which is build provenance and reads as noise in a customer-facing chooser. Not `kyc-aml`, which overclaims — the template carries financial and business sections |
| `template_key` | Stays `stage1-kyc`, untouched. It names a memorandum inside a tenant's configuration; `pack_key` names the pack it ships as. Different things, not to be made to match |
| The old revision 1 of tenant 0 | `kind = 'legacy'`, `pack_key = 'stage1-kyc'`. Every row left as `009` wrote it. Cheaper than a status column and reads better |
| Splitting in place | Refused. It would have meant deleting revision 1's template rows, and that revision is the record of what was forked into both live tenants. The two new revisions sit beside it |

### Verified, by query

- Tenant 0 holds three revisions: 1 legacy, 2 template/`due-diligence`,
  3 base/`base`.
- The base carries what revision 1 carried — 4 categories, 27 document types,
  8 schemas, 36 routings, 105 fields — identical to the before-state.
- The template carries 1 template, 8 sections, 63 bindings. Identical.
- Clean both ways: the base holds no template rows, the template holds no fact
  rows.
- Revision 1 untouched.
- Both live tenants unaffected, compared against a before-state rather than
  assumed. Tenant 1: 38 revisions, active 37, 119 facts, 85 bindings.
  Tenant 2: 53 revisions, active 53, 196 facts, 390 bindings.

### Found on the way

**`.sql` is normalised by `core.autocrlf`, not by `.gitattributes`** — which
covered `.tf` and `.py` only. A machine setting rather than a repository one, so
every `.sql` file would do the CRLF dance on somebody else's machine.
`*.sql text eol=lf` added.

---

## Step 2 — `fork_base` and `fork_template`

### What the code said

**Published revisions cannot be written into.** `config.load` caches by
`(tenant_id, revision)` for the life of the container and never invalidates —
"A revision is IMMUTABLE, so it is cached." Adding rows to the active revision
would be invisible to warm containers and would change a snapshot that
`document.config_revision` and `memo.config_revision` pin.

**The draft is the only mutable revision.** `editor._require_draft` gates every
editor write; `open_draft` copies the latest published revision into revision 0;
`publish` copies the draft into a new revision and moves `active_revision`.

**Everything that uses a memorandum reads the active revision, not the draft.**
`composition/app.py:626` takes `config.active_revision(tenant_id)`.
`GET /templates` and `generate()` both use `config.for_tenant`. So a template in
the draft is editable immediately and cannot be generated from until Publish.

**`validate` is only ever asked about the draft.** `GET /config/draft/validate`
and `publish` both pass `registry.DRAFT`. Nothing validates a pack revision and
nothing can — `tenant_id` comes from the token, so tenant 0 is unreachable.

### What was decided

| | |
|---|---|
| Where `fork_template` writes | The draft, always. Opening one if none exists, and never publishing by itself. One code path for first run and for six months later |
| Does first run publish | Yes, once, at the end. Base published as revision 1, every ticked template into the draft, then one publish. Otherwise a new tenant lands on facts with no memorandum and a Publish button whose purpose they have no way to understand — the first thing they meet being a step whose meaning depends on knowing what a revision is |
| An existing draft | Add into it, and say so. Refusing is honest but leaves the person stuck: their only way forward is to publish or discard work they may not be ready to decide about, in order to do something unrelated. The report tells them it went in alongside their own changes and that Publish ships both |
| A template before a base | Refused at the fork. Sections with no facts behind them is exactly what the validator exists to catch, and catching it at the fork is better than discovering it at Publish |
| `validate` | Unchanged in this step. If `fork_template` writes into the draft and adds what is missing, the draft stays whole and every bound field exists |

### What was built

- **`fork_base(tenant_id, email, pack_revision=None, pack_key="base")`** — what
  `fork()` did, restricted to a revision whose `kind` is `base`. Keeps the guard
  refusing a tenant with a published revision. Refuses a template or the legacy
  pack, either of which would give a tenant a configuration that extracts
  nothing.
- **`fork()` stays and delegates.** Its default moved from `pack_revision=1` to
  `None`, because revision 1 of the pack tenant is now the legacy pack and would
  be refused. Callers passing a revision are unaffected.
- **`fork_template(tenant_id, email, pack_key)`** — works out everything before
  writing anything: the facts the template binds that the draft lacks, their
  columns where a fact is a table, the schema each belongs to, the document
  types those schemas are fed by, and the categories those types sit in. Writes
  in reference order. **Every statement is `INSERT IGNORE`**, which is the
  skip-at-the-statement rule and what stops a shared key failing half-way.
- **`packs()` selects `kind = 'base'`**, ordered by `pack_key`. The legacy
  revision is no longer offered. `template_packs(tenant_id)` is a separate list
  carrying section and binding counts and whether the tenant already holds each.
- **Two admin routes** — `GET /config/templates/available`,
  `POST /config/templates/fork`. `POST /config/fork` now calls `fork_base`.

### Verified against dev

Exercised on a scratch tenant, 9001, then every row removed.

- Offers: one base (27 types, 105 facts), one template (`due-diligence`,
  8 sections, 63 bindings).
- Guards: a template before a base refused; a second base refused.
- First run: `fork_base` writes revision 1; `fork_template` puts 8 sections and
  63 bindings in the draft, adding no facts because they are all there;
  `validate` passes.
- Re-fork after edits: a renamed section title survived, nothing duplicated.
- **The March case.** Deleting `f_persons`, its 8 columns, the KYC schema and
  the pep-screen type, then re-forking, brought all nine facts back with the
  schema and the type, reported them, and left `validate` passing.
- Live tenants identical before and after, drafts untouched, `active_revision`
  still the latest published for both. No scratch rows left anywhere.

---

## Two behaviours to reconsider

**Re-forking restores bindings the tenant deliberately removed.** Unbinding nine
facts from a section and re-forking the same template puts them back. It follows
from additive forking — an absent binding is not "held" — but an unbound fact is
a deliberate act in the same way a deleted one is, and the specification says
deliberate deletions are not resurrected. Not a blocker. Probably wrong.

**A document type deleted while its facts are kept is not restored.** Types are
added only to support facts being added. This matches the specification and is
deliberate.

---

## State at the end of step 2

`tpl-fork`, off `main` at 3f72c93. The routes and the Lambda change do not exist
in API Gateway until `terraform apply` runs. No front end — that is step 3, the
Get started chooser.
