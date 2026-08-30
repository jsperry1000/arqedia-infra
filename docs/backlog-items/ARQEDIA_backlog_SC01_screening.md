# ARQEDIA — Backlog Item

## SC-01 · Sanctions screening and adverse media

| | |
|---|---|
| Status | Specified in Component 6; not built |
| Priority | High for the product's claim; not blocking any current stage |
| Type | Provider abstraction, backend, then a memo section |
| Raised | 28 August 2026 |

---

### Observation

Every memo generated so far reports screening as absent. The Cocoa Empire
memo's Open Items lists sanctions, adverse media and PEP screening as
outstanding, and the KYC field set carries `f_sanctions_matches`,
`f_pep_matches`, `f_screening_provider` and `f_screening_date` that nothing
populates.

Those fields fill only when a document *tells* us a screening was run. Nothing
in the product performs one.

**This is the gap between a document-reading tool and a diligence product.**
Extraction reports what a counterparty said about itself. Screening is the
first thing that checks it against the world.

### What Component 6 already settles

- A provider is a schema whose input is a **field value**, not a document.
  Results write back as ordinary extracted fields and bind to templates like
  any other value.
- Two interfaces: `ScreeningProvider` and `EnrichmentProvider`.
- `provider_credential` is scoped per tenant, so a customer may use their own
  subscription or the platform's.
- Screening is an **indicator, not a determination**. A name match is a
  question to answer, never an answer.

### Two pieces, different in kind

**1 — Sanctions screening (OFAC and equivalents)**

The lists are free. The work is ours:

- Ingest and refresh OFAC SDN, plus the consolidated EU, UK and UN lists.
  Each has its own format and update cadence.
- Normalise names: transliteration, ordering, honorifics, corporate suffixes.
- Fuzzy match, with a threshold that is a tuning decision against a real
  corpus rather than a number picked in advance.
- Record the list version screened against, so a screening can be reproduced.

**2 — Adverse media**

Not a list. A search, and a harder problem:

- Requires a provider — LSEG, Dow Jones, or a general web search with
  relevance filtering.
- **Redistribution rights are contractually unconfirmed** and remain the open
  item blocking phase 2. A licence permitting internal use may not permit
  surfacing results in a memo the customer shares with a third party.
- False positives are the norm. A common name returns hundreds of unrelated
  results, and a memo full of irrelevant hits is worse than none.

### What both need first

**Entity resolution.** Screening "Ivan Sergio Arrigazzi Juarez" requires
knowing that is one person, that the memo also calls him "Ivan Arrigazzi", and
which of the three registered identity numbers is his. Screening the wrong
string returns a clean result and proves nothing.

The Cocoa Empire corpus already shows this: four identity discrepancies across
two documents for one man, and two irreconcilable registration numbers for the
company.

### Sequence

| Step | What | Blocks |
|---|---|---|
| 1 | Entity resolution across an engagement's values | Everything below |
| 2 | OFAC ingest, normalisation, matching | Sanctions screening |
| 3 | `ScreeningProvider` interface and credential scoping | Both |
| 4 | Screening as a billable, deliberate act | Wallet integration |
| 5 | Adverse media provider | Redistribution rights (E1) |

### Notes

- **Screening is a charge point.** It costs per name and per run, so it sits
  alongside filing and generation as an act the person chooses.
- **A screening has a date and a list version.** A memo citing a screening
  must cite when it ran and against what, or it is an assertion about the
  past dressed as a current fact.
- **A clean result is a finding**, not silence. "Screened against OFAC SDN of
  27 August 2026, no matches" is materially different from the current "no
  screening results have been provided".
- The first provider decision — OFAC or LSEG — is open item A2 in the handoff
  and remains unanswered.

### Acceptance

An engagement's named entities can be screened on request; results write back
as extracted values with their provider, list version and date; and the memo
reports both matches and clean results as findings with citations.
