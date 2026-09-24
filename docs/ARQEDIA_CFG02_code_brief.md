# ARQEDIA — CFG-02 brief for Claude Code
## Configure the sections a composed section reads

Working directory `c:\terraform\arqedia`. Terraform and Docker.
Branch: `cfg-02-context-sections`, cut from the current main branch.

---

## Rules of engagement

Apply these throughout. Do not print them in replies.

- Schema-faithful. Where something is missing from the schema, flag it as proposed rather than inventing it.
- Additive and non-destructive. Nothing already recorded is overwritten or discarded.
- Two-LTV discipline: Bill of Exchange value is the invoiced amount, not marked to market.
- Confirm before build. Decisions that are hard to reverse are put to the owner before code is written.
- Concise.
- No assumptions about architecture or intent. Ask rather than infer.
- No fabrication. No hallucination.
- No rabbit-holing. Surface when a line of work has stopped being productive.
- Simple question, simple answer. Analysis only when asked for it.
- One path. No if-then branching in instructions.
- Read or ask for live state. Never infer it from naming.
- Review prior context before answering.
- Separate branches, commit periodically.
- Web-search third-party capabilities rather than assuming them.
- A short push summary on every push.
- Never edit a document, schema or file without first reading it in full.

---

## The problem

A section of kind `composed` is written from the sections named in its
`config_section.context_sections`. The Configure editor has no control for that
column, so it can only be set by SQL. A composed section with no context
sections silently produces nothing. The editor also shows field bindings on
composed sections, which composition never reads.

Live example (tenant 1, latest published revision): in
`lender-information-memorandum-2`, section `financing-requested` (sort 7) is
`composed`, has a summary prompt, and `context_sections` is NULL.

No database change is needed. The column exists.

---

## Decisions already made by the owner

1. The control lets the user tick **any** other section in the same
   memorandum, before or after the composed section. A section cannot tick
   itself.
2. Field bindings are **hidden** on a composed section.
3. Publishing is **refused** when any composed section has no context
   sections, with a notice saying why.

---

## Step 1: read, report, stop

Read these in full before writing anything:

- `lambda/composition/app.py`
- `lambda/api/editor.py`
- `Configure.tsx` (locate it in the repo and give its path)
- the publish handler (locate it and give its path)

Report back, with file and line references, on these points:

- How composition reads a composed section's context: the other sections'
  written text, their bound facts, or something else.
- Whether a composed section can read a section that sorts **after** it.
  Decision 1 depends on this. If it cannot, stop and report; do not redesign
  composition.
- Whether `POST /config/draft/sections` already accepts and saves
  `context_sections`.
- The exact storage format of `context_sections` as the code parses it. The
  documented example is comma-separated keys with no spaces
  (`identity,ownership`); confirm from the parser, and keep whatever it is.
- Where publish-time validation lives, if anywhere.

Then set out the planned change, file by file, and **wait for confirmation**.

---

## Step 2: the change, after confirmation

**API, `lambda/api/editor.py`**

- `POST /config/draft/sections` accepts and saves `context_sections` on
  revision 0 only, in the format confirmed in step 1.
- Reject keys that are not sections of the same memorandum in the draft, and
  reject the section's own key.
- Leave existing values in place unless the request changes them.

**Front end, `Configure.tsx`**

- On a `composed` section, show a tick list of every other section in the same
  memorandum, in sort order, labelled by numeral and title. Existing values
  load ticked.
- On a `composed` section, hide the field-binding list. Hide it only; do not
  delete any `config_section_field` rows.

**Publish**

- Refuse to publish when any composed section in any memorandum has an empty
  `context_sections`. Show a notice naming each offending section.
- Proposed notice text, for the owner to confirm: *"'{title}' is written from
  other sections, but none are ticked, so it would come out empty. Tick at
  least one section for it to read."*

**Out of scope, report only if found:** a renamed or deleted section leaving a
dangling key in another section's `context_sections`.

---

## Step 3: verify on dev

1. Open a draft in Configure.
2. On `lender-information-memorandum-2` → `financing-requested`, tick all seven
   other sections and save.
3. Confirm the stored value with the RDS Data API (pattern in
   `ARQEDIA_database_access.md`):

```sql
SELECT revision, section_key, context_sections FROM config_section
WHERE tenant_id = 1 AND revision = 0
  AND template_key = 'lender-information-memorandum-2'
  AND section_key = 'financing-requested'
```

4. Confirm the field-binding list is hidden on that section and still shown on
   the extract sections.
5. Untick everything and try to publish: publish is refused with the notice.
6. Re-tick, publish, regenerate a memo, and confirm the section is written.

Commit as you go. Give a short summary on every push.
