# ARQEDIA — Specification

## TPL-04 · Authoring a memorandum template

| | |
|---|---|
| Status | Specified. Nothing built |
| Depends on | TPL-02 steps 1 to 3, merged |
| Raised | 16 September 2026 |

> **Superseded in part, 17 September 2026.** Authoring happens directly in
> tenant 0, and the export command is not built. Open item 2 below is
> answered. See `docs/specs/revision_selection_decisions_2026-09-17.md`, which
> takes precedence; the missing-facts refusal and "only the memorandum" carry
> over to the on-offer mark. Nothing here is deleted: the reasoning for both
> is why those two rules survive.

---

### The problem

Six memoranda are named on the marketing site and in the product. **One
exists** — `due-diligence`, split out of `009` by migration 017.

Writing each of the other five as a hand-built migration full of `INSERT`
statements is not a process. It is unreviewable, it is slow, and getting a
section's wording right is exactly the kind of work that wants twenty
iterations rather than twenty migrations.

---

### SETTLED — export from a tenant

**A template is authored the way it is used: in the editor, in a real tenant,
against real documents. When it is right, it is exported into the catalogue.**

Authoring a template and using one become the same act. Somebody writing a Real
Estate Loan Memo builds it in a dev tenant, generates memoranda from real
documents, reads what comes out, fixes the wording, and only then exports.

The alternatives were rejected. A migration per template cannot be iterated —
each change is a release, and nobody proofreads SQL. A YAML file in the
repository is reviewable but is written blind: you cannot see what a section
says until it has been loaded into a tenant and run.

**This is deliberately an infrequent, manual process.** It runs a handful of
times a year, by us, against dev. It is a command, not a screen, and it has no
customer-facing surface at all.

---

### What export does

Given a tenant, a `template_key` and a `pack_key`:

1. Read that template from the tenant's **active** revision — its sections,
   their wording and numbering, and their fact bindings.
2. Write a new revision on the pack tenant with `kind = 'template'` and the
   given `pack_key`.
3. Report what was written, and what the template binds.

**From the active revision, not the draft.** A draft is work in progress by
definition. Exporting one ships something nobody has published, and publishing
is the act that says a person looked at it.

---

### The check that matters

**Every fact the template binds must exist in the base.**

`fork_template` already refuses a template that binds facts the base does not
define. If an export can create such a template, that refusal fires at the
customer rather than at us — and it fires at the worst moment, when somebody is
trying to start.

So the export refuses, and names what is missing. Two ways to resolve it, and
the author picks:

- **The fact belongs in the base.** It is one more thing every tenant should be
  able to record. Add it to the base and export again.
- **The fact is this firm's own.** The template cannot ship with it. Unbind it
  and export again, or do not ship the template.

That second case is the interesting one. A memorandum built in a real tenant
will bind facts that firm invented, and the export is where that gets caught.

---

### What is not exported

**Only the memorandum.** Sections, wording, numbering, bindings.

Not facts, not document types, not schemas, not categories. Those belong to the
base, and a template that quietly carried its own would reintroduce exactly the
duplication TPL-02 removed.

**Nothing tenant-specific.** No engagement, no document, no memorandum already
generated. A template is layout; it carries no content.

**A named check, not an assumption.** The export must confirm the rows it
writes contain nothing outside the three template tables, and say so.

---

### Where it runs

**A script under `tools/`, run by hand against dev.** Not a route, not a screen,
and not reachable by any tenant.

It writes to tenant 0. Nothing else in the product does, and a route that could
would be a route worth attacking.

---

### Removing and replacing

**A template already in the catalogue is superseded, not overwritten.**

A tenant who forked `real-estate` last month holds those sections in their own
configuration. Changing the pack cannot reach them and should not — their copy
is theirs, including anything they have edited.

So exporting the same `pack_key` again writes a new revision and the older one
stops being offered. `template_packs()` returns the highest revision for each
`pack_key`.

**That is a change to `template_packs()`**, which today returns every template
revision. Two revisions of `real-estate` would otherwise both appear in Get
started.

---

### Sequence

1. **`tools/export_template.py`** — read, check, write, report. Refuses on a
   missing fact.
2. **`template_packs()` returns the highest revision per `pack_key`.**
3. **Author the five missing memoranda** in a dev tenant and export them. Content
   work, not engineering, and the slowest part.
4. **The marketing site's list** matches what ships, whenever that is.

---

### Open

1. **Which five.** The site names Asset Based Loan, Real Estate Loan, Lender
   Marketing, Anonymous Project X, and KYC and AML as distinct from
   `due-diligence`. Whether all five are wanted, and whether `due-diligence`
   should be renamed to one of them, is a content decision.
2. **A pack tenant of its own.** Tenant 0 holds packs today. Whether authoring
   should happen in a dev tenant and export to 0, or whether 0 should be where
   authoring happens directly, decides whether the export crosses tenants at
   all.
3. **Un-shipping.** A template withdrawn from the catalogue — is there a state
   for that, or does it simply stop being exported.

---

### Acceptance

Somebody builds a Real Estate Loan Memo in a dev tenant, generates from real
documents until the wording is right, publishes, and runs the export. It
refuses, naming two facts that firm invented. They unbind both and export
again. The memorandum appears in every tenant's Get started list, and forking it
brings its sections and bindings and nothing else.
