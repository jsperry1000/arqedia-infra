# ARQEDIA — Backlog Item

## ENV-01 · There is one environment, and three things will not follow the variable

| | |
|---|---|
| Status | Parked. Not urgent, not optional |
| Priority | Before the first real tenant. Nothing in the UX branches touches it |
| Type | Terraform, CI, migrations, front-end config |
| Raised | 13 September 2026 |

---

### Where it stands

`main.tf:2` sets `name_prefix = "arqedia-${var.environment}"`, and every resource
in every `.tf` file derives its name from it. The separation is designed in.
Setting `environment = "prod"` builds a complete parallel stack — VPC, Aurora,
buckets, Cognito pool, CloudFront distribution — and costs nothing to have kept.

Today there is one stack, `arqedia-dev`, in account 667523685221, `us-east-2`.
Calling it dev names an intention, not a separation: there is no second place
for a change to be wrong in first.

---

### Unread, and it decides the shape of the work

- `versions.tf:4` opens `backend "s3"`. The state key was not read. A fixed key
  means applying with `environment = "prod"` overwrites the dev state file, and
  Terraform then believes the dev stack does not exist.
- `terraform workspace list` was not run. Workspaces solve the same problem a
  different way.

Read both before anything else here.

---

### Three things that will not follow the variable

- **The deploy workflow.** `.github/workflows/deploy-frontend.yml` hard-codes
  `BUCKET` and `DISTRIBUTION` as literals. A prod deploy needs its own workflow
  or those lifted into variables.
- **Migrations.** Applied by hand against whichever ARN is in the command.
  Nothing in the repository records which environment received which migration.
  Migration 013 (`tenant.brand_light`) was applied to dev only — that is
  recorded here and nowhere else.
- **Front-end configuration.** `ui/src/config.ts` carries the Cognito pool ids.
  One bundle cannot serve both stacks.

---

### The cheap half of this, worth doing whenever it is opened

A `docs/migrations.md` recording each migration, where it was applied, and when.
It costs nothing now and is expensive to reconstruct later.

---

### Not in scope

The stack itself, which is working. This item separates environments; it changes
no resource.

---

### Read, 26 October 2026 — Claude Code report (Prompt 1, ENV-01)

Read in full: `versions.tf`, `main.tf`, `variables.tf`, `providers.tf`,
`db/migrate.ps1`. Queried the live dev `schema_migration` table directly. Other
`.tf` files were searched for name attributes, not read in full — the collision
list below rests on that search, not a full read of each file.

**1. Backend key.** `versions.tf:6`: `key = "arqedia/us-east-2/terraform.tfstate"`,
bucket `arqedia-tfstate-667523685221`, workspace `default`. The key is fixed,
not parameterised by environment. Applying with `environment = "prod"` from
this directory would write to dev's state and plan to rename every
`arqedia-dev-*` resource to `arqedia-prod-*` — for most resources, a
destroy-and-recreate. It would turn dev into prod, not add a second stack.

**2. What collides in one account.** Most names carry `${local.name_prefix}-…`
and do not collide (Lambdas, IAM roles, secrets, SQS, S3, Aurora, DynamoDB,
KMS, log groups, API Gateway, Cognito, the layer, EventBridge, the VPC,
CloudFront OACs and function). Three things do collide:

| Resource | Why |
|---|---|
| `aws_iam_openid_connect_provider.github` (`ci.tf:7`) | One account can hold only one provider for `token.actions.githubusercontent.com` |
| CloudFront aliases `app.`, `admin.`, `arqedia.com`, `www.` (`frontend.tf:47`, `admin_frontend.tf:51`, `site.tf:64`) | A hostname sits on one distribution only; the hosts are fixed locals in `dns.tf:19-30` |
| `aws_route53_zone.root` (`arqedia.com`) | Not refused — AWS creates a second hosted zone with the same name, but the registrar points at dev's zone, so prod's records would never be served |

Shared rather than colliding (made outside Terraform or only read by it): SES
identity `arqedia.com`, configuration set `my-first-configuration-set`
(`share.tf:177`), SNS topic `ses-events`.

Hard-coded to dev outside Terraform: the three deploy workflows (bucket/role
defaults), `db/migrate.ps1:4`, `q.ps1:10`, `db/rerun_extraction.py:31,35` (dev
cluster ARN and review bucket), `ui/src/config.ts:60-62` (pool, client, API ID).

**3. Variables.** `environment` (default `dev`) feeds only `name_prefix`.
`aws_region`, `extraction_model_id`, `composition_model_id` are used. `scope`
is declared and never used. Fixed values that would need to vary: the backend
key; `root_domain` and every `dns.tf` host (locals, not variables);
`paddle_api_base = "https://sandbox-api.paddle.com"` and the hard-wired
`config/paddle/sandbox.json` (`paddle.tf`); `ses_configuration_set`; the CI
trust condition's `refs/heads/main` (`ci.tf:145`). Account ID 667523685221 is
also fixed, in the provider's `allowed_account_ids`.

**4. schema_migration.** Two columns: `filename varchar(255)` (primary key),
`applied_at datetime`. Dev holds 46 rows, 001 (26 Aug) to 048 (23 Oct); no 003,
no 041. No environment or cluster column — it cannot tell dev from prod by
itself. The only separation is that each cluster holds its own copy of the
table. `migrate.ps1` defaults to the dev cluster, so running it without
`-Cluster` applies to dev regardless of intent.

**5. Smallest changes — both paths, no preference stated.**

*A second environment beside dev:* a state key per environment (workspaces,
or `-backend-config="key=…"` at init); hostnames derived from environment
(which environment keeps `app.arqedia.com` is a decision for the owner); the
OIDC provider created once, read by the other stack (`count`, or a data
source); Paddle base URL and catalogue file chosen by environment, with a
`config/paddle/live.json`; workflows, `migrate.ps1`, `q.ps1`, `config.ts`
taking environment as a parameter.

*The same stack re-pointed (dev becomes prod):* one variable choosing Paddle
sandbox or live (`paddle_api_base` and catalogue file); live values in the
existing `arqedia-dev/paddle/*` secrets, plus a live webhook destination;
`ui/.env` changed to a `live_` token with `production`, web rebuilt. Names,
state, the backend, and `schema_migration` stay exactly as they are. Dev's
existing tenants and their sandbox subscription IDs would then sit in what has
become the production database.

No branch, no commit. This was a read.
