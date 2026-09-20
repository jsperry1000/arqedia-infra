# ARQEDIA — Work List UX-02

| | |
|---|---|
| Raised | 20 September 2026 |
| Source | Walk feedback, answered by number in chat |
| Status | Not started. Prompts below; one branch per group |
| Revised | 20 September 2026 — decisions on expiry, MFA, archive; admin page outline added |
| Revised | 20 September 2026 — admin on a separate path; viewer MFA reinstated |
| Revised | 20 September 2026 — home page motion graphic: speed and settled text |

---

## Conflicts with standing decisions — flagged, not resolved

| Item | Standing decision it touches | Source |
|---|---|---|
| ARQEDIA admin page | "React for customers, Retool for internal tooling" — decided below: a separate admin path in React. Supersedes the Retool half for this page | build_index, standing decisions |
| Share recipient registration | 6-month extension on registration (share_viewer_spec §3, §6) — not addressed by your decisions; stays as spec until you say | share_viewer_spec |
| Reassess the single fact base per tenant | Architecture, not front end | — |

Each of these is carried as a read-and-report prompt. Nothing in them is built until you decide.

## Decisions taken, 20 September 2026

| Decision | Supersedes |
|---|---|
| Share expiry for a verified (unregistered) recipient is **2 weeks** | 30 days — share_viewer_spec §3, §6 table and its closing summary; build_index |
| ~~No MFA for registered viewers~~ — **reversed the same day.** MFA for registered viewers is a need-to-have and stays as spec | Nothing. share_viewer_spec §3 and the build_index standing decision stand unchanged |
| The ARQEDIA admin page is built as a **separate admin path**: its own sign-in, front end, API, Lambda and deploy. It shares nothing with the customer path except the database it reads | build_index "Retool for internal tooling", for this page |
| Memos and engagements are **archived, not deleted**. Archived items drop out of the working views, which gain a way to show them | Resolves the conflict with "non-destructive throughout" |

The spec files in the project are read-only copies. These decisions are recorded here; the specs are to be amended in the repo on the `share-recipient` branch.

---

## Group 1 — Labels and lists
Branch `ux-labels`. Clear; build.

| # | Item |
|---|---|
| 1.1 | Rail: "Catalogue" → "Template Catalogue" |
| 1.2 | Configure a report: "Delete this memorandum" wording → "Delete this template" |
| 1.3 | Memo view: the "Rewrite" control → "Have Model Redraft a Section" |
| 1.4 | Memo list: the second column shows the template key; show the template name |

## Group 2 — Section editor, fields panel
Branch `ux-section-fields`. Clear; build.

| # | Item |
|---|---|
| 2.1 | Add a fact directly from the section's fact list |
| 2.2 | Align the columns of the upper (selected) and lower (unselected) portions |
| 2.3 | Upper portion: a select-all box at the top of each selected column |
| 2.4 | Upper portion only: a field shown in a column is not shown again in any column to its right. Leftmost wins. Lower portion unchanged |
| 2.5 | Lower portion: pin the column headers |
| 2.6 | Document panel that shows fields: search bar at the top; pin its headers |
| 2.7 | Edit field panel: description box grows vertically with its content, up to 25 lines |
| 2.8 | Ticking a field on or off has noticeable latency. Find the cause and fix it |

## Group 3 — Sections / Facts / Documents prominence and the static graphic
Branch `ux-backdrop`. Report first.

| # | Item |
|---|---|
| 3.1 | Sections / Facts / Documents made more prominent at the top of the page |
| 3.2 | Behind the app, a subtle static grey/black version of a stage of the home page's motion graphic, matching the selected item |

**Open:** which stage of the motion graphic belongs to Sections, to Facts and to Documents. Code reports the stages; you assign them.

## Group 4 — Confirm before spend
Branch `ux-spend-confirm`. Clear; build.

| # | Item |
|---|---|
| 4.1 | Generate memo: pressing Generate opens a confirm step that states the $1.00 charge and checks the balance covers it. The charge happens only on a second button. Parallel to how upload shows its cost |
| 4.2 | Top-up: a confirm step before charging |

Price source: `memo_generated` $1.00 (wallet_entitlement_spec, build_index). Standing decision: "No silent spend. Every charge follows a click."

## Group 5 — Signup flow
Branch `ux-signup`. Clear; build.

| # | Item |
|---|---|
| 5.1 | Region selection: the tickboxes do not align |
| 5.2 | A domain that already exists is reported at step 1, not step 4 |
| 5.3 | The flow can be left: a home button on every step |
| 5.4 | Back stays in the same place on every step; the panel is the same size on every step |

## Group 6 — Navigation and progress
Branch `ux-nav-progress`. Clear; build.

| # | Item |
|---|---|
| 6.1 | A home button on every page |
| 6.2 | The progress monitor is more prominent everywhere it appears |

## Group 7 — Memo view
Branch `ux-memo-view`. Clear; build.

| # | Item |
|---|---|
| 7.1 | Sources and Edit at the foot of each text block are clearly visible before hover or click |

## Group 8 — File upload, select to remove
Branch `ux-upload-select`. Report first.

| # | Item |
|---|---|
| 8.1 | A tick-box column to select files to remove, with select-all at the top |

**Open:** what "remove" does today, and whether it is destructive. Code reports.

## Group 9 — Branding
Branch `acct-branding`. Report first. Includes BR-01.

| # | Item |
|---|---|
| 9.1 | Tenant can edit its brand colours in Settings |
| 9.2 | BR-01: a fourth colour. Needs a migration, so it is put to you before build |

## Group 10 — Password and user id
Branch `acct-identity`. Report first.

| # | Item |
|---|---|
| 10.1 | Forgot password |
| 10.2 | Forgot user id |
| 10.3 | Change password |

## Group 11 — Plans and upgrade
Branch `acct-upgrade`. Report first.

| # | Item |
|---|---|
| 11.1 | An upgrade action on the account management page and on every throttled page |
| 11.2 | Enterprise is not shown on dev's subscription page. Find out why |

## Group 12 — Sharing
Branch `share-recipient`. Report first.

| # | Item |
|---|---|
| 12.1 | A verified recipient's access expires after 2 weeks (was 30 days) |
| 12.2 | Sending gives the recipient a free account on their email, with an initial password. Registered viewers keep MFA (spec §3) |
| 12.3 | A guide page for recipients ("click here to see the shared report") |
| 12.4 | **Your open question:** does the recipient get the editable memo or a PDF? Treated as a marketing opportunity; to be fleshed out |

## Group 13 — Design items
One read-only prompt. No branch.

| # | Item |
|---|---|
| 13.1 | Manage memo files: archive, live, draft; drag and drop; filter by template key, date, editor; a folder per template |
| 13.3 | ARQEDIA admin page: who accessed, who tried, who signed up. **Your open question:** does it live here or at Paddle? |
| 13.4 | Reassess the single fact base per tenant |

## Group 14 — Archive and clean views
Branch `archive`. Report first; likely a migration, so put to you before build.

| # | Item |
|---|---|
| 14.1 | Archive a memo; archive an engagement. Nothing is deleted |
| 14.2 | Archived items leave the working lists (engagements, memos, memo files) |
| 14.3 | Each list gains a way to show archived items, and to restore one |
| 14.4 | Ties to 13.1: archive is one of the memo file states (draft, live, archived) |

## Group 15 — Home page motion graphic
Branch `site-hero`. Clear; build.

The hero graphic on the marketing site that runs on first load: Documents → Facts → Filed → Retrieved, with its stage strip beneath.

| # | Item |
|---|---|
| 15.1 | Run 5% faster: every stage duration and transition divided by 1.05 |
| 15.2 | Each stage's text description stays once its stage has run. The final settle shows every stage with its description |

Linked: Group 3 (static stages behind the app) uses the same stages.

## ARQEDIA admin page — React app vs Retool

The page shows who accessed, who tried and failed, and who signed up. Where that data is recorded today is unknown until P13 reports; both options depend on that answer.

**Standing decision on record:** "React for customers, Retool for internal tooling" (build_index). The reason given there is that Retool's per-external-user pricing inverts against a $25 plan at scale. That reason concerns customer-facing use; an admin page used only by ARQEDIA staff is internal use.

### Option A — in the React app, as a tenant 0 screen

| | |
|---|---|
| How | New screens reachable only in tenant 0 (the ARQEDIA admin tenant, TPL-04 D8). Read routes on the existing API, refused for every other tenant in the dispatcher — the same guard pattern proven on `/config/offer` today |
| Operability | Same repo, same deploy, same sign-in. No second system to run. Every change is a code change, a PR and a deploy |
| Cost | No licence. Build time for each screen, filter and export. Runs on the existing Lambda and API |
| Security | Staff use the existing Cognito sign-in; nothing leaves AWS; no third party holds credentials. The risk is placement: cross-tenant data served by the same API customers use, so a guard mistake exposes one tenant's data to another. Every admin route needs the tenant 0 guard and a test proving the refusal |

### Option B — in Retool

| | |
|---|---|
| How | A Retool app connected to our data. **Unverified:** how Retool would reach Aurora (the cluster is private and we use the Data API), and Cognito's sign-in records. To be checked before choosing |
| Operability | Faster to assemble tables, filters and charts. A second system: its own logins, permissions and upkeep. Changes do not go through our PR and deploy path |
| Cost (published, checked September 2026) | Free: up to 5 users. Team: about $10 per builder and $5 per internal user per month, annual. Business: $50 per builder and $15 per internal user annual, $65 per builder monthly. Enterprise: custom. Billed by activity — a user who edits an app in a month is billed as a builder that month |
| Security | Retool holds credentials that read across every tenant. With Retool Cloud, data leaves our AWS account to Retool. Business adds audit logging and richer permission controls; SSO is reported as Business-tier. Standing decision: identity is regional — a cross-region admin view pulls per-region identities into one place, in either option, but in Retool that place is a third party |

### Decided — Option C: a separate admin path, in React

Neither A nor B. The admin page gets its own path end to end, so the two uses are not mixed and no customer-facing route can serve cross-tenant data.

| Component | What it is |
|---|---|
| Admin user pool | Its own Cognito pool, ARQEDIA staff only, MFA required. Customer pools never hold an admin |
| Admin front end | A separate small React app on its own subdomain, its own S3 bucket and CloudFront distribution |
| Admin API | A separate API Gateway whose authorizer trusts only the admin pool. A customer token is refused at the gateway, before any code runs |
| Admin Lambda | Its own function and IAM role: reads across tenants, writes nothing |
| Admin deploy | Its own workflow. An admin change never redeploys the customer app |

**Running cost.** Cognito Lite and Essentials: 10,000 monthly active users free, per account or AWS organization — shared with the customer pools, which are in the same account. Cognito Plus (risk-based sign-in protection): no free tier, $0.020 per active user per month. API Gateway, Lambda, S3 and CloudFront at admin volumes: small, not priced — unverified. Source: aws.amazon.com/cognito/pricing, checked 20 September 2026.

**Build cost.** Not estimated. P15 reads the current Terraform and estimates.

**Open — yours to decide:** do template authoring and the offer (tenant 0, TPL-04 D8) move to the admin path too, or does the admin path hold access and signup reporting only?

### Where the data sits (to be confirmed by P13)

| Question | Source |
|---|---|
| Sign-ins and failed sign-ins | Cognito (per-region pools) — unverified what is recorded |
| Signups | Our database (signup Lambda writes the tenant) |
| Subscriptions and payments | Paddle — what its dashboard and API expose to be web-searched in P13 |

## Rolled into existing backlog

| Item | Into |
|---|---|
| Rewrites in the memo feed back into the section's configuration, live or by a save-after-rewrite choice | HONE-01, as an addition. HONE-01's existing text is kept |
| Layer zip is not deterministic — Compress-Archive stamps build times, so every rebuild mints a new layer version and redeploys seven functions. Rebuild only when `lambda/shared/` changes; make the zip deterministic | BLD-01, as an addition. BLD-01's existing text is kept |

---

# Prompts for Code

Every prompt starts the same way. It is repeated in each so each can be pasted alone.

## P1 — Labels and lists (`ux-labels`)

```
git switch main; git pull --prune; git switch -c ux-labels
Read in full every file you will edit before editing it.

1. Rail: "Catalogue" -> "Template Catalogue".
2. Configure a report: the delete control's wording -> "Delete this template".
3. Memo view: the Rewrite control's label -> "Have Model Redraft a Section".
4. Memo list: the second column shows the template key. Show the template's
   name. Report where the name comes from; if the list's API response does
   not carry it, report and stop before changing the API.

tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## P2 — Section editor, fields panel (`ux-section-fields`)

```
git switch main; git pull --prune; git switch -c ux-section-fields
Read in full every file you will edit before editing it.

1. Add a fact directly from the section's fact list.
2. Align the columns of the upper (selected) and lower (unselected) portions.
3. Upper portion: a select-all box at the top of each selected column.
4. Upper portion only: a field shown in a column is not shown again in any
   column to its right. Leftmost wins. Do not change the lower portion.
5. Lower portion: pin the column headers.
6. The document panel that shows fields: search bar at the top; pin headers.
7. Edit field panel: the description box grows with its content, up to 25
   lines, then scrolls.
8. Ticking a field on or off is slow. Before fixing, report what happens on
   a click (renders, network calls, timings). Then fix.

Reuse existing CSS where a rendered pattern exists. Report any new CSS.
tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## P3 — Prominence and the static graphic (`ux-backdrop`) — report first

```
git switch main; git pull --prune; git switch -c ux-backdrop
Read-only until I reply.

1. Read the home page's motion graphic in site/. List its stages: what each
   shows and where in the code each is defined.
2. Report how Sections / Facts / Documents are presented today.
3. Propose how to make them more prominent at the top of the page, and how a
   static grey/black rendering of one stage could sit behind the app, subtly,
   per selected item.

Report and stop. I will assign stages to Sections, Facts and Documents.
```

## P4 — Confirm before spend (`ux-spend-confirm`)

```
git switch main; git pull --prune; git switch -c ux-spend-confirm
Read in full every file you will edit before editing it.

1. Generate memo: pressing Generate opens a confirm step stating the charge
   ($1.00, memo_generated) and whether the balance covers it. The charge
   happens only on a second button. Where the balance does not cover it,
   say so and offer top-up; do not charge.
   Read the price from where the code holds it. Do not hard-code $1.00 in
   the UI. Report where it is held.
2. Top-up: a confirm step before the charge.
3. Report how upload currently shows its cost, and match it.

tsc -b, vite build, tests in Docker with PYTHONDONTWRITEBYTECODE=1.
Commit, push, short push summary. Give me the walk.
```

## P5 — Signup flow (`ux-signup`)

```
git switch main; git pull --prune; git switch -c ux-signup
Read in full every file you will edit before editing it.

1. Region selection: align the tickboxes.
2. A domain that already exists is reported at step 1, not step 4. Report
   how the check runs today before changing it. If it needs a new API
   route, report and stop.
3. A home button on every step, so the flow can be left.
4. Back sits in the same place on every step; the panel is the same size on
   every step.

tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## P6 — Navigation and progress (`ux-nav-progress`)

```
git switch main; git pull --prune; git switch -c ux-nav-progress
Read in full every file you will edit before editing it.

1. A home button on every page.
2. List every place the progress monitor appears. Make it more prominent in
   each. Render and screenshot before and after.

tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## P7 — Memo view (`ux-memo-view`)

```
git switch main; git pull --prune; git switch -c ux-memo-view
Read in full every file you will edit before editing it.

1. Sources and Edit at the foot of each text block are clearly visible
   before hover or click. Render and screenshot before and after.

tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## P8 — Upload, select to remove (`ux-upload-select`) — report first

```
git switch main; git pull --prune
Read-only until I reply.

1. Report what removing a file from the upload page does today: which rows
   and objects it touches, and whether anything is deleted or only marked.
2. Report whether a filed document can be removed, and what happens to the
   facts extracted from it.

Report and stop. The build (a tick-box column with select-all) follows my
reply.
```

## P9 — Branding (`acct-branding`) — report first

```
git switch main; git pull --prune
Read-only until I reply. Read ARQEDIA_backlog_BR01 in docs/ if present.

1. Report what the tenant can edit in Settings > Brand today.
2. Report the tenant columns that hold brand colours, and where render
   reads them.
3. Propose: tenant edits all brand colours in Settings, and BR-01's fourth
   colour. Give the migration you would write, unapplied.

Report and stop.
```

## P10 — Password and user id (`acct-identity`) — report first

```
git switch main; git pull --prune
Read-only until I reply.

1. Report how sign-in is wired: Cognito hosted UI or our own screens, which
   pools, and what the user id is (email or otherwise).
2. Web-search Cognito's current forgot-password and change-password
   capabilities. Do not rely on memory.
3. Propose forgot password, forgot user id and change password, stating what
   Cognito provides and what we would build.

Report and stop.
```

## P11 — Plans and upgrade (`acct-upgrade`) — report first

```
git switch main; git pull --prune
Read-only until I reply.

1. Report why Enterprise does not show on dev's subscription page. Read the
   code and the Paddle catalog mapping in config/paddle.
2. List every page where a plan limit throttles the tenant.
3. Propose an upgrade action for the account page and each throttled page.

Report and stop.
```

## P12 — Sharing (`share-recipient`) — report first

```
git switch main; git pull --prune
Read-only until I reply. Read share_viewer_spec_v1 in full.

1. Report the share expiry in code today, and where it is set.
2. Report what the spec says a recipient gets, and what is built.
3. Decided: a verified recipient's access is 2 weeks (was 30 days).
   Registered viewers keep MFA, as the spec says. Report every place in code
   and in the specs that carries 30 days, and report whether viewer MFA is
   built.
4. Requested: the recipient gets a free account on their email with an
   initial password; a guide page for recipients. Report what this needs.
5. Lay out what a recipient could receive (the editable memo, a PDF, both)
   and what each costs to build.

Report and stop.
```

## P13 — Design items — read only

```
Read-only. No branch.

1. Memo files: report how memos are stored and listed today, and what
   states exist (draft, live, archived or otherwise).
2. Admin data: report what the system records about sign-ins, failed
   sign-ins and signups, and where (Cognito, our database, logs).
   Web-search what Paddle's dashboard and API expose about customers.
   Web-search how Retool connects to Aurora with the RDS Data API and to
   Cognito, and whether a private cluster needs a tunnel or self-hosting.
3. Report how the fact base is scoped per tenant today: which tables, which
   keys.

Report and stop.
```

## P14 — Archive and clean views (`archive`) — report first

```
git switch main; git pull --prune
Read-only until I reply.

1. Report the tables for memos and engagements, and every column that holds
   a state or status today.
2. Report every list that shows memos or engagements, and the API route
   behind each.
3. Propose: archive a memo, archive an engagement, nothing deleted; archived
   items leave the working lists; each list can show archived items and
   restore one. Give the migration you would write, unapplied.

Report and stop.
```

## P15 — Separate admin path (`admin-path`) — read and estimate

```
git switch main; git pull --prune
Read-only until I reply.

Decided: the ARQEDIA admin page is a separate path — its own Cognito pool
(staff only, MFA required), its own React app on its own subdomain (own S3
bucket and CloudFront), its own API Gateway with an authorizer trusting only
that pool, its own Lambda with a read-only cross-tenant IAM role, and its own
deploy workflow. Nothing shared with the customer path except the database.

1. Read the Terraform for the customer path: user pools, API Gateway and
   authorizer, Lambdas and roles, the web bucket and CloudFront, DNS and
   certificates, deploy workflows. Report what exists, by file.
2. For each admin component, report what can follow an existing pattern and
   what is new.
3. Estimate the build: new Terraform resources, new files, and the order to
   build them in. Name every hard-to-reverse step (DNS, certificates, pools).
4. Web-search current pricing for API Gateway HTTP APIs, CloudFront and
   Cognito Plus. Do not rely on memory.

Report and stop.
```

## P16 — Home page motion graphic (`site-hero`)

```
git switch main; git pull --prune; git switch -c site-hero
Read in full every file you will edit before editing it.

1. Read the hero graphic in site/ (the canvas and its stage strip). Report
   every duration and transition time it uses, and what text each stage
   shows today and when that text is shown and hidden.
2. Make it 5% faster: divide every stage duration and transition by 1.05.
   Report each value before and after.
3. Each stage's text description stays once its stage has run, so the
   final settle shows every stage with its description.
4. Leave the reduced-motion path working; report what it shows.

Build the site. Render it and screenshot the final settle.
Commit, push, short push summary. Give me the walk.
```

