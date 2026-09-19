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
