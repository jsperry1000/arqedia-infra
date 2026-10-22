-- 042_engagement_workspace.sql
-- PACK-01. An engagement belongs to a workspace.
--
-- Decided 22 October 2026: the engagement list is filtered to the active
-- workspace by a column on the engagement, not derived from what it holds.
-- An engagement is opened in a workspace and stays there; the same name in
-- two workspaces is two engagements.
--
-- APPLIED BEFORE THE CODE THAT READS IT, and safe under the code deployed
-- today, which names no workspace_id:
--
--   NOT NULL DEFAULT 0, NOT NULLABLE. The decision said nullable; it cannot
--   be. The deployed code finds-or-creates an engagement through its unique
--   key (INSERT ... ON DUPLICATE KEY, engagement_id() in the API and the
--   normalizer). A nullable column in that key lets every insert carry NULL,
--   and MySQL treats NULLs as distinct in a unique key, so one name would
--   become two rows. 0 is "in no workspace", as in migration 040.
--
--   THE OLD KEY STAYS. uq_engagement_name (tenant_id, name) is what the
--   deployed code collides on. The new key goes beside it; the old one comes
--   off in held/043, after the workspace code is deployed - until then one
--   name is one engagement across a tenant's workspaces, which is all any
--   tenant has ever had.
--
-- 040 IS HEAD. Read before writing this, not assumed:
--
--   SELECT filename FROM schema_migration ORDER BY filename DESC LIMIT 1
--   -> 040_workspace.sql
--
-- held/043 (formerly 041) is NOT pending: it sits where db/migrate.ps1 does
-- not look (it reads migrations/*.sql, not subfolders), because it must run
-- after the deploy and this must run before it. See its header.
--
-- ADDITIVE. One column, one unique key, and a backfill of the column. No row
-- is deleted, and no value already held is changed.

ALTER TABLE engagement
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  ADD UNIQUE KEY uq_engagement_workspace_name (tenant_id, workspace_id, name);

-- Every engagement into its tenant's workspace. Every tenant but 0 holds
-- exactly one today, so this is exact: an engagement's documents and memos
-- are all in it. Tenants holding several are left at 0 rather than guessed,
-- as 040 did, and there are none.
UPDATE engagement e
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = e.tenant_id
   SET e.workspace_id = w.workspace_id
 WHERE e.workspace_id = 0;


-- Verification
--
--   SELECT COUNT(*) FROM engagement WHERE workspace_id = 0 AND tenant_id <> 0
--
-- Expect 0.
--
--   SELECT COUNT(*) FROM engagement e
--     JOIN document d ON d.engagement_id = e.engagement_id
--    WHERE d.workspace_id <> e.workspace_id
--
-- Expect 0: every engagement is in the workspace of its documents. The same
-- for memo.
--
--   SHOW CREATE TABLE engagement
--
-- Expect both uq_engagement_name (tenant_id, name) and
-- uq_engagement_workspace_name (tenant_id, workspace_id, name).
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '042_engagement_workspace.sql'
--
-- Expect one row.
--
--
-- DEPLOY ORDER. THIS FIRST, before the code on feature/pack01-workspace-ui:
-- that code reads and writes engagement.workspace_id by name, and every
-- engagement route fails without it.
--
-- NO SEMICOLON ENDS A COMMENT LINE HERE. db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
