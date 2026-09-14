# site

The public marketing site for arqedia.com. A separate Vite project from `ui/`
deliberately: no Cognito, no API types, no shared runtime. A change here cannot
break the application bundle.

    npm install
    npm run dev      # local
    npm run build    # tsc -b then vite build, into dist/

Built and deployed by `.github/workflows/deploy-site.yml` on push to main
touching `site/**`. `tsc -b` runs first, so a type error stops the deploy.

## Tokens — one source

`src/styles/tokens.css` contains a single `@import` of `ui/src/tokens.css`.
That file is the only place in either codebase where a colour, a typeface or a
radius is declared. Change a value there and the application and this site both
follow.

Nothing here redeclares a token. If a value is needed and is missing, it is
added to `ui/src/tokens.css`.

The hero animation reads its colours from the same variables through
`getComputedStyle`, so it follows too.

Tenant brand colours are not in that file. `brand_deep`, `brand_mid`,
`brand_highlight` and `brand_light` belong to a tenant, are resolved at render
time by `style.palette_for`, and appear only on a rendered memorandum.

## Pages

Multi-page, not a single-page app. `index.html` and `pricing/index.html` are
real files at real paths, so the site distribution carries no 403/404 rewrite
and a genuine 404 stays a 404 — unlike `frontend.tf`, where the app router owns
its paths.

## The mark

One location: `/brand` at the repository root. `index.html` and
`pricing/index.html` reference `logo-deep.svg` from there by relative path and
Vite rewrites it at build. There is no copy in this project and no `public/`
folder — replacing the two files in `/brand` changes the application and the
site together.
