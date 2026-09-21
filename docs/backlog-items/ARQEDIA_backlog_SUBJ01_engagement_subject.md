# ARQEDIA — Backlog Item

## SUBJ-01 · A counterparty's facts are written as the subject's

| | |
|---|---|
| Status | Diagnosed. Decisions taken. Not built |
| Priority | High. The memo states wrong facts under correct citations |
| Type | Schema, extraction, composition, API, front end, configuration |
| Raised | 21 September 2026 |
| Branch | `feature/subj-01-engagement-subject` |

---

### Observation

Memo 120 (tenant 1, engagement 29 `COCOA-EMPIRE-1`, template
`lender-information-memorandum`, revision 42), section II:

> **GoodFlow** is a specialist originator and exporter of certified organic and
> Fairtrade cocoa beans ... *CE-_-Corporate-Legal-Deck.pdf, page 2*. The company
> reported approximately €100 million in sales in the 2025 financial year.

The cited page says **Cocoa Empire Uganda Limited** is the specialist
originator. GoodFlow is a **buyer**. Cocoa Empire was incorporated on 29 May
2026 and cannot have 2025 sales. The citation and the description are right;
the subject is wrong. The €100 million is probably value 10518
(`f_turnover_stated`, `call-Summary-8-27.pdf`). Not confirmed.

### Cause, established from the code and the data

1. **Extraction files a counterparty's facts in the subject's fields.** The
   descriptions of `f_company_summary` ("one-paragraph description of the
   entity"), `f_business_model` ("how it operates / makes money") and
   `f_turnover_stated` do not say whose facts they hold. In engagement 29,
   GoodFlow values sit in `f_business_model`, `f_company_summary` and
   `f_turnover_stated` (sales contract, purchase order, call summary,
   commercial rationale, transaction flow).
2. **Nothing records or passes the subject.** `engagement` has no subject
   column. The extraction prompt carries only field labels and descriptions.
   `cleanup.subject_from()` works out a subject but only the front matter uses
   it; no draft or consolidation prompt names it.
3. **Consolidation is told to merge.** `CLEANUP_PREAMBLE` rule 2: "Where two
   documents give the SAME entity under different names, merge them and use
   the fuller name." Two near-identical business descriptions, one naming
   each company, were merged. Not changed by this item; see Open.

### Decisions taken (user, 21 September 2026)

- **Fix by scoping (option B)**, not by an entity column on every value.
- **The word is "subject"**, not "borrower". A tenant may write a KYC memo on a
  counterparty, who is then the subject.
- **One subject per engagement**, recorded on the engagement.
- **Required before extraction.** No document in an engagement is extracted
  until the engagement has a subject.
- **Editable after extraction.** A changed subject reaches every memo generated
  afterwards. Values already extracted change only if re-extracted, which stays
  a separate, paid action.
- **Indicative, not dispositive.** "JonesCo" also matches "Jones Company" and
  "jones co." The model is told the entered name and to treat any name
  referring to the same company as the subject.

---

### Work

**Read every file named below in full before editing it.** Put anything marked
*Confirm* to the user before writing it.

**1 · Migration `031_engagement_subject.sql`.** Follow the pattern of
`030_engagement_and_memo_state.sql`.

```sql
ALTER TABLE engagement ADD COLUMN subject_name VARCHAR(255) NULL;
```

Additive and nullable. No backfill from `engagement.name`, which is a label.

**2 · Where engagements are created, and where extraction starts.** There are
two creation paths: `lambda/api/app.py` line 310 and
`lambda/normalizer/app.py` line 195. Extraction fires on a normalized envelope
landing in the review bucket (`lambda/extraction/app.py`). Read the API,
normalizer and collector to establish whether a document can reach extraction
before a person could have entered a subject. *Confirm* with the user where the
requirement is enforced and what a held document looks like on screen, before
building it.

**3 · API.** Subject set on creation and editable afterwards. *Confirm* the
route and its validation (empty, whitespace, length) with the user.

**4 · Front end.** Subject entered at engagement creation and editable on the
engagement. It must be visible wherever an engagement is chosen for upload, so
nobody uploads into one without a subject unawares.

**5 · Extraction** (`lambda/extraction/app.py`). Read `subject_name` through
`document.engagement_id` at extraction time. Open the prompt with:

> The subject of this file is **<subject_name>**. Documents may write the name
> differently - with or without a legal suffix such as Limited or Ltd, in
> another capitalisation, abbreviated, or in full. Treat any name that refers
> to the same company as the subject. Every other company - a buyer, supplier,
> lender, inspector or other counterparty - is not the subject.

Refuse, rather than extract, where the subject is empty: the second line of
defence behind item 2, logged and recorded as `document.extraction_error`
(migration 029), following the existing codes. *Proposed:* record the subject
name used on the envelope beside `model_id`, so a value can be traced to the
subject it was read under. Envelope only; no schema change.

**6 · Composition** (`lambda/composition/app.py`, `cleanup.py`). Pass the
engagement's current `subject_name` into the draft, consolidation and rewrite
prompts, with the same variant rule and: "Never state a fact about another
company as a fact about the subject." *Confirm* whether the front matter's
**Subject** row uses the entered name or keeps `subject_from()`.

**7 · Field descriptions: configuration, not code.** The user enters these in
Configure and publishes. They take effect only for documents filed under the
new revision, because extraction resolves against the filing revision.

`f_company_summary`
> One-paragraph description of the SUBJECT only. Where the document describes
> another company (a buyer, supplier, lender, inspector or other counterparty),
> do not record that description here, even if it is the only company the
> document describes. If the document does not describe the subject, return
> null.

`f_business_model`
> How the SUBJECT operates and makes money. Never record a buyer's, supplier's,
> lender's or other counterparty's business model here. If the document does
> not describe the subject's business model, return null.

`f_turnover_stated`
> The SUBJECT's annual turnover or trading volume as NARRATED in this document
> (not from financial statements). Include the period and currency stated. A
> buyer's, supplier's, lender's or other counterparty's turnover is never
> recorded here. If the document does not state the subject's turnover, return
> null.

`f_buyers` and `f_buyers.name` are unchanged. GoodFlow belongs there.

---

### Open, each a separate decision, not in this item

- **Engagement 29's stored values.** Extraction only ever INSERTs into
  `extracted_value`; re-extraction adds rows beside the old ones.
  `_load_values` has no `config_revision` filter, so GoodFlow's existing rows
  keep reaching memos after any re-extraction.
- **Consolidation rule 2** in `cleanup.py`, quoted above.
- **Citation placement is unchecked.** `_consolidate`'s docstring says so.
  Claims are recorded per section, not per statement.
- **A table carries one citation.** `_render_group` cites the first value of
  the first row for the whole table, though extraction records a unit per row
  since 9 September.

### Acceptance

- A document filed into an engagement with no subject is not extracted, and
  the screen says why.
- The subject can be entered at creation and changed afterwards.
- On a fresh engagement over the same documents as engagement 29, with subject
  "Cocoa Empire", a generated memo describes only Cocoa Empire's business in
  section II, carries no GoodFlow turnover as the subject's, and names GoodFlow
  only as a buyer.
- A subject entered as "Cocoa Empire" is honoured where documents write "Cocoa
  Empire Uganda Limited" or "CE".

---

### Working notes for the coder

- Working directory `c:\terraform\arqedia`, Terraform and Docker. Separate
  branch, commit periodically, a short push summary on every push.
- Rebuild the layer after editing anything in `lambda/shared/`; a
  `terraform apply` alone deploys nothing if the hash is unchanged.
- The database is MySQL through the Data API: no `LIMIT` inside an `IN`
  subquery.
- `q.ps1` in the repo root: `Set-ExecutionPolicy -Scope Process
  -ExecutionPolicy Bypass -Force; . .\q.ps1`.
- The only composition Lambda found is `borrower-document-composition-prod`,
  while memos land in `arqedia-dev-curated-…`. Not investigated; see ENV-01.

### Rules of Engagement

Schema-faithful: where something is missing from the schema, flag it as
proposed rather than inventing it. Additive and non-destructive: nothing
already recorded is overwritten or discarded. Two-LTV discipline: Bill of
Exchange value is the invoiced amount, not marked to market. Confirm before
build: decisions that are hard to reverse go to the user before code is
written. Concise. No assumptions about architecture or intent; ask rather than
infer. No fabrication. No hallucination. No rabbit-holing; surface when a line
of work has stopped being productive. Simple question, simple answer. One path;
no if-then branching in instructions. Read or ask for live state; never infer
it from naming. Review prior context before answering. Separate branches,
commit periodically. Web-search third-party capabilities rather than assuming
them. A short push summary on every push. Never edit a document, schema or file
without first reading it in full.
