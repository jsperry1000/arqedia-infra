# ROLE-01 — Configure's editing and Publish controls are live for a Member

**Raised 17 October 2026**, from the §7 copy review (item 10, `Account.tsx`).
**Finding only. Not fixed.** The ID is proposed.

---

## What was observed

Configuring and publishing are administrator-only in code: `_require_admin`
guards every draft, editor, publish and active-revision route in
`lambda/api/app.py` (CLAUDE.md, the 17.7 correction). A Member who presses
one of those controls is refused with `403`.

The screens gate only part of that:

| Control | Gated for a Member on screen? | Where |
|---|---|---|
| Get started (first run) | Yes, disabled, with "Setting up the configuration is an administrator's." | `ui/src/App.tsx:516-523` |
| AI Review | Yes, disabled, with "Only an administrator can review the configuration." | `ui/src/Configure.tsx:634-644` |
| Publish | No. Disabled only while busy or while validation forbids it | `ui/src/Configure.tsx:2206-2213` |
| Editing controls (sections, fields, document types, categories, templates) | No `role` check found in `Configure.tsx` | `ui/src/Configure.tsx` |

`useRole()` (`ui/src/upgrade.tsx:112`) already reads the role from the token,
and `App.tsx` uses it. `Configure.tsx` does not import it.

## What a Member therefore meets

Enabled controls that answer `403` on the click, with the server's sentence
"only an administrator may change the configuration". The data is safe; the
server is the control. The screen offers acts the person cannot perform,
which is the case `UpgradePrompt` and the `App.tsx` gate were written to
avoid.

## Verification

- `Configure.tsx`: `grep -n "role\|admin"` matches only the AI Review gate
  (lines 626-644) and an unrelated string at 194.
- Publish button conditions read at `Configure.tsx:2206-2207`.
- Not exercised as a Member on the live domain.
