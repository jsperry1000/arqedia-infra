# Build Index — DD SaaS Product

**Design specs · greenfield · not a build**
Canonical component numbering. Cross-references in every spec resolve here.

\---

## The ten components

|#|Component|Spec|State|
|-|-|-|-|
|1|Wallet \& entitlement gate|`wallet\\\\\\\_entitlement\\\\\\\_spec\\\\\\\_v1.md`|Written|
|2|Config registry|`config\\\\\\\_registry\\\\\\\_spec\\\\\\\_v1.md`|Written|
|3|Config editors \& mapping join|`config\\\\\\\_editors\\\\\\\_spec\\\\\\\_v1.md`|Written|
|4|Pipeline|`pipeline\\\\\\\_spec\\\\\\\_v1.md`|Written|
|5|Share \& viewer accounts|`share\\\\\\\_viewer\\\\\\\_spec\\\\\\\_v1.md`|Written|
|6|Provider abstraction|`provider\\\\\\\_abstraction\\\\\\\_spec\\\\\\\_v1.md`|Written|
|7|Isolation, Terraform \& deployment|`isolation\\\\\\\_terraform\\\\\\\_spec\\\\\\\_v1.md`|Written|
|8|Plans \& starter pack content|`plans\\\\\\\_starter\\\\\\\_packs\\\\\\\_spec\\\\\\\_v1.md`|Written|
|9|Identity \& seats|`identity\\\\\\\_seats\\\\\\\_spec\\\\\\\_v1.md`|Written|
|10|Front end \& onboarding|`frontend\\\\\\\_onboarding\\\\\\\_spec\\\\\\\_v1.md`|Written|

**Operational documents** (not design specs)

|Document|File|State|
|-|-|-|
|Administrator recovery policy|`admin\\\\\\\_recovery\\\\\\\_policy\\\\\\\_draft.md`|Draft — counsel review|

**All ten written.** Components 1–9 are the service; component 10 is the application over it.

> **Corrected 28 September 2026.** Seven of the files named above are not in
> this repository, on disk or in any commit on any branch (`git log --all`):
> `config_registry_spec_v1.md`, `config_editors_spec_v1.md`,
> `pipeline_spec_v1.md`, `provider_abstraction_spec_v1.md`,
> `isolation_terraform_spec_v1.md`, `frontend_onboarding_spec_v1.md` and
> `admin_recovery_policy_draft.md`. All seven exist outside it, in
> `C:\Terraform\terraform_package\docs\build-plans\ARQEDIA DD APP\`, the folder
> `share_viewer_spec_v1.md` was copied from (#198). A citation of components
> 2, 3, 4, 6, 7 or 10 from inside the repository resolves to nothing here.
>
> **Corrected 29 September 2026.** All seven are now committed here, in
> `docs/specs/`, copied unchanged from that folder (dated 23–27 August). They
> are the design as written then; later decision records and the corrections
> in the other specs take precedence where they differ.
>
> **Also noted, not resolved.** This index counts ten components; three specs
> in `docs/specs/` call themselves "of 9" (`identity_seats_spec_v1.md`
> "Component 9 of 9", `plans_starter_packs_spec_v1.md` "Component 8 of 9",
> `share_viewer_spec_v1.md` "Component 5 of 9"). Which count is right is not
> decided here.

\---

## Settled economics

|Plan|Price/mo|Seats|Credit|Shares/mo|Schemas/type|Sections/template|Daily classify|
|-|-|-|-|-|-|-|-|
|Base|$25|2|$5|5|3|12|$5|
|Small Business|$65|5|$15|unlimited|5|25|$15|
|Enterprise|negotiated|n|n|n|10 def.|50 def.|negotiated|

Billable: `document\\\\\\\_filed` $0.25 · `memo\\\\\\\_generated` $1.00 · provider call (phase 2, TBD).

> **Decided 29 September 2026.** `document_filed` is $0.25 per split part, not
> per uploaded file: each part is its own `document` row
> (`011_document_parts.sql`). Live `meter_price` on dev, 29 September:
> `document_filed` 25 cents, standard (`tenant_id IS NULL`), no tenant override.

Allowances, sealed from real balance: `test` $1/day · `classify` per plan.
Trial: 30 days, seats free, $5 metered cap, expiring to `capped`.

> **Corrected 22 September 2026.** The trial is **14 days**, not 30. It was
> changed by the Paddle decision record of 16 September
> (`paddle_subscription_decisions_2026-09-16.md`, "Trial is 14 days in all
> cases (was 30, Wallet §2)") and `signup.TRIAL_DAYS` has said 14 since. The
> line above is left standing because it is what this document said; the
> published figure now lives in `config/plans.json` as `trial_days`, which
> the marketing site and the application both render at build.
Top-up: $5 × seats, on consent, prompted at $5, hard stop at $0.
Cash expires 30 days per tranche; credit forfeits at anniversary; spend order is
soonest expiry first.

\---

## Open items across all specs

**Needs a decision from you**

|Item|Spec|
|-|-|
|Handler list|2, 3, 4 — held for build phase by decision|
|Share rate limit — the number|5|
|First screening provider — OFAC or LSEG|6|
|Customer vetting position for self-serve signup|10|
|Domain review of the three starter packs|8 — the one that matters most|
|Pack ownership after launch|8|
|Jurisdictional pack variants|8|
|Redistribution rights — assumed, unconfirmed|6 — blocks phase 2|

**Account state — needs an AWS read**

|Item|Spec|
|-|-|
|Nothing holds a persistent connection|1, 7 — no RDS Proxy present today|
|~~Separate AWS account~~ — SETTLED: ARQEDIA 667523685221|7|

**Deferred vendor picks, all behind interfaces**

|Item|Spec|
|-|-|
|Payment processor|1|
|Email delivery|5|
|Identity provider — must support per-region pools|9|

> **Corrected 28 September 2026.** Three of these are picked and in use.
> Payments: **Paddle** — `lambda/api/paddle_api.py`, `paddle.tf`,
> `config/paddle/sandbox.json`, decision record
> `paddle_subscription_decisions_2026-09-16.md`. Email: **Amazon SES** —
> `lambda/api/mail.py` and `lambda/signup/app.py`, and the user pools'
> `email_sending_account = "DEVELOPER"` in `auth.tf`. Identity: **Amazon
> Cognito** — `aws_cognito_user_pool` in `auth.tf` (customers) and
> `admin_auth.tf` (staff). Whether per-region pools exist is not verified by
> this note.

**Build-phase measurements**

|Item|Spec|
|-|-|
|Text-layer readability floor|1, 4|
|Classification notional price (placeholder $0.05)|4|
|Staging retention period|4|
|Draft lock heartbeat \& expiry|2|
|Session lifetime \& re-auth frequency|9|

| OFAC match threshold, against a labelled test set | 6 |
| OFAC list refresh cadence | 6 |
| Screening staleness threshold | 6 |
| Provider call pricing, per provider | 6 — phase 2 gated |

**Legal review — start before launch**

|Item|Spec|
|-|-|
|Per-document deletion vs statutory erasure rights|1|
|Marketing opt-in jurisdiction defaults|5|
|Authority-to-disclose affirmation wording|5|
|Screening framed as indicator, not compliance determination|6|
|Admin recovery evidence standard \& approval authority|9 — before first tenant|

\---

## Standing decisions that cut across components

* **Aurora MySQL Serverless v2, min 0 ACU, new cluster** — separate from the eBL
cluster on contract grounds, not hygiene.
* **Snapshot versioning.** One mutable draft per tenant; publish freezes an
immutable revision. Every job pins one revision and never re-reads.
* **Stable `field\\\\\\\_id`.** Labels are display only. Rename is free; delete is a
real break.
* **Non-destructive throughout.** Retirement is absence from a new revision.
Account deletion is the only destructive action and it scrubs everything.
* **No silent spend.** No config edit re-extracts. Every charge follows a click.
Allowances can never draw on real balance and vice versa.
* **MFA on every seat**, and on registered viewers. Verified-only viewers use
mailbox control as the single factor.
* **React for customers, Retool for internal tooling.** Retool's per-external-user
pricing inverts against a $25 plan at scale; it stays where it is strong.

> **Corrected 28 September 2026.** For the staff admin page this is
> superseded: `docs/ARQEDIA_worklist_UX02_2026-09-20.md`, decisions of 20
> September and Group 16, builds it as a separate admin path in React, live at
> admin.arqedia.com since 22 September (16.12).
* **Identity is regional.** A global directory maps a hashed email to a region
and holds no addresses; real identities live in per-region pools.
* **Fields may repeat as a row.** Grouped fields carry a row index so a
shareholder's name stays attached to their percentage.
* **Validation at publish, never at save.** Drafts are legitimately incoherent
mid-edit.
* **Two launch regions**, `us-east-2` and `eu-central-1`; Singapore, UAE and
São Paulo on demand. Region is a Terraform variable, tenant-declared at
signup, immutable after. CDN geo-restricted to the memo's own region.

