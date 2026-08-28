-- 004_tenant_plan_and_branding.sql
-- Plan gates branding: Base takes ARQEDIA's, Business and Enterprise may set
-- their own, Enterprise may remove the ARQEDIA footer.
--
-- Component 8 specifies plans as rows rather than an enum, so this column is
-- the interim: a plan key on the tenant, replaced by a foreign key when the
-- plan table exists. Values are constrained by the application, not the
-- column, so adding a plan later needs no migration.

ALTER TABLE tenant
  ADD COLUMN plan VARCHAR(32) NOT NULL DEFAULT 'base' AFTER region,
  ADD COLUMN brand_logo_key VARCHAR(1024) NULL AFTER plan,
  ADD COLUMN brand_deep VARCHAR(9) NULL AFTER brand_logo_key,
  ADD COLUMN brand_mid VARCHAR(9) NULL AFTER brand_deep,
  ADD COLUMN brand_highlight VARCHAR(9) NULL AFTER brand_mid;
