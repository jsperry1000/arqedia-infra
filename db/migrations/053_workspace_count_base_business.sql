-- 053_workspace_count_base_business.sql
--
-- How many workspaces a plan holds, changed 5 November 2026 by
-- sperry@ebl-finance.com: Base 1 -> 2, Small Business 5 -> 4. Solo stays 1
-- (migration 050). Enterprise is tenant.workspace_limit, negotiated, and is
-- not touched.
--
-- Read on dev before this was written:
--
--   SELECT plan_key, workspace_count FROM plan
--     -> base 1, business 5, solo 1
--
--   Workspaces held, by tenant (plan, held): 0 base 2 (exempt in code - its
--   workspaces are offerings), 5 business 3, 13 base 1.
--
-- SO NOBODY IS LEFT OVER THE NEW LIMIT. Lowering Business to 4 refuses a
-- fifth workspace; it deletes nothing, and the only Business tenant holds 3.
--
-- An UPDATE of two rows, as 050 changed Base's seats. Running it again
-- writes the same numbers.

UPDATE plan SET workspace_count = 2 WHERE plan_key = 'base';

UPDATE plan SET workspace_count = 4 WHERE plan_key = 'business';

-- Verification
--
--   SELECT plan_key, workspace_count FROM plan ORDER BY plan_key
--
-- Expect: base 2, business 4, solo 1.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '053_workspace_count_base_business.sql'
--
-- Expect one row.
--
-- No semicolon ends a comment line here: db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
