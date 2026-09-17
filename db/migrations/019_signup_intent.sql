-- 019_signup_intent.sql
--
-- What somebody came to do when they signed up, and which plan they chose if
-- they came to subscribe. Decision record, amendment of 17 September 2026.
-- PROPOSED.
--
-- Additive. Five nullable columns with no default and no backfill. Every
-- existing row stays valid and reads NULL, which is true: nobody was asked.
--
-- Values are constrained by the application, not the column, as tenant.plan
-- is:
--   intent / signup_intent  'trial' or 'subscribe'
--   plan / signup_plan      a plan.plan_key ('base', 'business')

-- --- pending_signup --------------------------------------------------------
--
-- Held from begin to verify, so a code opened on another device still knows
-- the plan chosen on the pricing page. The browser that verifies is not
-- trusted to remember it.

ALTER TABLE pending_signup
  ADD COLUMN plan   VARCHAR(32) NULL AFTER pack,
  ADD COLUMN intent VARCHAR(16) NULL AFTER plan;

-- --- tenant ----------------------------------------------------------------
--
-- signup_plan and signup_intent are copied from pending_signup at verify and
-- record what was asked for. They are not the plan: subscription.plan_id is,
-- and tenant.plan stays its copy (CLAUDE.md, Money).
--
-- checkout_offered_at is set when the first-sign-in checkout transaction is
-- created, so a subscribe signup is offered checkout once and not on every
-- sign-in after.

ALTER TABLE tenant
  ADD COLUMN signup_plan         VARCHAR(32) NULL AFTER signup_ip,
  ADD COLUMN signup_intent       VARCHAR(16) NULL AFTER signup_plan,
  ADD COLUMN checkout_offered_at DATETIME    NULL AFTER signup_intent;


-- Verification
--
--   SHOW COLUMNS FROM pending_signup WHERE Field IN ('plan', 'intent')
--
-- Expect two rows: plan varchar(32), intent varchar(16); both Null YES,
-- Default NULL.
--
--   SHOW COLUMNS FROM tenant
--    WHERE Field IN ('signup_plan', 'signup_intent', 'checkout_offered_at')
--
-- Expect three rows: signup_plan varchar(32), signup_intent varchar(16),
-- checkout_offered_at datetime; all Null YES, Default NULL.
--
--   SELECT COUNT(*) FROM tenant
--    WHERE signup_plan IS NOT NULL OR signup_intent IS NOT NULL
--       OR checkout_offered_at IS NOT NULL
--
-- Expect 0.
--
--   SELECT filename FROM schema_migration WHERE filename = '019_signup_intent.sql'
--
-- Expect one row.
