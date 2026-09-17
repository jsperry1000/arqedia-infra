-- 020_subscription_previous_plan.sql
--
-- The plan a subscription had before its last plan change. PROPOSED.
--
-- Decision record item 16 grants the difference in monthly credit on a
-- mid-cycle upgrade, measured from the old plan. Paddle does not deliver in
-- order: subscription.updated can arrive before the transaction.completed
-- that paid for the change, and by then subscription.plan_id already shows
-- the new plan. This column keeps the old one, so the grant is the same
-- whichever event lands first.
--
-- Written only by the Paddle processor, when subscription.created or
-- .updated changes plan_id. Kept as it was when the plan does not change.
--
-- Additive. One nullable column, no default, no backfill. Every existing row
-- reads NULL, which is true: no plan change has been recorded against it.
-- No foreign key: plan_id carries one already, and this column only ever
-- holds a value copied from it.

ALTER TABLE subscription
  ADD COLUMN previous_plan_id BIGINT NULL AFTER plan_id;


-- Verification
--
--   SHOW COLUMNS FROM subscription LIKE 'previous_plan_id'
--
-- Expect one row: bigint, Null YES, Default NULL.
--
--   SELECT COUNT(*) FROM subscription WHERE previous_plan_id IS NOT NULL
--
-- Expect 0.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '020_subscription_previous_plan.sql'
--
-- Expect one row.
