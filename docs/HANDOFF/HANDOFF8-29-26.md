# Handoff — DD SaaS Platform

**As at 24 August 2026. Design complete; build not started.**

---

## 1. What this is

A multi-tenant, customer-configurable due diligence service. Customers define
their own document categories, extraction schemas and report templates; a single
generic pipeline runs against that configuration and produces evidence-backed
memos they can share.

Positioned against folders, Word, Excel and manual labour — not against
enterprise data rooms.

**Ten components are specified. Nothing is built.**

---

## 2. Files

All in the outputs folder. Markdown is the working source; the Word files are
compiled deliverables.

| File | What it is |
|---|---|
| `build_index.md` | **Start here.** Canonical component numbering, settled economics, standing decisions |
| `dd_platform_design_spec.docx` | Components 1–9 compiled, 12 chapters, 63pp |
| `dd_platform_addendum_existing_architecture.docx` | Whether the eBL pipeline transfers, and what citation costs |
| `frontend_onboarding_spec_v1.docx` / `.md` | Component 10 — front end and onboarding |
| `wallet_entitlement_spec_v1.md` | Component 1 |
| `config_registry_spec_v1.md` | Component 2 |
| `config_editors_spec_v1.md` | Component 3 |
| `pipeline_spec_v1.md` | Component 4 |
| `share_viewer_spec_v1.md` | Component 5 |
| `provider_abstraction_spec_v1.md` | Component 6 |
| `isolation_terraform_spec_v1.md` | Component 7 |
| `plans_starter_packs_spec_v1.md` | Component 8 |
| `identity_seats_spec_v1.md` | Component 9 |
| `admin_recovery_policy_draft.md` | Operational policy, draft, needs counsel |

**Numbering warning.** Component numbers (source markdown) and chapter numbers
(the compiled Word file) differ by one from Chapter 2 onward, because Chapter 1
is the overview. Component 7 is Chapter 8. Component 9 is Chapter 10. Component
10 is not yet in the compiled document. This has already caused two errors —
check `build_index.md` before citing a number.

---

## 3. Settled economics

| Plan | Price/mo | Seats | Credit | Shares/mo | Schemas/type | Sections/template | Daily classify |
|---|---|---|---|---|---|---|---|
| Base | $25 | 2 | $5 | 5 | 3 | 12 | $5 |
| Small Business | $65 | 5 | $15 | unlimited | 5 | 25 | $15 |
| Enterprise | negotiated | n | n | n | 10 def. | 50 def. | negotiated |

- Billable: document filed $0.25 · memo generated $1.00 · provider call TBD.
- Allowances sealed from real balance: test $1/day, classification per plan.
- Trial: 30 days, seats free, $5 metered cap, expires to read-only.
- Top-up: $5 × seats, on explicit consent. Soft prompt at $5, hard stop at $0.
- Cash expires 30 days per tranche; monthly credit forfeits at anniversary;
  spend order is soonest-expiry-first.

---

## 4. Standing architectural decisions

- **Aurora MySQL Serverless v2, min 0 ACU, new cluster.** Verified available in
  `us-east-2` at `8.0.mysql_aurora.3.12.0`. RDS Data API instead of RDS Proxy —
  a proxy holds persistent connections and would defeat auto-pause, costing
  ~$44/month idle.
- **Snapshot versioning.** One mutable draft per tenant; publish freezes an
  immutable revision. Every job pins one revision and never re-reads.
- **Stable field IDs.** Labels are display only. Rename free, delete is a real
  break.
- **Fields may repeat as a row.** Grouped fields carry a row index so a
  shareholder's name stays attached to their percentage.
- **Non-destructive throughout.** Retirement is absence from a new revision.
  Account deletion is the only destructive action and scrubs everything.
- **No silent spend.** No config edit re-extracts. Every charge follows a click.
- **Validation at publish, never at save.**
- **Two launch regions**, `us-east-2` and `eu-central-1`; Singapore, UAE and
  São Paulo on demand. Region declared at signup, immutable after. CDN
  geo-restricted to the report's own region. No AWS region exists in Argentina.
- **MFA on every seat** and on registered viewers.
- **Identity is regional.** A global directory maps a hashed email to a region
  and holds no addresses.
- **React for customers, Retool for internal tooling.** Retool's
  per-external-user pricing inverts against a $25 plan at scale.

---

## 5. Decisions still required

| # | Item | Blocks |
|---|---|---|
| ~~1~~ | ~~Separate AWS account~~ — **SETTLED 24 Aug.** `ARQEDIA` 667523685221, member of the eBL Finance Inc organization | — |
| 2 | Customer vetting position for self-serve signup | Launch, and procurement conversations |
| 3 | First screening provider — OFAC or LSEG | Component 6 build. See `ARQEDIA_backlog_SC01_screening.md` |
| 4 | Share rate limit — the number | Component 5 build |
| ~~5~~ | ~~Extraction handler list~~ — **SETTLED 26 Aug.** Four handlers: text, tables, forms, expense. See `ARQEDIA_handlers_and_span_join_v1.md` | — |
| 6 | Practitioner review of the three starter packs | Nothing — but it decides product quality |

**Item 1 is closed.** The ARQEDIA account exists under the same organization, so
billing stays consolidated and quotas are isolated from eBL. New-account setup
tasks moved to §6.

**Item 6 outranks everything else commercially** and appears on no engineering
critical path. Most customers will run a forked pack largely unchanged for years.

---

## 6. Procurement

| Item | Status | Lead time |
|---|---|---|
| AWS account | **Done** — ARQEDIA 667523685221 | — |
| Bedrock model access, per region | Not started | Request per model per region; **blocks the pipeline** |
| Service quota increases | Not started | New accounts start low; Textract, Lambda concurrency, SES |
| SES production access | Not started | Days; **per region** — needed for both |
| Paddle account | Not started | Days; business verification |
| Domains, DNS, Retool | Already owned | — |

**New-account setup, before Phase 0:**

- **Centralize root access via IAM**, per the console prompt. Deletes root
  credentials on the member account and moves privileged actions to the
  management account.
- **Root email is currently a personal Gmail address.** Root email controls
  account recovery. Move it to a controlled corporate alias — the same reasoning
  as the administrator recovery policy in Chapter 11, applied to ourselves.
- **Terraform targets the ARQEDIA account** (667523685221), not eBL. State
  backend — S3 bucket plus lock — lives in ARQEDIA. Set before the first
  `terraform apply`.
- **New GitHub repo, held under the eBL GitHub organization for now.**
  Separate repo from the eBL build; may move to its own organization later.
- **GitHub Actions OIDC role** in ARQEDIA, trusted to that repo. No long-lived
  access keys.
- **AWS Budgets alert** on the ARQEDIA account.

**Payment processor: Paddle recommended**, not on fees but on tax. Stripe leaves
you as legal seller, so you register and file VAT in the EU, GST in Singapore
and equivalents in the UAE and Brazil yourself. Paddle is merchant of record at
5% + $0.50 and remits across 200+ jurisdictions. At $25/month the fee difference
is roughly fifty cents per tenant.

**Two things to confirm with Paddle before committing:** that they support
one-off charges against a stored card with no standing mandate — the
consent-per-top-up model depends on it — and that they will accept a
sanctions-screening product, since a merchant of record approves what it sells.

---

## 7. The evidence question — read the addendum before building

Review raised that the design was an extraction-and-report system rather than an
evidence-backed workspace. Assessment, after reading the eBL source:

- The eBL pipeline's three-stage split — raw document, normalized envelope,
  curated artifact — transfers largely unchanged.
- **Document-level citation is deterministically available today.** Composed
  sections already receive their source document identifiers in the context the
  model reads; nothing renders them.
- **Page-level citation needs one join** — the extractor must return the page or
  unit alongside each value, and that must meet the existing character-span
  structure. **SETTLED 26 Aug** in `ARQEDIA_handlers_and_span_join_v1.md` §3.
- **Clickable drill-down is separate work again**: an in-app report renderer, a
  version-pinned source viewer, and a share grant scope that permits evidence
  access. The current share spec says a viewer sees no source documents, which
  would disable the feature for the audience it is meant to impress.
- **Correction to the main spec:** the readability gate rejects anything without
  a text layer, which excludes every spreadsheet. The eBL pipeline already
  handles XLSX natively with per-worksheet spans. The gate belongs on the PDF
  path only.

---

## 8. Front-end build sequence

Procurement runs alongside. Phases 0–2 are the critical path.

| Phase | Content | Depends on |
|---|---|---|
| 0 | Repo, CI, Terraform static hosting, TypeScript strict | AWS account |
| 1 | Shell, region routing, auth, tenants, seats, MFA | Component 9 backend |
| 2 | **Vertical slice** — upload → quote → commit → generate → read | Components 1, 4 |
| 3 | Source viewer, citations | **Blocked by the unspecified span join (§7)** |
| 4 | Config editors and the mapping matrix | Components 2, 3 |
| 5 | Wallet, plans, top-up | Paddle account |
| 6 | Share and viewer experience | SES production access |
| 7 | Engagement workspace, document vault | Phase 3 evidence data |
| 8 | Onboarding flow; Retool internal tools in parallel | — |
| 9 | Accessibility, mobile, copy, second region, load test | — |

**Phase 2 is the de-risking phase and must precede breadth.** If integration is
going to hurt, it should hurt there, cheaply.

---

## 9. Working agreement

Rules of Engagement are restated at the head of every response. They are not
decoration — several caught real errors in this session. Notably: RoE 4 kept a
loan-to-value ratio out of the credit starter pack, because the denominator
convention differs by lender and shipping one would silently impose it on every
customer who forked it.

Conventions that held well and should continue:

- Anything unverified is marked **PROPOSED** and says why.
- Open items are grouped by what would resolve them — decision, measurement,
  vendor, legal — because that determines who acts.
- Third-party capabilities are verified by search and attributed, never
  asserted from memory.
- An item is only "open" if it blocks work. Everything else is a caveat.
