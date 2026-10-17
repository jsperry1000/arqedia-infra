# ERR-01 — A failed Update section shows the raw exception text

**Raised 17 October 2026**, from the §7 copy review. **Finding only. Not
fixed.** The ID is proposed. Left out of `fix/copy-review-critical` because
that branch's brief named `composition/app.py:1280` and `:747`, not this line.

---

## What was observed

In an Update, each section's comparison runs in `compare()`. When one raises,
the exception's class and text become that section's error:

```python
except Exception as exc:  # noqa: BLE001 - recorded on a row
    return section["key"], None, "%s: %s" % (
        type(exc).__name__, exc)
```

`lambda/composition/app.py:1205-1206` on `fix/copy-review-critical`
(`:1195-1196` on `main` at e35bed9).

That string is written to `memo_rewrite.error` by `_update_row(...,
error=error)` (`:1256`), read back by `list_rewrites` in `lambda/api/app.py`
as `error`, and rendered as written by `ui/src/Memo.tsx:870` and `:940`
(`<p className="error">{result.error}</p>`).

## What a person therefore sees

`<ExceptionClass>: <its text>` beside a section of their memorandum - for
instance `ValueError: the model did not answer in the form asked for`, which
`_parse_update` raises (`:1007` on `fix/copy-review-critical`), or the text of
any boto or Python exception raised inside `_merge`. The
exception is not logged anywhere else: the only record of it is the row.

## Related

The whole-run failure on the same path (`:1280` on `main`) was changed on
`fix/copy-review-critical` to log the exception and write a fixed sentence.
This per-section path was not.

## Verification

- Code read at the lines above. Not exercised against a live Update.
