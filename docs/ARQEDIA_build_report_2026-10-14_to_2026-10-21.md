# ARQEDIA — Build report, one Claude Code session, 14–21 October 2026

Written 24 October 2026. It covers everything this session did, from the
launch-gate audit on 14 October to the tenant 0 offer move on 21 October.
Work merged by other sessions in the same period (for example #313, #317,
#320, #322–#326 and #329, plus everything from #351 onwards) is not covered
here except where it affected this session.

**How it was compiled.** This session's transcript is the source for what
was asked, decided and verified. `origin/main` at `d35d863` is the source for
what merged. PR numbers come from the squash-merge commits on main. Branch
commits were squashed, so their hashes are not in main's history.
Statements about live state are as verified **on the date given**. Only
one was re-checked for this report: the #341 deploy (§2.16).

---

## 1. Summary

| # | Workstream | Branch | Merged as | Lambda / TF apply | `web/` |
|---|---|---|---|---|---|
| 1 | Launch-gate audit | — (read-only) | — | — | — |
| 2 | Branch housekeeping | — (local deletes) | — | — | — |
| 3 | Terms docx + ignore `*.apk` | `docs/terms-privacy-draft` | #311 (#315, #318 empty duplicates) | — | — |
| 4 | §7 copy review | — (read-only, private artifact) | — | — | — |
| 5 | §7 "revision" not "version" | `docs/s7-revision-wording` | #312 | — | — |
| 6 | Raw exception text, copy fixes, 4 backlog docs | `fix/copy-review-critical` | #310 (#314 empty) | Applied 17 Oct, verified | Yes |
| 7 | Accessibility and mobile audit | — (read-only) | — | — | — |
| 8 | A11y / mobile fixes | `fix/a11y-mobile-critical` | #316 | — | Yes |
| 9 | Empty / error states inventory | — (read-only) | — | — | — |
| 10 | Empty / error states fixes | `fix/empty-error-states` | #319 (#321 empty) | — | Yes |
| 11 | Viewer-path load test | `test/viewer-loadtest` (deleted, never pushed) | — | Separate stack, built and destroyed | — |
| 12 | Checkout / layer drift between sessions | — | — | Plan only | — |
| 13 | EU second region: scoping and decisions | `docs/eu-region-decisions` | #327 (#332 empty) | Dry-run plan only | — |
| 14 | Launch review; copy triage | — (read-only) | — | — | — |
| 15 | SES bounce notices (10.6) | `docs/ses-bounce-notices` | #328 | SNS subscription via CLI | — |
| 16 | ERR-01 to ERR-03 | `fix/raw-error-text` | #330 (#333 empty) | Applied 20 Oct, verified | — |
| 17 | ROLE-01: Configure read-only for a Member | `fix/configure-role-gate` | #331 | — | Yes |
| 18 | 20 October decisions in CLAUDE.md | `docs/decisions-2026-10-20` | #338 | — | — |
| 19 | Terms and privacy rewritten to match the product | `docs/terms-match-product` | #339 | — | — |
| 20 | EXT-02: failed extraction refunded | `fix/ext02-refund-failed-extraction` | #341 | Applied (verified 24 Oct, §2.16) | — |
| 21 | Manual account-deletion runbook + inventory | `docs/account-deletion-runbook` | #344 (#347 closed unmerged) | — | — |
| 22 | Deletion cancels the Paddle subscription | `feature/deletion-cancels-paddle` | #345 | Applied 20 Oct 22:17 UTC, verified | — |
| 23 | Paddle live readiness | — (read-only) | — | — | — |
| 24 | Tenant 0 root config copied from tenant 5 | — (data change on dev) | — | — | — |
| 25 | Catalogue: moving the offer drops absent memoranda | `fix/catalogue-offer-move` | #350 | — | Yes |

"Empty duplicates" are second PRs from the same branch that GitHub merged
with no file changes. They are harmless and change nothing.

---

## 2. Work in detail

### 2.1 Launch-gate audit (14 Oct, read-only)

This checked the repository, Terraform state, Docker, TODO markers and nine
gate items.

- **Terraform:** one workspace, `default`. One state key,
  `arqedia/us-east-2/terraform.tfstate`.
- **Aurora** (`arqedia-dev-aurora`): min 0, max 4, auto-pause 300 s.
  `ServerlessDatabaseCapacity` reached 0.0 every day from 7 to 13 October.
- **CloudFront:** 3 distributions, all serving from us-east-2.
- **Docker:** no running containers and no release tags.
- **Build Plan v1 / Phase 9:** found nowhere in the repository or its
  history. The closest is one table row, `docs/HANDOFF/HANDOFF8-29-26.md:203`.
- **§7 copy rules:** later located at
  `docs/specs/frontend_onboarding_spec_v1.md:174`.

Gate results on 14 October:

| Status | Items |
|---|---|
| Done | Aurora pausing; share rate limit (`DAILY_LIMIT = 20`) |
| Not done | Second region; vetting position; screening provider; starter-pack review |
| Unknown | Accessibility; empty / error states; copy review; load test |

The rest of this session closed or decided most of those.

### 2.2 Branch housekeeping (16–17 Oct)

- **Inventory:** 24 local branches had `[gone]` upstreams.
- **Patch-id check:** four of them were confirmed as already on main by
  matching patch-id:
  - `feature/pentest-isolation-report` matches #274;
  - `fix/share-link-possession-read` matches #293;
  - `fix/share-registration-takeover` matches #291;
  - `fix/viewer-mfa-setup-timeout` matches #292.
- **Deleted, with approval:** those four local branches and three clean
  worktrees.
- **Left behind:** an empty folder, `.claude/worktrees/link-read`, which was
  locked by another process.
- **Also found:** a 201 MB `.apk` under `mobile/` that git did not ignore,
  above GitHub's 100 MB limit. It is now ignored by `mobile/**/*.apk` (#311).

### 2.3 Copy review against §7 (17 Oct, read-only)

Four parallel read-only reviews covered `ui/src`, `lambda/` error strings,
email templates and `site/`. They found 158 findings: about 83 R1, 36 R2 and
46 R3, with overlap.

- **Spot-check:** 12 of the findings were checked at their file:line; all
  matched.
- **Published:** a private artifact, https://claude.ai/artifact/QCCq33ELqLHRJ3aBkyGC28.
- **Decisions:**
  - "Revision" stays as the word. §7 is corrected to match, not the code
    (#312).
  - `Account.tsx:891` ("no reversals") and `:1143` (Member "edit and
    publish") are out of step with CLAUDE.md, not §7 breaches. Both were
    fixed in #310.
- **Eight paths** were found where raw exception or vendor text reached a
  person. They are fixed in #310 and #330.

### 2.4 `fix/copy-review-critical` (#310, 17 Oct)

**Part A: raw exception text.** In each case the detail now goes to the log
and the person sees a fixed sentence.

| Site | Change |
|---|---|
| `api`, `share_viewer`, `reviewer` catch-all `ValueError` | Unreadable JSON is caught before the catch-all and answered "That request could not be read. Reload the page and try again." Deliberate `ValueError` messages are unchanged. |
| `signup` Cognito password refusal | Our own sentence, `PASSWORD_REFUSED`, which spells out the `auth.tf` policy. `tests/test_invitation_password.py` was updated, because it pinned Cognito's wording. |
| `composition` rewrite and Update failures | "…stopped because of a fault on our side. Try it again." |
| `proposer` `exc.reason` | One sentence per kind of failure; pypdf's text goes to the log only. |
| Staff `signup_attempt.detail` | Fixed where it is written (`signup/app.py`), not in `cross_tenant.py`, which only reads it. It now stores the exception type plus the Cognito error code. |

**Part B: copy.** `Account.tsx` now says a failed document is refunded on a
line of its own, and the Member column says "no" for configuring.

**Backlog docs:** ROLE-01 and ERR-01 to ERR-03 were added as findings only.
Their IDs were proposed at the time.

**Tests and build:**

- 762 tests before and after. The new paths were also run once with a
  throwaway script, which was not committed.
- The `web/` bundle is `index-DuhHKQPf.js`. A grep of the bundle confirmed
  the new wording and the absence of "There are no reversals".

**Apply (17 Oct):**

- The plan showed 6 Lambdas, plus `aws_iam_role_policy.api` as "known after
  apply". That is caused by a data source depending on the Lambdas.
- Its statements were compared with the live policy before the apply: the
  same 11.
- After the user's apply, every Lambda code hash matched the plan, the IAM
  policy was unchanged, and a fresh plan showed "No changes".

### 2.5 Accessibility and mobile (17 Oct)

**Audit.**

- **Method:** axe-core 4.10, WCAG 2.1 A and AA, at 1280, 375 and 768 px.
- **Routes:** 16 in all. Five signed out; 11 signed in as the test account
  `joeschmoe1000@gmail.com` (tenant 2), with every non-GET API request
  blocked by the script.
- **Findings:**

| Severity | Finding |
|---|---|
| Critical | `aria-expanded` on an `<a>` with no `href` in the header menu (all 11 signed-in routes) |
| Critical | Missing labels: 70 share checkboxes, the logo input, 4 colour swatches, 2 plan radios, the upload input |
| Serious | `--medium` `#278ACA` at 3.59–3.76:1; green tags at 1.84–1.92:1; `.start-pill` at 3.86:1 |
| Mobile | The 200 px side menu never collapsed, so 8 routes scrolled sideways |

**Fix (#316):**

- **Header menu:** now a `<button>` with `aria-expanded` and
  `aria-controls`. `aria-haspopup` was left off deliberately, because the
  panel is a list of links, not a menu.
- **Labels:** added at all five places. Share rows are labelled by their own
  content.
- **Colours:**
  - `--medium` is now `#2279B2` (4.72:1 on white, 4.51:1 on `#F7FAFD`).
  - A new `--green-ink` is `#5F7D22`.
  - The disabled start pill uses `--ink-2` on `--line` (7.32:1).
- **Layout:** at 900 px and below the side menu becomes tabs. Nine wide
  tables scroll inside a focusable, labelled `TableScroll` wrapper
  (`shell.tsx`).
- **Gold:** "Open" and both "Publish" buttons are no longer gold.

**Verification:**

- 0 axe violations on 17 routes at all three widths, and no page scrolls
  sideways.
- Vitest 15/15 and `tsc` clean.
- The bundle has `#2279B2` and no `#278ACA`.
- After merge, `app.arqedia.com` served `index-DQxlfe-e.js`, with the new
  tokens confirmed in the live CSS.

**Not tested:** real phones, Safari and screen readers.

**Side effects:**

- The marketing site imports `tokens.css`, so its blue also changed.
- `main button` remained gold by default. #378 later changed that, in
  another session.
- The test account's password was given in the session. Rotating it was
  recommended.

### 2.6 Empty and error states (17–19 Oct)

**Inventory.** It covered 25 screen components. The gaps found:

- **No load error:** Engagements home, Configure ("Loading…" for ever), and
  Settings ("Loading…" for ever).
- **False empties:** the Engagements list, the Balance ledger, and the
  Catalogue (which showed the error and the empty message together).
- **No empty message:** the engagement memo list.

**Fix (#319):**

- All of the above, plus two found afterwards: Configure's first-run
  starting points, and the ARQEDIA catalogue section.
- Each uses the file's existing `if (error && !x)` / `<p className="error">`
  pattern.
- Before merging, main (#317 TrialBanner, #318) was merged in and `web/`
  rebuilt from the combined source; the conflict markers were not edited by
  hand. The bundle `index-BSedWvZF.js` was checked for both #317's day count
  and this branch's new sentences.

**Verified on screen:** the Engagements home only, as chosen. Playwright
aborted the list request rather than editing the source.

- With 3 rows loaded and then a failed reload, the error shows, there is no
  empty message, and 0 rows are left.
- A failed first read gives the same result.

**Unverified:** the other seven fixed screens have not been seen failing.
The error text shown is the browser's own "Failed to fetch".

### 2.7 Viewer-path load test (19 Oct)

**Stack.** A separate root, `loadtest/`, with state key
`arqedia/us-east-2/loadtest-viewer.tfstate` and every name prefixed
`arqedia-loadtest-`.

- It had 33 resources: an HTTP API with the live 25/50 throttle, the real
  `share_viewer` code, a stub "workspace" route, the 4 share tables, KMS,
  S3, and a viewer pool.
- The layer was built in `loadtest/build/`, so the live `build/` hash was
  not disturbed.
- The user approved the plan and the stack was applied.

**Run.**

- **Seeding:** 200 grants, 155 recipients, 5 registered viewers, 400 PDFs.
- **Tool:** k6 `constant-arrival-rate`, run 12:11–12:50 UTC, 31,383
  requests.
- **Phases:** 1, 5, 10 and 20 RPS, then 50 RPS for 1 min, then 40 RPS for
  2 min.
- **Mix:** 85% `GET /view`, 10% download, 5% `GET /viewer/shares`.

**Results:**

| Criterion | Result |
|---|---|
| `GET /view` p95 < 1 s | 143 ms — pass |
| Download p95 < 3 s | 306 ms — pass |
| Errors < 1% (excluding 429s in the over-limit phase) | 5.05% — fail. All 1,470 counted errors were 429s in the 50 RPS phase; there were no 5xx. |
| Lambda throttles | 0 (peak concurrency 29) — pass |
| DynamoDB throttles | 0 — pass |
| `[viewer-error]` lines | 0 — pass |
| Access log matches opens | Exact: 21,912 / 21,912; downloads 2,510 / 2,510 — pass |

**Findings:**

1. The stage throttle is **shared by every route**. The stub route was
   throttled too, and the accepted total held near 25/s.
2. The 50 RPS minute was planned wrong. It tested the steady limit, not the
   burst allowance.

**Decisions:** leave the throttle as is; delete the branch; no retest.

**Teardown.**

- The user ran the destroy, because the session's own destroy was blocked
  by the permission check.
- Verified afterwards:
  - the state list is empty and `plan -destroy` shows nothing;
  - AWS holds no `loadtest` resources;
  - every version of the state and lock files was deleted;
  - the local seed and token files were deleted.
- The KMS key was scheduled for deletion on 26 October.
- The `test/viewer-loadtest` branch (`438a5b5`) was never pushed and is
  gone.

**Not tested:** the burst allowance, the S3 PDF fetch, the CloudFront path
and recipient registration. The per-route CloudWatch queries returned 0,
likely because of the dimension names used.

### 2.8 Checkout and layer drift between sessions (19 Oct)

**What happened.** Applies at 11:42 and 13:30 UTC came from another session's
worktree, `C:\Terraform\arqedia-generate-refund`.

- CloudTrail showed Terraform 1.14.8 from this machine's IP address.
- That worktree's layer zip hash equals live layer v46.

**The risk.** This checkout's `build/` held the 16 October layer, and 13
Lambda folders carried `__pycache__`. An apply from here would have put the
old layer back.

**Fixed by:**

- pulling #325 (which excludes `__pycache__`);
- running `build-layer.ps1`, after which all 978 files in the new layer
  hashed identical to v46.

The remaining plan was cosmetic: a byte-different but identical layer. It
was not applied from here.

### 2.9 EU second region (19 Oct)

**Dry run.**

- A throwaway workspace, `eu-central-1-dryrun`, was used with
  `-var aws_region=eu-central-1`, then deleted. Live state was not written.
- The plan stopped at `auth.tf:22`, because SES is verified for
  `arqedia.com` only in us-east-2.
- It reached 184 resources to add, out of about 319 in a full stack.

**What it found:**

- **Name collisions in one account:** 7 S3 buckets, 18 IAM roles, the OIDC
  provider, the CloudFront aliases, and the zone.
- **Hardcoded `us-east-2`:** `config.ts`, `signup/app.py:762`, three
  workflows, `q.ps1`.
- **Bedrock:** `eu.` Haiku 4.5 and Sonnet 4.6 profiles are ACTIVE.

**Decisions (#327):**

- a separate EU account;
- `eu.app.arqedia.com`, with each tenant assigned to one stack;
- one shared EU stack;
- anywhere in the EU is sufficient.

Pros and cons were given before the decisions were written. Nothing was
built, and EU work is set aside.

### 2.10 Launch review and the copy-review triage (19 Oct)

- **Critical and revert rows:** every one in the untracked
  `ARQEDIA_copy_review_launch_triage.xlsx` was confirmed fixed on main.
- **Still open from the same review:** ERR-01 to ERR-03 and ROLE-01, built
  next (§2.12, §2.13).
- **Deferrable R1–R3 rows:** not verifiable, because their source HTML is
  not in the repository.
- **Advice:** given in order — before beta, decisions; before beta, small
  builds; before real customer data. The user took items 5–7: site packs,
  bounces, and ERR / ROLE.

### 2.11 SES bounce notices, 10.6 (#328)

The configuration set had published to SNS `ses-events` since 15 September,
but the topic had no subscriber.

- `sperry@ebl-finance.com` was subscribed by CLI, the same way the topic
  was created. The user confirmed the subscription, and it was verified with
  a real subscription ARN on 20 October.
- The comments in `share.tf` and CLAUDE.md were corrected.

### 2.12 ERR-01 to ERR-03 (#330)

| Item | Change |
|---|---|
| ERR-01 | A failed Update section reads "This section could not be compared because of a fault on our side. Run the update again." The exception goes to the log. |
| ERR-02 | A rewrite that cannot start reads "The rewrite could not be started because of a fault on our side. Try it again." This failure was not logged at all before. |
| ERR-03 | Python's `int()` wording is recognised at the single error handler in `api/app.py`, so the 103 `int()` call sites did not need changing. |

**Tests:** `tests/test_raw_error_text.py` is new (4 tests), and an assertion
was added to `test_memo_update.py`. The suite stood at 798.

**Apply (20 Oct, by the user):** verified — the `api` and `composition`
hashes matched, every Lambda is on layer v47, and the plan showed "No
changes".

**Not covered:** `share_viewer` and `reviewer` still pass `ValueError` text
through. This is noted in ERR-03.

### 2.13 ROLE-01 (#331)

`Configure.tsx` now follows `App.tsx`'s Get started pattern for a Member:

- The screen says "Changing the configuration is an administrator's. You can
  read it here."
- **Disabled:** Publish, Start editing, every Save and every tick.
- **Hidden:** Rename, Duplicate, Discard, Use this revision, every delete and
  every add.
- **Build and checks:** `web/` is `index-CIIUOLQE.js`, confirmed live on
  19 October. `tsc` clean, Vitest 15/15.
- **Unverified:** no Member account has walked the screen.

### 2.14 20 October decisions (#338)

These were recorded additively in CLAUDE.md, under the open items they
settle:

- **ONB-01:** no vetting gate, provisional.
- **SC-01:** deferred until after launch.
- **TPL-01:** the pack review is assigned to sperry@ebl-finance.com.
- **Recipient registration:** open. Already built (`share_rules.py`): two
  weeks unregistered, six months registered.
- **Site PACKS:** held until the last step before launch.
- **Before real customer data:** IP retention, account deletion and EXT-02.
- **Front-matter counts after an Update:** re-checked; still not fixed.

### 2.15 Terms and privacy matched to the product (#339)

A new file, `docs/legal/ARQEDIA_terms_and_privacy_2026-10-20.md`. The
7 October `.docx` is unchanged. Every claim was taken from a cited
code-reading pass.

**Main corrections:**

- **Users:** trial, paid and share-recipient, replacing "free account".
- **Money:** Paddle is merchant of record (checked in Paddle's docs). Credit
  and refunds are described as built.
- **Hosting:** "one shared platform in the US (Ohio)", replacing "separate
  accounts".
- **Sub-processors:** Textract, SES, Cognito and Bedrock (not used for
  training, per AWS), and Paddle.
- **Removed:** export, self-serve deletion, and leaked internal phrasing.
- **Courts:** those of England and Wales.

**Still `[TO DECIDE]`:**

1. Eligibility law.
2. The mocked region choice at sign-up (it offers the EU and Singapore while
   storing in Ohio).
3. Retention periods for deleted versions, sign-up IPs and share records.
4. Whether to record the accepted version, which needs a schema change, or
   only the date.

**Build constraint, decided:** the terms show only at the last step of
sign-up or registration. No build has started.

### 2.16 EXT-02: failed extraction is refunded (#341)

**Investigation.** The user's live test file (`bogus-Business-model-additions.pdf`)
was refused by the normalizer at upload (`pdf-parse-failed`), before filing.
It was never charged and never reached extraction.

**Where the real gap is.** `lambda/extraction/app.py` had no refund in any of
four cases:

1. every part fails;
2. no subject is named (deliberate);
3. a crash, timeout or out-of-memory kill — extraction has no failure
   destination;
4. extraction never starts.

On dev, **document 862** (tenant 2, filed 23 September) is case 4: charged,
OCR'd and never extracted.

**Decision:** Option 1, `wallet.refund()`, the same as failed OCR (keyed
`refund:<document_id>`). The 21 September rebate bucket is marked
superseded, not deleted.

**Build:**

- After a document is marked failed, it is refunded if its run errored and
  it holds no extracted values in the database. A re-extraction that fails
  on a document that already has values keeps its charge.
- If the refund itself fails, that is logged for a refund by hand.
- `extraction.tf` adds the three `rds-data` transaction actions.
- 7 new tests: 21/21 in the file, 805 in total.

**Apply:** verified live on 24 October for this report.
`arqedia-dev-extraction` (last modified 2026-10-23 17:57 UTC) runs an
`app.py` byte-identical to `origin/main`, and its role carries
`BeginTransaction`, `CommitTransaction` and `RollbackTransaction`.

**Not covered:**

- cases 3 and 4, so document 862 stays charged;
- Review screen wording about the refund;
- the stale `wallet.py` docstring, left because editing it would mean
  rebuilding the layer.

### 2.17 Manual account deletion (#344)

**Read from live Aurora:**

- 29 tables carry `tenant_id`.
- There is one foreign key (`subscription.plan_id → plan`) and no triggers.
- Every S3 bucket is versioned. Tenant 10 already held 40 hidden versions.

**Deliverables:**

- `docs/runbooks/account_deletion_manual.md`: 9 ordered steps, each with a
  check. The Aurora deletes run child-first in one transaction. Every S3
  version is deleted. Cognito users are disabled first and deleted last.
- `docs/runbooks/tenant_inventory.py`: read-only counts, run before and
  after a deletion. It stops if the table list has changed. It ran
  correctly against tenant 10.

**Why `share.purge_tenant` is not used.** The procedure does its work
instead, because the function:

- runs only inside the API function;
- reads only the first page of results;
- deletes only the current object versions.

**Gaps recorded in the runbook:**

- no dry run and no undo;
- backups hold the data for 7 days (Aurora) and 35 days (DynamoDB);
- logs are kept for ever;
- sign-up records hold no tenant id;
- the 45-second statement timeout is untested on a large tenant (about
  67,000 citation rows on tenant 1);
- whether Textract or Bedrock retain anything was not checked.

**Decisions (20 Oct):**

- The ledger and `paddle_event` are kept, with no blanking of addresses.
- Paddle cancellation is part of every deletion, and the deletion request is
  the confirmation.

### 2.18 Deletion cancels the Paddle subscription (#345)

The user had believed cancellation was automatic. It was not: no cancel call
existed.

**Build.** The endpoint and webhooks were checked in the paddle-docs MCP
first.

- `paddle_api.cancel_subscription()`:
  - sends `POST /subscriptions/{id}/cancel` with `effective_from:
    immediately`;
  - returns Paddle's status;
  - is reached from no route.
- `docs/runbooks/cancel_subscription.py`:
  - reads the subscription from Aurora and does nothing if there is none or
    it is already cancelled;
  - copies the `PADDLE_*` settings from the deployed `arqedia-dev-api`
    function and calls the function above.
- **Runbook step 3** now runs the script. Step 6 must wait until the
  subscription reads `canceled`, because the `subscription.updated` webhook
  upserts the row and would otherwise recreate it.
- **Test:** `test_cancel_is_immediate_and_answers_the_status`. The suite
  stands at 806.

**Merge.**

- An add/add conflict with #344 was resolved in a separate worktree, keeping
  the branch's copy (merge commit `81929ba`).
- #347 (the old runbook branch) was assessed as redundant: merging it would
  have restored hand-cancelling. The user closed it.
- Main's five files were verified byte-identical to `81929ba`.

**Apply.**

- The first apply ran from a checkout on `infra/arqedia-mail-dns`, so it
  changed nothing.
- After switching to main, the plan showed 1 change. The user re-applied.
- At 22:17 UTC the deployed `paddle_api.py` matched main, and the plan
  showed no changes.

**Unverified:** the script has never run against Paddle.

### 2.19 Paddle live readiness (20–21 Oct, read-only)

**Status on 21 October:** sandbox throughout.

- The API calls `https://sandbox-api.paddle.com`.
- `app.arqedia.com` carries a `test_` token.
- Only `config/paddle/sandbox.json` exists.

**Going live needs:**

1. Paddle account and identity verification, and domain approval. This has
   the longest lead time and can start now.
2. A live catalog.
3. Live API key, webhook destination and secret, put into Secrets Manager.
4. `config/paddle/live.json`, plus `paddle.tf:72` and `:81` switched.
5. A `live_` token with `VITE_PADDLE_ENVIRONMENT=production`, and
   `pwCustomer`.
6. One real checkout and one real top-up, then refunded.

**Open decision:** ENV-01 — go live on the single `arqedia-dev` stack, or
build production first.

### 2.20 Tenant 0 root configuration from tenant 5 (21 Oct, data change on dev)

- **Login:** `admin@arqedia.com` is tenant 0's only login (Administrator,
  no `seat` row).
- **Before:** tenant 0 was on revision 29 with an open draft from
  1 October. That draft was verified row-for-row identical to revision 29
  before it was replaced.
- **Method:** the same as `registry._copy`, in one rds-data transaction:
  1. clear tenant 0's draft rows, in reverse `registry.TABLES` order;
  2. write a new draft `config_revision` (note "copied from tenant 5
     revision 32", `forked_from = tenant:5:32`, by `admin@arqedia.com`);
  3. `INSERT … SELECT` for each of the 8 tables.
- **Verified:** a row-by-row comparison in both directions found 0
  differences. Counts:

| Categories | Document types | Fact groups | Routings | Facts | Memoranda | Sections | Bindings |
|---|---|---|---|---|---|---|---|
| 5 | 38 | 62 | 277 | 235 | 4 | 43 | 413 |

- **The user then:**
  - published revision 30;
  - removed the two eBL Finance references, publishing up to revision 32;
  - moved the offer.
- **Verified after:**
  - `active_revision = 32`;
  - `engagement-letter` reads "engagement of financial advisor or arranger
    or servicer";
  - `f_agency_and_servicing_fee` is absent;
  - no document type mentions eBL Finance.
- **Offer**, marked 2026-10-21 20:43:45 UTC by `admin@arqedia.com` at
  revision 32: base, `credit-memorandum`,
  `kyc-customer-due-diligence-memorandum-2`,
  `trade-finance-credit-memo-duplicate` and
  `trade-finance-lender-brief-3-duplicate`.
- **Not checked:** whether any renamed fact still describes eBL's own fee.
  The search was by key and by document-type description.
- **Not reproducible on a future production stack.** Tenant 5 exists only
  on dev (ENV-01); migration 021 is the precedent for writing such a copy
  as literal rows.

### 2.21 Catalogue: moving the offer (#350)

**The bug.** The ticks were seeded from the old offer, which named
`kyc-customer-due-diligence-memorandum` and `lender-information-memorandum`.
Revision 30 holds neither, so they had no checkbox to untick and were still
sent. The API log showed three `PUT /config/offer` 400s, and nothing was
written.

**Fix:**

- Ticks are seeded only from templates the live revision holds.
- The rest are named: "Revision N does not hold …; they come off the offer
  when this is saved."
- The list is cleared after a successful save.
- `web/` is `index-CTV1pu9f.js`.

**Note:** the session's direct `registry.set_offer` call was denied by the
permission check and was not retried another way.

**Verified:** the user moved the offer through the fixed screen and it
worked (§2.20).

---

## 3. Testing record

| Suite | Count over the session |
|---|---|
| Python (`python -m unittest discover -s tests`) | 762 → 798 → 805 → 806, all passing at each stage |
| UI (Vitest) | 15 / 15 at each UI change; `tsc` clean via `npm run build` |
| Accessibility | axe-core 4.10, 0 violations on 17 routes at 3 widths, after #316 |
| Load | k6, 31,383 requests, against an isolated stack |

`pytest` is not installed locally, so `unittest` is the runner.

---

## 4. Live data and infrastructure touched

| When (UTC) | What | Who |
|---|---|---|
| 17 Oct 17:31 | Apply: 6 Lambdas (#310) | User; verified by session |
| 19 Oct 12:08–13:58 | `arqedia-loadtest-*` stack created, then destroyed; state versions purged | Session applied; user destroyed |
| 19 Oct | SNS email subscription on `ses-events` | Session (CLI); user confirmed |
| 19 Oct | Dry-run workspace `eu-central-1-dryrun` created and deleted | Session |
| 20 Oct 09:13 | Apply: `api`, `composition`, layer v47 (#330) | User; verified |
| 20 Oct 22:17 | Apply: `api` (#345) | User; verified |
| 21 Oct 20:22 | Tenant 0 draft replaced with tenant 5 revision 32 | Session, with approval; verified |
| 21 Oct 20:3x–20:43 | Revisions 30–32 published; offer moved to 32 | User; verified |

---

## 5. Open, unverified, and leftovers as of 21 October

**Unverified (each is a gap, not a note):**

- ROLE-01 has not been walked as a Member.
- Seven of the eight empty / error fixes have not been seen failing.
- ERR-01 to ERR-03 have not been triggered live.
- `cancel_subscription.py` has never run against Paddle.
- Deletion steps 3–7 have never run. The first run should be on a throwaway
  dev tenant with a sandbox subscription.
- The EXT-02 refund (#341) is deployed (checked 24 October), but no live
  document has failed that way since, so it has not been seen working.
- Real phones, Safari and screen readers.

**Open work:**

- EXT-02 cases 3 and 4 (document 862).
- Review screen refund wording.
- The stale `wallet.py` docstring.
- `share_viewer` and `reviewer` raw `ValueError` text.
- The Terms `[TO DECIDE]` items and the terms build.
- Paddle live, and the ENV-01 stack decision.
- Site PACKS, now likely the four offered memoranda.
- The front-matter counts after an Update.

**Leftovers on this machine:**

- Local branches `docs/account-deletion-runbook` and
  `feature/deletion-cancels-paddle` are safe to delete.
- An empty `.claude/worktrees/link-read` folder.
- `loadtest/` holds only git-ignored results.

---

## 6. Process notes

- **Squash merges hide ancestry.** Use content (blob or patch-id) comparison
  against `origin/main`, never `git branch --merged`.
- **Several sessions share one checkout.** Twice the main checkout was
  switched under this session (to `infra/arqedia-mail-dns`, then
  `feature/ai-review-edit-doctype`). One apply ran from the wrong branch and
  deployed nothing. Work done in a separate `git worktree` avoids disturbing
  the other session; check the branch before every plan.
- **A stale `build/` is a hazard.** A checkout's stale `build/` layer can
  undo another session's apply. Rebuild the layer before planning from a
  checkout that has not built recently.
- **Duplicate PRs from the same branch** produced empty merges (#311/#315/
  #318, #314, #321, #332, #333). They are harmless, but they make the
  history harder to read.
- **Load-test planning:** a burst phase must be shorter than the bucket
  refill, or it tests the steady limit instead.
