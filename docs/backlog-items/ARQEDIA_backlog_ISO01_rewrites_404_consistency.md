# ISO-01 — `GET /memos/{id}/rewrites` answers `200`-empty for a memo that is not the tenant's

**Raised 4 October 2026**, during the tenant-isolation pentest
(`docs/pentest-results/tenant_isolation_2026-10-04.md`, vector 1a).
**Low priority. Not a security defect** — no data crosses the tenant boundary.
A consistency wrinkle only.

---

## What was observed

As tenant A, calling the endpoint with tenant B's memo ids — and with a memo id
that does not exist at all (`99999`) — returned:

```
GET /memos/146/rewrites   -> 200  {"memo_id": 146, "rewrites": []}
GET /memos/99999/rewrites -> 200  {"memo_id": 99999, "rewrites": []}
```

Every sibling endpoint refuses the same cross-tenant id with `404`:

```
GET /memos/146            -> 404  {"error": "not found"}
GET /memos/146/working    -> 404  {"error": "not found"}
```

## Why it is not a leak

`list_rewrites` (`lambda/api/app.py:1822`) is tenant-scoped at the query:

```sql
SELECT ... FROM memo_rewrite
WHERE tenant_id = :t AND memo_id = :m
```

A foreign or nonexistent memo matches no rows, so the result is an empty list.
The handler (`app.py:3000-3002`) returns `200` with whatever `list_rewrites`
gives it, without first checking that the memo belongs to the caller — unlike
`GET /memos/{id}` and `/working`, which look the memo up and return `404` when
it is `None`. So the endpoint never reveals another tenant's rewrite content; it
only fails to 404.

## Why it is nevertheless worth a small change

Two readers' arguments, left for whoever picks this up to settle:

- **For aligning to `404`:** every other memo route 404s a foreign id;
  answering `200` here is an inconsistency a future reviewer has to re-derive is
  safe (this pentest spent a drill-down doing exactly that). If the query were
  ever edited to drop the `tenant_id` clause, this is the one memo route whose
  missing existence check would turn that into a cross-tenant read without a
  test noticing — the 404 check would be a second line of defence.

- **For leaving it:** `200`-empty is returned for *both* a foreign id and a
  nonexistent one, so it is not an existence oracle — arguably a hair better
  than `404`, which distinguishes "not yours" from "no such memo". The current
  behaviour leaks strictly nothing.

## Suggested change (if taken)

In `GET /memos/{id}/rewrites` (`app.py:3000`), look the memo up first — reuse
`get_memo(tenant_id, memo_id)` or a lightweight existence check scoped by
`tenant_id` — and return `404` when it is not the tenant's, before calling
`list_rewrites`. Keep the empty-list `200` for a memo that is the tenant's but
has no rewrites yet. One handler, no schema change.

## Verification

- `SELECT ...` guard confirmed at `app.py:1852`.
- Behaviour confirmed live against tenants 1 and 2 on 4 October 2026.
