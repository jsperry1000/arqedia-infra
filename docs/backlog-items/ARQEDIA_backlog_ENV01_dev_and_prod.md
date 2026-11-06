# ARQEDIA — Backlog Item

## ENV-01 · There is one environment, and three things will not follow the variable

| | |
|---|---|
| Status | Parked. Not urgent, not optional |
| Priority | Before the first real tenant. Nothing in the UX branches touches it |
| Type | Terraform, CI, migrations, front-end config |
| Raised | 13 September 2026 |
| Revised | 28 September 2026 — a copy of this item under `docs/HANDOFF/` was an older subset of this file and was removed in `a599d23` ("remove HANDOFF duplicates of backlog items"); this is the copy that stands. Cross-reference to BLD-01 added under the 16 September note |

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
- **Front-end configuration.** `ui/src/config.ts` carries the Cognito pool ids
  and the API URL as literals. One bundle cannot serve both stacks.

  **The Paddle half of this is closed (19 September).** The client-side token
  and its environment now come from `VITE_PADDLE_TOKEN` and
  `VITE_PADDLE_ENVIRONMENT`, read at build time from `ui/.env`, which is
  git-ignored; `ui/.env.example` is committed and holds no real token. Neither
  is defaulted: `vite.config.ts` refuses to emit a bundle when either is
  missing, and refuses a **mismatched pair** - `sandbox` takes a `test_` token
  and `production` takes a `live_` one, per Paddle's documented format. Both
  refusals were exercised, not assumed. `config.ts` repeats the same checks as
  a second line of defence for a bundle built some other way.

  **What that does not fix, and why this item stays open.** `web/` is committed
  build output, so whatever token the last build used is in git inside
  `web/assets/`. Moving the value out of `config.ts` does not take it out of
  the repository - it means the *live* token never has to be committed to
  produce a live build. The Cognito ids and the API URL are untouched and
  still wrong for a second stack.

---

### The cheap half of this, worth doing whenever it is opened

A `docs/migrations.md` recording each migration, where it was applied, and when.
It costs nothing now and is expensive to reconstruct later.

---

### Not in scope

The stack itself, which is working. This item separates environments; it changes
no resource.

---

### Note — 16 September 2026: bytecode in Lambda zips

`archive_file` zips everything under `source_dir`, including `__pycache__`.
The blocks for `signup`, `api`, `composition`, `extraction`, `normalizer`,
`proposer`, `render` and `collector` set no `excludes`. The deployed
`arqedia-dev-signup` zip carried `__pycache__/app.cpython-314.pyc` beside
`app.py`. Fix: `excludes = ["__pycache__"]` on each block. The two Paddle blocks
already have it.

`lambda/shared` is not an `archive_file`: it reaches the Lambdas through the
`docprocessing` layer built by `build-layer.ps1`. Whether that script zips
`__pycache__` has not been read.

**Added 28 September 2026.** This defect is BLD-01
(`ARQEDIA_backlog_BLD01_pycache_in_three_lambda_zips.md`), raised 19
September, which carries the fix. There are twelve `archive_file` blocks, not
the ten named here: `reconcile.tf` has `excludes`, and `admin_api.tf`
(`lambda/admin`) does not. Not fixed on 28 September.

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

---

### Decided, 6 November 2026 — the same stack, re-pointed

Live Paddle runs on the existing `arqedia-dev` stack. There is no second stack.
This is the second path of the 26 October read, §5.

What that means, from the read:

- Names, state, the backend key and `schema_migration` stay as they are. There
  is one cluster, so the per-environment migrations question (go-live list,
  stage 1) does not arise; `schema_migration` is the record.
- What changes: one variable choosing Paddle sandbox or live
  (`paddle_api_base` and the catalogue file), live values in the existing
  `arqedia-dev/paddle/*` secrets, a live webhook destination, and `ui/.env`
  set to a `live_` token with `production`, with `web/` rebuilt.

Not decided, and left open by this:

- Dev's existing tenants and their sandbox subscription IDs would then sit in
  what has become the production database. What happens to them is not settled.
- After the switch there is no environment where a change can be wrong first.
- The name `arqedia-dev` stays on a production stack.
