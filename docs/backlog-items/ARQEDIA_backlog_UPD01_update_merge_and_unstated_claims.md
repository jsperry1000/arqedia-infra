# ARQEDIA — Backlog Item

## UPD-01 · Update: a new fact as its own sentence, and "not stated" beside a citation

| | |
|---|---|
| Status | Finding only. Not fixed |
| Priority | Medium |
| Type | Composition (Update) |
| Raised | 9 November 2026 |

The ID is proposed. Both were found on memo 349 (tenant 5, engagement 49),
while finding out why the date of incorporation would not reach section I.
That case is now met by Rewrite, which since #483 is given the section's
facts on file. Neither finding below is changed by #483.

---

### 1 · An addition is a sentence of its own, not worked into the text

Update 247 offered the date of incorporation as a separate sentence ("The
documents now on file state ...") placed after the section's text. It did not
offer the date inside the existing sentence about the company.

This follows from the design, not a bug in it. `UPDATE_PREAMBLE`
(`lambda/composition/cleanup.py`) says the model never returns the saved
text: it returns only what to add and where, by block number, and code puts
the addition in. That every saved character stays where it was is a property
of the code (decision of 16 October 2026).

Working a fact into a sentence means changing a saved sentence, which that
decision rules out. A change here is therefore a decision to be put first,
not a fix. One path exists today without changing it: Rewrite the section
with an instruction to include the fact. Since #483 that rewrite is given the
fact, and the person accepts or discards the result.

### 2 · "Not stated" written alongside a citation to a document that states it

Update 246 on memo 349 wrote that the date of formation was not stated, and
cited documents. Update 246 ran before NOVL_COI-1.pdf (document 1325) was
filed. Whether any of the documents it cited do state the date has not been
re-checked against their text. That check comes first.

What is true either way: nothing checks a "not stated" claim against the
values on file for the section. Citation checks confirm that a token belongs
to a source. They do not confirm that the cited material lacks what the
sentence says it lacks.

Wanted, once item 2 is reproduced: a "not stated" claim is not saved, or is
marked, when a value for that fact is on file for the section under the
revision in use.

---

### Not verified

- Item 2 is not reproduced. The run is on record (`memo_rewrite` 246), but
  its cited pages have not been read against its claim.
- Neither item has a test.
