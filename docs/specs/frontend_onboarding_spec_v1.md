---
title: "Component 10 — Front End & Onboarding"
subtitle: "Customer-facing application, internal tooling boundary, and self-serve signup at scale"
date: "23 August 2026"
lang: en-GB
---

# 1. Scope and verdict

**Owns:** the customer-facing web application, the boundary between it and
internal tooling, and the signup and approval path.

**Does not own:** any server-side logic in components 1–9. This is a client over
those interfaces.

**Verdict: build the customer-facing application in React; keep Retool for
internal tooling.** That is a tool boundary, not a compromise — Retool remains
where it is strong, and the team keeps the skill it already has.

Third-party pricing in §2 was verified against published sources at the time of
writing.

---

# 2. Why not Retool for customers

**Per-external-user pricing inverts against the product's economics.** Retool
external users are free to 50, then tiered — roughly $8/user/month at 51–250,
$6 at 251–500, $4 above 500, with custom pricing at higher volumes. Ten thousand
users at the lowest published rate is $40,000/month. Against roughly 4,000 Base
tenants at $25 that is 40% of revenue before inference. The product's entire
pricing logic is that users are cheap and usage is metered; Retool's is the
reverse.

**SSO is Enterprise-only.** SAML and OIDC sit above the Business tier, and
component 9 sells single sign-on as an Enterprise feature. Building it on Retool
Business is not possible.

**Three surfaces are bespoke interaction, not forms over tables** (see §5):
the mapping matrix, the report reader with citation drill-down, and the source
viewer. A low-code builder would be fought at every step.

**The viewer surface is an acquisition channel.** Branded, fast, mobile, first
impression on a qualified lead. Load performance is a recurring complaint in
Retool user reports — least important on an internal tool, most important here.

---

# 3. What Retool keeps

Internal only. Builder seats plus internal users, no external-user exposure.

| Tool | Purpose |
|---|---|
| Pack authoring console | Author and publish the three starter packs |
| Support console | Tenant lookup, entitlement state, ledger inspection |
| Administrator recovery | The Chapter 11 workflow, with its evidence and approval fields |
| Reconciliation views | Ledger sums against granted buckets, alarm triage |
| Cost dashboards | Per-tenant inference, storage and KMS attribution |

**This means no admin panel is built.** That is a meaningful saving and the main
reason to keep Retool rather than drop it.

---

# 4. Stack

| Layer | Choice | Rationale |
|---|---|---|
| Framework | React + TypeScript, Vite build | Team familiarity; no SSR requirement behind login |
| Delivery | Static bundle to S3, CloudFront per region | Matches regional data planes (Chapter 9); no always-on compute |
| API | API Gateway + Lambda | Existing backend; no new surface |
| Auth | Regional identity pools (Chapter 12) | Identity stays in the tenant's region |
| State | Server state via a query cache; local UI state in components | Avoid a global store for data the API owns |
| Marketing site | Separate static site | SEO and public content; no coupling to the app |

**Not server-side rendering.** There is no SEO need behind the login wall, and
SSR reintroduces always-on compute — the opposite of the zero-idle discipline the
Aurora and Lambda decisions were built on. *(In plain terms: rendering pages on a
server would put a machine on the clock that we deliberately took off it.)*

**One bundle, region-agnostic.** The app is built once and deployed to each
region's distribution. Region is resolved at login from the global routing
directory; the client holds no regional configuration.

## 4.1 Why React, and why not something newer

Recorded so the choice is deliberate rather than inherited.

**The four hard components decide it.** A PDF viewer with page deep-linking, a
virtualised matrix, a worksheet grid with cell-range highlighting, and a report
reader. Third-party library depth is React's one unassailable advantage, and it
lands exactly where this build carries most risk. Svelte and Solid have fewer
mature UI libraries — in those frameworks these components mean wrappers or
ground-up builds.

**Performance is not the bottleneck.** Svelte and Solid win real benchmarks on
bundle size and first paint, measured in tens of milliseconds. The viewer
surface's actual constraint is a ~15-second Aurora resume from zero capacity,
which is why memos are cached at the edge (Chapter 6 §4). Framework overhead is
noise against that.

**Hiring compounds.** React holds roughly 45% share among professional
developers with two to three times the job listings of the alternatives. Over a
product's life, a choice that narrows the talent pool creates friction that
technical quality does not offset.

**The React churn is real, and we decline it.** Server Components and the
gravitational pull toward meta-frameworks are a complexity tax. Using React as a
client-side view library with Vite — no SSR, no meta-framework — is a deliberate
opt-out of the part of React that is thrashing while keeping the part that is
stable. *(In plain terms: we are using the boring, settled subset on purpose.)*

**The considered runner-up is Solid, not Svelte** — JSX, signals, top of the
benchmarks, learnable in a day by a React developer. Declined on ecosystem depth
for the four components above, not on merit.

**Revisit only if** a measured business problem appears that the framework
causes. Switching to chase benchmarks is not a reason.

---

# 5. Surfaces

## 5.1 The four hard ones

These carry most of the effort. Everything else is conventional.

**Mapping matrix.** Document types down, schemas across, checkbox at each
intersection, live margin counts. Empty row is a zero-read; empty column an
orphan schema; hovering a row lists every field its mapped schemas produce with
duplicates highlighted. Virtualised grid — at tenant scale (dozens by tens) it
fits a screen, but the interaction is custom.

**Source viewer.** `pdf.js` with page deep-linking, plus a grid renderer for
worksheets that can highlight a cell range. This is the component the citation
feature depends on and the one with no off-the-shelf answer. *(This is what turns
a footnote into "open the statement at page 14".)*

**Report reader.** Rendered report with a citation gutter; clicking a claim opens
the source viewer at the cited location, version-pinned. Requires the evidence
join described in the addendum.

**Upload and quote review.** Drop files, watch classification propose parts,
correct proposed types, merge or split, see the cost and balance, commit. This is
where money moves, so it must be unambiguous.

## 5.2 The rest

Configuration editors (categories, schemas, templates) with the persistent draft
bar, issue count, lock holder and Publish. Engagement workspace as a tree.
Document vault: browse, search, versions, tags, "used in these sections".
Wallet: balance, top-up, plan. Seats and invitations. Share dialogue with grant
scope. Viewer experience — the recipient's read of a shared report, served from
cache, never touching the paused database.

---

# 6. Quality floor

Non-negotiable, not announced in the UI:

- Responsive to mobile. The viewer surface especially — recipients open reports
  on phones.
- Visible keyboard focus throughout; the config editors are keyboard-heavy work.
- Reduced motion respected.
- Every blocking validation issue links to the object that caused it. A publish
  failure reading "3 issues" with no navigation is a support ticket.
- Empty states are instructions, not decoration. First run is fork-a-pack, never
  a blank editor.

---

# 7. Copy rules

The interface vocabulary is how people learn the product. Three rules:

- **Name things by what the person controls**, never by how the system is built.
  No "schema", "envelope", "revision id", "handler". Say document type, field
  set, version.
- **An action keeps its name through the whole flow.** The button says Publish,
  the confirmation says Published.
- **Errors state what happened and what to do.** They do not apologise and are
  never vague.

---

# 8. Onboarding — the self-serve path

Unattended, no queue, no manual approval.

```
verify email → create tenant → declare jurisdiction → confirm region
   → fork a starter pack → trial begins
```

- **Region is suggested by geolocation and confirmed by the person**, then
  immutable (Chapter 9). The declared jurisdiction binds, not the IP.
- **No card at signup.** The trial is 30 days, full use, capped at $5 metered.
  A card wall at the front contradicts the positioning and cuts trial starts.
- **Fork-a-pack is the first screen after signup**, not an empty configuration
  editor.
- **Prompt for a second administrator during setup.** The cheapest version of the
  Chapter 11 recovery policy is one that is never invoked.

---

# 9. Abuse controls at scale

A 30-day full-use trial on our inference is the exposure. Controls, in order of
effectiveness:

| Control | Where it lives |
|---|---|
| $5 metered ceiling on trial | Wallet, already specified |
| Daily classification and test allowances | Wallet, already specified |
| Entitlement check ahead of every model call | Wallet, already specified |
| Disposable-email domain blocking | Signup |
| One trial per email domain | Signup |
| Signup rate limit per IP and per domain | Edge |

**Only the last three are new.** The specification already contains the controls
that bound cost; signup adds the controls that bound volume.

---

# 10. Manual review — what stays human

At ten thousand users, manual steps must be exceptions measured in tens per week:

- Enterprise plan setup and negotiated terms.
- Administrator recovery requests (Chapter 11).
- Abuse flags raised by the controls in §9.
- Evidence-package or data-export disputes.

Everything else is unattended. If a manual step appears in the ordinary path, it
is a design error at this scale.

---

# 11. Customer vetting — an open question, not a gap

**We would be selling a sanctions and diligence tool self-serve, at $25, with no
vetting of the buyer.** The payment method is effectively the only signal about
who a tenant is.

That may be entirely acceptable — it is how most self-serve software works. But
a regulated customer will ask it during procurement, and the answer should be
deliberate. Three positions are available: accept it and say so plainly; require
business email and a verified payment method as a light gate; or vet tenants
above a usage threshold. **This needs a decision and probably counsel input. It
is not resolvable here.**

---

# 12. Open

1. **Vetting position** (§11) — needs a decision.
2. **Design direction** — palette, typography, layout. Not attempted here; the
   product's visual identity is a separate brief.
3. **Component library** — build on a headless primitive set or from scratch.
   Build-phase, but affects the accessibility floor in §6.
   Alongside it, three choices that will shape this codebase more than the
   framework name did: TypeScript strict mode, a server-state library rather
   than hand-rolled fetching, and a router that handles the region redirect
   cleanly.
4. **Spreadsheet rendering approach** (§5.1) — the worksheet viewer has no
   obvious off-the-shelf answer and needs a spike before it is estimated.
5. **Effort and sequencing** — this component is larger than any other and the
   nine that precede it assume it exists. It should be scheduled first, not last.
