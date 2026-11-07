# Handoff: mobile app workspace selection, 7 November 2026

**Done.** Built, merged and walked on a device the same day. The proposal and
its two questions are kept below, under "As proposed", for the record.

## Outcome

| PR | What |
|---|---|
| #479 | Workspace selection (`feature/mobile-workspace`) |
| #480 | `tsconfig.json`: `baseUrl` dropped, which TypeScript 6 refuses; `npm run typecheck` runs again |

No server or Terraform change, and no apply.

**Decided by sperry:**

1. The selector is on the **Account** tab: every workspace listed, the active
   one ticked. Memos and Share name it in their headers.
2. An administrator with no workspace is told to set one up on the web. The
   app offers no setup.

**Built.** `src/workspace.tsx` holds the active workspace, read from
`GET /settings` and remembered per tenant in AsyncStorage. `call()` in
`src/api/client.ts` adds `?workspace=<id>` to every request. Memos and Share
start over when it changes. A member with no workspace is shown the server's
own `NO_WORKSPACE_ASSIGNED` sentence.

**Walked** on an Android development build against dev: signed in, and the
workspace cases (administrator with two, member with two, member with one,
administrator with none) reported good by sperry.

**Builds on EAS** (project `chase-creek-llc/arqedia-mobile`):

- development: build `c0485c54-5fba-4cfa-bd18-e8e3709423eb`
- preview (standalone APK for Android testers): build
  `703aefac-d52b-4cf9-92fb-6c4311468e23`

## Open

- **Going live in the stores.** Not started. Needs a Google Play and an Apple
  Developer account. A Google Play personal account made after November 2023
  must run a 14-day closed test with 12 testers first; an organisation account
  is exempt.
- **Which backend a store build points at.** `src/config.ts` is dev, which is
  production for now (ENV-01).
- **Apple and account deletion (5.1.1(v)).** It applies to apps that support
  account creation. This app only signs in, so it is probably not caught, but
  that is not confirmed. Account deletion does not exist anywhere yet.
- **EAS Update** is not set up, so every fix needs a new build.
- **iOS** has not been built or run.

## As proposed (before the build)

The app sent no workspace on any request, and the server chose one
(`lambda/api/app.py`, `ws()`): an administrator got
`config.workspace(tenant, None)`, a member with one got it, a member with
several was refused with `WorkspaceRequired`, and a member with none with
`NO_WORKSPACE_ASSIGNED`. The proposal copied the web app
(`ui/src/workspace.ts`, `ui/src/App.tsx`) and asked where the selector goes
and what an administrator with no workspace sees. Both are answered above.
