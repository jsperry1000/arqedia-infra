# ARQEDIA — where the configuration path is inconsistent

**5 September 2026.** Written after two faults in one afternoon, both mine, both
from adding a control without reading what the write path does with the value.
Everything below is read from the code, with the line. Nothing is inferred from
a name.

---

## What went wrong, exactly

`config_field` carries two answers to "is this a table":

- `cardinality = 'group'`
- `group_key = field_key`

`editor.save_field` sets both on **insert** but its `ON DUPLICATE KEY UPDATE`
clause listed only `cardinality`. So changing an existing field's shape updated
one and left the other null.

`config.py:176` routes a row with no `group_key` into `singles`, which is a
five-part tuple. `config.py:193` builds a group as a six-part tuple. Extraction
reads `field[5]` for anything whose `cardinality` says group — and got a
five-part tuple. `IndexError`, on every document carrying a table.

**Two representations of one fact, written by different lines, read by
different rules.** That is the shape of every finding below.

---

## Findings

### 1 · One reader guards the tuple length, the other does not

`lambda/api/app.py:1068` — `f[5] if len(f) > 5 else []`
`lambda/extraction/app.py:108` (before today) — `field[5]`

The API's author knew the tuple could be short. Extraction did not. The same
malformed field returned a clean payload to the screen and killed the document
in extraction.

**Severity: was fatal.** Fixed today in extraction. The lesson is that the
guard existed in one place and its reason was never written down.

### 2 · `draft()` and everything else disagree about what a table is

`editor.py:192` — `"is_group": bool(group_key)`
`Configure.tsx:89` and `Propose.tsx` — `cardinality === "group"`

The payload the screen receives carries `is_group` derived from one column and
`cardinality` derived from another. While they disagreed, the editor drew a
column editor for a field the same payload said was not a group.

**Severity: high.** They agree again now, but nothing enforces it. One
derivation should exist, not two.

### 3 · Nothing validates the disagreement

`registry.validate` checks four things: a section binding an undefined field
(fatal), a type feeding no schema, a schema no type feeds, a field no section
binds. It does not check:

- `cardinality = 'group'` with `group_key` null
- a group with no columns
- a column key without its group prefix
- a composed section with no `context_sections`

All four are the faults we hit. **The broken revision published without a
murmur**, which is why it reached fifty-six documents.

**Severity: high.** Validation is the one place these could have been caught
before anyone filed anything.

### 4 · A column key's prefix is assumed in four places and enforced in none

`api.py:163`, `api.py:466`, `composition/app.py:140`, `composition/app.py:162`,
`composition/app.py:198` all do `field_id.split(".", 1)[0]` to recover the
group from a column.

A column stored as `role` rather than `f_vessel_carriers.role` returns `role`.
Composition would treat it as a top-level field and render it outside its
table, silently. Extraction crashed loudly; composition would not.

`_save_columns` (`editor.py:580`) mints the prefixed key **only when the caller
sends none**. Nothing rejects a caller that sends its own.

**Severity: high.** Fixed in the front end today. The editor should refuse a
column key that does not begin with its group.

### 5 · Neither screen can repair a wrong column key

`Configure.tsx:82` and `Propose.tsx` both send `key: c.key` for a column that
already has one. Re-saving a field with broken columns writes the broken keys
straight back.

Confirmed today: three fields were re-saved and all three remained broken. The
only repair is to delete the field and recreate it.

**Severity: medium.** It cost an hour and a wrong instruction from me.

### 6 · Changing a table back to a single value orphans its columns

`save_field` calls `_save_columns` only when `cardinality == "group"`
(`editor.py:560`). Change a group to `one` and its column rows stay in
`config_field`, still pointing at it.

`config.py:176` files them under `columns[group_key]` with no `group_meta`
entry, so they vanish from `SCHEMAS`. `editor.draft()` filters them out of
`fields`. They are invisible in the UI, invisible to extraction, and still
there.

**Severity: medium.** Not harmful today. It is a tombstone the design says
should not exist.

### 7 · `shape_key` is written, carried, and read by nothing

`editor.py:264` writes it, defaulting to the section key. `config.py:246`
loads it as `section["shape"]`. Nothing in composition or render reads it.

It is a `varchar(32)` beside a `varchar(64)` key, and this morning it refused
a section whose heading was perfectly legal — a dead column causing a live
failure.

**Severity: low, but it has already cost a session.** Either something should
read it or it should go.

### 8 · `save_section` does not update `shape_key` either

Same class as the fault we fixed: `shape_key` is on the insert and absent from
the update clause. Harmless only because nothing reads it. If anything ever
does, it will be stale for every section ever edited.

**Severity: latent.**

### 9 · `set_field_documents` moves a schema; `save_field` must not

`save_field` re-reads the existing `schema_key` (`editor.py:530`) rather than
taking one from the caller, and omits it from the update clause. That is
correct and deliberate — the schema is derived from the documents, not
authored — but nothing says so at the point a reader would ask.

**Severity: none.** Listed because it looks like finding 1 and is not.

### 10 · Two full copies of field and document editing

`Configure.tsx` and `Propose.tsx` each implement the field form, the column
editor, the document form and both tick lists. Today they diverged: one sent a
column key, the other did not, and only one of them broke extraction.

**Severity: high, and rising.** This is the source that will keep producing
findings 4 and 5.

---

## What would have caught this

In the order I would do them.

**A · Validation refuses a field whose `cardinality` and `group_key`
disagree**, a group with no columns, and a column key without its group
prefix. Fatal, not a warning — each one produces a document that cannot be
read. This is the single highest-value change here.

**B · One derivation of "is this a table."** `draft()` should report
`is_group` from the same column everything else uses, or the schema should
stop carrying two answers.

**C · `_save_columns` refuses a column key that does not begin with its
group**, rather than accepting whatever it is handed.

**D · Share the field and document editing between the two screens**, so
finding 5 is fixed once rather than twice.

**E · Decide what `shape_key` is for**, and delete it if the answer is
nothing.

---

## What I should have done differently

I read `save_field`'s update clause today, looking for `cardinality`, found it,
and stopped. The question I did not ask was: *what else does this row need in
order to be read correctly, and does the update clause set all of it?*

For any control that changes a stored value, that is the question. Not "does
the API accept it" — it accepted both of these.
