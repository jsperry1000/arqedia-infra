# ERR-03 — A non-numeric id or number in a request returns Python's own error

**Raised 17 October 2026**, from the §7 copy review. **Finding only. Not
fixed.** The ID is proposed. Left out of `fix/copy-review-critical` by
decision: that branch catches unreadable JSON only.

---

## What was observed

`lambda/api/app.py` converts request input with `int()` in many places. A
value that is not a number raises `ValueError("invalid literal for int() with
base 10: 'abc'")`, and the dispatcher's catch-all answers every `ValueError`
with its text:

```python
except ValueError as exc:
    return _reply(400, {"error": str(exc)})
```

Because deliberate refusals are also `ValueError`s, the handler cannot tell
the two apart by type. The JSON-decode catch added on
`fix/copy-review-critical` does not cover this case.

## Where request input reaches `int()` (lines on `fix/copy-review-critical`)

| Input | Line(s) |
|---|---|
| `?limit=` on `GET /wallet/ledger` | 3292 |
| `?n=` on `GET /wallet/quote` | 3298 |
| `{document_id}` on `DELETE /documents/{document_id}` | 3185 |
| `{revision}` on `GET /config/{revision}` | 2755, 2757 |
| `revision` in the body of `POST /config/fork` | 3540 |
| `?ids=` on `GET /memos/{memo_id}/rewrites` | 1966 |
| `?unit=` on `GET /documents/{document_id}/passage` | 1442, 1456 |
| `{memo_id}` and `{document_id}` path parameters, inside the route functions | e.g. 611, 780, 1305, 1324, 1541, 1652, 1882, 1964, 2066 |
| `rewrites` list in the body of `POST /memos/{memo_id}/revise` | 1728 |

Not an exhaustive audit: these are the sites found by `grep` for `int(` on a
path parameter, query value or body field.

## What a person therefore sees

`invalid literal for int() with base 10: 'abc'`. In normal use the screens
send numbers, so this is reached by a hand-edited address or request, a
bookmark with a mangled id, or a screen defect.

## Verification

- Handler read at `app.py:3746-3747`. Not exercised live.
