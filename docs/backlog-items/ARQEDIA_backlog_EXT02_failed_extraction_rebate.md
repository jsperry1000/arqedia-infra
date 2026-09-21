# ARQEDIA — Backlog Item

## EXT-02 · A failed extraction is charged, and a poor one may cost the client

| | |
|---|---|
| Status | Parked. Decision approved, not built |
| Priority | Before the first paying tenant |
| Type | Wallet, extraction, spec amendment |
| Raised | 21 September 2026 |

---

### Where it stands

Filing charges $0.25 per part at stage 4. Extraction runs after that, at stage 5.
A document that fails extraction keeps its charge. The two specs record this
as deliberate:

- `wallet_entitlement_spec_v1.md` §4: the ledger is append-only and monotonic,
  with no negative entries, credits or reversals.
- `pipeline_spec_v1.md` §6: nothing is refunded.

Both rest on the readability gate stopping unreadable material before money
moves. On 5 September, 102 tenant-2 documents failed extraction for a different
reason: revisions 2 and 3 carried group fields with no `group_key`. The gate
cannot catch that kind of failure.

---

### Decision, 21 September 2026 (approved, not built)

- **Rebate total failures only.** A document that ends with `extraction_error`
  set and zero extracted values is rebated $0.25.
- **As a credit bucket, not a ledger entry.** A new bucket is granted, linked to
  the document's `charge_entry_id`. The ledger stays append-only.
- **A document holding some values keeps its charge.**

**Proposed, not in the schema:** a bucket source identifying a rebate, and the
link from that bucket to `charge_entry_id`.

**Spec amendment:** both specs move to v1.1, with the old rule kept and marked
superseded. Neither is overwritten.

---

### The concern behind it, and still open

A poor extraction is a client-relations risk, not only a total failure. By
that we mean a document that read, but thinly or wrongly. The rebate rule
covers none of it. Open questions:

- What counts as a poor extraction, and who decides: the client, a threshold,
  or a review?
- Is anything returned for it, or is the answer better extraction and a clear
  retry?
- What does the client see, so that a thin result is not presented as a
  complete one?

---

### Depends on

The `extraction-error` branch, which adds `document.extraction_error`. The
rebate rule reads that column.

---

### Not in scope

The 102 historical rows from 5 September. These are dev data and have no
rebate to make.
