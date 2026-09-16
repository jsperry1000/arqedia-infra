# Plans & Starter Packs — Spec v1.0

**DD SaaS product · greenfield · design spec**
Component 8 of 9. Content published through *Config Registry v1.0*; constrained
by *Wallet & Entitlement Gate v1.0* and *Pipeline v1.0* §8.2.

---

## 0. Status of every claim here

Plan economics in §1 are settled from prior decisions. **Pack content in §3–§5
is proposed domain content, not decided** — it is a starting point for review by
someone who runs these files for a living, and every field and section is
expected to move. Open items in §7.

---

## 1. Plans — settled

| Plan | Price/mo | Seats | Credit | Shares/mo | Schemas/type | Sections/template | Daily classify |
|---|---|---|---|---|---|---|---|
| Base | $25 | 2 | $5 | 5 | 3 | 12 | $5 |
| Small Business | $65 | 5 | $15 | unlimited | 5 | 25 | $15 |
| Enterprise | negotiated | n | n | n | 10 def. | 50 def. | negotiated |

**A plan is a row, not an enum.** Every Enterprise contract is another row. This
is what makes negotiated terms a data entry task rather than a release.

---

## 2. What a pack is, and why it carries disproportionate weight

A pack is a published revision in a reserved pack tenant. Forking deep-copies it
into the new tenant as their revision 1, preserving `field_id` values
(*Registry* §7).

**A pack is also the vocabulary a tenant's own memo is matched against.** The
derive-template-from-memo flow (*Config Editors* §6A) reconciles a tenant's
existing memo against their forked pack — which means pack field coverage
directly determines how well that flow works. A thin pack produces a derived
template full of unmatched proposals.

**Most tenants will never materially edit what they fork.** They will rename a
few labels, add one or two document types, and run the pack as shipped for
years. That makes pack quality the actual product experience for the majority of
your users, and pack authorship a domain job rather than an engineering one.

**Hard constraint: every pack must publish cleanly on Base.** No document type
may map to more than 3 schemas, no template may exceed 12 sections. A pack that
only validates on Small Business is a pack that breaks the moment a Base tenant
forks it and tries to publish an edit. The three packs below are built to that
ceiling deliberately.

---

## 3. Pack 1 — KYC/AML

For onboarding a corporate counterparty.

**Categories:** Corporate Identity · Ownership & Control · Individuals ·
Regulatory & Screening

| Document type | Category | Mapped schemas |
|---|---|---|
| Certificate of Incorporation | Corporate Identity | Company Identity |
| Memorandum & Articles | Corporate Identity | Company Identity |
| Certificate of Good Standing | Corporate Identity | Company Identity |
| Shareholder Register | Ownership & Control | Ownership |
| UBO Declaration | Ownership & Control | Ownership |
| Board Resolution | Ownership & Control | Authorised Persons |
| Passport / National ID | Individuals | Individual Identity |
| Proof of Address | Individuals | Address Verification |
| Regulatory Licence | Regulatory & Screening | Licensing |
| Audited Accounts | Associated Entities | Service Providers |
| Client / Counterparty List | Associated Entities | Commercial Relationships |
| Bank Reference Letter | Associated Entities | Service Providers |
| Insurance Certificate | Associated Entities | Service Providers |

**Categories, revised:** Corporate Identity · Ownership & Control · Individuals ·
Regulatory & Screening · **Associated Entities**

**Schemas**

| Schema | Fields (type) |
|---|---|
| Company Identity | Registered Name (Entity name) · Company Number (Identifier) · Jurisdiction (Text) · Legal Form (Text) · Incorporation Date (Date) · Registered Office (Address) · Status (Text) |
| Ownership | Shareholder Name (Entity name, multi) · Holding % (Number, multi) · UBO Name (Entity name, multi) · UBO Date of Birth (Date, multi) · UBO Nationality (Text, multi) |
| Authorised Persons | Director Name (Entity name, multi) · Signatory Name (Entity name, multi) · Authority Limit (Currency amount) · Resolution Date (Date) |
| Individual Identity | Full Name (Entity name) · Document Number (Identifier) · Nationality (Text) · Date of Birth (Date) · Expiry Date (Date) |
| Address Verification | Name (Entity name) · Address (Address) · Document Date (Date) |
| Licensing | Licence Number (Identifier) · Regulator (Entity name) · Licence Type (Text) · Valid Until (Date) |
| Screening *(provider-backed)* | Match Found (Boolean) · Matched Name (Entity name) · List Source (Text) · Match Score (Number) · Retrieved (Date) |
| Service Providers ⟲ | Provider Name (Entity name) · Provider Role (Text) · Identifier (Identifier) · Relationship Since (Date) |
| Commercial Relationships ⟲ | Counterparty Name (Entity name) · Relationship Type (Text) · Jurisdiction (Text) · Share of Revenue (Number) |

⟲ = repeating group (§6).

**Service Provider Role** is a controlled list in the pack: Bank · Auditor ·
Accountant · Insurer · Legal Adviser · Broker · Custodian. **Relationship Type**:
Customer · Supplier · Distributor · Agent · Affiliate.

**Why this belongs in a KYC pack.** Who a counterparty banks with, who audits
them, who insures them and who their largest customers are is a substantial part
of assessing them — and every one of those is a named entity that may itself
warrant diligence. Capturing them as `Entity name` rather than free text is what
makes them actionable (§5A).

**Template — KYC Memo** (10 sections): Counterparty Summary · Corporate Standing ·
Ownership & Control · Authorised Signatories · Individual Verification ·
**Service Providers** · **Commercial Relationships** · Screening Results ·
Outstanding Items · Conclusion

Still inside Base's 12-section ceiling, with two to spare.

---

## 4. Pack 2 — Vendor Onboarding

**Categories:** Legal Entity · Payment & Tax · Risk & Insurance · Commercial

| Document type | Category | Mapped schemas |
|---|---|---|
| Certificate of Incorporation | Legal Entity | Vendor Identity |
| Shareholder Register | Legal Entity | Vendor Ownership |
| UBO Declaration | Legal Entity | Vendor Ownership |
| Tax Form (W-9 / equivalent) | Payment & Tax | Tax & Payment |
| Bank Details Letter | Payment & Tax | Tax & Payment |
| Insurance Certificate | Risk & Insurance | Insurance Coverage |
| Financial Statements | Risk & Insurance | Financial Health |
| Code of Conduct Attestation | Commercial | Attestations |
| Reference Letter | Commercial | References |

**Schemas**

| Schema | Fields (type) |
|---|---|
| Vendor Identity | Legal Name (Entity name) · Trading Name (Text) · Company Number (Identifier) · Registered Office (Address) · Incorporation Date (Date) |
| Vendor Ownership ⟲ | Shareholder Name (Entity name) · Holding % (Number) · UBO Name (Entity name) · UBO Date of Birth (Date) · UBO Nationality (Text) · Control Basis (Text) |
| Tax & Payment | Tax ID (Identifier) · Tax Residence (Text) · Bank Name (Entity name) · Account Identifier (Identifier) · Currency (Text) |
| Insurance Coverage | Insurer (Entity name) · Policy Number (Identifier) · Cover Type (Text) · Limit (Currency amount) · Expiry (Date) |
| Financial Health | Period End (Date) · Revenue (Currency amount) · Net Assets (Currency amount) · Auditor (Entity name) · Audited (Boolean) |
| Attestations | Policy Name (Text) · Signed By (Entity name) · Signed Date (Date) · Confirmed (Boolean) |
| References | Referee (Entity name) · Relationship (Text) · Period (Text) · Positive (Boolean) |

**Template — Vendor Onboarding Memo** (8 sections): Vendor Summary ·
Legal Entity · **Ownership & UBO** · Payment & Tax Position · Insurance ·
Financial Standing · Compliance Attestations · Recommendation

**UBO is not optional in vendor onboarding.** Paying an entity whose ultimate
owner is unknown is the same sanctions and bribery exposure as onboarding a
counterparty, and procurement teams are increasingly asked to evidence it. The
schema mirrors the KYC pack's `Ownership` deliberately, so a tenant running both
packs sees the same fields.

---

## 5. Pack 3 — Credit File

**Categories:** Borrower · Financials · Existing Debt · Security · **Market Exposure**

| Document type | Category | Mapped schemas |
|---|---|---|
| Certificate of Incorporation | Borrower | Borrower Identity |
| Audited Accounts | Financials | Financial Summary |
| Management Accounts | Financials | Financial Summary |
| Aged Debtors / Creditors | Financials | Working Capital |
| Bank Statements | Financials | Working Capital |
| Facility Agreement | Existing Debt | Existing Facilities |
| Security / Charge Document | Security | Security Position |
| Valuation Report | Security | Asset Valuation |
| Trade Contract / Offtake | Market Exposure | Trade Flow |
| Business Overview / IM | Market Exposure | Business Profile |

**Schemas**

| Schema | Fields (type) |
|---|---|
| Borrower Identity | Registered Name (Entity name) · Company Number (Identifier) · Jurisdiction (Text) · Group Parent (Entity name) |
| Financial Summary | Period End (Date) · Revenue (Currency amount) · EBITDA (Currency amount) · Net Assets (Currency amount) · Total Debt (Currency amount) · Audited (Boolean) |
| Working Capital | As At (Date) · Receivables (Currency amount) · Payables (Currency amount) · Inventory (Currency amount) · Cash (Currency amount) |
| Existing Facilities | Lender (Entity name) · Facility Type (Text) · Limit (Currency amount) · Outstanding (Currency amount) · Maturity (Date) |
| Security Position | Chargor (Entity name) · Security Type (Text) · Secured Party (Entity name) · Registered Date (Date) · Assets Covered (Text) |
| Asset Valuation | Asset (Text) · Valuer (Entity name) · Valuation Basis (Text) · Value (Currency amount) · Valuation Date (Date) |
| Business Profile | Business Description (Text) · Sector (Text) · Primary Markets (Text) · Years Trading (Number) · Employees (Number) |
| Trade Flow ⟲ | Counterparty (Entity name) · Commodity / Product (Text) · Direction (Text) · Annual Volume (Number) · Annual Value (Currency amount) · Contract Expiry (Date) |
| Market Data *(provider-backed, phase 2)* | Observed Counterparty (Entity name) · Commodity (Text) · Observed Volume (Number) · Period (Text) · Retrieved (Date) |

**Template — Credit Memo** (11 sections): Borrower Overview ·
**Business & Markets** · Financial Performance · Working Capital ·
Existing Indebtedness · Security Position · **Trade Flows & Concentration** ·
**Independent Market Data** · Facility Request · Key Risks · Recommendation

Eleven sections — one inside Base's ceiling. Deliberate: this is the pack most
likely to be extended, and a tenant on Base has exactly one section of headroom
before they must upgrade. That is a real upsell pressure point and should be a
conscious choice rather than an accident.

**`Market Data` is where Kpler binds** (*Provider* §2). It is a provider schema
whose input is the `Counterparty` and `Commodity` values already extracted from
trade contracts, and whose output is independent observed flow — the point being
that a borrower's stated trade profile and observed reality can be compared.
Empty until phase 2; the section renders as uncovered, which is correct.

**Deliberate omission: no loan-to-value field.** LTV depends entirely on which
value a lender uses as the denominator — invoiced value, market value, forced
sale value — and those give materially different numbers on the same asset. A
pack that ships one definition silently imposes it on every tenant who forks it.
`Asset Valuation` therefore captures **Valuation Basis alongside Value**, and any
ratio is left to the tenant's own field and their own convention. Shipping a
ratio would be the most consequential mistake in this pack.

---

## 5A. Associated entities → new DD targets

**When an `Entity name` value appears in a memo in an associated-entity role,
offer to open a diligence file on it.** One click creates a new counterparty
file in the tenant's workspace, pre-seeded with the entity name and its role,
using their existing config.

Why it belongs in the product rather than a backlog:

- **It is the natural next thought.** A reviewer reading that a counterparty's
  largest customer is an entity they have never heard of will want to look at
  it. The product should be standing there when they do.
- **It is the internal analogue of the share funnel.** Sharing acquires new
  tenants; this expands usage inside an existing one. Every new file created
  this way is uploads and a memo — real metered revenue on work the tenant
  wanted to do anyway.
- **It costs almost nothing to build.** The entity names are already typed
  values. The action is a pre-filled create, not new machinery.

**Constraints:** the offer appears only for `Entity name` fields the tenant has
marked as associated-entity roles, never for every name in a memo. It creates a
file; it never runs anything. No inference, no charge, no provider call without
a further explicit action — the no-silent-spend rule holds absolutely.

**Lineage is recorded — settled.** Every file opened this way records the file
it came from and the role the entity appeared in.

```
counterparty_file   file_id PK, tenant_id FK, subject_name,
                    parent_file_id FK NULL,     -- the file it was opened from
                    origin_field_id NULL,       -- which field named it
                    origin_role NULL,           -- 'Bank', 'Customer', 'UBO'
                    created_at, created_by_seat_id
```

This gives a tree that walks both ways: from a parent down to everything it
produced, and from a child back to why it exists. It also carries useful
context into the child's memo — a file opened because the entity was named as
the counterparty's auditor is read differently from one opened as their largest
customer.

**What lineage does not give you.** It records *how a file came to exist*. It
does not recognise that the same bank appearing in two unrelated files is the
same bank. Two parents can each open a file on the same company, producing two
files that look identical. That is expected under lineage alone and is what a
real entity register would fix (§8).

**Consequence for the workspace.** Files can spawn files without limit, so the
file list must be a tree rather than a flat list. At real usage volumes a flat
list becomes unusable within weeks.

---

## 6. Repeating groups — a gap in the current model

**These pack additions surfaced a modelling gap that already existed.**

Several schemas hold fields that repeat *together*: Shareholder Name with
Holding %, Provider Name with Provider Role, Counterparty with Commodity and
Volume. The current model stores values as `(document_id, field_id, value)`, so
a multi-cardinality field is a flat list. Two parallel lists give no reliable
way to know that the third shareholder name goes with the third holding
percentage.

This is latent in the KYC pack as already written — `Ownership` has exactly this
problem — and every addition above makes it worse.

**Proposed fix, small now and expensive later:**

- `schema_field` gains `group_key` — fields sharing a key repeat as a unit.
- Extracted values gain `row_ordinal` — which repetition this value belongs to.
- Extraction returns rows for a group rather than independent lists.
- Templates bind a group as a table rather than as separate fields.

This is the same argument as stable `field_id`: trivial to build before any
tenant data exists, and effectively impossible to retrofit across live
configurations and extracted values. **It amends *Config Registry* §4,
*Pipeline* §6 and *Config Editors* §5.2, and needs a decision before those are
built.**

---

## 7. Pack maintenance

- **Packs are versioned like any tenant config.** A new pack revision does not
  reach existing tenants; `forked_from_revision_id` lets us tell them a newer
  version exists. Upgrade is manual and opt-in (*Registry* §7).
- **Packs need an owner.** Sanctions terminology, tax forms and accounting
  presentation all drift. A pack that silently ages is worse than no pack,
  because tenants trust it.
- **Prompts ship with packs and are the hardest part to get right.** The field
  lists above are the easy half; the extraction prompt behind each schema is
  what determines whether the pack actually works.

---

## 8. Open

1. **Domain review of all three packs** — §0 stands: this is proposed content
   from a design exercise, not validated by a practitioner. It needs someone who
   runs KYC files, vendor onboarding or credit files to mark it up.
2. **Pack ownership** (§6) — who maintains them after launch.
3. **Jurisdictional variants** — the KYC pack assumes a broadly common-law
   corporate document set. A German GmbH or a UAE free-zone entity presents
   different documents. Either the pack is deliberately generic and tenants
   adapt it, or there are regional variants. Not decided.
4. **Whether a fourth pack is needed at launch** — three is the settled number,
   noted here only because pack coverage drives self-serve conversion more than
   any feature.

5. **~~Repeating groups~~ (§6) — SETTLED.** Built. Amends *Registry* §3.2a,
   *Editors* §5.2, *Pipeline* §6.
6. **Entity recognition** (§5A) — lineage is settled; recognising the same
   company across unrelated files is not built. Deliberately out of scope, and
   noted because lineage is the first half of it if you build it later.
7. **Workspace tree view** (§5A) — a consequence of lineage, not a decision.
   Belongs to component 9 or the front end, wherever the file list lives.

**Nothing in this component now blocks the build.** Item 1 does not block
building, but it decides whether the thing built is any good.

**Settled since v1.0:** associated entities in all three packs; UBO in the
vendor pack; business profile, trade flows and provider-backed market data in
the credit pack; parent lineage on files opened from an associated entity.
