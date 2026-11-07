# ARQEDIA Mobile

React Native (Expo, TypeScript). Signs in to the live dev backend and works
in one workspace at a time.

## Screens

- **Memos**: the open engagements, then one engagement's memos, then a memo
  and its PDF.
- **Share**: pick a memo, send it, revoke a share, open a share's details.
- **Account**: the signed-in email, the workspace list (the active one
  ticked), and Sign out.

The active workspace travels on every request as `?workspace=<id>`, as on
the web (`src/workspace.tsx`, `src/api/client.ts`). It is remembered per
phone and per tenant. An administrator with no workspace is told to set one
up on the web; the app offers no setup.

## What it points at

`src/config.ts`: the dev Cognito pool, the web app client, and the dev API,
the same values as `ui/src/config.ts`. Dev is production for now (ENV-01),
so every build, store builds included, signs in to dev until this changes.

`src/types/index.ts` is copied by hand from `ui/src/api.ts`; a field that
changes there changes here.

## Run on a phone

The app needs a development build, not Expo Go (Amplify's native module).
Build once, and again only after a native change (a native package, or
`app.json`):

```
npm install
npx eas build --profile development --platform android
```

Install the APK from the link EAS gives, then serve the JavaScript:

```
npx expo start --dev-client
```

Open the app and connect to the server (same Wi-Fi, or add `--tunnel`).

## Builds for other people

| Profile | What it makes | For |
|---|---|---|
| `development` | APK that loads JS from your PC | you |
| `preview` | standalone APK, installed from a link | Android testers |
| `production` | store build, then `npx eas submit` | Google Play, App Store |

`npm run typecheck` checks the code.
