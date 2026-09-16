# ARQEDIA — Specification

## TPL-02 · One base, and templates over it

| | |
|---|---|
| Status | Specified. Nothing built |
| Supersedes | The "starter pack" model as forked by `registry.fork()` |
| Raised | 15 September 2026 |
| Blocks | Forking the packs chosen at signup |

---

### What is wrong today

A pack is one revision holding everything — categories, document types, facts,
their bindings, and one memorandum with its sections. `registry.fork()` copies
the whole thing into revision 1, publishes it, and refuses to run again.

That makes six packs mean six duplicated sets of facts. It also made "fork the
two packs somebody chose" impossible: two bases cannot be merged, and nothing
decides which wins on a shared key.

The model was wrong. **It is not the facts that differ between a KYC file and a
trade credit file. It is what gets said about them.**

---

### The model

**One base.** Categories, document types, facts and their wording, and which
facts are sought in which document type. The same for every tenant, forked once.

**Templates over it.** Named memoranda — their sections, the numbering, the
wording of each section, and which facts each section renders. Six named
today, matching the report selector inside the application because they are
the same thing:

- KYC and AML
- Trade Credit
- Asset Based Loan Memo
- Real Estate Loan Memo
- Lender Marketing Memo
- Anonymous Project "X" Memo

**A template is additive.** Forking one adds sections and bindings. It never
touches another template, and it never removes anything.

That is the whole of it, and it is why the questions that made the old model
hard do not arise. There is no merge, because two templates over one base do
not collide. There is no second base, because there is only ever one.

---

### What a fork does

**First run.** Fork the base, then fork each template the person ticked. Base
first, always, because a template binds facts that must already exist.

**Later.** Fork another template into the existing configuration, at any time.
Same call, same behaviour. Adding Real Estate Loan six months in is not a
special case.

---

### SETTLED — a template brings back what it needs

A template forked later may bind a fact the tenant does not have: never forked,
or deleted since.

**The fork adds the missing facts back to the base.** It also adds any document
types those facts are sought in, and any category those types belong to.

The alternatives were rejected. Dropping the bindings silently gives a
memorandum with holes in it and no explanation. Refusing gives an error listing
things the person has never heard of and no way forward.

**Two constraints on how it is added:**

- **Additive only.** A fact the tenant already holds is left exactly as it is,
  including any wording they have changed. The pack's version does not
  overwrite theirs. This is the same rule as every upsert in the editor: keep
  what the row had.
- **It is reported.** The fork returns what it added — facts, document types,
  categories — and the screen says so. Somebody who deleted `Property
  Valuation` in March and finds it back in September must be told why, in the
  moment, not left to discover it.

---

### Schema

Proposed. Nothing here exists.

```
config_revision   ... existing columns ...
                  kind        VARCHAR(16) NOT NULL DEFAULT 'tenant'
                              -- 'tenant' | 'base' | 'template'
                  pack_key    VARCHAR(64) NULL
                              -- 'base', 'kyc-aml', 'trade-credit', ...
```

**`pack_key` is what signup should have stored.** It stores a display string
from `mock.tsx` today, and nothing maps that to a revision number — which is
the second reason the fork could not be written. A key is stable, a display
label is not.

**`config_revision.note` is not the mapping.** It is editable free text and
must not become load-bearing.

**Ordering must stop being the mapping too.** `packs()` sorts by revision
descending, so `ensureDraft`'s `packs[0]` is the highest-numbered pack — adding
a pack silently changes what new tenants get. Packs are selected by `pack_key`,
never by position.

---

### What breaks when a revision is not whole

Found while writing migration 017, 15 September 2026. **None of it is fixed by
that migration** — it is additive and touches no reader. This is step 2's work,
recorded here so it is not discovered from scratch a second time.

Every one of these assumes a revision holds a whole configuration, which is
exactly what a base revision and a template revision each stop being.

**`config.Registry._load`** reads all eight tables for one `(tenant_id,
revision)`.

- A **base-only** revision loads with `TEMPLATES = {}`, so `TEMPLATE_KEY` is
  `None` and `MEMO_SECTIONS` is empty. Composition would have nothing to write.
- A **template-only** revision loads with no categories, document types,
  schemas or fields, so `schemas_for` returns nothing, `document_type_list` is
  empty, and `label_for` falls back to raw keys.

**`config.load` and `for_tenant`** pin one integer, and the pipeline pins one
everywhere: extraction takes `document.config_revision`, composition the memo's
revision, classification the tenant's `active_revision`. So a split revision
must never become the revision a document or a memo is pinned to. A fork has to
land the base and its templates in ONE tenant revision, which is what
`fork_template` adding into an existing revision means.

**`registry.validate`** is the sharpest. Its first fatal check left-joins
`config_section_field` to `config_field` within the same revision, so run
against the template revision it reports *template binds undefined field* for
every one of its 63 bindings. Run against the base revision, the
*field-unbound* warning fires for all 105 fields, since no section renders
them. Validation is a question about a tenant's draft and must not be asked of
a pack revision.

**`registry.packs`** lists every published revision of the pack tenant, counts
document types and fields, and orders by revision descending. After 017 it
returns three rows, one of them the template revision showing 0 document types
and 0 facts. Step 2 selects `kind IN ('base', 'template')` and by `pack_key`.
Until then, the base is deliberately the highest-numbered revision so that
`ensureDraft`'s `packs[0]` forks the base.

**`registry._copy`, `publish` and `open_draft`** all move a revision wholesale.
That stays right for a base. It is `fork_template` that must add to a revision
rather than create one, and skip rows the tenant already holds.

---

### What has to change in the registry

**`registry.fork()` splits in two.**

`fork_base(tenant_id, email)` — what fork does today, restricted to a base
revision. Writes revision 1, publishes it, sets `active_revision`. Keeps its
guard: a tenant that already has a published revision cannot fork a base again.

`fork_template(tenant_id, email, pack_key)` — new. Copies one template's
sections and bindings into the tenant's configuration, adds whatever facts,
document types and categories those bindings need and the tenant lacks, and
returns what it added.

**`_copy` needs to stop being a bare `INSERT ... SELECT`.** Any key shared
between what is being added and what the tenant holds fails the statement and
leaves the revision half written. Template forking must skip rows the tenant
already has rather than fail on them — which is the additive rule, enforced at
the statement.

---

### Where the choice is made

**Not at signup.** It moves to Get started, the first screen after signing in,
where there is room to show what each template contains and the person has
somewhere to go afterwards.

Signup keeps `tenant.forked_pack` as a record of interest — useful, and it can
pre-tick the list — but it decides nothing.

**The marketing site's wording changes with it.** "Pick one or more starter
packs" becomes what it actually is: choosing which memoranda you want laid
out, over one set of facts.

---

### Content

Four templates exist as content today and can be supplied. The other two are
aspirational and are not to be listed anywhere a person can tick them until
they exist.

`db/migrations/009_pack_revision_1.sql` holds the current pack, whole. It has
to be split: the base into one revision, its memorandum into a template
revision.

---

### Sequence

1. **Migration.** `kind` and `pack_key` on `config_revision`. Split 009 into a
   base and a template. Additive; the existing tenants keep their revision 1.
2. **`registry.fork_base` and `registry.fork_template`.** `fork()` stays,
   delegating to `fork_base`, so nothing calling it breaks.
3. **Routes.** `GET /config/templates/available`, `POST /config/templates/fork`.
4. **Get started.** The chooser, showing what each template contains, and the
   report the fork returns.
5. **The site copy.**

---

### Open

1. **The two aspirational templates.** Built as content, or removed from every
   list until they are.
2. **Does a tenant ever want a second base?** The model says no. If a firm
   genuinely needs two disjoint sets of facts, that is two tenants, and saying
   so now is cheaper than discovering it later.
3. **Can a template be un-forked?** Deleting a memorandum already exists in the
   editor. Whether that should also offer to remove facts nothing else uses is
   a separate question and probably answered "no".
4. **TPL-03 · Configure's first-run screen is now wrong.** `Configure.tsx`
   carries its own first-run screen, separate from Get started: it reads
   `GET /config/packs` and forks the revision a person picks from a select.
   Since the split that list returns bases, while the screen still calls them
   memoranda and offers "Draft your own from scratch" beside them. Forking
   from it leaves a tenant with facts and no memorandum — the state Get
   started exists to prevent. It does not depend on pack ordering, so it is
   wrong rather than dangerous. Left alone deliberately in step 3: changing it
   is real work and belongs on its own branch.

5. **The site's pack list has drifted, and signup no longer records one.**
   `site/src/main.ts` declares its own six-entry `PACKS` array under a
   "starter packs" heading. One template ships today — `due-diligence` — so
   that list names five memoranda nobody can have, which is what item 1 above
   forbids. Its wording had already diverged from the copy signup used:
   "eligibility and ineligibility tests" against "eligibility tests", and
   curly quotes in Project "X". Step 5 of the sequence above, and a separate
   project. Recorded here so the divergence is not rediscovered a third time.

   In the same week, signup stopped asking altogether. `SIGNUP_PACKS` is gone
   from `mock.tsx`, `verify()` no longer writes `tenant.forked_pack`,
   `GET /config` no longer returns it, and Get started no longer pre-ticks from
   it. **This supersedes the note under "Where the choice is made" above**,
   which has signup keeping the column as a record of interest: a column NULL
   for every tenant from now on drives nothing, and a pre-tick that can never
   fire is dead code wearing the face of live code. The column and the two rows
   already in it stay — they record something that was once true. What drew
   somebody in, if we want it, is lead capture on the site and not this column.

---

### Acceptance

A person signing up, reaching Get started, ticking KYC and Trade Credit, and
pressing Get started ends with one set of facts, one set of document types, and
two memoranda laid out over them — each editable, neither having disturbed the
other.

Six months later the same person ticks Real Estate Loan, gets its sections and
its bindings, is told which facts were added back to support it, and finds
nothing they had edited has changed.
