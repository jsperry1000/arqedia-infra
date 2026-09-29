# Provider Abstraction — Spec v1.0

**DD SaaS product · greenfield · design spec**
Component 6 of 9. Extends *Config Registry v1.0* and *Pipeline v1.0*. Charged by
*Wallet & Entitlement Gate v1.0*.

---

## 0. Status of every claim here

Third-party capabilities in §6 were verified by search and are cited as such.
Everything else is a decision made for this product. **§5 is the important
section** — OFAC screening is not a bolt-on feature, and the spec says so with
specifics. Items awaiting a decision are collected in §8.

Phase 1 ships OFAC only. LSEG and Kpler are phase 2, built against the same
interface.

---

## 1. Scope

**Owns:** the interface external data providers sit behind, how their results
enter the tenant's data, how they are triggered, priced and entitled.

**Does not own:** the config editors (component 3), memo composition
(component 4), or plan commercials (component 8).

---

## 2. Core decision — a provider is a schema

**Provider results are ordinary extracted field values.** They persist as
`(document_id, field_id, value, revision_id)` exactly like document extraction,
and bind to template sections like any other data.

This falls out of modelling a provider as a **schema whose input is a field
value rather than a document**. Everything already built then applies unchanged:

| Existing machinery | Applies to providers how |
|---|---|
| `schema_def` + `schema_field` | Provider output fields, with stable `field_id`s |
| Publish validation (registry §5) | Orphan, overlap and binding checks work as-is |
| Template binding | Screening results drop into memo sections like any field |
| Coverage report (pipeline §7) | A missing screening shows as an uncovered section |
| Wallet ledger | Provider calls are a fifth billable event |

The only genuinely new thing is the **trigger**: a document schema runs against
a filed document; a provider schema runs against field values already extracted.

**This is why the eight data types matter** (*Config Editors* §5.2). Entity
name, Address and Identifier exist as distinct types precisely so a provider
schema can declare what it needs as input. If they had collapsed into Text there
would be nothing to bind against.

---

## 3. The interface

Two shapes, because screening and enrichment are genuinely different and
forcing them into one signature would produce a lowest-common-denominator
contract that fits neither.

```
ScreeningProvider
  screen(subject: {name, identifiers[], address?, dob?, country?})
        → Match[] { matched_name, list_source, match_score,
                    match_type, entry_ref, listed_at }

EnrichmentProvider
  enrich(subject: {identifiers[]}, fields_requested[])
        → FieldValue[]

Provider (common)
  provider_code, display_name, kind, entitlement_required,
  cost_cents_per_call, health() → Ok | Degraded | Down
```

Dispatch is by `provider_code` on the provider schema, mirroring `handler_code`
on a document schema. A tenant selects a provider; they never author one.

---

## 4. Trigger, freshness and re-screening

**Trigger is explicit, never automatic.** The tenant runs screening on a
counterparty file, or includes it as a step before composing a memo. No provider
call ever fires as a side effect of filing a document — that would spend money
without a click, which the wallet forbids absolutely.

**Every result carries `retrieved_at`.** A sanctions check from six months ago
is not a sanctions check. Templates bound to provider fields render the
retrieval date alongside the value, and the coverage report flags results older
than a threshold as stale.

**Re-screening is a new billable call.** Results are immutable and timestamped;
a fresh screen writes new values rather than overwriting old ones, so a memo
composed in March still shows what was known in March.

---

## 5. OFAC — what shipping this actually requires

**Verified:** OFAC's Sanctions List Service is free and requires no
authentication, but it is <cite index="21-1">a file delivery service — it
publishes list files rather than offering a screening API</cite>. Consuming it
means building the screening ourselves.

**What "ours to build" covers:**

- **Ingest and refresh.** Download, parse and index the SDN and consolidated
  lists on a schedule. Lists change without notice; a stale index is worse than
  no index because it reads as authoritative.
- **Normalisation.** Names arrive with aliases, transliterations, and multiple
  scripts. Entity types differ — individuals, vessels, aircraft, organisations.
- **Matching.** Fuzzy name matching against sanctions lists is a discipline in
  itself, not a string comparison. Threshold choice is the entire product: too
  loose and every tenant drowns in false positives, too tight and the feature is
  worse than useless.
- **Explainability.** A match must show *why* it matched — which name, which
  list, what score — or a tenant cannot act on it.

**This is the highest-risk component in the product.** Everywhere else, being
wrong produces a bad memo. Here, being wrong produces a tenant who believes a
counterparty is clear when it is not. Two consequences follow, and neither is
optional:

- **Framing is a screening indicator, not a compliance determination.** The
  product surfaces potential matches for the tenant to assess. It does not
  clear anyone. This wording belongs in the UI at the point of result, in the
  memo output, and in the terms.
- **The threshold is a build-phase decision made against a labelled test set**,
  not a number chosen in a spec. It needs measurement, and it needs revisiting.

**Sequencing note:** OFAC is free to consume and expensive to do well. LSEG,
which is the opposite, may be the better first screening provider commercially
even though it is scheduled later. Worth deciding deliberately rather than by
default.

---

## 6. LSEG and Kpler — phase 2

**Verified capabilities.**

LSEG World-Check One is <cite index="37-1">a REST API over HTTPS returning JSON,
with a published Swagger schema</cite>. There is <cite index="38-1">a Zero
Footprint variant that stores no screening record at LSEG, though it does not
support batch screening</cite>. LSEG states <cite index="38-1">its data is made
available only to those with a due-diligence or regulatory obligation</cite>.

Kpler is available <cite index="4-1">via API, SDK, Snowflake, Kafka and an Excel
add-in</cite>, sold <cite index="14-1">demo-led with no public self-service
pricing</cite>.

**Redistribution is assumed permitted, by instruction, and is not verified.**
I could not confirm from either provider's public documentation that reselling
their data to our tenants under our licence is allowed. LSEG's obligation-based
access language points the other way. **This must be contractually settled
before phase 2 ships**, because the alternative model — each tenant brings their
own credentials and we supply the integration — changes premium from a margin
line to a feature fee, and changes this spec's entitlement model.

**Design consequence either way:** `provider_credential` is scoped so it can
hold either our platform credential or a tenant's own. Building it
tenant-scoped from the start costs nothing and covers both outcomes.

---

## 7. Data model

```
provider              provider_code PK, display_name, kind,   -- screening | enrichment
                      cost_cents_per_call, active TINYINT(1)

provider_credential   credential_id PK, provider_code FK,
                      tenant_id FK NULL,        -- NULL = platform credential
                      secret_ref, created_at    -- secret in AWS Secrets Manager

provider_schema       schema_id FK, provider_code FK,
                      -- marks a schema_def as provider-backed rather than
                      -- document-backed; input bindings are schema_fields
                      -- of type Entity name / Identifier / Address

provider_call         call_id PK, tenant_id FK, provider_code FK,
                      schema_id FK, subject_ref, event_ref,
                      retrieved_at, status, cost_cents

screening_match       match_id PK, call_id FK, matched_name, list_source,
                      match_score, match_type, entry_ref, listed_at
```

`plan_provider` (wallet §3) carries entitlement. `price_book` is keyed by
`event_type` and must extend to `provider_code`, since provider costs differ by
orders of magnitude — OFAC is free to us, World-Check is not.

Credentials live in AWS Secrets Manager; only `secret_ref` is in the database.

---

## 8. Open

1. **Provider call pricing** — per provider, not flat. Cannot be set until
   phase 2 provider costs are contracted.
2. **Match threshold** (§5) — build-phase, measured against a labelled test set.
3. **List refresh cadence** (§5) — how often OFAC lists are re-ingested.
4. **Staleness threshold** (§4) — at what age a screening result is flagged.
5. **Redistribution rights** (§6) — assumed by instruction, contractually
   unconfirmed. Blocks phase 2, not phase 1.
6. **First screening provider** (§5) — OFAC or LSEG. A sequencing decision with
   commercial consequences.

Items 5 and 6 need you. The rest are build-phase or phase-2 gated.
