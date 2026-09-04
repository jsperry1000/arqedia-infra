# ARQEDIA — Backlog Item

## UP-01 · Confirm before read, and charge only for what is kept

| | |
|---|---|
| Status | Not started. The screen is specified in `ARQEDIA_upload_review_screen_spec_v1.md`; the charging rule is recorded nowhere |
| Priority | Before launch, after the pipeline works |
| Type | Front end, pipeline, billing |
| Raised | 3 September 2026 |

---

### Observation

A document is read the moment it lands. S3 emits an event, the normalizer runs,
extraction follows, and none of it waits for a person.

A binder holding seven documents therefore produces seven extractions before
anyone has seen a single proposal. Setting one aside afterwards cannot un-spend
it, and the operator is charged for reading something they did not want.

Raised by a real upload: one file, seven parts, all read, all chargeable, and
the operator's only control arriving after the money was gone.

### The rule

**No charge for anything not read, and nothing is read until a person confirms
it.**

The second half is what makes the first half honest. Charging only for kept
parts while reading all of them moves the cost off the invoice and onto us.

### What has to move

Extraction is triggered by the envelope landing. It must be triggered by the
filing action instead — the point the upload review screen already calls the
charge point.

That is the change. The screen itself is specified; this item is the pipeline
half of it plus the billing rule.

### Decisions taken 3 September

- **A file that cannot be read gets a register row marked rejected, showing
  why.** Today it is absent from FILED with no trace on any screen, which reads
  as a broken page rather than a rejected file. It cost an afternoon of
  diagnosis to establish that nothing was broken.
- **Same for a scan with no text layer.** Rejected, with its own reason, not
  silently dropped.
- **No charge for anything not read.** A rejected file is not charged. A part
  the operator removes before filing is not charged.

### Rejection reasons observed so far

| Reason | Cause | Fixable |
|---|---|---|
| `pdf-parse-failed: cryptography>=3.1 is required for AES algorithm` | Encrypted PDF; `cryptography` absent from the layer | Yes — see UP-03 |
| `no_text_layer` | A scan. Needs Textract, deferred from Stage 1 | Not until Textract is built |

Both currently produce the same outcome — no row, no message, no evidence the
file was ever uploaded.

### Notes

- **Charging is deliberately left as it is for now.** The pipeline is the
  priority; UX and money are addressed together at the end. This item records
  the decision so it is not rediscovered.
- **A rejected row is not a filed document.** It feeds no memorandum, carries no
  extracted values, and is not counted in the in-use total.
- The reason string belongs in the register, not only in the log. A person
  reading the screen should not need CloudWatch to know why a file is absent.

### Acceptance

A binder of seven parts is uploaded, the operator removes three before filing,
four are read, and four are charged. A locked PDF and a scan each appear in the
register marked rejected with their reason, and neither is charged.
