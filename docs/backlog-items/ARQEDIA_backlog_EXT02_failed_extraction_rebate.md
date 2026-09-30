# ARQEDIA — Backlog Item

## EXT-02 · A failed extraction is charged, and a poor one may cost the client

| | |
|---|---|
| Status | Parked. Decision approved, not built |
| Priority | Before the first paying tenant |
| Type | Wallet, extraction, spec amendment |
| Raised | 21 September 2026 |
| Status | 28 September 2026: decision extended, see "Decision, 28 September 2026" below. Still not built: nothing in `lambda/extraction/` refunds. `document.extraction_error` exists (`b7cc99b`, #199; migration 029) |

---

### Where it stands

Filing charges $0.25 per part at stage 4. Extraction runs after that, at stage 5.
A document that fails extraction keeps its charge. The two specs record this
as deliberate:

- `wallet_entitlement_spec_v1.md` §4: the ledger is append-only and monotonic,
  with no negative entries, credits or reversals.
- `pipeline_spec_v1.md` §6: nothing is refunded.

**Corrected 28 September 2026.** `pipeline_spec_v1.md` is not in the
repository and never has been: `git log --all -- '*pipeline_spec_v1.md'`
returns nothing. §6 cannot be read here. `docs/specs/wallet_entitlement_spec_v1.md`
is present.

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

### Decision, 28 September 2026

Recorded on the user's instruction of 28 September. **A failed extraction and
a failed generation are not charged.** This modifies CLAUDE.md's settled
decision "The ledger is append-only. … There are no reversals" — which the
code had already departed from for failed reads.

**What is already built for that case.** `wallet.refund()` in
`lambda/shared/wallet.py`, added by `8169385` (#168), called by the collector
when OCR fails and by `file_documents` in `lambda/api/app.py`. It appends; it
edits nothing:

- a `wallet_ledger` row, `event_type = 'document_filed_refund'`, with a
  **negative** `amount_cents` equal to what the charge actually took (from the
  charge's own `unit_cents`, never from `meter_price`);
- a new `wallet_bucket`, `kind = 'refund'`, for the same sum, expiring in
  `REFUND_DAYS` (30), because the bucket that paid may have expired;
- once per document, enforced by `uq_idempotency` on `refund:<document_id>`,
  in one transaction, ledger row first.

The module docstring records the change of rule: "There IS now a reversal …
It still adds a row rather than editing one".

**PROPOSED, not decided:** EXT-02 uses this same mechanism — `wallet.refund()`
and its ledger row plus refund bucket — rather than the rebate-only credit
bucket decided on 21 September above. The 21 September decision stands as
written until this is put and answered. Also open: whether "failed" for
extraction stays "`extraction_error` set and zero values" (21 September), and
the generation half, which is UX-02 item 20.1
(`docs/ARQEDIA_worklist_UX02_2026-09-20.md`): `wallet.refund()` as written
keys on `document_id` and writes `document_filed_refund`, so it does not fit a
generation without change.

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
