-- 046_workspace_limit.sql
--
-- How many workspaces a plan holds (PACK-01 settled 3, PACK-02, settled
-- 23 October 2026): Base 1, Small Business 5, Enterprise negotiated.
--
-- 045 IS APPLIED, read before writing this:
--
--   SELECT filename, applied_at FROM schema_migration ORDER BY applied_at DESC
--   -> 045_seat_workspace.sql | 2026-10-23 13:56:53
--
-- ON THE DAY THIS IS WRITTEN NO TENANT HOLDS MORE THAN ITS PLAN ALLOWS
-- (tenant: plan, workspaces): 1 base 1, 2 business 2, 5 business 4, 9 base
-- trial 1, 10 base 1. Tenant 0 holds 2 and is exempt in code - its
-- workspaces are offerings. So nothing is deleted, and nothing needs to be.
--
-- ADDITIVE. Two nullable columns and two updates of a column that did not
-- exist before. NULL IS NOT ZERO: a limit not set is no limit, which is what
-- Enterprise has until one is negotiated.

-- --- per plan ----------------------------------------------------------------
--
-- Read through subscription.plan_id, as seat_count is, and through
-- tenant.plan on a trial. Enterprise has no plan row (config/plans.json says
-- why) and so is not here.

ALTER TABLE plan ADD COLUMN workspace_count INT NULL;

UPDATE plan SET workspace_count = 1 WHERE plan_key = 'base';

UPDATE plan SET workspace_count = 5 WHERE plan_key = 'business';

-- --- per tenant, for Enterprise ---------------------------------------------
--
-- The negotiated number, set by hand when it is agreed. Read only when the
-- tenant is on Enterprise (tenant.plan = 'enterprise'). NULL there means no
-- limit until one is set. On any other plan it is ignored: the plan decides.

ALTER TABLE tenant ADD COLUMN workspace_limit INT NULL;
