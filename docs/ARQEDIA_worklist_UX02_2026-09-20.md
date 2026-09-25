# ARQEDIA — Work List UX-02

| | |
|---|---|
| Raised | 20 September 2026 |
| Source | Walk feedback, answered by number in chat |
| Status | Not started. Prompts below; one branch per group |
| Revised | 20 September 2026 — decisions on expiry, MFA, archive; admin page outline added |
| Revised | 20 September 2026 — admin on a separate path; viewer MFA reinstated |
| Revised | 20 September 2026 — home page motion graphic: speed and settled text |
| Revised | 20 September 2026 — one numbering scheme: groups and items only; admin page is Group 16 |
| Revised | 22 September 2026 — Groups 13, 14, 16 and most of 18 closed; Group 18 added with the walk notes and every decision taken on 21 and 22 September |

**Numbering.** Groups are numbered 1–21. Items are numbered within their group (2.3 is Group 2, item 3). Each group has one prompt for Code, named by its group. Nothing else is numbered.

**Next up:** 19.2 — nothing warns a tenant that the trial is ending, and
nothing announces that it has ended. Today the only place the countdown
appears is Account > Subscription; no screen a person works on shows it, and
no email exists. A tenant loses the ability to file with no notice. Build the
banner before the first paying tenant.

**Also:** 20.1 — a generation that fails keeps the money; see Group 20.

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
| 5.2 | **Deferred to backlog, 20 September 2026.** Not built. Since the allowlist (#174), an uninvited address is refused as not invited before the domain check, and invited addresses skip the domain check, so the domain refusal cannot fire. Moving the not-invited refusal to step 1 needs a new route that would disclose who is on the allowlist. Kept at step 4; revisit when signup opens to the public |
| 5.3 | A home button on every step, so the flow can be left. Decided: it goes to the public site, not the app's sign-in card |
| 5.4 | Back stays in the same place on every step; the panel is the same size on every step |

## Group 6 — Navigation and progress
Branch `ux-nav-progress`. Clear; build.

| # | Item |
|---|---|
| 6.1 | A home button on every page |
| 6.2 | The progress monitor is more prominent everywhere it appears |
| 6.3 | **Closed on tidy-ups, 22 September 2026:** five screens moved to the shared monitor; three inline indicators in flex rows stay, with the reason in a comment. Not built, found in Group 6, 20 September 2026: five screens report progress with a bare `<p className="busy">` instead of the shared monitor — Account.tsx:232 and :771, Settings.tsx:118, SignUp.tsx:177, Memo.tsx:565 and :634. UX-12 says one indicator for everything that runs. Convert them |

## Group 7 — Memo view
Branch `ux-memo-view`. Clear; build.

| # | Item |
|---|---|
| 7.1 | Sources and Edit at the foot of each text block are clearly visible before hover or click |

## Group 8 — File upload, select to remove
Branch `ux-upload-select`. 8.1 decided: tick boxes on the two pre-filing blocks only; confirm step; bulk remove reports partial failure. 8.2 decided; built on its own branch after 8.1.

| # | Item |
|---|---|
| 8.1 | A tick-box column to select files to remove, with select-all at the top |
| 8.2 | **Decided 20 September 2026.** A filed document can be deleted entirely, together with the facts extracted from it. This is about clearing a mistake, not compensating for one: the $0.25 filing and any $1.00 memo already generated are the tenant's own cost, and a clean memo is a new generation at $1.00. Memos already generated are immutable artifacts and are left as they are. Overrides "non-destructive throughout" for this one act, by decision. Needs its own branch: what deleting touches (document row, extracted values, claims, memo sources, S3 objects), what the confirm step must say, and what it reports |

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
| 10.4 | **Approved 20 September 2026.** Move the user pool off Cognito's default sender onto SES (email_sending_account DEVELOPER, the verified arqedia.com identity, no-reply@arqedia.com), which lifts the 50-a-day account cap to the SES quota and puts bounces where we can see them. Take ARQEDIA's own wording for the verification message at the same time. The apply session needs iam:CreateServiceLinkedRole once |
| 10.5 | Approved 20 September 2026: the seat invitation is actually sent. Nothing sends it today; the screen says so. A small mail helper on the API, an ses:SendEmail statement and SENDER on the API role, and the send after invite() so a failed send never loses the seat. From no-reply@arqedia.com, Reply-To the inviting administrator. The token still comes back in clear: the link is the fallback when mail goes astray |
| 10.6 | Backlog, 20 September 2026: no bounce handling. With production access a bounced invitation counts against our sending reputation, and there is no mailbox for SES's notifications. Proper answer is a configuration set with an SNS topic. Survivable at this volume; its own branch |
| 10.7 | Built 20 September 2026: an invitation link landed on the sign-in card, for an account that did not yet exist, and the token was never read. Now a /invitation page sets the name and password, accepts, signs in and lands on Engagements; signed in as someone else, it offers Sign out. Server: a password below Cognito's policy is refused as 400 in Cognito's words, before the seat is written |
| 10.8 | Backlog, 20 September 2026: nothing trades an invitation token for who invited them, the firm or the role, so the welcome page says "an ARQEDIA workspace". Closing it needs GET /invitations/{token} — unauthenticated, but the token is the secret |
| 10.9 | Backlog, 20 September 2026: a revoked invitation and an already-accepted one both say "That invitation is no longer open", because a revoked row and a consumed row are both no row. Telling them apart is a schema decision |

## Group 11 — Plans and upgrade
Branch `acct-upgrade`. Report first.

| # | Item |
|---|---|
| 11.1 | An upgrade action on the account management page and on every throttled page |
| 11.2 | Enterprise is not shown on dev's subscription page. Find out why |
| 11.4 | Enterprise has no route in, found in Group 11, 20 September 2026. It is deliberately not a plan row (018_billing.sql: "Enterprise is a row per contract"), has no Paddle product and is refused by _known_plan. But site/pricing sells it as a third column, and Settings tells every Base tenant that Enterprise removes the ARQEDIA footer line. So a tenant can want it and has no way to ask. **Decided 20 September 2026:** a "Talk to us about Enterprise" link on Settings and the plan table, to enterprise@arqedia.com. Built with 11.1 |
| 11.5 | enterprise@arqedia.com is forwarded through Cloudflare (owner, 20 September 2026). Terraform declares no MX record and a public lookup on 20 September returned none, so confirm by sending a test message. If it bounces, the forwarding is on a zone that is not answering for the domain. Mail sending is separate: SPF points at SES |
| 11.6 | Built on ux-upgrade, 20 September 2026: Review.tsx:996-1002 carried prose above the Generate button ("A memorandum costs $X and $Y is available... Top up under Settings, Account management"). It is now an UpgradePrompt landing on /account?tab=balance, so all three not-enough-balance blocks carry the same control. One prose path remains, in the mid-flight charge refusal (Review.tsx:490), which has no room for a control |
| 11.3 | Pricing, single source: report where every price lives (meter_price table, code constants, config/paddle, Paddle catalogue), whether Paddle's catalogue is pushed from the repo or edited by hand, and whether the site and app pick up a price change. Known so far: metered prices come from meter_price via GET /wallet/quote; the $5 top-up increment is a UI constant TOPUP_CENTS (Group 4, 4.2), so the top-up confirm states a client-side figure. Held 20 September 2026; the read-only prompt is kept for the end of the thread |

## Group 12 — Sharing
Branch `share-recipient`. Report first.

| # | Item |
|---|---|
| 12.1 | A verified recipient's access expires after 2 weeks (was 30 days) |
| 12.2 | Sending gives the recipient a free account on their email, with an initial password. Registered viewers keep MFA (spec §3) |
| 12.3 | A guide page for recipients ("click here to see the shared report") |
| 12.4 | **Settled by the spec (§5), accepted 20 September 2026:** the recipient reads the memo in the app and can download a watermarked copy, both. No editable memo: §2 makes a share a single immutable artifact |
| 12.5 | Proposed 20 September 2026, awaiting agreement: the spec says a registered viewer's grants last "6 months from registration", which leaves a memo sent long after registration already expired. Rule: grants that exist at registration run 6 months from registration; grants sent afterwards run 6 months from their send. The tenant's explicit expiry still wins. Registration itself never expires |
| 12.6 | Design group, not a branch: the viewer (CDN-served, no Aurora read, revocation that invalidates the CDN before returning), viewer accounts and registration with MFA, the watermark burned into every page, and the three tables (viewer_account, share_grant, share_access_log). Sharing is mocked today |

## Group 13 — Design items
One read-only prompt. No branch.

| # | Item |
|---|---|
| 13.1 | Manage memo files: archive, live, draft; drag and drop; filter by template key, date, editor; a folder per template |
| 13.2 | **Answered 21 September 2026:** facts are per tenant and per document; no fact is shared across tenants. Tenant 0 is the catalogue configurations are copied from, not a shared fact base. Within a tenant, an engagement is imposed only at read time by matching the document's S3 key |
| 13.3 | **Closed 22 September 2026:** engagement table and memo state (030, #200, #201), every read switched to engagement_id (#217). Original entry: Found 21 September 2026, the gap under 13.1 and Group 14: there is no engagement table and no memo state. An engagement is a typed string used as a folder name; it has no creator, date or status, and disappears when its last document goes. engagement_id exists on memo and document and has never been populated. A memo has no status column and cannot be archived, hidden or deleted. Every list filters by LIKE on S3 keys. Decide the schema (an engagement table; a memo state) before building Group 14 or 13.1 |

The admin page, previously listed here, is now Group 16.

## Group 14 — Archive and clean views
**Closed 22 September 2026 (#218, applied and walked).** Built on Group 13's engagement rows and memo state.
Branch `archive`. Report first; likely a migration, so put to you before build.

| # | Item |
|---|---|
| 14.1 | Archive a memo; archive an engagement. Nothing is deleted. Built 22 September 2026: any seat may archive or restore, by decision |
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
| 15.3 | Dead code: flock.ts mode 'work' claims to drive the app's working indicator (UX-12). Nothing in ui/src imports it; the app uses .working-bar. Remove the mode or correct the comment. Found reading for Group 3, 20 September 2026 |

Linked: Group 3 (static stages behind the app) uses the same stages.

## Group 16 — ARQEDIA admin page, on a separate path
Branch `admin-path`. Read and estimate first.

| # | Item |
|---|---|
| 16.1 | Admin user pool: its own Cognito pool, ARQEDIA staff only, MFA required |
| 16.2 | Admin front end: a separate small React app on its own subdomain, own S3 bucket and CloudFront |
| 16.3 | Admin API: a separate API Gateway whose authorizer trusts only the admin pool |
| 16.4 | Admin Lambda: its own function and IAM role, reads across tenants, writes nothing |
| 16.5 | Admin deploy: its own workflow |
| 16.6 | The page: who accessed, who tried and failed, who signed up |
| 16.7 | Found 21 September 2026: sign-ins and failed sign-ins are recorded nowhere usable. Amplify talks to Cognito directly, so our API never sees a sign-in; the pool is on Essentials with no threat protection, so there is no auth event history; there is no CloudTrail trail, only 90 days of event history. Signups are recorded well in signup_attempt. Fix is Cognito Plus on the customer pool ($0.020 per active user, no free tier) or a CloudTrail trail. Decide before the admin page shows sign-ins |
| 16.8 | Decided 21 September 2026: the admin path uses its own certificate for admin.arqedia.com and its own deploy role; the staff pool is Essentials with MFA required. First version shows signups, tenants, seats and Paddle data. Template authoring and the offer stay on tenant 0 until the admin path has proved itself |
| 16.9 | Required before admin.arqedia.com resolves, decided 21 September 2026: the admin Lambda's read-only guarantee is code (cross_tenant.py refuses anything but SELECT), not credentials — rds-data:ExecuteStatement autocommits. Give the admin function a SELECT-only database user with its own secret, per OBS-02, so a cross-tenant console cannot write even if the code guard is bypassed |
| 16.10 | Deferred 22 September 2026: the admin reader's database password does not rotate. The master secret rotates every 7 days through an RDS-managed function; the reader needs a rotation Lambda with VPC placement. Build before production |
| 16.11 | Decided 22 September 2026: the admin reader is granted SELECT on six tables only — tenant, subscription, plan, seat, seat_invitation, signup_attempt — not the whole schema, so the staff console cannot read document content. Any new table the console needs is a grant decision. The reconciler's own identity stays under OBS-02 |
| 16.12 | **Live 22 September 2026.** admin.arqedia.com on its own certificate, staff pool (MFA required, deletion protection on), API trusting only that pool (a real customer token refused at the gateway), and a Lambda reading as a SELECT-only user on six tables. First staff account info@ebl-finance.com signed in with a scanned QR. Tenants, Seats and Signups work. Not yet built from 16.8's first version: Paddle data. ops@arqedia.com could not be used (no mail server for arqedia.com; 11.5) |

The options considered and the decision follow.

### Options considered

Where the page's data is recorded today is unknown until the Group 16 prompt reports.

**Standing decision on record:** "React for customers, Retool for internal tooling" (build_index). The reason given there is that Retool's per-external-user pricing inverts against a $25 plan at scale. That reason concerns customer-facing use; an admin page used only by ARQEDIA staff is internal use.

#### Option A — in the React app, as a tenant 0 screen

| | |
|---|---|
| How | New screens reachable only in tenant 0 (the ARQEDIA admin tenant, TPL-04 D8). Read routes on the existing API, refused for every other tenant in the dispatcher — the same guard pattern proven on `/config/offer` today |
| Operability | Same repo, same deploy, same sign-in. No second system to run. Every change is a code change, a PR and a deploy |
| Cost | No licence. Build time for each screen, filter and export. Runs on the existing Lambda and API |
| Security | Staff use the existing Cognito sign-in; nothing leaves AWS; no third party holds credentials. The risk is placement: cross-tenant data served by the same API customers use, so a guard mistake exposes one tenant's data to another. Every admin route needs the tenant 0 guard and a test proving the refusal |

#### Option B — in Retool

| | |
|---|---|
| How | A Retool app connected to our data. **Unverified:** how Retool would reach Aurora (the cluster is private and we use the Data API), and Cognito's sign-in records. To be checked before choosing |
| Operability | Faster to assemble tables, filters and charts. A second system: its own logins, permissions and upkeep. Changes do not go through our PR and deploy path |
| Cost (published, checked September 2026) | Free: up to 5 users. Team: about $10 per builder and $5 per internal user per month, annual. Business: $50 per builder and $15 per internal user annual, $65 per builder monthly. Enterprise: custom. Billed by activity — a user who edits an app in a month is billed as a builder that month |
| Security | Retool holds credentials that read across every tenant. With Retool Cloud, data leaves our AWS account to Retool. Business adds audit logging and richer permission controls; SSO is reported as Business-tier. Standing decision: identity is regional — a cross-region admin view pulls per-region identities into one place, in either option, but in Retool that place is a third party |

### Decided — a separate admin path (Option C): a separate admin path, in React

Neither A nor B. The admin page gets its own path end to end, so the two uses are not mixed and no customer-facing route can serve cross-tenant data.

| Component | What it is (items 16.1–16.5) |
|---|---|
| Admin user pool | Its own Cognito pool, ARQEDIA staff only, MFA required. Customer pools never hold an admin |
| Admin front end | A separate small React app on its own subdomain, its own S3 bucket and CloudFront distribution |
| Admin API | A separate API Gateway whose authorizer trusts only the admin pool. A customer token is refused at the gateway, before any code runs |
| Admin Lambda | Its own function and IAM role: reads across tenants, writes nothing |
| Admin deploy | Its own workflow. An admin change never redeploys the customer app |

**Running cost.** Cognito Lite and Essentials: 10,000 monthly active users free, per account or AWS organization — shared with the customer pools, which are in the same account. Cognito Plus (risk-based sign-in protection): no free tier, $0.020 per active user per month. API Gateway, Lambda, S3 and CloudFront at admin volumes: small, not priced — unverified. Source: aws.amazon.com/cognito/pricing, checked 20 September 2026.

**Build cost.** Not estimated. The Group 16 prompt reads the current Terraform and estimates.

**Open — yours to decide:** do template authoring and the offer (tenant 0, TPL-04 D8) move to the admin path too, or does the admin path hold access and signup reporting only?

### Where the data sits (to be confirmed by the Group 16 prompt)

| Question | Source |
|---|---|
| Sign-ins and failed sign-ins | Cognito (per-region pools) — unverified what is recorded |
| Signups | Our database (signup Lambda writes the tenant) |
| Subscriptions and payments | Paddle — what its dashboard and API expose to be web-searched by the Group 16 prompt |

## Group 17 — Serious bugs
Tracked, not scheduled. Each item is fixed on its own branch when taken up.

| # | Item |
|---|---|
| 17.1 | **Closed 21 September 2026 (#208, layer rebuilt, applied and walked).** A body with no key is a create and is refused if the fact exists; a body with a key is an edit. Tenant 0's f_company_summary shape restored; its description now carries the SUBJ-01 wording, deliberately. Original entry: Adding a fact whose key matches an existing fact overwrites that fact instead of refusing. Found walking 2.1, 20 September 2026. The walk overwrote a field in a draft on dev; not yet identified or restored. Fix: the server refuses a create on an existing key, the field card shows the refusal, the edit path is unchanged |
| 17.2 | Found in Group 9, 20 September 2026: ten Python sources are CRLF in the working copy against .gitattributes — composition/cleanup.py, extraction/app.py, normalizer/classify.py, proposer/app.py, render/app.py, render/style.py, shared/config.py, shared/editor.py, shared/pack.py, shared/textract.py. Git stores LF, so a checkout elsewhere hashes differently and those Lambdas plan as changed on another machine. Normalise them |
| 17.3 | Found 21 September 2026: an engagement name with a space (or apostrophe, ampersand) sits on "analysing" for ever. upload_url cleans the name for the S3 key ("TEST - 2" becomes "TEST-2"), but the screen keeps and polls the typed name, which matches nothing. Nothing is lost; the documents are under the cleaned name. Long-standing, not caused by 030. Fix: POST /uploads returns the cleaned name and the screen navigates to it, showing "Will be saved as ..." while typing |
| 17.4 | **Closed on tidy-ups, 22 September 2026:** upload_url returns the cleaned filename and stored() is deleted. Found 21 September 2026: Review.tsx:18-28 stored() is a TypeScript copy of the server's filename cleaning, used to match uploaded files to rows. Same drift risk as 17.3 in a smaller place. Ask the server instead, as 17.3's fix does |
| 17.5 | **Closed 22 September 2026 (tidy-untracked).** Two documents committed that existed only in this working copy and had never been touched by any commit on any branch: CMP-01 as it stood, and PAY-02 moved from docs/ into docs/backlog-items/ where PAY-01 already sat. PAY-02 was marked "Before the first paying tenant" and had been unbacked on one machine for two days. Five scratch files deleted — cleanup_py.txt (a UTF-16 dump of lambda/composition/cleanup.py taken before SUBJ-01 changed it, 277 lines against the tracked 317), field_defs.txt, field_defs_full.txt and subj_check.txt (query output from that investigation) and composition_log.txt (empty); none was tracked, so removing them produced no commit. `/*.txt` now ignored at the repository root, anchored so it cannot reach lambda/layers/docprocessing/requirements.txt, which is tracked and is what the layer is built from. ARQEDIA_backlog_UX01_mvp_ui_worklist (1).md was already gone from disk, deleted by somebody else between the morning of 22 September and the tidy-up. Original entry: Housekeeping: untracked scratch files at the repository root — cleanup_py.txt, composition_log.txt, field_defs.txt, field_defs_full.txt, ARQEDIA_backlog_UX01_mvp_ui_worklist (1).md — and docs/ARQEDIA_backlog_PAY02_paddle_what_is_left.md, which is untracked and may belong in docs/. Tidy in one pass |
| 17.6 | **Closed on tidy-ups, 22 September 2026:** terraform fmt on api.tf, composition.tf, normalizer.tf and site.tf; fmt -check -recursive passes. Found 22 September 2026: api.tf fails terraform fmt -check (exit 3) — nine misaligned lines in the API Lambda's environment block, predating the engagement-reads branch. Run terraform fmt on its own branch |
| 17.7 | **Decided 22 September 2026:** configuring and publishing are for administrators only, as the code already enforces. A Member uploads, files, generates and shares; an administrator who wants a Member to configure makes them an administrator. CLAUDE.md's settled decision is wrong and is corrected |
| 17.8 | Found 22 September 2026: the eight --dull-* and --lit-* tokens in tokens.css are referenced by nothing since the Configure strip became one canvas (ux-config-18b). Remove them in a tidy-up |
| 17.9 | Found 22 September 2026: no workflow runs the tests. The three jobs in .github/workflows deploy only, so the 411-test suite — including the new check that a plan's price matches Paddle's — runs only when somebody remembers. Add a test job on pull requests |
| 17.10 | Found 22 September 2026 tidying 17.5: docs/HANDOFF/ carries duplicates of backlog items that also live in docs/backlog-items/ — ARQEDIA_backlog_HONE01_keep_a_rewrite_prompt (1).md beside ARQEDIA_backlog_HONE01_keep_a_rewrite_prompt.md, plus ENV01 and UX01. Four tracked files. Three are byte-identical to their namesakes and are straightforward deletions; **ENV01 is not** — docs/HANDOFF/ holds 63 lines and docs/backlog-items/ holds 95, so closing this means reading both and choosing which copy is authoritative, not just deleting the spare. Its own branch |

## Group 18 — UI/UX notes, 22 September 2026
Raised on the walk. Items marked *open* need an answer before a prompt is written.

| # | Item |
|---|---|
| 18.1 | **Built 22 September 2026 (ux-cite-links, ux-cite-persist).** Clicking a footnote highlights every other place in the memo where the same footnote is used; the highlight survives closing the passage panel, and deleted-source citations light but do not open |
| 18.2 | Document types > fields sought: the drawer scrolls up behind the page head and shows above the header; it must stay below it. Put the drawer's Save button in its pinned head |
| 18.3 | Configure's stage strip: the static highlight does not make sense on configuration; the sequence makes sense as a workflow. Order the parts Documents / Facts / Report sections, matching the strip. The selected part's icon shows enlarged, 1.5 to 2 times the strip's size, in the white space on the left of the panel. The strip plays its sequence left to right once each time Configure opens; when done, the swarm keeps moving |
| 18.4 | Band descriptions: Facts reads "The extracted facts which all memos draw upon"; Document types reads "Which documents are expected to contain required facts" |
| 18.5 | Enterprise more prominent, on the same level as the other plans and arranged horizontally, on both Account > Subscription and the public pricing page. Pricing shown in both places comes from one source, so what is offered and what is marketed cannot drift apart. Joins 11.3 |
| 18.6 | **Built 22 September 2026 (ux-generate-template).** The template choice shows whenever there is one, preselected when it is the only one, and the confirm step names it |
| 18.7 | **Closed 22 September 2026 (classify-filename, migration 032, applied and walked).** The file name goes to the model as a hint that may mislead and never overrides the content or a boundary; the folder is recorded from a folder picker and never read by the model; the line under the type dropdown says so |
| 18.8 | The flow through fields, upload, memo generation, template selection and publish is esoteric for a general user; streamline it or add guidance. **Closed 22 September 2026 (ux-first-memo, applied and walked):** all five fixes built — Memos opens when a memo can be generated, Engagements points an unconfigured tenant to its memoranda, Get started says what leaving costs, an empty type list says where types come from, and the second-administrator step left signup (18.15) |
| 18.9 | Closing the account runs through two confirmation gates. Report what exists today first |
| 18.10 | Backlog, 22 September 2026: clean up the Configure strip and side icon (ux-strip-flock, merged). The side icon's layout arithmetic assumes a 1560px content column and a 200px rail and hides below a 2156px window, so it does not show on a 1920 screen even where white space appears; check it against what actually renders, with a full-window screenshot, and correct. Review the strip's feel against the home page once seen. Remove the unused tokens with it (17.8) |
| 18.11 | Backlog, 22 September 2026: in rewrite mode the memo renders one MemoDocument per section, each with its own citation highlight, so clicking a citation lights its other uses only within that section. In read mode it spans the whole memo. Fix by lifting the highlight state into MemoView |
| 18.12 | **Closed 22 September 2026 (ux-first-memo, applied).** Original: with zero published templates, the generate step shows no choice and calls api.generate with no template; what the server does then is unverified. Check it, and make it refuse plainly before any charge |
| 18.13 | **Decided 22 September 2026, from the Group 18 reports.** (1) Classification passes the file name to the model as a hint alongside the document's text, and the folder is recorded as provenance (document.source_folder, proposed column). (2) Closing an account is held for 30 days with a cancel, behind two confirmation gates: a server-counted statement of what is lost, then the organisation's name typed exactly; administrator only. The deletion itself (29 tenant tables, S3 prefixes, Cognito users, tenant_domain) is not built and is its own design. (3) The three limits advertised but not enforced — field sets per document type, sections per template, daily classification allowance — are enforced by the app and clearly configurable per plan. (4) Approved: the 18.8 new-tenant fixes, the 18.12 no-template message, and config/plans.json as the one source for plans and prices, with a build check against Paddle and Enterprise as a third column that cannot be bought |
| 18.14 | Decided 22 September 2026: prices and plan limits are changed in config/plans.json, reviewed and deployed — not from the staff admin page, which shows them read-only. Process written: ARQEDIA_process_changing_prices_and_limits.md, to be committed to docs/ with the 18.5 build |
| 18.15 | Found 22 September 2026 building 18.8: signup's second-administrator step wrote second_admin to pending_signup and nothing ever read it — no seat_invitation, no email. Anyone who named a colleague was told they would be invited and no invitation existed. The step is removed from signup and replaced by a prompt on Get started pointing at Account > Seats. The column stays; zero rows on dev ever carried a value |
| 18.16 | Found 22 September 2026, stage 3 of 18.5: Enterprise's column wording sits in ui/src/upgrade.tsx, because it is deliberately not a plan row and the API bundle cannot read config/plans.json from the repository root. Close it by getting the file into the API bundle so /billing/subscription reports Enterprise too — a build change |

## Group 19 — The trial
Raised 22 September 2026, walking the trial after 18.5.

| # | Item |
|---|---|
| 19.1 | **Closed 22 September 2026 (trial-length, layer 41, applied and walked):** every customer-facing place says 14 days, from config/plans.json, and standing() reports trial_ended instead of trial for ever |
| 19.2 | Not built: nothing warns a tenant before the trial ends, and nothing announces that it has. No email, no banner on any working screen. Filing simply starts refusing once the trial money expires. Build a banner at 7, 3 and 1 day, and a plain ended state; email later. **Confirmed 22 September 2026:** no scheduled job watches trial_ends_at — the three EventBridge rules are envelope_written, docs_created and reconcile, and none touches trials; no code anywhere compares trial_ends_at to a clock; mail.py sends exactly one thing, the seat invitation. The only surface carrying the countdown is Account.tsx's Subscription tab, which a person has to navigate to. Tenant 9 on dev sits eight days out, with its trial bucket moved to the same instant, so the countdown can be watched |
| 19.3 | Not built: on the ended-trial screen no plan is preselected. Preselect Small Business, which the tenant can change before paying |

## Group 20 — A generation that fails keeps the money
Found 24 September 2026 on dev. Ledger entry 50, tenant 2, engagement 30
(TEST-2): $1.00 taken at 18:28:16, composition request
382f77b5-ba19-41e3-9cb3-3433a0d86e9a failed three times on Bedrock
ServiceUnavailableException, the event was dropped, and no memo exists.
No refund, no retry, nothing on screen, no record but the log. Not
refunded: dev.

| # | Item |
|---|---|
| 20.1 | The charge is taken before the work and nothing reverses it when the work fails. A failed composition must refund its charge, and the screen must say generation failed and nothing was charged |
| 20.2 | Composition has no failure destination, so after Lambda's two retries the event is dropped with no record. Add one, and record every failed run where somebody can see it |
| 20.3 | The charge and the composition are not linked: no idempotency key and no ledger entry id reach composition, and the memo table holds neither. Carry the ledger entry id through and store it on the memo, so a charge can be traced to its result |
| 20.4 | A transient model failure is not retried inside the run. Retry on ServiceUnavailableException before giving up |
| 20.5 | Nothing tells the person. The API answers "started" and the memo simply never appears. The screen must show a failed generation |

## Group 21 — Filing at scale, and what you get out
Raised 24 September 2026 on the walk.

| # | Item |
|---|---|
| 21.1 | Categorising a large upload is lost work. Reach the end without enough balance and you must leave to top up; coming back reverts everything. No way to file part of the batch now and the rest later, and no way to leave and return to where you were |
| 21.2 | The top-up screen does not say how much is needed for the thing that sent you there |
| 21.3 | No way to search or sort uploaded files while categorising them. A large upload becomes unworkable |
| 21.4 | The document-type groups shut themselves. Open each one individually, and opening another must not close the first |
| 21.5 | A tenant's templates do not show which ARQEDIA template revision they were taken from, so nobody can tell whether a newer one exists |
| 21.6 | Printing a PDF asks before it prints: None (the default), Draft, Confidential, or Confidential Draft, as a diagonal watermark. Decided 24 September 2026 |
| 21.7 | Offer a DOCX download as well as PDF |
| 21.8 | A memo downloaded by a share recipient carries their email address and the time, burned in, whatever the tenant chose above. That is the share spec's own rule (§5) and it is not a choice; it belongs with the viewer work in 12.6, which is unbuilt |
| 21.9 | Raised 24 September 2026: a screen does not call out what must be done first. Filing is blocked until the engagement has a subject, but nothing puts that in front of the person before they categorise a batch. Every screen with a precondition should say so, first and plainly, so the work is not done twice |
| 21.10 | Raised 24 September 2026 on the walk: after filing, six rows sat saying they were filing. They never progressed, stayed on screen, and could not be clicked. Find out what they were waiting on and what left them there: whether the filing failed after the charge, whether the poll stopped, or whether the rows were left in a state the screen has no handling for |
| 21.11 | Found 24 September 2026: a filed document with no extracted_at and no extraction_error shows "extracting…" for ever, and the engagement's banner counts it. 47 documents across 9 engagements are in that state on dev; 13 in COCOAEMPIRE were extracted on 28 August, had no type so no schema, produced nothing, and were left NULL by 007's backfill. The screen has no state for "extracted and found nothing", and no end to the wait. Give it one, and stop the banner counting rows nothing will ever move |

## Rolled into existing backlog

| Item | Into |
|---|---|
| Rewrites in the memo feed back into the section's configuration, live or by a save-after-rewrite choice | HONE-01, as an addition. HONE-01's existing text is kept |

---

# Prompts for Code

Each prompt is named by its group and can be pasted alone. Build prompts are numbered by item. Report-first prompts list what to read; they are not items.

## Group 1 prompt — Labels and lists (`ux-labels`)

```
Group 1 — Labels and lists.
git switch main; git pull --prune; git switch -c ux-labels
Read in full every file you will edit before editing it.

1.1 Rail: "Catalogue" -> "Template Catalogue".
1.2 Configure a report: the delete control's wording -> "Delete this template".
1.3 Memo view: the Rewrite control's label -> "Have Model Redraft a Section".
1.4 Memo list: the second column shows the template key. Show the template's
    name. Report where the name comes from; if the list's API response does
    not carry it, report and stop before changing the API.

Report by item number.
tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## Group 2 prompt — Section editor, fields panel (`ux-section-fields`)

```
Group 2 — Section editor, fields panel.
git switch main; git pull --prune; git switch -c ux-section-fields
Read in full every file you will edit before editing it.

2.1 Add a fact directly from the section's fact list.
2.2 Align the columns of the upper (selected) and lower (unselected) portions.
2.3 Upper portion: a select-all box at the top of each selected column.
2.4 Upper portion only: a field shown in a column is not shown again in any
    column to its right. Leftmost wins. Do not change the lower portion.
2.5 Lower portion: pin the column headers.
2.6 The document panel that shows fields: search bar at the top; pin headers.
2.7 Edit field panel: the description box grows with its content, up to 25
    lines, then scrolls.
2.8 Ticking a field on or off is slow. Before fixing, report what happens on
    a click (renders, network calls, timings). Then fix.

Reuse existing CSS where a rendered pattern exists. Report any new CSS.
Report by item number.
tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## Group 3 prompt — Prominence and the static graphic (`ux-backdrop`) — report first

```
Group 3 — Sections / Facts / Documents prominence and the static graphic.
git switch main; git pull --prune; git switch -c ux-backdrop
Read-only until I reply.

- Read the home page's motion graphic in site/. List its stages: what each
  shows and where in the code each is defined.
- Report how Sections / Facts / Documents are presented today.
- Propose 3.1 (more prominent at the top of the page) and 3.2 (a static
  grey/black rendering of one stage behind the app, subtly, per selected
  item).

Report and stop. I will assign stages to Sections, Facts and Documents.
```

## Group 4 prompt — Confirm before spend (`ux-spend-confirm`)

```
Group 4 — Confirm before spend.
git switch main; git pull --prune; git switch -c ux-spend-confirm
Read in full every file you will edit before editing it.

4.1 Generate memo: pressing Generate opens a confirm step stating the charge
    ($1.00, memo_generated) and whether the balance covers it. The charge
    happens only on a second button. Where the balance does not cover it,
    say so and offer top-up; do not charge. Read the price from where the
    code holds it; do not hard-code $1.00 in the UI. Report where it is
    held. Report how upload currently shows its cost, and match it.
4.2 Top-up: a confirm step before the charge.

Report by item number.
tsc -b, vite build, tests in Docker with PYTHONDONTWRITEBYTECODE=1.
Commit, push, short push summary. Give me the walk.
```

## Group 5 prompt — Signup flow (`ux-signup`)

```
Group 5 — Signup flow.
git switch main; git pull --prune; git switch -c ux-signup
Read in full every file you will edit before editing it.

5.1 Region selection: align the tickboxes.
5.2 A domain that already exists is reported at step 1, not step 4. Report
    how the check runs today before changing it. If it needs a new API
    route, report and stop.
5.3 A home button on every step, so the flow can be left.
5.4 Back sits in the same place on every step; the panel is the same size on
    every step.

Report by item number.
tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## Group 6 prompt — Navigation and progress (`ux-nav-progress`)

```
Group 6 — Navigation and progress.
git switch main; git pull --prune; git switch -c ux-nav-progress
Read in full every file you will edit before editing it.

6.1 A home button on every page.
6.2 List every place the progress monitor appears. Make it more prominent in
    each. Render and screenshot before and after.

Report by item number.
tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## Group 7 prompt — Memo view (`ux-memo-view`)

```
Group 7 — Memo view.
git switch main; git pull --prune; git switch -c ux-memo-view
Read in full every file you will edit before editing it.

7.1 Sources and Edit at the foot of each text block are clearly visible
    before hover or click. Render and screenshot before and after.

tsc -b, vite build. Commit, push, short push summary. Give me the walk.
```

## Group 8 prompt — Upload, select to remove — report first

```
Group 8 — File upload, select to remove.
git switch main; git pull --prune
Read-only until I reply.

- Report what removing a file from the upload page does today: which rows
  and objects it touches, and whether anything is deleted or only marked.
- Report whether a filed document can be removed, and what happens to the
  facts extracted from it.

Report and stop. 8.1 (a tick-box column with select-all) is built after my
reply.
```

## Group 9 prompt — Branding — report first

```
Group 9 — Branding.
git switch main; git pull --prune
Read-only until I reply. Read ARQEDIA_backlog_BR01 in docs/ if present.

- Report what the tenant can edit in Settings > Brand today.
- Report the tenant columns that hold brand colours, and where render
  reads them.
- Propose 9.1 (tenant edits all brand colours in Settings) and 9.2 (BR-01's
  fourth colour). Give the migration you would write, unapplied.

Report and stop.
```

## Group 10 prompt — Password and user id — report first

```
Group 10 — Password and user id.
git switch main; git pull --prune
Read-only until I reply.

- Report how sign-in is wired: Cognito hosted UI or our own screens, which
  pools, and what the user id is (email or otherwise).
- Web-search Cognito's current forgot-password and change-password
  capabilities. Do not rely on memory.
- Propose 10.1 (forgot password), 10.2 (forgot user id) and 10.3 (change
  password), stating what Cognito provides and what we would build.

Report and stop.
```

## Group 11 prompt — Plans and upgrade — report first

```
Group 11 — Plans and upgrade.
git switch main; git pull --prune
Read-only until I reply.

- 11.2: report why Enterprise does not show on dev's subscription page. Read
  the code and the Paddle catalog mapping in config/paddle.
- List every page where a plan limit throttles the tenant.
- Propose 11.1: an upgrade action for the account page and each throttled
  page.

Report and stop.
```

## Group 12 prompt — Sharing — report first

```
Group 12 — Sharing.
git switch main; git pull --prune
Read-only until I reply. Read share_viewer_spec_v1 in full.

- Report the share expiry in code today, and where it is set.
- Report what the spec says a recipient gets, and what is built.
- 12.1 is decided: a verified recipient's access is 2 weeks (was 30 days).
  Registered viewers keep MFA, as the spec says. Report every place in code
  and in the specs that carries 30 days, and whether viewer MFA is built.
- 12.2 and 12.3: the recipient gets a free account on their email with an
  initial password; a guide page for recipients. Report what these need.
- 12.4: lay out what a recipient could receive (the editable memo, a PDF,
  both) and what each costs to build.

Report and stop.
```

## Group 13 prompt — Design items — read only

```
Group 13 — Design items.
Read-only. No branch.

- 13.1: report how memos are stored and listed today, and what states exist
  (draft, live, archived or otherwise).
- 13.2: report how the fact base is scoped per tenant today: which tables,
  which keys.

Report and stop.
```

## Group 14 prompt — Archive and clean views — report first

```
Group 14 — Archive and clean views.
git switch main; git pull --prune
Read-only until I reply.

- Report the tables for memos and engagements, and every column that holds
  a state or status today.
- Report every list that shows memos or engagements, and the API route
  behind each.
- Propose 14.1-14.3: archive a memo, archive an engagement, nothing deleted;
  archived items leave the working lists; each list can show archived items
  and restore one. Give the migration you would write, unapplied.

Report and stop.
```

## Group 15 prompt — Home page motion graphic (`site-hero`)

```
Group 15 — Home page motion graphic.
git switch main; git pull --prune; git switch -c site-hero
Read in full every file you will edit before editing it.

First, report: every duration and transition time the hero graphic uses,
and what text each stage shows today and when it is shown and hidden.

15.1 Make it 5% faster: divide every stage duration and transition by 1.05.
     Report each value before and after.
15.2 Each stage's text description stays once its stage has run, so the
     final settle shows every stage with its description.

Leave the reduced-motion path working; report what it shows.
Build the site. Render it and screenshot the final settle.
Report by item number.
Commit, push, short push summary. Give me the walk.
```

## Group 16 prompt — ARQEDIA admin page, separate path — read and estimate

```
Group 16 — ARQEDIA admin page, on a separate path.
git switch main; git pull --prune
Read-only until I reply.

Decided: 16.1 its own Cognito pool (staff only, MFA required); 16.2 its own
React app on its own subdomain (own S3 bucket and CloudFront); 16.3 its own
API Gateway with an authorizer trusting only that pool; 16.4 its own Lambda
with a read-only cross-tenant IAM role; 16.5 its own deploy workflow.
Nothing shared with the customer path except the database.

- Read the Terraform for the customer path: user pools, API Gateway and
  authorizer, Lambdas and roles, the web bucket and CloudFront, DNS and
  certificates, deploy workflows. Report what exists, by file.
- For 16.1-16.5, report what can follow an existing pattern and what is new.
- Estimate the build: new Terraform resources, new files, and the order to
  build them in. Name every hard-to-reverse step (DNS, certificates, pools).
- For 16.6, report what the system records about sign-ins, failed sign-ins
  and signups, and where (Cognito, our database, logs). Web-search what
  Paddle's dashboard and API expose about customers.
- Web-search current pricing for API Gateway HTTP APIs, CloudFront and
  Cognito Plus. Do not rely on memory.

Report and stop.
```
