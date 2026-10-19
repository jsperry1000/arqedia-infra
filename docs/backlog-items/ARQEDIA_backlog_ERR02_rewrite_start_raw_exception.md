# ERR-02 — A rewrite that cannot be started shows the raw exception text

**Raised 17 October 2026**, from the §7 copy review. **Finding only. Not
fixed.** The ID is proposed.

**Fixed 19 October 2026 on `fix/raw-error-text`.** The exception is logged
as `[rewrite-not-started]` and the row carries `REWRITE_NOT_STARTED`.
Asserted in `test_raw_error_text`. Not live until applied.

---

## What was observed

`start_rewrites` writes a `memo_rewrite` row, then invokes composition
asynchronously. If the invocation raises, the row is marked failed with the
exception in it:

```python
[_p("e", ("could not be started: %s" % exc)[:1024]),
```

`lambda/api/app.py:1942` (the same line on `main` at e35bed9 and on
`fix/copy-review-critical`).

The row's `error` is returned by `GET /memos/{memo_id}/rewrites`
(`list_rewrites`) and rendered as written by `ui/src/Memo.tsx:870` and `:940`.

## What a person therefore sees

`could not be started: ` followed by the exception's own text - for a boto
`ClientError`, botocore's form `An error occurred (<code>) when calling the
Invoke operation: <message>`. Nothing logs the exception: there is no
`print` in that `except`.

`Memo.tsx:521` has its own client-side "The rewrite could not be started."
for a different failure (the POST itself failing); it does not cover this one.

## Verification

- Code read at the lines above. Not exercised live.
