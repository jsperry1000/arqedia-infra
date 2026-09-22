# ARQEDIA — Changing prices and plan limits

| | |
|---|---|
| Written | 22 September 2026 |
| Decision | Prices and limits are changed in one committed file, reviewed and deployed. Not from the staff admin page (18.13, option A) |
| Status | **Describes the process once 18.5 / 11.3 is built.** `config/plans.json`, the build check against Paddle and the new limit columns do not exist yet. Until they do, this document is the target, not the practice |

---

## What lives where

| Thing | Where it is defined | Who reads it |
|---|---|---|
| Plans: name, seats, monthly price, monthly credit, share allowance, field sets per document type, sections per template, daily classification allowance, how it starts | `config/plans.json` — **the one source** | The database (through a migration), the pricing page (at build), the app (through the database) |
| Per-use prices: $0.25 a document filed, $1.00 a memo generated | `meter_price` table | The wallet, and every quote the app shows |
| What Paddle charges for each plan | The Paddle catalogue, with its ids in `config/paddle/sandbox.json` | Paddle, at checkout and renewal |
| Enterprise | `config/plans.json`, with `null` where a number would be a price and "as contracted" where the page prints one | The pricing page and the app, shown as a column that cannot be bought |

The staff admin page **shows** plans and limits. It cannot change them: its database user reads six tables and writes nothing (16.9).

The build fails if a plan's monthly price in `config/plans.json` disagrees with its Paddle price. That check is what stops the page, the app and the bill drifting apart.

---

## Before you start: two facts about Paddle

1. **A subscriber keeps the price they signed up on.** Paddle stores the price on a subscription as a snapshot of the price at the time it was added. Changing the price later does not change what existing subscribers pay.
2. **Moving existing subscribers to a new price is a separate, deliberate act.** It means replacing the item on each subscription, and Paddle prorates the change unless told otherwise.

So every price change has a second question: **new customers only, or existing customers too?** Decide it before step 1.

---

## A. Changing a plan's price

1. **Decide:** the new price, the date it takes effect, and whether existing subscribers move.
2. **In Paddle** (sandbox first): create the new price on the plan's product. Note its price id.
3. **Branch** off main: `git switch -c price-<plan>-<date> origin/main`.
4. **Edit `config/plans.json`:** the plan's `monthly_price_cents`.
5. **Edit `config/paddle/sandbox.json`:** the plan's price id and amount, to the new Paddle price.
6. **Build and test.** The Paddle check must pass. If it fails, the two files and Paddle disagree: stop and find which.
7. **Pull request, review, squash and merge.**
8. **Deploy from main,** in `c:\terraform\arqedia`, by the named apply session:
   - run the plans migration through `db/migrate.ps1`, which updates the `plan` table from the file;
   - `terraform plan`, which should show only the Lambdas that carry Paddle price ids; read it, then apply;
   - the pricing page rebuilds and publishes itself on the merge.
9. **Check live:**
   - arqedia.com/pricing shows the new price;
   - Account → Subscription shows the new price;
   - the staff admin page shows the new price;
   - a sandbox checkout charges the new price.
10. **Existing subscribers,** if step 1 said they move: replace the item on each subscription in Paddle, with the proration you decided. This is not done by the deploy.

## B. Changing a limit

Seats, monthly credit, share allowance, field sets per document type, sections per template, daily classification allowance.

1. **Decide** the new value, and what happens to a tenant already over it. A tenant with 30 sections on a plan lowered to 25 keeps what they have and cannot add more; nothing is deleted.
2. **Branch,** edit the value in `config/plans.json`.
3. **Build and test.**
4. **Pull request, review, squash and merge.**
5. **Deploy from main:** the plans migration through `db/migrate.ps1`. No Paddle change and no `terraform apply` are needed for a limit.
6. **Check live:** the pricing page, Account → Subscription and the staff admin page show the new value, and the app enforces it, for example by refusing one section over the new limit.

## C. Changing a per-use price

$0.25 a document filed, $1.00 a memo generated.

1. **Decide** the new price and the date.
2. **Branch** and write a migration that inserts or updates the `meter_price` row. Never edit a price in the database by hand: a migration is reviewed and recorded.
3. **Update the pricing page's wording** if it states the price. The quotes in the app read `meter_price` and change by themselves.
4. **Pull request, review, merge; run the migration** from main.
5. **Check live:** the upload and generate confirm steps quote the new price before charging.

## D. Adding a plan

1. **Decide** everything in section A and B for the new plan.
2. **In Paddle:** create the product and its price.
3. **Add a row** to `config/plans.json` and the ids to `config/paddle/sandbox.json`.
4. Continue from step 6 of section A.

A plan is retired by marking it inactive in the file, never by deleting its row: existing subscriptions still point at it.

---

## Never

- Change a price in the Paddle dashboard without the same change in `config/plans.json` and `config/paddle/sandbox.json`. The build check will fail the next build, but the live bill will already be wrong.
- Change a price or limit directly in the database. The next migration run restores the file's value.
- Edit the pricing page's HTML to change a number. It is generated from the file.
- Give Enterprise a price in the file. A negotiated price must not be a release.
