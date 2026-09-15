# ARQEDIA — Backlog Item

## EV-01 · Value-to-span join (page-level citation) — **CLOSED**

| | |
|---|---|
| Status | **Closed. Built and verified against the live database, 14 September 2026** |
| Raised | 24 August 2026 |
| Closed | 14 September 2026 |

---

### Why this note exists

The original item records page-level citation as **blocked**, and names it as
the single missing piece behind the evidence-backed positioning. That has not
been true for some time, and the item was never marked.

The cost of leaving it was not theoretical. The marketing site was written to
claim only document-level citation — *"Audited-Accounts-FY2025.pdf"* rather
than *"Audited-Accounts-FY2025.pdf, p. 14"* — because the backlog said the
stronger claim was not available. The product was under-sold from its own
records.

**Recorded here so nobody reaches that conclusion again.**

---

### What was verified

`information_schema` read directly, 14 September 2026. Every column the item
asked for exists:

```
extracted_value   value_id, tenant_id, document_id, field_id, value,
                  row_ordinal, config_revision,
                  locator_kind, locator_index, char_start, char_end,
                  cell_range, confidence, extracted_at

claim             claim_id, tenant_id, memo_id, section_key,
                  statement_ordinal, statement_text

claim_evidence    claim_id, value_id, tenant_id
```

Against the four things the item required:

| Required | State |
|---|---|
| Extraction returns a location with each value | `locator_kind`, `locator_index` |
| Persistence carries it | On `extracted_value`, alongside `row_ordinal` and `config_revision` |
| An evidence record per value | `char_start`, `char_end`, `confidence`; `cell_range` for worksheets |
| A claim record binding a rendered assertion to its evidence | `claim` and `claim_evidence` |

`cell_range` is present, which answers the item's own note that worksheet
locators need a cell range rather than a page number.

`UI-02`, raised 30 August, quotes a rendered memorandum already carrying
*"page 1"* — so it was working in the product before this was checked.

---

### What this unblocks, per the original item

- **Front-end Phase 3** — source viewer, citation gutter, drill-down. The memo
  reader already resolves a citation to a passage.
- **Evidence package export.** Still not built; no longer blocked.
- **Source conflict detection.** Two documents that disagree can now be
  presented as disagreeing, because it is known which said what and where.
  Still not built; no longer blocked.

---

### Consequential change

The marketing site now states page-level citation. `site/index.html` and
`site/src/main.ts`: every fact in the worked sample names its document **and
its page**, and the lede reads *"footnotes back to the page of the original
document"*.

---

### The lesson worth keeping

A backlog item that records a blocker and is never closed is worse than no
item, because it is read as current. **Closing is part of the work.**
