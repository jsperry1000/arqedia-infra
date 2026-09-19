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
- **Front-end configuration.** `ui/src/config.ts` carries the Cognito pool ids,
  and since 19 September the **Paddle client-side token and environment** as
  well. Both are sandbox-bound: a `test_` token works only against Paddle's
  sandbox and a `live_` one only against live, and `paddleEnvironment` names
  which. One bundle cannot serve both stacks, and the build compiles these
  values into `web/`, so **the committed bundle carries a sandbox credential**.
  It is a credential Paddle documents as safe to publish - client-side tokens
  "have limited access to the data in your system" - so this is an environment
  problem, not a secret leak. **Before live, this file must come from the build
  rather than from git**: an environment variable read at build time, or a
  configuration fetched at start-up. Shipping today's bundle against a live
  Paddle account would open a sandbox checkout at real prices and collect
  nothing.

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
