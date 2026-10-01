-- 036_share_allowance.sql
--
-- Sharing a memorandum: the allowance each plan includes, and what a share
-- past it costs. Decided 30 September - 1 October 2026 (share-recipient).
-- PROPOSED, and not applied.
--
-- WHAT CHANGES
--
--   plan.share_allowance   base       5    -> 10
--                          business   NULL -> 25
--
--   meter_price            share_overage_base       100   ($1.00)
--                          share_overage_business    25   ($0.25)
--
-- THIS OVERWRITES TWO VALUES, and says so. Every other migration on the plan
-- table has been additive; this one replaces 5 and NULL because the decision
-- replaces them. The old values are recorded here, which is where anybody
-- looking for them will look:
--
--   SELECT plan_key, share_allowance FROM plan     (read 30 September 2026)
--   -> base     | 5
--   -> business | NULL
--
-- BUSINESS IS NO LONGER UNLIMITED. NULL still means unlimited in the column
-- (migration 018) and the code still reads it that way; Business simply stops
-- being NULL. It is 25 a month, and a share past 25 is charged, not refused.
--
-- A TRIAL HAS NO ROW. A tenant on trial gets Base's allowance - 10 - once, for
-- the whole trial, whatever plan it signed up for. That rule is in
-- lambda/api/share.py, which reads Base's row for it; there is no trial plan
-- and this migration does not make one.
--
-- WHY TWO meter_price ROWS AND NOT A PLAN COLUMN. The overage price depends on
-- the plan, and meter_price has no plan. Two event types keep the table's
-- shape and wallet.unit_price() exactly as they are: the share code chooses
-- which event to charge from the plan, and a negotiated Enterprise price is
-- still a tenant row against either event, as for every other price. A trial
-- is charged as share_overage_base.
--
-- GUARDED, NOT UPSERTED, for the reason 035 gives: uq_tenant_event is
-- (tenant_id, event_type) and MySQL does not treat two NULLs as equal, so a
-- plain INSERT run twice would write two standard prices.

UPDATE plan SET share_allowance = 10 WHERE plan_key = 'base';
UPDATE plan SET share_allowance = 25 WHERE plan_key = 'business';

INSERT INTO meter_price (tenant_id, event_type, unit_cents)
SELECT NULL, 'share_overage_base', 100
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1 FROM meter_price
  WHERE tenant_id IS NULL AND event_type = 'share_overage_base'
);

INSERT INTO meter_price (tenant_id, event_type, unit_cents)
SELECT NULL, 'share_overage_business', 25
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1 FROM meter_price
  WHERE tenant_id IS NULL AND event_type = 'share_overage_business'
);

-- Verification
--
--   SELECT plan_key, share_allowance FROM plan ORDER BY plan_id
--
-- Expect: base | 10, business | 25.
--
--   SELECT tenant_id, event_type, unit_cents FROM meter_price
--    WHERE event_type LIKE 'share_overage_%' ORDER BY event_type
--
-- Expect exactly two rows: NULL | share_overage_base | 100 and
-- NULL | share_overage_business | 25.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '036_share_allowance.sql'
--
-- Expect one row.
--
--
-- DEPLOY ORDER. Either order is safe. Without the meter_price rows a share
-- past the allowance is refused as unpriced and nothing is charged or sent.
-- Without the plan values, Base allows 5 and Business is unlimited, as today.
--
-- NO SEMICOLON ENDS A COMMENT LINE HERE. db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
