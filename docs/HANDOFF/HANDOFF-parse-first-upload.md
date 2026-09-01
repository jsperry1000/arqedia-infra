# Parse-first upload — complete build handoff

Everything needed to build this in one pass. Self-contained: no questions should
need to come back, and nothing here needs to be re-derived from the repo.

All AWS work is deployed and verified in production. What remains is entirely in
the React app.

---

## 1. Why this is being built

Operators upload counterparty due-diligence documents by choosing a category and
a document type from two dropdowns, then uploading one file. Two failures follow
from that, both visible in production data.

**The type is chosen before anything has read the file.** `Expanded-Lender-Memo.pdf`
is filed as `mfa-document` and is now the only source feeding Section VI of a
live credit memo. Every pricing, fee, pledge and set-off fact in that memo comes
from a marketing document. It is populated, it is wrong, and it raises no
warning precisely because it is populated.

**One file often holds several documents.** A corporate pack arrives as one PDF
containing articles, a questionnaire and financial statements. There is one
dropdown and several right answers, so the same file is uploaded repeatedly
under different types. One file in the register is filed five times. Across the
register, 28 distinct files occupy 67 rows — 39 redundant extraction passes over
bytes already read.

**The fix:** remove the dropdowns from the upload step. The operator drops files;
a classifier reads each one, decides whether it holds one document or several,
and proposes a type per part; the operator reviews and corrects. Correcting a
proposal is a smaller and better-informed job than filling in a form before
anything has read the file.

---

## 2. What already exists

### Deployed and working — do not rebuild

| Thing | Where |
|---|---|
| `requestPresignedPost.ts` | `/backend/documents/` — Call 1 of filing |
| `postToS3.ts` | `/frontend/utils/` — Call 2, browser POST |
| `usePresignedUpload.ts` | `/frontend/hooks/` — chains the two |
| `UploadPanel.tsx` | `/frontend/components/documents/` — single-file dropzone |
| `CounterpartyDdSection.tsx` | `/frontend/components/documents/` — current UI |

The two-call presigned flow works. CSP `connect-src` and the bucket's CORS both
allow the browser POST from `https://vmac--credit-memo-viewer.retool.app`.

### New AWS resource to register

A REST API resource is needed for the classifier Lambda. If it is not yet
registered:

| Field | Value |
|---|---|
| Name | `classifierLambda` |
| Base URL | `https://xuctjirh6wfbihx3rj6bx5md2m0cjeet.lambda-url.us-east-2.on.aws` |
| Headers | `Content-Type: application/json` |
| Exclude default headers | checked |
| Auth | AWS Signature v4 |
| Region | `us-east-2` |
| Service Name | `lambda` — **not** `execute-api` |
| Credentials | same key pair as `triggerLambdaToPresignedPost` |

Service Name is part of the SigV4 signature. A wrong value returns a bare 403
with no explanation. Exposed to backend functions as the global
`classifierlambda`.

---

## 3. How a file moves through the system

Five steps per file. Steps 1 to 3 write nothing an operator will ever see.

```
  1  browser -> staging/            put the original somewhere private
  2  browser -> classifier analyze  read it, propose a split
  3  ---- operator reviews and edits the proposal ----
  4  browser -> classifier cut      one call per confirmed part
  5  browser -> presign + S3 POST   file the binder, then each part
```

**Why staging exists.** `staging/` is a prefix in the documents bucket that no
event rule matches. A file placed there is not registered, not indexed, not
extracted, and appears in no document list. It expires by itself after seven
days. That is what makes Cancel free: nothing was filed, and abandoned bytes
clean themselves up.

**Why the original is filed too.** When a file is split, the original is filed
alongside the parts under `document_class: 'source-binder'`. Without it, each
part's `parent_document_id` would point at something that expired, and nobody
could open the binder a memo fact came from. `source-binder` is excluded from
memo scope, so the original is stored and openable but never feeds a memo —
otherwise the binder and its own parts would both contribute the same content.

**When a file is not split** — one part covering every page — **file only that
one document. No binder.** Filing both would create two registry rows with
identical bytes, which is the duplication this work exists to remove.

---

## 4. The screen

Replaces the upload half of `CounterpartyDdSection.tsx`. The document registry
table below it stays as it is.

Three states in sequence, replacing each other in place. No modal, no wizard.

### State 1 — Select

```
+--------------------------------------------------------+
|  Counterparty   [ Manty SA                         v ] |
|                                                        |
|  +--------------------------------------------------+  |
|  |         Drop files here or click to browse       |  |
|  +--------------------------------------------------+  |
|                                                        |
|  Binder1.pdf                       2.4 MB          x   |
|  Manty-financials-2025.pdf         0.8 MB          x   |
|  Corporate-presentation.pdf       11.2 MB          x   |
|                                                        |
|                                  [ Analyse 3 files ]   |
+--------------------------------------------------------+
```

- Counterparty picker first, required. Nothing else enabled until it is set.
  (In the existing component `counterpartyId` arrives as a prop — keep that.)
- Multi-file drop zone: drag-drop and click-to-browse.
- Each file listed with size and a remove control.
- **No category or type dropdown anywhere on this screen.** This is the point of
  the change.
- Primary button reads `Analyse N files`, disabled with no files.

### State 2 — Review

One card per file, stacked. Cards resolve independently as each analysis
returns — a fast file must not wait behind a slow one.

```
+--------------------------------------------------------+
|  Binder1.pdf                      31 pages, 3 parts    |
+--------------------------------------------------------+
|  Pages   Document type             Conf.  Why          |
|  1-6     [ Articles             v]  high  Certificate. |
|  7-22    [ Operations Memo      v]  high  Company desc |
|  23-31   [ Beneficial Ownership v]  low   Shareholder  |
|                                                        |
|  (i) The original will also be filed, so any part can  |
|      be opened alongside the document it came from.    |
+--------------------------------------------------------+

+--------------------------------------------------------+
|  Manty-financials-2025.pdf        12 pages, 1 part     |
+--------------------------------------------------------+
|  Pages   Document type             Conf.  Why          |
|  1-12    [ Financial Statements v]  high  Balance sheet|
+--------------------------------------------------------+

+--------------------------------------------------------+
|  Corporate-presentation.pdf       Could not analyse    |
+--------------------------------------------------------+
|  No extractable text on any of 24 pages. This looks    |
|  like a scan.                                          |
|  [ File whole document v ]     [ Retry ]  [ Remove ]   |
+--------------------------------------------------------+

                           [ Cancel ]  [ File all ]
```

Rules:

- **Only the type cell is editable.** Page ranges belong to the classifier. If
  the ranges are wrong the operator cancels and files manually — an operator
  editing page boundaries by hand is slower and more error-prone than the
  problem it solves.
- **The type dropdown lists only counterparty-DD classes**, grouped by category.
  See section 6 for how to load them.
- **Confidence is shown per row.** `low` gets visible emphasis — amber text or a
  dot. It is not a blocker; it is where attention should go.
- **The rationale column** is the classifier's one-line reason. Truncate with a
  tooltip for the full text.
- **A single-part file shows one row.** This is the common case for ordinary
  uploads and must not look like an error or a failure to split.
- **A failed analysis does not block the batch.** That card offers a manual type
  dropdown, a retry, and a remove. The others proceed.
- **`File all` is disabled** while any card is still analysing.

### State 3 — Filing

```
+--------------------------------------------------------+
|  Filing 3 documents...                                 |
|                                                        |
|  Binder1.pdf                                           |
|    original                                    done    |
|    pages 1-6  . Articles                       done    |
|    pages 7-22 . Operations Memo                ...     |
|    pages 23-31 . Beneficial Ownership          -       |
|  Manty-financials-2025.pdf                     -       |
+--------------------------------------------------------+
```

- Per-item progress. Sequential within a file; files may run in parallel.
- On completion, a summary line and a refresh of the document table.
- **A partial failure is reported, not rolled back.** Documents already filed
  stay filed; failed ones are listed with their errors and a retry. Rolling back
  would mean deleting registry rows, which is worse than an incomplete batch the
  operator can see and finish.

---

## 5. Files to create

Three backend functions. Full source below — create them verbatim.

### `/backend/documents/stageDocument.ts`

```typescript
// Step 1 of the parse-first flow: get a presigned POST for dropping an original
// into staging/.
//
// staging/ is a prefix in the documents bucket that no EventBridge rule
// matches. An object placed there is not registered, not normalized, not
// extracted, and appears in no document list. It expires by itself after seven
// days. That is what makes Cancel free — the operator's abandoned work costs a
// dead object that cleans itself up, and there is no registry row to undo.
//
// This cannot go through triggerLambdaToPresignedPost. That Lambda computes a
// canonical key under trader/ or counterparty/ from the scope it is given, and
// a staged original has no scope yet — working out what it is is the entire
// point of the classifier. It also issues an HMAC upload token that causes
// uploads-finalize-event to register the object, which is precisely what must
// not happen here.
//
// Writes nothing. Safe to test-run.
//
// Returns { ok } like requestPresignedPost so callers handle both the same way.

type Params = {
  originalFilename: string
  // MUST be the true byte length. It is pinned into the S3 policy as an exact
  // content-length-range — not a range with slack — so a wrong value fails the
  // browser POST, not this call.
  expectedSizeBytes: number
  contentType?: string
  // Omit on the first file of a batch and reuse the returned value for the
  // rest, so one operator action produces one run.
  runId?: string
}

export type StageSuccess = {
  ok: true
  run_id: string
  staging_key: string
  url: string
  fields: Record<string, string>
  expires_in: number
}
export type StageFailure = { ok: false; errors: string[] }
export type StageResult = StageSuccess | StageFailure

type LambdaResponse =
  | {
      run_id: string
      staging_key: string
      url: string
      fields: Record<string, string>
      expires_in: number
    }
  | { errors: string[] }

export default async function stageDocument(req: {
  params: Params
}): Promise<StageResult> {
  const p = req.params

  if (!p.originalFilename?.trim()) {
    return { ok: false, errors: ['originalFilename is required'] }
  }
  if (!Number.isInteger(p.expectedSizeBytes) || p.expectedSizeBytes < 1) {
    return { ok: false, errors: ['expectedSizeBytes must be a positive integer'] }
  }

  const { data } = await classifierlambda.rawRequest<LambdaResponse>({
    path: '',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: {
      action: 'stage',
      original_filename: p.originalFilename,
      expected_size_bytes: p.expectedSizeBytes,
      ...(p.contentType != null ? { content_type: p.contentType } : {}),
      ...(p.runId != null ? { run_id: p.runId } : {}),
    },
  })

  // A malformed or absent body would otherwise surface as a TypeError on
  // undefined two lines down — a crash instead of a message.
  if (!data || typeof data !== 'object') {
    return { ok: false, errors: ['Classifier returned an unexpected response'] }
  }
  if ('errors' in data && Array.isArray((data as { errors: unknown }).errors)) {
    return { ok: false, errors: (data as { errors: string[] }).errors }
  }

  const ok = data as Extract<LambdaResponse, { staging_key: string }>
  return {
    ok: true,
    run_id: ok.run_id,
    staging_key: ok.staging_key,
    url: ok.url,
    fields: ok.fields,
    expires_in: ok.expires_in,
  }
}
```

### `/backend/documents/analyzeDocument.ts`

```typescript
// Step 2 of the parse-first flow: read a staged original and propose how to
// split it.
//
// Proposes only. Nothing is cut, nothing is written, nothing is filed. The
// operator reviews the result and either confirms each part or rejects the lot.
//
// Why this exists: operators receive bound PDFs — a corporate pack holding
// articles, a questionnaire and financial statements in one file. With one
// document-type dropdown and several right answers, the same file gets uploaded
// repeatedly under different types. One file in the register is filed five
// times; across the register 28 distinct files occupy 67 rows. Each duplicate
// is a separate extraction pass over bytes the system had already read.
//
// Writes nothing. Safe to test-run.

type Params = {
  stagingKey: string
  counterpartyId: number
  originalFilename: string
}

export type ProposedPart = {
  part_index: number
  page_from: number
  page_to: number
  proposed_document_class: string
  // Derived from the class by the classifier, never chosen separately. That
  // removes an entire failure mode: a class/category pair that does not exist.
  proposed_dd_category: string
  confidence: 'high' | 'medium' | 'low'
  rationale: string
  // Lower-cased, extension stripped, page range embedded. logical_name is part
  // of the resolver's grouping key, so two parts of the same class from one
  // binder must not collide on it.
  logical_name: string
}

export type AnalyzeSuccess = {
  ok: true
  page_count: number
  pages_without_text: number
  size_bytes: number
  parts: ProposedPart[]
  // The whole file, filed alongside the parts under document_class
  // 'source-binder' so any part can be opened beside the document it came from.
  // Excluded from memo scope, so it is stored and openable but never feeds a
  // memo — otherwise the binder and its own parts would both contribute the
  // same content.
  binder: {
    proposed_document_class: 'source-binder'
    proposed_dd_category: 'source'
    logical_name: string
    original_filename: string
  }
}

export type AnalyzeFailure = {
  ok: false
  errors: string[]
  // True when the call itself worked but the answer could not be trusted —
  // most often a scan with no text layer. The operator can retry or file the
  // document whole. Distinct from a server error, which is not retryable.
  retryable: boolean
}

export type AnalyzeResult = AnalyzeSuccess | AnalyzeFailure

type LambdaResponse =
  | {
      page_count: number
      pages_without_text: number
      size_bytes: number
      parts: ProposedPart[]
      binder: AnalyzeSuccess['binder']
    }
  | { errors: string[]; retryable?: boolean }

export default async function analyzeDocument(req: {
  params: Params
}): Promise<AnalyzeResult> {
  const p = req.params

  if (!p.stagingKey?.startsWith('staging/')) {
    return {
      ok: false,
      errors: ['stagingKey must be a staging/ key'],
      retryable: false,
    }
  }
  if (!Number.isInteger(p.counterpartyId)) {
    return { ok: false, errors: ['counterpartyId is required'], retryable: false }
  }

  const { data } = await classifierlambda.rawRequest<LambdaResponse>({
    path: '',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: {
      action: 'analyze',
      staging_key: p.stagingKey,
      counterparty_id: p.counterpartyId,
      original_filename: p.originalFilename,
    },
  })

  if (!data || typeof data !== 'object') {
    return {
      ok: false,
      errors: ['Classifier returned an unexpected response'],
      retryable: true,
    }
  }
  if ('errors' in data && Array.isArray((data as { errors: unknown }).errors)) {
    const err = data as { errors: string[]; retryable?: boolean }
    return { ok: false, errors: err.errors, retryable: err.retryable ?? false }
  }

  const ok = data as Extract<LambdaResponse, { page_count: number }>
  return {
    ok: true,
    page_count: ok.page_count,
    pages_without_text: ok.pages_without_text,
    size_bytes: ok.size_bytes,
    parts: ok.parts,
    binder: ok.binder,
  }
}
```

### `/backend/documents/cutDocumentPart.ts`

```typescript
// Step 4 of the parse-first flow: cut ONE confirmed part out of the staged
// original and write it back to staging/.
//
// One part per call. The operator confirms N parts and the client makes N
// calls. Each stays short, and a failure on one part does not cost the others.
//
// Runs only after the operator has accepted the part, so a rejected proposal
// costs one read in analyze and no cutting at all.
//
// Writes to staging/ only. The part is filed into counterparty/ afterwards by
// requestPresignedPost + the browser POST, which is what owns tagging, identity
// checks and the registry row. The classifier holds no permission on
// counterparty/ and cannot file anything itself.

type Params = {
  // The staged ORIGINAL, not a part. Every cut reads from the same source.
  stagingKey: string
  // From the analyze response for this part. Carries the page range, so two
  // parts of the same class from one binder cannot collide.
  logicalName: string
  // From the stage response. Same value across every part of one run, and
  // written to document_registry.upload_session_id.
  runId: string
  pageFrom: number
  pageTo: number
  partIndex: number
}

export type CutSuccess = {
  ok: true
  part_staging_key: string
  size_bytes: number
  page_count: number
  content_type: string
}
export type CutFailure = { ok: false; errors: string[] }
export type CutResult = CutSuccess | CutFailure

type LambdaResponse =
  | {
      part_staging_key: string
      size_bytes: number
      page_count: number
      content_type: string
    }
  | { errors: string[] }

export default async function cutDocumentPart(req: {
  params: Params
}): Promise<CutResult> {
  const p = req.params

  if (!p.stagingKey?.startsWith('staging/')) {
    return { ok: false, errors: ['stagingKey must be a staging/ key'] }
  }
  if (!p.logicalName?.trim()) {
    return { ok: false, errors: ['logicalName is required'] }
  }
  if (!p.runId?.trim()) {
    return { ok: false, errors: ['runId is required'] }
  }

  // Checked here for a clear message rather than a round trip. The Lambda
  // re-validates the range against the actual page count regardless — these are
  // separate requests and the client controls this payload, so a range that was
  // valid when proposed is not evidence it is valid now.
  for (const [name, value] of [
    ['pageFrom', p.pageFrom],
    ['pageTo', p.pageTo],
    ['partIndex', p.partIndex],
  ] as const) {
    if (!Number.isInteger(value)) {
      return { ok: false, errors: [`${name} must be an integer`] }
    }
  }
  if (p.pageFrom < 1 || p.pageFrom > p.pageTo) {
    return {
      ok: false,
      errors: [`page range ${p.pageFrom}-${p.pageTo} is not valid`],
    }
  }

  const { data } = await classifierlambda.rawRequest<LambdaResponse>({
    path: '',
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: {
      action: 'cut',
      staging_key: p.stagingKey,
      logical_name: p.logicalName,
      run_id: p.runId,
      page_from: p.pageFrom,
      page_to: p.pageTo,
      part_index: p.partIndex,
    },
  })

  if (!data || typeof data !== 'object') {
    return { ok: false, errors: ['Classifier returned an unexpected response'] }
  }
  if ('errors' in data && Array.isArray((data as { errors: unknown }).errors)) {
    return { ok: false, errors: (data as { errors: string[] }).errors }
  }

  const ok = data as Extract<LambdaResponse, { part_staging_key: string }>
  return {
    ok: true,
    part_staging_key: ok.part_staging_key,
    size_bytes: ok.size_bytes,
    page_count: ok.page_count,
    content_type: ok.content_type,
  }
}
```

Then add the hooks to `/frontend/hooks/backend/documents.ts` if that file is
generated from the backend functions; if it does not update itself, callers can
use `useBackendFunction('/backend/documents/stageDocument.ts')` directly.

---

## 6. Files to modify

### `requestPresignedPost.ts` — return `document_id`

The presign Lambda now returns `document_id` in its 200 body. Parts need the
binder's id to set `parent_document_id`, and there is currently no other way for
the client to learn it.

Add to `PresignSuccess`, to the `LambdaResponse` success arm, and to the
returned object:

```typescript
export type PresignSuccess = {
  ok: true
  upload_token: string
  document_id: string        // <- add
  url: string
  fields: Record<string, string>
  expires_at: string
}
```

```typescript
  return {
    ok: true,
    upload_token: ok.upload_token,
    document_id: ok.document_id,   // <- add
    url: ok.url,
    fields: ok.fields,
    expires_at: ok.expires_at,
  }
```

### `usePresignedUpload.ts` — surface `document_id`, drop the shared `busy`

Two changes.

**1. Return `document_id` alongside the S3 result.** The caller files the binder,
reads its `document_id`, and passes it as `parentDocumentId` on every part. Add
it to `PresignResult`'s success arm and to what `upload()` resolves with:

```typescript
return { ...s3Result, documentId: result.document_id }
```

**2. `busy` is a single boolean for the whole hook.** With several files filing
in parallel, the first to finish clears it for all of them. Either key it by an
id supplied by the caller, or drop it and let the caller track per-file state.
Per-file state in the component is simpler and is what the progress list needs
anyway.

### `UploadPanel.tsx` — multi-file, and stop computing base64

Two changes.

**1. Multiple files.** `useState<File | null>` becomes `useState<File[]>`, the
input gets `multiple`, the list renders each with its own remove control, and
`onUpload` becomes `onAnalyse(files: File[])`.

**2. `handleSubmit` calls `readAsBase64(file)` on every upload and the
counterparty path never reads it.** For a 59 MB binder that is a wasted
FileReader pass and a ~79 MB string, on exactly the path the presigned flow
exists to avoid. Make it lazy:

```typescript
export type SelectedFile = {
  name: string
  type: string
  size: number
  raw: File
  /** Base64 callers only. Not computed unless called. */
  getBase64: () => Promise<string>
}
```

Other callers of `UploadPanel` (trader-docs) still use base64 — keep it working,
just do not compute it up front.

### `CounterpartyDdSection.tsx` — the new flow

Replace the `UploadPanel` + two `FieldSelect` block with the three-state screen.
Keep `DocumentRegistryTable`, `DocumentPreviewDialog`, the `canUpload` read-only
branch, and the `loadDocs` + delayed re-poll pattern — the registry row is
written asynchronously, so the existing `window.setTimeout(loadDocs, 4000)` is
still needed after filing completes.

**Document classes.** `useGetDocumentClasses` currently takes
`{ category, dataDomain }` and the new screen has no category picker. Call it
once per `dd_category` from `useGetDdCategories` and merge the results into one
grouped option list. Build it once when the counterparty loads, not per row.

---

## 7. Wiring — exact call sequence

### On `Analyse N files`, per file, in parallel

```
1. stageDocument({ originalFilename, expectedSizeBytes, contentType, runId? })
      -> { run_id, staging_key, url, fields, expires_in }

   Omit runId on the first file, reuse the returned run_id for the rest, so one
   operator action produces one run.

2. POST the raw File to `url` with `fields`, using the existing postToS3 helper.
   Success is 204.

3. analyzeDocument({ stagingKey, counterpartyId, originalFilename })
      -> { page_count, parts[], binder }
```

Render each card as its analyze resolves.

### On `File all`, per file

**Order matters. Binder first, then parts.**

```
IF parts.length > 1:

  a. cutDocumentPart(...) for each part
        -> { part_staging_key, size_bytes, page_count }

  b. File the BINDER:
     - fetch the staged original from its staging URL as a Blob
     - usePresignedUpload.upload(file, {
         dataDomain: 'counterparty-dd',
         logicalName: binder.logical_name,
         documentClass: 'source-binder',
         scope: { counterparty_id, dd_category: 'source' },
         uploadSessionId: runId,
       })
     - keep the returned documentId

  c. File each PART, in order:
     - fetch the part from its part_staging_key as a Blob
     - usePresignedUpload.upload(partFile, {
         dataDomain: 'counterparty-dd',
         logicalName: part.logical_name,
         documentClass: part.proposed_document_class,   // after operator edit
         scope: {
           counterparty_id,
           dd_category: part.proposed_dd_category,      // re-derive if edited
         },
         parentDocumentId: binderDocumentId,
         pageFrom: part.page_from,
         pageTo: part.page_to,
         uploadSessionId: runId,
       })

ELSE (single part covering every page):

  File the original ONCE under the proposed class. No binder, no provenance
  fields. It is an ordinary upload.
```

**Wait for the binder's 204 before starting the parts.** Its `document_id` is
what they reference.

### On Cancel

Drop the state. Staged objects expire on their own in seven days; there is
nothing to delete and no registry row to undo.

---

## 8. Values and where they come from

| Field | Source |
|---|---|
| `counterparty_id` | Component prop |
| `documentClass` | The type cell, after any operator edit |
| `dd_category` | Derived from the class — never chosen separately. If the operator changes the class, re-derive the category from the class list |
| `logicalName` | The classifier's, per part. Lower-cased, extension stripped, page range embedded |
| `pageFrom` / `pageTo` | The classifier's, not editable |
| `parentDocumentId` | The binder's `document_id`, from its presign response |
| `uploadSessionId` | `run_id` from step 1, same for every file in the batch |
| `documentState` | Omit — the backend defaults to `submitted` |
| `retentionClass` | Omit — the backend defaults to `credit-doc-7y` |
| `expectedSizeBytes` | The true byte length. Pinned into the S3 policy, so a wrong value fails the POST, not the presign |

---

## 9. Behaviour that is easy to get wrong

- **Do not auto-file anything.** Every part is filed only after the operator
  presses `File all`. Silent misclassification is the failure this work exists
  to prevent; automating it faster is not a fix.
- **The three provenance fields travel together.** `parentDocumentId`,
  `pageFrom`, `pageTo` — all three or none. Supplying one or two is a 400. A
  part with a parent but no page range cannot be drilled back to; a page range
  with no parent points nowhere.
- **A single-part file gets no binder and no provenance fields.**
- **A low-confidence part is filed if the operator confirms it.** Confidence is
  information, not a gate.
- **`source-binder` must never appear in the operator's type dropdown.** An
  operator filing a whole document as a binder produces a document nothing will
  ever read. It is marked `operator_selectable: false` in the vocabulary — if
  `getDocumentClasses` returns that flag, filter on it; if not, exclude the
  value explicitly.
- **`analyzeDocument` returns `retryable` separately from `errors`.** A scan
  with no text layer is `retryable: true` — offer Retry and File-whole. A server
  error is `false` — offer Remove.
- **There is no finalize call.** S3 emits an event, EventBridge routes it, and a
  Lambda writes the registry row. A deprecated finalize endpoint still exists;
  calling it double-writes.
- **The registry row is written asynchronously.** Refresh the document table on
  completion and again a few seconds later, as the current code already does.
- **A 400 from any of these functions is actionable.** `errors` is an array of
  plain sentences. Show them.

---

## 10. Build order

The screen can be built before the classifier resource is registered by stubbing
the three backend functions' responses. The shapes in section 5 are final.

1. `UploadPanel` multi-file + lazy base64
2. `requestPresignedPost` and `usePresignedUpload` — `document_id` passthrough
3. The three backend functions
4. State 1 and State 2 against stubbed analyze responses
5. State 3 and the filing sequence
6. Swap the stubs for the real calls
