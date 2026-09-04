# ARQEDIA — Which edits reach documents already filed

**Project context. Most configuration edits take effect immediately. A few do
not, and the difference is not obvious from the editor.**

---

## The one distinction

**Extraction is pinned. Composition is live.**

- **Extraction** runs once, at filing, against the revision the document was
  filed under. It never runs again.
- **Composition** runs every time a memo is generated, against the tenant's
  active revision, and binds whatever values exist by `field_id`.

So an edit that changes *what is read out of a document* reaches nothing
already filed. An edit that changes *what is done with values already held*
reaches everything, at once.

---

## What reaches old documents

| Edit | Reaches old documents |
|---|---|
| Bind a field to a section | **Yes** |
| Unbind a field | **Yes** |
| Add, retitle or reorder a section | **Yes** |
| Change a section's prompt or context sections | **Yes** |
| Add a whole memorandum | **Yes** |
| Rename a field's label | **Yes**, and free |
| Add a field | No |
| Change a field's description | No |
| Change which document types a field is sought in | No |
| Add or edit a document type's description | No |

The right-hand column is short, and everything in it concerns the extraction
prompt.

---

## Why reconfiguring appears to work

Because most of it is composition-side, and that is by far the larger part of
the editor.

1. A memo is composed fresh each time, against the active revision.
2. Section order, bindings, prompts, adding a memorandum — all composition.
   None needs a document re-read.
3. The values are the old ones. They still resolve because `field_id` is
   permanent and a label is display metadata.
4. So the memo changes, correctly, and nothing looks wrong.

**What is quietly not happening:** a field whose description you improved still
yields what it yielded when the document was filed. The better description
improves the next document filed, not that one.

**And the case that shows:** a field added after a document was filed is empty
for it. On a group field that renders as a table of em dashes; on a single
field, as an absent line. Neither announces itself.

---

## Why it is built this way

A memo written in March reproduces in September because the values behind it
are pinned to the configuration that produced them.

If a field edit re-extracted, three things would follow. A published memo could
change under a reader who had already been sent it. Every configuration edit
would spend inference without anyone clicking anything, which the pipeline spec
forbids — no config edit re-extracts, and every charge follows a click. And
`extracted_value.config_revision` would stop meaning anything, since a value
would no longer belong to one revision.

---

## Checking a particular field

One query, and it separates the two cases that look identical in a memo.

```sql
SELECT COUNT(DISTINCT document_id) FROM extracted_value
WHERE tenant_id = 1 AND field_id LIKE 'f_service_counterparties%'
```

Compare with the engagement's document count.

- **Zero.** Never extracted. The field postdates every document, or no document
  of a type it is sought in has been filed.
- **Materially fewer than the corpus.** The field postdates most of it. Values
  exist only for documents filed since.
- **All of them, and still nothing renders.** Extracted and not rendered — the
  fault is the binding, the template, or the published revision. This is the
  case that cost an hour on 2 September: 102 values, correctly bound, rendering
  nothing because composition was reading a hard-coded template.

---

## Re-extraction

`db/rerun_extraction.py` exists and does **not** fill a new field.

```
python db/rerun_extraction.py 199 200 201
python db/rerun_extraction.py --stuck
```

It deletes the document's `extracted_value` rows, clears `extraction_complete`
on the envelope, and writes the envelope back, which re-fires extraction. The
document row, the file and the filing are untouched, so **nothing is re-filed
and nothing is charged** — inference is spent, the $0.25 filing charge is not.

**It re-extracts against the same revision.** The envelope carries
`config_revision` and the script does not change it, so a document filed under
revision 15 is extracted against revision 15 again. A field added in revision 17
is still absent.

Its actual purpose is narrower: a document whose extraction failed part-way has
values written and no `extracted_at`, and the screen reports it as extracting
for ever. `--stuck` finds exactly those. A document with no values at all is
left alone, since it may simply have yielded nothing.

---

## Filling a new field on an old document

**Nothing in the repository does this.** It would mean advancing the revision on
the envelope before re-firing, and that breaks the guarantee above.

The supported route is to file the document again: a new document row, a new
filing, a new charge. Set the old one aside rather than deleting it — a filed
document is kept, and a memo already written cited what was current when it was
written.

**In practice, that is what has been happening.** Re-uploading documents after a
configuration change is why the newer fields carry values. It works because it
is a new filing, not because the edit reached backwards.

---

## The habit worth keeping

**Author fields before filing a corpus, and bindings whenever you like.**

Getting the field vocabulary and the descriptions right up front is worth more
than it looks, because those are the two things a later edit cannot repair
without re-filing. Sections, bindings and whole memoranda can be rearranged
afterwards at no cost at all.
