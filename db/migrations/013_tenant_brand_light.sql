-- 013_tenant_brand_light.sql
-- A fourth tenant colour, for the palest weight on the rendered memorandum.
--
-- Additive only. One nullable column, no default and no backfill, so every
-- existing row stays valid and a tenant who never sets it renders as before.
--
-- The memorandum uses four weights and the tenant held three: deep for a
-- section band, mid for a sub-heading band, highlight for a table rule, and
-- nothing for the fourth-level pill, which borrowed the mid. See BR-01.
--
-- NULL is meaningful, not missing. style.palette_for reads it as "mix the mid
-- towards white", so a tenant who chose three colours still gets a light that
-- belongs to its own palette.

ALTER TABLE tenant
  ADD COLUMN brand_light VARCHAR(9) NULL AFTER brand_highlight;


-- Verification
--
--   SHOW COLUMNS FROM tenant LIKE 'brand_light'
--
-- Expect one row, varchar(9), Null YES, Default NULL.
--
--   SELECT COUNT(*) FROM tenant WHERE brand_light IS NOT NULL
--
-- Expect 0.
--
--   SELECT filename FROM schema_migration WHERE filename = '013_tenant_brand_light.sql'
--
-- Expect one row.
