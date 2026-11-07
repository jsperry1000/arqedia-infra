# ARQEDIA — Legal pages handoff, 27 October 2026

Pasted in from a separate Claude Code session. Not launch ready. Nothing is
deployed yet.

## Pushed, two branches

- `docs/legal-v1` — `docs/legal/terms_v1.md`, `privacy_v1.md`, `refunds_v1.md`,
  plus a README and the 27 October decisions record. Docs only, no `web/`
  build. The 20 October draft and the `.docx` are untouched.
- `feature/legal-pages` — branched from the docs branch, PR carries both.
  - Site: `/terms`, `/privacy`, `/refunds`, rendered at build from
    `docs/legal`. Each `noindex`, linked only to each other, no other site
    page links to them.
  - App: acceptance checkboxes at sign-up and invitation, recipient
    registration linked, Refund Policy links beside Subscribe/Top up,
    "Terms and Conditions" at the foot of the rail.
  - Version recording: `config/legal.json` holds version 1 as the one
    source. Signup Lambda refuses sign-up/invitation without the tick or
    with another version, records each acceptance. Recipient registration
    does the same, stores version on the viewer account.
  - Migration 049 adds the acceptance table. **Not applied.**
  - `web/` rebuilt and included.

## Tested

Python: 1,063 tests, 12 new ones passing, only the 4 pre-existing main
failures (`test_archive`, `test_document_delete`). App type-checks and
builds. Site builds; Terms/Privacy checked at desktop width; Accept stays
disabled until ticked.

**Not tested:** phone width (browser wouldn't resize), the real sign-up
checkbox (needs a real emailed code), the recipient form (needs a real
share), the new SQL against a database, any walk on the real domain.

## Deploy order — yours (migration, merge, terraform apply)

1. Apply migration 049.
2. Merge — deploys app and site.
3. `terraform apply` for signup and share_viewer Lambdas.

If the Lambdas go live before the new app, every sign-up is refused. Then
walk sign-up, invitation, registration signed out on the real domain.

## Blocking launch

1. **Privacy §4 isn't true yet.** DynamoDB recovery is 35 days, not 7;
   earlier S3 versions never expire; nothing deletes sign-up IPs a year
   after cancellation, or share records after 3 years.
2. **Homepage contact.** Paddle wants `info@arqedia.com` reachable from the
   homepage; where it goes is undecided.
3. **Paddle live hasn't started** — verification, live catalogue, keys,
   webhook, `live_` token. Ties directly to the ENV-01 / go-live work in
   `ARQEDIA_HANDOFF_paddle_2026-10-26.md` and
   `ARQEDIA_paddle_go_live_cc_prompts.md`. A go-live build list from another
   session sits untracked at `docs/ARQEDIA_paddle_go_live_build_list.md` —
   not yet pulled into this project's docs.
4. **Acceptance records are new data the Privacy Policy doesn't list.** Its
   table names acceptance only for recipients; Policy text is approved, so
   it wasn't changed.
5. **Account deletion undecided** — whether acceptance rows are kept like
   the ledger or deleted. Tenant inventory script also no longer lists every
   tenant table; workspace tables are missing too.
6. **Tenants 1 and 9** — latest config revisions still say "eBL Finance" in
   the engagement-letter description.

## PRs open

- `docs/legal-v1` — Terms, Privacy, Refund Policy v1, effective 27 October
  2026, approved by counsel for Chase Creek LLC. Docs only, no `web/` build.
- `feature/legal-pages` — pages + acceptance checks, migration 049 (not
  applied, must precede the signup Lambda). `web/` included. Includes
  docs/legal-v1.
