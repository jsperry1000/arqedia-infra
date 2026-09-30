-- 035_config_review_price.sql
--
-- The price of an AI Review session (REV-01): $1.00, the standard price for
-- every tenant. Decided 30 September 2026.
--
-- WHY A ROW AND NOT A CONSTANT. Prices are data (CLAUDE.md, Money). An event
-- with no row refuses rather than charging nothing, so until this row exists
-- the review's first accept is refused as Unpriced - which is the safe
-- failure, and is why this may land before or after the code.
--
-- ADDITIVE. One row in one table. Nothing is altered or deleted.
--
-- GUARDED, NOT UPSERTED. uq_tenant_event is (tenant_id, event_type), and
-- MySQL does not treat two NULLs as equal in a unique key, so a plain INSERT
-- run twice would write two standard prices for one event. unit_price() would
-- then pick either. The NOT EXISTS makes a second run write nothing.

INSERT INTO meter_price (tenant_id, event_type, unit_cents)
SELECT NULL, 'config_review', 100
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1 FROM meter_price
  WHERE tenant_id IS NULL AND event_type = 'config_review'
);

-- Verification
--
--   SELECT tenant_id, event_type, unit_cents FROM meter_price
--    WHERE event_type = 'config_review'
--
-- Expect exactly one row: NULL | config_review | 100.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '035_config_review_price.sql'
--
-- Expect one row.
--
--
-- DEPLOY ORDER. Either order is safe. Without this row the reviewer's first
-- accept is refused as unpriced and nothing is written or charged; with it and
-- no code, nothing reads it.
