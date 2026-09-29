# Isolation, Terraform & Deployment — Spec v1.0

**DD SaaS product · greenfield · design spec**
Component 7 of 9. Underpins all other components.

---

## 0. Status of every claim here

AWS capabilities and prices in §3 and §5 were verified by search and are cited.
Everything else is a decision made for this product. Items awaiting a decision
are collected in §9.

**§5 is the important section** — per-tenant KMS keys cost 4–12% of a Base
subscription, and that changes the encryption design.

---

## 1. Scope

**Owns:** the deployment shape, tenant isolation invariants, storage and
encryption layout, Terraform module structure, and the regulated-stack design.

**Does not own:** application logic in components 1–6, or plan commercials
(component 8).

**Standing decision:** single multi-tenant deployment to start, with the
regulated stack **designed and parameterised, not built**.

---

## 2. Isolation invariants

Four rules. Every one is cheap now and a rewrite later.

- **`tenant_id` on every row**, on every table, without exception — including
  join and log tables. No table is "obviously global."
- **Per-tenant S3 prefix**, with IAM and application-level scoping. Staging and
  filed material live under the same tenant prefix, in separate subtrees.
- **No shared mutable resource in the request path.** No shared cache holding
  tenant data, no shared queue whose ordering couples tenants, no cross-tenant
  singleton. One tenant's load or failure must not be visible to another.
- **Tenant scope resolved once, at the edge**, from the authenticated session,
  and passed down. Never re-derived from a request parameter deeper in the
  stack, which is how cross-tenant leaks happen.

---

## 3. Compute and the connection problem

**Aurora MySQL Serverless v2 at minimum 0 ACU** (*Wallet* §3) pauses when idle
and bills no instance capacity while paused. **Anything holding a persistent
connection defeats this** and restores the ~$44/month floor.

This rules out RDS Proxy, which is the conventional answer for Lambda-to-Aurora
connection pooling and works by holding warm connections.

**Settled — RDS Data API instead of RDS Proxy.** <cite index="24-1">Aurora
MySQL supports a redesigned RDS Data API for Serverless v2, giving secure HTTP
access to run SQL without database drivers or managed connections; it pools and
shares connections on the service side, and imposes no rate limit on requests to
Serverless v2 clusters.</cite> <cite index="15-1">It requires Aurora MySQL 3.07
or higher.</cite>

**Settled — Aurora MySQL `8.0.mysql_aurora.3.12.0` or later.** Verified
available in `us-east-2` (account 539247473206), five minor versions above the
3.07 floor for Data API. No upgrade required; no existing cluster and no RDS
Proxy in that region, so there is nothing inherited to work around.

Cluster shape: engine mode `provisioned`, instances of class `db.serverless`,
`MinCapacity` 0, HTTP endpoint enabled at creation.

**`provisioned` is correct and is not a contradiction.** Serverless v2 is an
instance class inside a provisioned cluster, not an engine mode — only the
retired Serverless v1 used the `serverless` engine mode. A version reporting
`SupportedEngineModes: {provisioned}` is exactly what Serverless v2 requires.

**Data API support is not exposed by `describe-db-engine-versions`.** There is
no `SupportsHttpEndpoint` field on `DBEngineVersion`; the documented version
floor is the contract, and empirical confirmation happens when the dev cluster
is created with the HTTP endpoint enabled. That is a build step, not a design
gate.

**Compute shape:**

| Workload | Shape | Why |
|---|---|---|
| API and editors | Lambda behind API Gateway | Bursty, short, idle most of the time |
| Classification & extraction | Step Functions orchestrating Lambda | Fan-out over parts and schemas; retries and partial failure are first-class |
| Composition & render | Step Functions | Fan-out over sections |
| Scheduled work | EventBridge → Lambda | Bucket expiry sweeps, OFAC list refresh, staging retention |

**Fan-out is why Step Functions rather than a single Lambda.** One filed part
runs every mapped schema, and one memo runs every section (*Pipeline* §8.2).
That is a parallel map with per-branch failure, which a single 15-minute Lambda
handles badly and a state machine handles natively.

**Cold start, and where it actually costs you.** Resume from 0 ACU takes roughly
15 seconds. For an admin uploading documents this is unremarkable. **For a
viewer opening a shared memo it is the first impression of the product on a
qualified lead** (*Share* §1). That surface should be served without touching
the paused cluster — the rendered memo and its grant check are cacheable, and
should be.

---

## 4. Storage

```
s3://<bucket>/tenants/<tenant_id>/staging/<upload_id>/parts/…
s3://<bucket>/tenants/<tenant_id>/documents/<document_id>/…
s3://<bucket>/tenants/<tenant_id>/memos/<memo_id>/…
```

- **One bucket, per-tenant prefixes.** A bucket per tenant hits account quotas
  and adds no security a correctly scoped prefix policy does not.
- **Lifecycle rules** expire staging objects per the retention decision
  (*Pipeline* §9).
- **Account deletion** deletes the tenant prefix wholesale (*Wallet* §9).
- **Secrets** — provider credentials and database credentials in AWS Secrets
  Manager; only references in the database (*Provider* §7).

---

## 5. Encryption — the per-tenant key question

**Verified:** <cite index="41-1">Each KMS key costs $1/month, prorated hourly,
and the first and second rotation each add $1/month, capped at the second
rotation; AWS managed keys carry no storage charge.</cite>

**The arithmetic against a $25 Base plan:** a per-tenant customer-managed key is
$1/month, rising to $3/month once rotation is enabled — **4% to 12% of the
subscription, before a single document is processed**. On a product positioned
as practically free, that is not a rounding error.

**Settled — one platform-managed CMK, per-tenant encryption context, S3 Bucket
Keys enabled.** The encryption context binds each object to its `tenant_id`, so
a key policy or IAM condition can enforce tenant scope cryptographically without
a key per tenant. <cite index="31-1">S3 Bucket Keys can cut KMS request volume
for SSE-KMS workloads by up to 99%</cite>, which matters because request charges
scale with document volume while key storage does not.

**Per-tenant CMKs become an Enterprise and regulated-stack feature**, where $1–3
a month is trivial against a negotiated price and where the buyer is asking for
exactly that separation. The Terraform module takes key strategy as a
parameter, so this is a variable rather than a fork.

---

## 6. Multi-region and data residency

**Launch with two regions. Build region as a variable from day one.**

| Market | Region | Status |
|---|---|---|
| USA | `us-east-2` | Launch |
| EU + UK | `eu-central-1` | Launch |
| Singapore | `ap-southeast-1` | On demand |
| UAE / Dubai | `me-central-1` | On demand — opt-in region, enable at account level |
| Brazil + Argentina | `sa-east-1` | On demand |

`us-east-2` rather than `us-east-1`: it is where the account already operates,
marginally cheaper, and avoids Virginia's well-known incident concentration.
Nothing in the design prefers Virginia.

**There is no AWS region in Argentina.** Buenos Aires has a Local Zone — single-
zone edge compute that does not run Aurora Serverless v2. Argentine tenants are
served from São Paulo. Chile is announced for end of 2026 and may change this.

**UK is covered by `eu-central-1`.** The UK operates its own regime — UK GDPR
plus DPA 2018 as amended by the Data (Use and Access) Act 2025 — but the
Commission renewed both adequacy decisions on 19 December 2025, running to
27 December 2031, so EEA–UK flows need no additional safeguards. Frankfurt is a
lawful home for UK tenant data. **Commercial sufficiency is a separate
question:** UK financial-services procurement may demand `eu-west-2` regardless,
which is precisely why region is a variable.

### 6.1 Region selection

- **Geolocate to suggest, never to decide.** IP location is a network fact;
  residency is a legal choice. A German firm signing up from Singapore must land
  in Frankfurt.
- **The tenant declares jurisdiction and confirms the region at signup.**
- **Region is immutable thereafter.** Changing it is a migration with downtime
  and re-encryption, not a settings toggle.

### 6.2 Global control plane, regional data planes

Something must know where a tenant lives before it can route them. Keep that
layer as small as it can possibly be:

| Plane | Holds |
|---|---|
| Global | email → tenant → region; payment method reference |
| Regional | documents, extracted values, memos, config registry, ledger, seats, share grants |

Every byte in the global plane is a byte you must defend in a residency
conversation. Nothing goes there that can live regionally.

### 6.3 CDN — geo-restricted to the memo's own region

**Settled — Option A.** Cached viewer delivery (*Share* §4) uses a CDN
distribution scoped to the memo's own region. An EU tenant's memo caches only at
EU edges; it never replicates to a US edge to serve a US viewer.

Cost: a viewer outside the region pays one cross-region fetch on first open,
then hits a regional edge. Benefit: residency holds absolutely, with no consent
carve-out.

**The rejected alternative matters enough to record.** Global edge caching would
have been faster and would have required the tenant to consent, inside a send
dialog, to moving data out of the region they deliberately chose. That is where
consent goes unread, and the failure would surface in a customer's audit rather
than in our monitoring.

### 6.4 Per-region cost

**Lower than it looks, because Data API removes the VPC requirement.** Lambda
never needs VPC access to the database, so there are no NAT gateways — normally
the dominant per-region idle cost. With 0-ACU Aurora, idle compute is near zero.
What remains per region is a KMS key, CloudWatch, S3 and Route 53 — low tens of
dollars.

**The real cost is operational:** every additional region is another deploy,
another set of alarms, another schema migration, another on-call surface. That
is the argument for two at launch and more on demand, not the money.

---

## 7. Terraform structure

Per RoE 16: `c:\terraform\terraform_package`, Terraform and Docker.

```
modules/
  network/         vpc, subnets, endpoints
  data/            aurora cluster, data api, secrets
  storage/         s3, lifecycle, kms strategy
  compute/         lambda, step functions, api gateway
  identity/        cognito or equivalent (component 9)
  observability/   logs, metrics, alarms

environments/
  dev/             scope = shared,    region = us-east-2
  prod-us/         scope = shared,    region = us-east-2
  prod-eu/         scope = shared,    region = eu-central-1
  regulated/       scope = dedicated, region = <tenant>  ← designed, not applied
```

**The regulated stack is the same modules at a different scope**, not a second
codebase. Scope is a variable driving: dedicated cluster, dedicated bucket,
per-tenant CMK, and optionally a separate AWS account and region.

**Region is the second variable**, alongside scope. Every module takes both.
Adding Singapore is a new environment directory, not a code change.

**Deliberate consequence:** every module must be parameterised for
single-tenant from the start, even while only the shared scope is applied.
A module that hard-codes multi-tenancy is the thing that turns the regulated
stack from a `terraform apply` into a project.

---

## 8. Regulated stack — designed, not built

What changes when scope is `dedicated`:

| Dimension | Shared | Dedicated |
|---|---|---|
| Aurora cluster | One, all tenants | One per tenant |
| S3 | One bucket, prefixed | One bucket |
| KMS | Platform CMK + context | Per-tenant CMK |
| AWS account | Shared | Optionally separate |
| Region | Single | Tenant-selected |

What does **not** change: application code, schema, config registry semantics,
pipeline, billing. If any of those need to differ, the parameterisation has
failed and it will be discovered at the worst moment.

---

## 9. Observability

- **Token counter per inference call** (*Wallet* §2), tagged with tenant, event
  type and config revision. This is the only instrument that tells you whether
  $0.25 and $1.00 hold. It is not optional and it is not a phase 2 item.
- **Ledger reconciliation** — sum of `ledger_entry` against granted bucket
  amounts, alarmed on divergence.
- **Per-tenant cost attribution** — inference, storage, KMS requests, so an
  unprofitable tenant is visible before the invoice.
- **Auto-pause monitoring** — alarm if the cluster stops pausing, which is the
  signal that something has taken a persistent connection.

---

## 10. Open

1. **~~Aurora engine version~~ — CLOSED.** `us-east-2` offers up to
   `8.0.mysql_aurora.3.12.0`; no upgrade needed, no RDS Proxy present.
   Empirical Data API and auto-pause confirmation happens at dev cluster
   creation (§3).
2. **~~Region and data residency~~ — CLOSED.** Two at launch, `us-east-2` and
   `eu-central-1`; three more on demand; region is a Terraform variable (§6).
3. **Separate AWS account for the SaaS product** — recommended, to keep blast
   radius and billing distinct from eBL. Not decided.
4. **Staging lifecycle period** (§4) — carried from *Pipeline* §10.
5. **Identity provider** (§7) — component 9.
6. **`eu-west-2` for UK procurement** (§6) — a sales question, not a legal one.
   Adding it is a new environment directory when a UK buyer requires it.

Item 3 is the one that needs a decision before the first `terraform apply`.
