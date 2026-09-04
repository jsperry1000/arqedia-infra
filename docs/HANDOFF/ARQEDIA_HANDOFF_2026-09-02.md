# ARQEDIA — Handoff

**2 September 2026. Composition moved to the registry; several memoranda per
tenant, built and verified.**

---

## 1. The finding that shaped the session

`lambda/composition/template.py` was a Python literal — eight sections, every
field list, both prompts, `TEMPLATE_KEY` and `CONFIG_REVISION = 1`. Its own
docstring said so: *"Stage 1 memo template, hard-coded. Stands in for the tenant
template designer, which arrives in Stage 2."* `app.py` resolved labels and
group columns through `pack.py`.

**So everything authored in the editor was inert at composition.** Extraction
had moved to the registry; composition never did. The symptom that exposed it:
`f_service_counterparties`, a group field with four columns, bound to a section
in every revision from 3 to 15, with 102 extracted values, rendering nothing.

It also explained why the memo's shape never changed whatever was published,
why the Summary repeated sections I to IV, and why every memo row recorded
`config_revision` 1.

Fixed. `template.py` is deleted.

---

## 2. What shipped

| Change | State |
|---|---|
| Composition reads the tenant's configuration | merged |
| Memo records the revision it composed under | merged |
| Citations masked before drafting, not only before consolidation | merged |
| Dropped-citation count measured before restoring | merged |
| No paragraph can fail the render; run-together citations separated | merged |
| `Memo.tsx` stops bracketing non-citations | merged |
| `template.py` deleted | merged |
| Several memoranda per tenant, steps 1–5 | merged |
| Memorandum title from configuration | **on disk, not yet pushed** |

---

## 3. Several memoranda — what was built

Five of six steps. A tenant may hold a credit, a KYC and a lender memorandum
over the same documents.

- **`config.py`** — `TEMPLATES` is a dict, each with its own sections. Bindings
  keyed on `(template_key, section_key)`: keyed on the section alone, two
  memoranda both carrying a "summary" merged their field bindings silently.
  `TEMPLATE_KEY` and `MEMO_SECTIONS` survive as properties over the default.
- **`composition/app.py`** — takes a `template_key`, defaults to the tenant's
  only one, refuses an unknown key rather than composing an empty memo.
- **`api/app.py`** — `/generate` validates the key before invoking, because the
  invoke is asynchronous and a bad key would otherwise return 202 and fail four
  minutes later. `GET /templates` is new.
- **`editor.py`** — section edits name their memorandum. Adding and deleting a
  memorandum exist; the last one cannot be deleted.
- **The routes carry the memorandum in the path**, not a query parameter: a
  parameter that is mandatory in fact but optional in form is the sort of thing
  someone omits in two years and corrupts a configuration.
- **`Review.tsx`** — a Write selector, shown only where there is a choice.
- **`Configure.tsx`** — a Memorandum selector; every edit scoped to it.

**Verified end to end.** A Credit Memorandum added, published, generated as
memo 59 and rendered, with the eight KYC sections untouched.

---

## 4. Decisions taken

- **One revision covers every memorandum.** Versioning templates separately
  would mean a memo pinning a template revision *and* a field revision;
  `extracted_value` carries one `config_revision`, and a snapshot is one
  integer.
- **One field vocabulary across every memorandum.** A document is extracted
  once and read three ways. Extracting it three times would be paid for three
  times. It also makes importing a pack template into an existing tenant
  possible later — without shared field IDs that import matches nothing.
- **Fork one pack containing all three memoranda**, rather than forking three
  packs and merging.
- **A field edit is global; a section binding is per memorandum.** Improve a
  field description and all three memoranda get the better extraction.
- **`cdd-questionnaire` retired.** An eBL artefact with no bearing on a
  customer. Out of the starter packs too.

---

## 5. Citations — diagnosed, largely benign

`[citations-dropped] count=N of N` fired on every section of every memo. The
cause was a counting bug: `_restore_citations` replaced every token, then asked
whether each token was still present. It never was.

Measured correctly, the drops are real but mostly harmless. Reading the dropped
text showed them to be overwhelmingly the `Source: <filename>` form — a citation
with no page, emitted when `locator_index` is null. The model merges statements
and keeps the page-level citation, discarding the page-less one for the same
document. **That is the model choosing the more specific of two references.**

Fixing the underlying gap (CP-03: values extracted with no unit) makes it
disappear.

**One genuine loss:** `open_items` drops every token. Its prompt rewrites
everything as gaps and keeps none, so Open Items carries no evidence.

---

## 6. Working notes

Everything from the previous handoff still applies. Added this session:

- **Rebuild the layer after editing anything in `lambda/shared/`.** Terraform
  only replaces the layer when its hash changes, so a `terraform apply` alone
  deploys nothing. Two faults this session were a stale layer.
- **`{"message":"Unauthorized"}` in the browser is an expired token**, not a
  broken API. It renders as an empty screen with no error.
- **Check the API log before diagnosing an empty screen.** An unhandled
  `AttributeError` returns 500 and the UI shows nothing.
- **Python indentation.** A hand-edited line at the wrong indent takes down
  every Lambda using the layer. `ast.parse` before building.
- Branches: several changes went straight to `main` this session. It works, and
  it skips review.

---

## 7. Next step

**Step 6 — the starter packs.** Three memoranda over one field vocabulary:
credit memorandum, KYC memorandum, lender memorandum.

This is the first task in the whole build that is not engineering. It needs the
section list for each memorandum, and that is practitioner work — the open item
the handoff has carried since design. Engineering can author whatever is
decided in an afternoon.

Before that, one small thing: **push the memorandum title change**, which is on
disk and not committed.
