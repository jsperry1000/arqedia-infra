-- 033_plan_limits.sql
--
-- The three limits the pricing page sells and the database has never held,
-- and the plan table filled from config/plans.json.
-- PROPOSED, and not applied.
--
-- WHY. site/pricing/index.html advertises six things per plan. The plan table
-- holds three of them:
--
--   Seats                                 2 / 5      plan.seat_count
--   Monthly credit                   $5 / $15        plan.monthly_credit_cents
--   Shared memoranda per month   5 / unlimited       plan.share_allowance
--   Field sets per document type      3 / 5          NOWHERE
--   Sections per template           12 / 25          NOWHERE
--   Daily classification allowance   $5 / $15        NOWHERE
--
-- The last three are sold and are not recorded anywhere a machine can read.
-- The nearest constants in the code are not per plan and do not match:
--
--   lambda/api/app.py:1632      _REWRITE_MAX_SECTIONS = 50
--   lambda/proposer/app.py:69   _MAX_SECTIONS = 40
--
-- So a Base tenant is advertised twelve sections and bounded at forty or
-- fifty, whichever path they reach. This migration does not close that -
-- nothing here enforces anything. It gives the numbers a home, so that the
-- app and the marketing page can be made to read one source (18.5 / 11.3
-- stage 2) instead of one table and one hand-written HTML file.
--
-- 032 IS APPLIED. Checked before writing this, not assumed:
--
--   SELECT filename, applied_at FROM schema_migration
--    WHERE filename = '032_document_source_folder.sql'
--   -> 032_document_source_folder.sql | 2026-09-22 17:36:55
--
--   SELECT plan_key, name, seat_count, monthly_price_cents,
--          monthly_credit_cents, share_allowance, active FROM plan
--   -> base     | Base           | 2 | 2500 |  500 |    5 | 1
--   -> business | Small Business | 5 | 6500 | 1500 | NULL | 1
--
-- ADDITIVE. Three nullable columns, and an upsert of the two rows that are
-- already there. Nothing is dropped, no row is deleted, and every value the
-- upsert writes is the value the row already holds except for the three new
-- columns, which are NULL until it runs.

-- --- the three limits --------------------------------------------------------
--
-- NULLABLE, AND NULL IS NOT ZERO. A plan that has not been given a limit has
-- not been given one; a plan limited to zero sections could render no
-- memorandum at all. Anything reading these has to tell the two apart, which a
-- NOT NULL DEFAULT 0 would make impossible.
--
-- daily_classification_cents IS CENTS, like every other money column here, and
-- like meter_price.unit_cents. The pricing page prints $5.00 and $15.00.
--
-- NOT ENFORCED BY THIS MIGRATION OR BY ANY CODE ON THIS BRANCH. They are
-- recorded, and recording them is what lets the two surfaces agree about what
-- was sold. Enforcing them is a separate decision with a separate refusal
-- message per limit, and it is not taken here.

ALTER TABLE plan
  ADD COLUMN field_sets_per_type        INT NULL AFTER share_allowance,
  ADD COLUMN sections_per_template      INT NULL AFTER field_sets_per_type,
  ADD COLUMN daily_classification_cents BIGINT NULL AFTER sections_per_template;

-- --- the plans, from config/plans.json ---------------------------------------
--
-- KEYED ON plan_key, which carries uq_plan_key - so this is an upsert and not
-- an insert, and running it twice changes nothing the second time.
--
-- IT KEEPS WHAT IT DOES NOT SEND. The UPDATE clause names only the columns in
-- the VALUES list. plan_id is untouched, so subscription.plan_id keeps
-- pointing at the row it always did - rewriting that would repoint every
-- tenant's subscription at a plan they did not buy. A column added to this
-- table later is likewise not zeroed by this statement.
--
-- ENTERPRISE IS ABSENT, DELIBERATELY. config/plans.json carries it and this
-- does not, because seat_count, monthly_price_cents and monthly_credit_cents
-- are NOT NULL:
--
--   SELECT COLUMN_NAME, IS_NULLABLE FROM information_schema.COLUMNS
--    WHERE TABLE_SCHEMA='arqedia' AND TABLE_NAME='plan'
--   -> seat_count           | NO
--   -> monthly_price_cents  | NO
--   -> monthly_credit_cents | NO
--
-- A row for Enterprise could therefore only exist by inventing three numbers,
-- and a negotiated price must not be a release (CLAUDE.md, Money). It is also
-- what billing._plans() reads to decide what may be bought: a row here would
-- put Enterprise in the plan table with a made-up price and let _known_plan
-- accept it. The file is its home; stage 2 renders it from there.

INSERT INTO plan
  (plan_key, name, seat_count, monthly_price_cents, monthly_credit_cents,
   share_allowance, field_sets_per_type, sections_per_template,
   daily_classification_cents, active)
VALUES
  ('base',     'Base',           2, 2500,  500,    5, 3,  12,  500, 1),
  ('business', 'Small Business', 5, 6500, 1500, NULL, 5,  25, 1500, 1)
ON DUPLICATE KEY UPDATE
  name                      = VALUES(name),
  seat_count                = VALUES(seat_count),
  monthly_price_cents       = VALUES(monthly_price_cents),
  monthly_credit_cents      = VALUES(monthly_credit_cents),
  share_allowance           = VALUES(share_allowance),
  field_sets_per_type       = VALUES(field_sets_per_type),
  sections_per_template     = VALUES(sections_per_template),
  daily_classification_cents = VALUES(daily_classification_cents),
  active                    = VALUES(active);

-- Verification
--
--   SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
--     FROM information_schema.COLUMNS
--    WHERE TABLE_SCHEMA = 'arqedia' AND TABLE_NAME = 'plan'
--      AND COLUMN_NAME IN ('field_sets_per_type', 'sections_per_template',
--                          'daily_classification_cents')
--
-- Expect three rows, all YES:
--   field_sets_per_type        | int    | YES
--   sections_per_template      | int    | YES
--   daily_classification_cents | bigint | YES
--
--   SELECT plan_id, plan_key, name, seat_count, monthly_price_cents,
--          monthly_credit_cents, share_allowance, field_sets_per_type,
--          sections_per_template, daily_classification_cents, active
--     FROM plan ORDER BY plan_id
--
-- Expect exactly two rows, and plan_id 1 and 2 UNCHANGED:
--   1 | base     | Base           | 2 | 2500 |  500 |    5 | 3 | 12 |  500 | 1
--   2 | business | Small Business | 5 | 6500 | 1500 | NULL | 5 | 25 | 1500 | 1
--
-- plan_id is the thing to read most carefully. subscription.plan_id points at
-- it, and three tenants on dev hold plan_id 2:
--
--   SELECT plan_id, COUNT(*) FROM subscription GROUP BY plan_id  -> 2 | 3
--
-- If either id has moved, the upsert has inserted rather than updated and
-- three subscriptions now name a plan nobody bought.
--
--   SELECT COUNT(*) FROM plan WHERE plan_key = 'enterprise'
--
-- Expect 0. Enterprise is in config/plans.json and is not a row.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '033_plan_limits.sql'
--
-- Expect one row.
--
--
-- DEPLOY ORDER. This migration may be applied on its own, before or after any
-- code: nothing on this branch reads the three new columns, and seats.py's
-- change reads seat_count, which has been there since 018. The one thing that
-- must not happen is applying it while another migration is mid-flight, for
-- the ordinary reason.
--
-- IF THE VALUES IN config/plans.json CHANGE, THIS MIGRATION DOES NOT. It is a
-- record of what was true on 22 September 2026, as every migration is. A later
-- change of price is a later migration, and tests/test_plans_source.py is what
-- stops the file and the Paddle catalogue drifting apart in between.
