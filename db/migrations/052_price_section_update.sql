-- 052_price_section_update.sql
--
-- A price for updating ONE section of a memo (31 October 2026): 50 cents,
-- the standard price, decided by sperry@ebl-finance.com. An Update of every
-- section stays memo_generated, a whole generation ($1.00).
--
--   meter_price   memo_section_updated   50
--
-- PRICES ARE DATA. Until this row exists the API refuses a one-section
-- Update as unpriced rather than charging nothing (wallet.Unpriced).
--
-- A failed one-section Update is refunded as a generation is
-- (wallet.refund_generation), as memo_section_updated_refund. A refund has
-- no meter_price row: it gives back what the charge's own ledger entry
-- says was paid.
--
-- Read on dev before this was written:
--
--   SELECT event_type, unit_cents FROM meter_price WHERE tenant_id IS NULL
--     -> document_filed 25, memo_generated 100, config_review 100,
--        share_overage_base 100, share_overage_business 25,
--        share_overage_solo 100
--
-- GUARDED, NOT UPSERTED, as 050: a second run writes nothing.

INSERT INTO meter_price (tenant_id, event_type, unit_cents)
SELECT NULL, 'memo_section_updated', 50
FROM DUAL
WHERE NOT EXISTS (
  SELECT 1 FROM meter_price
  WHERE tenant_id IS NULL AND event_type = 'memo_section_updated'
);

-- Verification
--
--   SELECT event_type, unit_cents FROM meter_price
--    WHERE tenant_id IS NULL AND event_type = 'memo_section_updated'
--
-- Expect one row: memo_section_updated 50.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '052_price_section_update.sql'
--
-- Expect one row.
--
-- DEPLOY ORDER. This migration, then the layer (build-layer.ps1) and
-- terraform apply for the api, composition and composition-failed
-- functions, then merge for the screen. A screen offering one section
-- before the API knows the price would be refused as unpriced, not
-- mischarged.
--
-- NO SEMICOLON ENDS A COMMENT LINE HERE. db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
