-- 050_plan_solo.sql
--
-- A one-seat plan, Solo, and Base from two seats to three (28 October 2026).
-- PROPOSED, and not applied.
--
--   plan              solo   new row: Solo, 1 seat, $8.00 a month, $8.00
--                            monthly credit, 5 shares a month, 5 sections per
--                            template, 1 workspace
--   plan.seat_count   base   2 -> 3
--   meter_price       share_overage_solo   100   ($1.00, as Base)
--
-- config/plans.json is the published copy of every value here, and
-- tests/test_plans_source.py compares the two. The Paddle price is
-- "ARQEDIA Solo" in config/paddle/sandbox.json, $8.00 monthly, made in the
-- sandbox on 28 October 2026.
--
-- Read on dev before this was written:
--
--   SELECT plan_key, seat_count FROM plan   -> base 2, business 5
--   SELECT plan, COUNT(*) FROM tenant GROUP BY plan
--                                           -> base 1 (tenant 0), business 1
--
-- BASE TO THREE SEATS ONLY RAISES A LIMIT: no tenant holds more than it
-- did, and nothing is deleted. The old value is recorded here.
--
-- SOLO'S UNUSED COLUMNS ARE NULL. field_sets_per_type and
-- daily_classification_cents are no longer sold (config/plans.json, the two
-- dropped notes), so a new plan is given neither.
--
-- ADMIN / MEMBER MANAGEMENT is not a column. The pricing page and the app
-- show No on a plan of one seat and Yes otherwise: with one seat there is
-- nobody to invite, and seats.seats_bought already refuses the invitation.
--
-- GUARDED, NOT UPSERTED, as 036: a second run writes nothing.

INSERT INTO plan (plan_key, name, seat_count, monthly_price_cents,
                  monthly_credit_cents, share_allowance, sections_per_template,
                  workspace_count, active)
SELECT 'solo', 'Solo', 1, 800, 800, 5, 5, 1, 1
FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM plan WHERE plan_key = 'solo');

UPDATE plan SET seat_count = 3 WHERE plan_key = 'base';

INSERT INTO meter_price (tenant_id, event_type, unit_cents)
SELECT NULL, 'share_overage_solo', 100
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1 FROM meter_price
  WHERE tenant_id IS NULL AND event_type = 'share_overage_solo'
);

-- Verification
--
--   SELECT plan_key, name, seat_count, monthly_price_cents,
--          monthly_credit_cents, share_allowance, sections_per_template,
--          workspace_count, active FROM plan ORDER BY monthly_price_cents
--
-- Expect three rows: solo Solo 1 800 800 5 5 1 1, base Base 3 2500 2500 10
-- 12 1 1, business Small Business 5 6500 6500 25 25 5 1.
--
--   SELECT event_type, unit_cents FROM meter_price
--    WHERE tenant_id IS NULL AND event_type LIKE 'share_overage_%'
--
-- Expect three rows: share_overage_base 100, share_overage_business 25,
-- share_overage_solo 100.
--
--   SELECT filename FROM schema_migration WHERE filename = '050_plan_solo.sql'
--
-- Expect one row.
--
-- DEPLOY ORDER. Merge, then terraform apply (PADDLE_PRICE_SOLO on the API
-- and paddle-processor functions), then this migration straight after. The
-- app lists plans from this table, so the row must not arrive before the
-- functions know Solo's price. In the minutes between, a Solo checkout from
-- the pricing page is refused by billing._known_plan, not mischarged.
--
-- NO SEMICOLON ENDS A COMMENT LINE HERE. db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
