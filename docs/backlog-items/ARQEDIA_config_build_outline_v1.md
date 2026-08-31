# ARQEDIA — Configuration Build Outline

**Stage 2 · the config registry, the pipeline switch, and four editors**
Written 30 August 2026. Companion to `config_registry_spec_v1.md` and
`config_editors_spec_v1.md`, which remain authoritative on rules; this document
covers sequence, what a person does, and what happens behind it.

---

## 1. What changes

Today every tenant extracts against one hard-coded pack: 27 document types, 8
schemas, 83 fields, 8 memo sections, all defined in `lambda/shared/pack.py`. A
firm doing shipping finance gets a pack built for cocoa exporters in Uganda.

After this, a tenant authors their own — categories, document types, field
schemas, memo templates — and the pipeline reads what they authored.

---

## 2. The chain

A fact reaches a memo through four links:

```
  category  ─────►  document type  ─────►  schema  ─────►  template
  "Corporate"       "Certificate of        field set        memo section
                     Incorporation"        + prompt         bound to fields
```

A break at any link is silent. The fact is simply absent from the memo, and
nothing says why. Stage 1 produced exactly this: a template naming a field the
pack did not define wrote a memo confidently reporting facts as missing when
they had been extracted and stored.

The `document type → schema` link is many-to-many. One type can feed several
schemas; one schema can be fed by several types. That link is where duplicate
extraction, overlaps and zero-read schemas originate, which is why it gets its
own editing surface rather than being a field on a form.

---

## 3. What a person does

```
   ┌──────────────────────────────────────────────────────────────┐
   │  1. FORK A STARTER PACK                                      │
   │     Choose the pack closest to their work.                    │
   │     It is copied, not referenced: their revision 1.           │
   └───────────────────────────┬──────────────────────────────────┘
                               ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  2. EDIT THE DRAFT                                            │
   │     Four surfaces, any order, any number of sittings:         │
   │                                                               │
   │     Types      add "Charterparty", retire "Cap Table"         │
   │     Mapping    which types feed which schemas                 │
   │     Schemas    fields, groups, the extraction prompt          │
   │     Templates  sections, and which fields each binds          │
   │                                                               │
   │     Nothing here affects any memo. The draft is a workspace.  │
   └───────────────────────────┬──────────────────────────────────┘
                               ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  3. PUBLISH                                                   │
   │     Validation runs. Coverage is shown:                       │
   │                                                               │
   │       · a type feeding no schema                              │
   │       · a schema no type feeds                                │
   │       · a field no template binds                             │
   │       · a template binding a field that does not exist        │
   │                                                               │
   │     A failing draft cannot become a revision.                 │
   └───────────────────────────┬──────────────────────────────────┘
                               ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  4. WORK CARRIES ON                                           │
   │     New documents file against the new revision.              │
   │     Everything filed before still resolves against the one    │
   │     it was filed under. Old memos still reproduce.            │
   └──────────────────────────────────────────────────────────────┘
```

---

## 4. What happens behind it

**Draft and revisions.** One mutable draft per tenant; an append-only series of
immutable revisions. Editors write only the draft. Extraction and composition
read only a revision. Publishing copies the draft into a new revision and
leaves it untouched thereafter.

**Snapshot, not per-object versions.** A memo depends on the whole chain across
all four object kinds. Versioning each object separately would mean pinning a
set of versions and resolving cross-object references at each — a dependency
graph that worsens with every edit. A snapshot is one integer.

**Stable identity.** A `field_id` is minted at creation and never changes. A
label is display metadata. Renaming "Reg. No." to "Registration Number" is free
and orphans nothing. Deleting a field is a genuine break and is treated as one.

**Retirement without tombstones.** There is no retired flag. A document type
present in revision 11 and absent from revision 12 is retired going forward;
everything filed under 11 still resolves against 11. Non-destructive by
construction.

**Fork copies.** A starter pack lives in a reserved pack tenant. Forking deep-
copies a pack revision as the new tenant's revision 1. Later edits to the pack
never reach a tenant who has already forked it.

**Where a revision is recorded.** Every document already carries
`config_revision`; every extracted value carries it too. Those columns exist and
are populated with 1. They become meaningful rather than decorative.

---

## 5. Build sequence

| # | What | Visible to a user | Proves |
|---|---|---|---|
| 1 | Schema and loader | Nothing | The existing pack loads as revision 1 and reads back identically |
| 2 | Pipeline switch | Nothing | The Cocoa corpus extracts against revision 1 exactly as it does today |
| 3 | Registry API | Nothing | Draft, publish, validation, fork |
| 4 | Types and categories editor | First screen | A tenant can add a type |
| 5 | Mapping matrix | Second screen | Coverage becomes visible |
| 6 | Schema editor | Third screen | Fields, groups, prompts |
| 7 | Template editor | Fourth screen | Sections bound to fields |
| 8 | Starter packs | Onboarding | A new tenant begins somewhere sensible |

Steps 1 and 2 are invisible and are the foundation. If extraction against
revision 1 does not reproduce what already exists, everything after is built on
sand. That is the reason they come first and are verified against the real
corpus before an editor is written.

---

## 6. What this touches

**Reads `pack.py` today, and moves to reading a revision:**

- `lambda/normalizer/classify.py` — the document type list and descriptions
- `lambda/extraction/app.py` — schemas, fields, prompts
- `lambda/composition/template.py` — memo sections and their field bindings
- `lambda/api/app.py` — the type list served to the review screen

**Unchanged:** storage layout, the review and filing flow, OCR, the memo
reader, rendering, revisions of memos. The registry changes what the pipeline
reads, not how it runs.

---

## 7. Migration

Every document filed so far was extracted against the hard-coded pack, and
every value references a `field_id` from it. The loader therefore writes that
exact pack into the pack tenant as revision 1 and forks it to each existing
tenant, so existing values keep resolving and nothing already extracted breaks.

Verification is not "it runs". It is: re-extract a document from the Cocoa
corpus against revision 1 and compare the values field by field with what is
already stored.
