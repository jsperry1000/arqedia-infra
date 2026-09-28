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

### State at the end of step 2

`tpl-fork`, off `main` at 3f72c93. The routes and the Lambda change do not exist
in API Gateway until `terraform apply` runs. No front end — that is step 3, the
Get started chooser.

---

## Step 3 — the Get started chooser

`tpl-chooser`, 0d1ef8a.

### What the code said

**`Welcome.tsx` was inert.** A static page whose only prop was `onStart`,
wired to `setChoosing(true)` — Get started merely opened the rail's flyout. It
fetched nothing and knew nothing about packs.

**`ensureDraft` had exactly three callers**, all inside `ReportChooser` in
`App.tsx`: `open()`, `scratch()` and `fromReport()`. So the rail chooser was the
only path through it, and all three changed together.

**Nothing exposed `tenant.forked_pack`.** `signup/app.py` writes it and no code
reads it. `GET /config` returned `active_revision`, `revisions`, `draft` and
`templates`; `GET /settings` the name, plan, flags, logo and colours. The answer
somebody gave at signup was being discarded and the question asked twice.

**A second forking path exists that is not `ensureDraft`.** `Configure.tsx` has
its own first-run screen calling `api.packs()` and `api.forkPack()`. It does not
depend on ordering — a person picks from a list — but since the split that list
returns bases only while the screen still calls them memoranda, and forking from
it leaves a tenant with facts and no memorandum.

**Which partial states are recoverable**, read from the merged code rather than
assumed:

| Call | Repeatable |
|---|---|
| `fork_base` | **No.** Raises where a published revision exists |
| `fork_template` | Yes. Every write is `INSERT IGNORE` |
| `publish` | Yes. Returns `{published: false, validation}` rather than throwing; the draft is untouched |

### What was decided

| | |
|---|---|
| `forked_pack` on `GET /config` | Yes. One field. Signup asked the question; discarding the answer means asking it twice |
| `Configure.tsx`'s first-run screen | Left alone, recorded as **TPL-03**. It is wrong rather than dangerous, and changing it is its own branch |
| The base fork | **Conditional, always.** Re-read `GET /config` and fork only where `revisions` is empty. That is what makes every partial state recoverable by pressing again |
| The publish warning | **In front of the button, not only in the report.** `publish` ships the whole draft and cannot be selective. Somebody about to press Get started with their own edits open needs to know before, not after. No warning where there is no draft — a first-run tenant has nothing of their own to ship, and a warning there is noise |

### What was built

- **`Welcome.tsx` is the chooser.** Each memorandum with its name, its section
  count and whether it is already held; the count reveals that memorandum's
  headings. Signup's answer pre-ticks and decides nothing.
- **Get started** re-reads the configuration, forks the base only where there is
  no published revision, then each ticked memorandum, then publishes once. A
  refused publish is reported as a refusal rather than thrown.
- **First run shows the introduction**; a tenant who already holds a base and
  memoranda gets "Add a memorandum" instead.
- **The report lands on Configure** — a note above the editor naming the
  memoranda, the revision they published as, and the facts, document types and
  categories they brought. Named rather than counted: six, then "and N more".
- **Ordering is gone.** `ensureDraft` calls `forkBase()`, and nothing picks a
  pack by position.
- **`template_packs()` returns each pack's label and headings.** `pack_key` is
  an identity and the note is provenance; neither belongs in front of a
  customer.

### Two things the render caught that reasoning had not

Both found by looking, which is the rule.

- A row carrying "already yours" pushed its count 80px left of the others, so
  the column of numbers could not be compared. The marker now reads before the
  count and they align.
- The count was mouse-only. It takes focus now. The popover was measured to
  overlay the rows beneath rather than displace them, and to stay inside the
  viewport on both edges.

### Verified

Routes confirmed by call rather than by assertion, and discriminated against a
sibling path because something answers every `/config/*` GET with 401:
`GET /config/templates/available` → 401 where `GET /config/templates/nope` →
404; `POST /config/templates/fork` → 401 where an unknown POST → 404.

`tsc -b && vite build` clean, 635 modules. Both Lambda files compile.

---

## Step 4 — the starter-pack step comes out of sign-up

`signup-no-pack`, b0203ef.

### Why

TPL-02 moved the choice of memoranda to Get started, where there is room to
show what each contains. Sign-up still asked it — step 4 of six, single-select
radios over a list including templates that do not exist. **A person was asked
the same question twice, and first in the worse place.**

Found by walking the live flow rather than reading the code: the screen at
`/signup` looked nothing like what TPL-02 had built, because it was not the
screen TPL-02 built.

### What the code said

**`pack` is optional the whole way down.** `api.signup` types it `pack?:
string`; `begin()` binds `None` to an `isNull` parameter; `pending_signup.pack`
and `tenant.forked_pack` are both `VARCHAR(64) NULL` with no default.

**The only reader was `config_state` → `Welcome.tsx`**, and both are null-safe
as written — `(chosen ?? "").split(",").filter(Boolean)` returns an empty set.

**`SIGNUP_PACKS` was used nowhere but `SignUp.tsx`.**

**The six-assumption was not in the CSS.** `.stepper` is flex with `flex: 1`
and a percentage connector; no `nth-child`, no fixed widths. **The real
six-assumption was five hard-coded step indices in `SignUp.tsx`** — exactly
where an off-by-one lands.

### What was decided

| | |
|---|---|
| What sign-up sends as `pack` | Nothing. Omitted from the body. A display-shaped string matching no memorandum is a lie in a field whose whole job is matching |
| `forked_pack` | **Go further than the brief.** If it is uniformly null from now on, the pre-tick it drives never fires again — so it is not inert, it is dead, and dead code that looks live is worse than either. `verify()` stops writing it, `config_state` stops returning it, `Welcome.tsx` stops pre-ticking from it |
| The column itself | Stays. Dropping it is a destructive migration for no gain, and the two existing rows record something that was once true |
| Knowing what drew somebody in | Lead capture on the site, not this column |
| The site's own `PACKS` array | Flagged, not touched. Step 5 of the specification's sequence and a separate project |

### What was built

- Five steps: details, organisation, region, second administrator, verify.
- **The five hard-coded indices became two named constants**, so they cannot
  drift apart.
- The summary drops the starter-pack row.
- `SIGNUP_PACKS` removed from `mock.tsx`.
- `forked_pack` and `pack` out of the TypeScript types. `begin()` still accepts
  `pack` and `verify()` still selects it, so no column position moves.

### Verified

`tsc -b && vite build` clean; both Lambda files compile. The flow walked in a
headless browser: five evenly spaced steps, "Continue" on 1 to 3 and "Send my
code" only on 4, one request out with no `pack` in its body, step 5 asking for
the code with "Start the trial" disabled until one is typed.

### Found on the way

- **The marketing site's `PACKS` array lists six memoranda where one ships**,
  and its wording has drifted from `mock.tsx` — "eligibility and ineligibility
  tests" against "eligibility tests", curly quotes in Project "X". Recorded in
  the specification as open item 5.
- **A stray `configure_screen.tsx` at the repository root**, carrying a
  "Starter pack" fallback label. Not under `ui/src` and not part of the build.
- **`CLAUDE.md` is out of date** on two counts: "Forking the chosen packs at
  first run" is done, and `forked_pack` no longer records the choice.

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

## Still open

**TPL-03 · `Configure.tsx`'s first-run screen is now wrong.** Since the split it
offers bases while calling them memoranda, and forking from it leaves a tenant
with facts and no memorandum. It does not depend on ordering, so it is wrong
rather than dangerous. Its own branch.

**The two behaviours above** — restored bindings, and unrestored document
types.

**`CLAUDE.md`** needs both TPL-02 lines corrected once step 4 merges.

**The stray `configure_screen.tsx`** at the repository root.

---

## State

Steps 1 to 3 merged. Step 4 on `signup-no-pack`, b0203ef, pushed and not
merged.

First run now works end to end: a tenant signing up, reaching Get started,
ticking memoranda and pressing the button ends on a published revision holding
one set of facts and the memoranda they chose over it.
