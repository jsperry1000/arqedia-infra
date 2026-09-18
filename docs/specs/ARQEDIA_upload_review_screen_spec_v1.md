# Upload Review Screen — Spec v1.0
 
**ARQEDIA · amends Components 3, 4 and 10**
 
Restores the confirmation step the design always called for: classification is
a proposal, a person confirms it, and filing is a deliberate act.
 
---
 
## 1. Why
 
- Classification runs on extracted text. A certified scan carries only its
  stamp, so the proposal is made from ~68 characters and is silently wrong.
- Once a person confirms the type, the system knows what the document should
  contain — and can OCR it with the right Textract mode. Today it cannot.
- Filing is where money will change hands. It needs an explicit action.
---
 
## 2. States
 
| State | Meaning |
|---|---|
| `uploaded` | In storage, nothing read yet |
| `analysed` | Text extracted, type proposed, not yet filed |
| `filed` | Type confirmed, extraction run, values persisted |
| `rejected` | Excluded from this engagement, kept, not extracted |
 
Only `filed` documents feed a memo.
 
---
 
## 3. Sequence
 
**1 — Drop files.** Each row appears immediately: name, size, `Uploading`.
 
**2 — Analyse, per file as it lands.** Not batched. Row shows page count,
proposed type, confidence, and one line of reasoning.
 
**3 — Review.** For each row the person sees:
 
- Pages, and the page range if the file holds more than one document
- Proposed type in a dropdown, grouped by category
- Confidence — `high`, `medium`, `low`, with low marked in colour
- Why — the sentence the classifier reasoned from
- A warning where the text is too thin to be trusted (see §5)
**4 — Correct.** Change the type from the dropdown. Split a file into page
ranges where it holds several documents. Uncheck to reject.
 
**5 — File.** One action for all confirmed rows. Runs extraction against the
confirmed types. This is the charge point.
 
**6 — Watch.** Rows move to `filed` and show values found.
 
---
 
## 4. Screen
 
```
COCOA EMPIRE                                    20 files
 
  ┌──────────────────────────────────────────────────────────┐
  │ Certificate of Incorporation.pdf        1 page, 1 part    │
  │ ─────────────────────────────────────────────────────────│
  │ ☑  1-1   [Certificate of Incorporation ▾]   low   ⚠ scan │
  │          Only a certification stamp was readable.         │
  └──────────────────────────────────────────────────────────┘
 
  ┌──────────────────────────────────────────────────────────┐
  │ CE_Response_Lender_IM_and_KYC.pdf      14 pages, 1 part   │
  │ ☑  1-14  [CDD Questionnaire ▾]              high          │
  │          Entity answers questions about itself.           │
  └──────────────────────────────────────────────────────────┘
 
                                       [ File 18 documents ]
```
 
- Checkbox = include. Unchecked is rejected, not deleted.
- Dropdown grouped by category, as eBL's.
- Reason is one line, truncated, full text on hover.
---
 
## 5. Thin text warning
 
A row is flagged when extracted text is implausibly short for its page count.
 
- Displayed as `⚠ scan — only a certification stamp was readable`.
- Does **not** block filing. The person decides.
- Filing a flagged row **routes it to OCR** rather than the text path.
This replaces the current gate, which silently accepted 68 characters as a
readable page.
 
---
 
## 6. What filing does
 
For each confirmed row:
 
1. Confirmed type recorded on the document; `document_type_confirmed = true`.
2. Thin-text rows go to Textract, mode chosen by confirmed type — cheapest OCR
   for prose, forms-and-tables for questionnaires and ownership forms.
3. Extraction runs against the schemas the confirmed type maps to.
4. Values persist with their locators.
---
 
## 7. Changes required
 
| Where | Change |
|---|---|
| Database | `document.state`; `page_range`; `document_type_confirmed` already exists |
| Normalizer | Stop extracting on upload. Analyse only: text, spans, proposal, confidence, reason. |
| API | `GET /engagements/{id}/pending`, `POST /engagements/{id}/file` |
| Extraction | Triggered by filing, not by the envelope landing |
| Front end | The review screen above |
| Textract | New: async job, completion notification, collection |
 
---
 
## 8. Deliberately not included
 
- Splitting a file into page ranges is in the screen but **not** in the first
  build. One file, one document, until the simple case works.
- No bulk type-change across rows.
- No re-filing a filed document. Correcting a type means a new upload.
---
 
## 9. Open
 
1. **Textract is now required, not deferred.** It is the largest piece of this
   work and was explicitly held back in Stage 1.
2. **Confidence thresholds** — what counts as low. Tuning, set against this
   corpus.
3. **Thin-text rule** — characters per page failed. Proposed: flag when a page
   yields under ~200 characters *and* the file is over ~100 KB per page, which
   is the signature of an image with a stamp.
 