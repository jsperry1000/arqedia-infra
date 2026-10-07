# Arqedia Mobile — scaffold

React Native (Expo, TypeScript). Three screens, matching the approved canvas
mockup: Memos (list), Share (memo picker + send + revoke), Memo Detail
(download / open-in-viewer).

## Drop-in path

Place this folder at `c:\terraform\arqedia\mobile`.

## Run

```
npm install
npx expo start
```

## What's real vs. stubbed

- UI, navigation, theme (eBL palette): built.
- `src/api/client.ts`: mock data only. No live API base URL, auth flow, or
  endpoint list exists in the project docs yet — this is the seam to wire
  once that's available.
- Download / Open in PDF viewer buttons on the Memo Detail screen: UI only,
  not wired to a real file.
- Login / auth screens: not built yet — out of scope until the mobile-facing
  auth flow is specified.

## Not inferred, flagged here rather than guessed

- `Memo` and `ShareGrant` fields not named in `share_viewer_spec_v1.md`
  (title, memo_type, page_count, file_size_bytes, etc.) are marked
  `PROPOSED` in `src/types/index.ts` — display conveniences, not schema.
