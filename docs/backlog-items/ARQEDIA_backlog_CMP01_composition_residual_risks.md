# ARQEDIA — Backlog Item

## CMP-01 · Composition: what SUBJ-01 left behind

| | |
|---|---|
| Status | Recorded, not fixed |
| Priority | Low. Back burner |
| Type | Composition, data |
| Raised | 21 September 2026 |

---

### Context

SUBJ-01 closed on 21 September 2026. Memo 120 (tenant 1, engagement 29)
described the buyer GoodFlow as the subject under correct citations. The cause
was fixed by recording a subject on the engagement and naming it to extraction
and composition. Deployed and tested: engagement 31 (`COCOA-EMPIRE-2`), same 25
documents, filed no GoodFlow facts in the subject's fields, and its memo reads
correctly.

The items below are separate. Each can produce a subtler version of the same
symptom. None blocks anything today.

---

### 1 · Memo 120 and engagement 29 are still wrong on record

Engagement 29's stored values predate the fix: GoodFlow's description and
turnover sit in `f_company_summary`, `f_business_model` and
`f_turnover_stated`. Extraction only ever INSERTs, and `_load_values` in
`lambda/composition/app.py` has no `config_revision` filter, so any memo
regenerated on engagement 29 carries them again. Engagement 31 replaces it.

Decision wanted: archive memo 120 and engagement 29, or leave them.

### 2 · Consolidation rule 2 invites merging

`CLEANUP_PREAMBLE` in `lambda/composition/cleanup.py`, rule 2: "Where two
documents give the SAME entity under different names, merge them and use the
fuller name." Two similar descriptions of different companies can read as one
entity under two names. The subject rule added by SUBJ-01 now counters this for
the subject; it does not for two counterparties.

### 3 · Citation placement is not checked

Masking makes citation text exact. It does not verify which statement a
citation ends up attached to; `_consolidate`'s own docstring says so. Claims
are recorded per section (`_record_claim` stores the whole section with every
value fed into it), so a sentence cannot be traced to its evidence from the
data.

### 4 · A table carries one citation

`_render_group` cites the first value of the first row for the whole table,
though extraction records a unit per row since 9 September. Rows read from
other pages or documents are credited to that one citation.

---

### Related, already on the backlog

MEMO-01 (the lender's CEO in Individuals), SC-02 (screening fields filled from
correspondence), CP-04 (Open Items carries no citations).

### Acceptance

Each item is either fixed or closed by a recorded decision.
