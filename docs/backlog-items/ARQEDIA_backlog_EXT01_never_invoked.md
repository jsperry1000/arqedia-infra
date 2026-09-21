# ARQEDIA — Backlog Item

## EXT-01 · Nine documents were filed and extraction was never invoked

| | |
|---|---|
| Status | Recorded, not diagnosed and not built |
| Priority | Before the first paying tenant |
| Type | Pipeline, filing |
| Raised | 21 September 2026 |

---

### What this is not

It is not the 5 September failure. That one is understood: revisions 2 and 3
carried group fields with no `group_key`, the extractor raised `IndexError` on
`field[5]`, and 102 documents kept the values written before the exception and
never got their `extracted_at`. Migration 029 marks those rows
`group_key_missing`, and the `extraction-error` branch stops it recurring.

These nine are a different shape. **Extraction did not fail on them. It never
ran.** There is no invocation, no error, no traceback, and no `extracted_value`
row — the CloudWatch log group for the window contains nothing about them at
all. They are not marked by migration 029 and must not be: their revisions are
19, 21, 28 and 40, none of which carries a malformed field.

---

### The nine rows

Read from the live dev cluster on 21 September 2026. Columns are
`document_id | filename | engagement | filed_at | config_revision |
document_type | active | char_count | extracted_value rows`.

```
484 | CE-_-Share-Valuation-Report-Registered-Copy.pdf               | COCOA-EMPIRE-4  | 2026-09-06 18:28:19 | 19 | regulatory-filings | 1 |   834 | 0
490 | ROSFL-_-Management-Accounts-_-January-2026-Unaudited.pdf      | COCOA-EMPIRE-4  | 2026-09-06 18:28:21 | 19 | operations-memo    | 0 | 10004 | 0
493 | ROSFL-Audited-Financial-Statements-FY2025-Grant-Thornton.pdf  | COCOA-EMPIRE-4  | 2026-09-06 18:28:23 | 19 | operations-memo    | 0 | 57583 | 0
568 | Business-projections-Waste-products_M8-PL-projections323.pdf  | Knightsbridge-1 | 2026-09-07 11:17:01 | 21 | interim-statements | 0 |   287 | 0
577 | Business-projections-Waste-products_M8-PL-projections323.pdf  | Knightsbridge-2 | 2026-09-08 17:37:26 | 28 | interim-statements | 0 |   287 | 0
580 | Business-projections-Waste-products_M8-PL-projections323.xlsx | Knightsbridge-2 | 2026-09-08 17:42:33 | 28 | interim-statements | 1 |   419 | 0
603 | CE-_-Share-Valuation-Report-Registered-Copy.pdf               | COCOA-EIMPIRE-5 | 2026-09-10 18:47:04 | 40 | regulatory-filings | 1 |   834 | 0
612 | ROSFL-_-Management-Accounts-_-January-2026-Unaudited.pdf      | COCOA-EIMPIRE-5 | 2026-09-10 18:47:07 | 40 | interim-statements | 0 |  9992 | 0
613 | ROSFL-Audited-Financial-Statements-FY2025-Grant-Thornton.pdf  | COCOA-EIMPIRE-5 | 2026-09-10 18:47:08 | 40 | audited-statements | 0 | 56073 | 0
```

Every one is `state = 'filed'`, `extracted_at IS NULL`, zero values. Three are
still in use; six were set aside by hand afterwards, which is a person working
around this rather than a second finding.

---

### The evidence, raw

**Extraction ran that evening and these three were not in it.** Log group
`/aws/lambda/arqedia-dev-extraction`, retention `None`, window 10 September
18:40–19:20 UTC:

```
filter-pattern "ERROR"            →  (no events)
filter-pattern "[extracted] doc=" →  72 completions:
doc=590 … doc=602, doc=604 … doc=611, doc=614 … doc=662
```

603, 612 and 613 are absent from that list. Their neighbours on either side
completed in the same minutes. No error was logged, so this is a missing
invocation and not a swallowed failure.

**The normalizer did its part.** Same window, log group
`/aws/lambda/arqedia-dev-normalizer`:

```
[analysed] doc=603 part=1 of 1 pages=1-1  method=pdf-text type=None
           key=tenants/2/docs/COCOA-EIMPIRE-5/CE-_-Share-Valuation-Report-Registered-Copy.pdf
[analysed] doc=612 part=1 of 1 pages=1-11 method=pdf-text type=interim-statements
           key=tenants/2/docs/COCOA-EIMPIRE-5/ROSFL-_-Management-Accounts-_-January-2026-Unaudited.pdf
[analysed] doc=613 part=1 of 1 pages=1-27 method=pdf-text type=audited-statements
           key=tenants/2/docs/COCOA-EIMPIRE-5/ROSFL-Audited-Financial-Statements-FY2025-Grant-Thornton.pdf
```

So each was read, segmented and given a row. What did not happen is the step
after it.

**Nothing was written for them.**

```sql
SELECT document_id, COUNT(*) FROM extracted_value
 WHERE tenant_id = 2 AND document_id IN (603, 612, 613)
 GROUP BY document_id
```

Returned no rows at all.

---

### Where the gap has to be

Extraction fires on a `.normalized.json` object landing in the review bucket,
and `file_documents` is what puts one there — it reads `<key>.analysed.json`
and writes it back under `.normalized.`. Between a document reaching `filed`
and the extractor being invoked there are four places this can be lost, and
**none of them has been checked**:

1. the envelope was never written, and `file_documents` swallowed it — but
   that path refunds and marks the row `unreadable`, and these rows are
   `filed`, so it is unlikely rather than excluded;
2. the envelope was written under a key the trigger does not match — the
   `_envelope_suffix` rule is mirrored in three places, which is exactly the
   shape of defect that produces a silent miss;
3. the S3 event was raised and not delivered;
4. the invocation was delivered and dropped before any log line, which would
   show as a throttle or an async-delivery failure and was not looked for.

**Checking whether the `.normalized.json` objects exist in the review bucket
for these nine keys would eliminate 1 and 2 in one command.** It has not been
run.

---

### Why it matters more than nine rows

Filing charges. Each of these was paid for and read nothing back, and unlike
the 5 September failures there is no trace anywhere that would tell a person
why — the row says only `extracted_at IS NULL`, which after the
`extraction-error` branch means "still working". **A document lost this way
still shows "extracting…" for ever, because `extraction_error` is only set by
an extractor that ran.** Whatever closes this needs to answer for a document
that was filed and never picked up, which is a different question from a
document picked up and failed.

---

### Not in scope

The nine historical rows. They are dev data; three are in use and six are set
aside, and nothing is to be rewritten before the cause is known.
