# ARQEDIA — Reading the database directly

**Project context. Reading live state is how RoE 13 is satisfied; this is the
mechanism.**

---

## The connection

There is no direct SQL client. Aurora Serverless v2 sits in a private VPC and
pauses at zero capacity, so everything goes through the RDS Data API.

Set these once per terminal. They are lost when the window closes, which is the
single most common cause of a failed query in this project:

```powershell
$cluster = "arn:aws:rds:us-east-2:667523685221:cluster:arqedia-dev-aurora"
$secret  = "arn:aws:secretsmanager:us-east-2:667523685221:secret:rds!cluster-8f9fa8a3-b863-480a-b1cf-d00308c8b9f1-0e65rq"
$sql     = "SELECT ..."
aws rds-data execute-statement --profile arqedia --resource-arn $cluster --secret-arn $secret --database arqedia --sql $sql --output json
```

Always the `arqedia` profile. Account 667523685221, region `us-east-2`.

---

## Three things that will happen

**`DatabaseResumingException`.** The cluster auto-pauses. Wait fifteen seconds
and run the same line again. Normal operation, not a fault.

**A command that vanishes mid-line.** Long single-line commands get truncated in
the shell. Put the ARNs and the SQL in variables first, always.

**`StatementTimeoutException`.** Usually a query with an unbounded join rather
than a slow database. Add the tenant and revision predicates before blaming the
cluster.

---

## Writing a query that will not mislead

**Always filter on `tenant_id` AND `revision`.** Every configuration table is
keyed on both. A query missing `revision` returns every revision ever
published — twenty-five copies of the same row — and reads as duplication that
is not there.

**Revision 0 is the draft.** Editors write it; nothing in the pipeline reads it.
To change what a memo will say, write revision 0 and publish. To see what a memo
did say, read the revision it recorded.

**Sections and bindings are keyed by template too.** `config_section` and
`config_section_field` are keyed on `(tenant_id, revision, template_key,
section_key)`. Omit `template_key` and two memoranda's sections come back as
one list.

---

## The tables worth knowing

| Table | What it holds |
|---|---|
| `tenant` | `active_revision` — the revision new work files against |
| `config_revision` | One row per revision. Revision 0 is the draft; status `draft` or `published` |
| `config_template` | One row per memorandum: `template_key`, `label` |
| `config_section` | Sections, per template. `numeral`, `title`, `kind`, `prompt`, `context_sections`, `sort_order` |
| `config_section_field` | Which fields a section renders |
| `config_field` | The field vocabulary. `field_key` is permanent identity; `group_key` binds a table's columns |
| `config_document_type` | What a document can be, with the description the classifier reads |
| `config_type_schema` | Which document types feed which schemas — the mapping |
| `document` | One row per document. `state`, `active`, `config_revision`, `page_from`/`page_to` for a part of a file |
| `extracted_value` | Every value, with `field_id`, `row_ordinal`, and the locator columns |
| `memo`, `memo_source`, `claim`, `claim_evidence` | What was written and what it was written from |

---

## Queries that answer the usual questions

**Which revision is live, and what drafts exist**

```sql
SELECT revision, status, note, published_at FROM config_revision
WHERE tenant_id = 1 ORDER BY revision
```

**What memoranda this tenant holds**

```sql
SELECT template_key, label FROM config_template
WHERE tenant_id = 1 AND revision = 0
```

**A memorandum's sections, in the order they will render**

```sql
SELECT sort_order, numeral, section_key, kind, context_sections
FROM config_section
WHERE tenant_id = 1 AND revision = 0 AND template_key = 'stage1-kyc'
ORDER BY sort_order
```

**Where a field renders, and which documents feed it**

```sql
SELECT template_key, section_key FROM config_section_field
WHERE tenant_id = 1 AND revision = 0 AND field_key = 'f_buyers'
```

```sql
SELECT t.type_key FROM config_field f
JOIN config_type_schema t
  ON t.tenant_id = f.tenant_id AND t.revision = f.revision
 AND t.schema_key = f.schema_key
WHERE f.tenant_id = 1 AND f.revision = 0 AND f.field_key = 'f_buyers'
```

**Whether a field was ever extracted**

```sql
SELECT COUNT(*) FROM extracted_value
WHERE tenant_id = 1 AND field_id LIKE 'f_buyers%'
```

That last one distinguishes "never extracted" from "extracted and not
rendered", which are different faults with different fixes and look identical
in a memo.

---

## Writing

A write is legitimate for two things: **repairing a draft** where the editor has
no control for a column, and **investigating**. Both are additive under RoE 3.

Only ever write **revision 0**. A published revision is immutable — that is what
makes a March memo reproduce in September, and what every extracted value is
pinned to. Writing one silently changes memos already generated.

Open a draft in the Configure screen first, or there is no revision 0 to write,
and the update reports zero rows.

```sql
UPDATE config_section SET context_sections = 'identity,ownership'
WHERE tenant_id = 1 AND revision = 0
  AND template_key = 'stage1-kyc' AND section_key = 'summary'
```

Then publish in the editor. A change written to the draft and not published
reaches nothing.

---

## Before diagnosing anything

**Read the live state; never infer it from a file, a name, or a previous
answer.** Most of the wasted time on this project has been the reverse — a
theory about what the configuration must contain, tested three steps later.

Two habits worth keeping:

- When something does not render, ask in order: was it extracted, is it bound,
  is that binding in the *published* revision, and is the deployed code reading
  that revision. Four queries, and they eliminate three of four causes.
- When a screen shows nothing, check the API log before the database. An
  expired token and an unhandled exception both render as an empty screen with
  no error.
