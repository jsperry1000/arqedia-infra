-- 041_workspace_drafts.sql
-- PACK-01. One draft per workspace: the old single-workspace key comes off
-- the nine config tables.
--
-- NOT TO BE APPLIED UNTIL THE WORKSPACE CODE IS DEPLOYED. Order, decided 22
-- October 2026: merge feature/pack01-workspace-scope, rebuild the layer
-- (build-layer.ps1), terraform apply, confirm the deployed layer carries the
-- new registry.py and editor.py - THEN run this. db/migrate.ps1 applies every
-- pending file it finds, so it is not run for anything else in between.
--
-- WHY THE ORDER IS NOT OPTIONAL. Migration 040 kept each config table's old
-- (tenant_id, revision, key) as uq_single_workspace, because the code then
-- deployed upserts the draft by that key and names no workspace_id. Dropped
-- under that code, every editor save would insert a second row beside the
-- one it meant to update, at workspace 0 - the whole draft duplicated, one
-- edit at a time. The code on the branch above names workspace_id in every
-- write, and its upserts collide on the widened primary key instead, so
-- this key has nothing left to do except refuse a second workspace's draft.
--
-- What it refuses, until this runs: a draft is revision 0 in every
-- workspace, so two workspaces of one tenant cannot both hold one.
-- registry.open_draft reads information_schema for this index and says so in
-- words; after this runs, it no longer finds it and stops refusing.
--
-- Published revisions were never what this key protected. Their numbers
-- come from one counter per tenant (registry._next_revision), so they do not
-- repeat across a tenant's workspaces with or without it.
--
-- 040 IS HEAD. Read before writing this, not assumed:
--
--   SELECT filename FROM schema_migration ORDER BY filename DESC LIMIT 1
--   -> 040_workspace.sql
--
-- ADDITIVE IN DATA, SUBTRACTIVE IN ONE INDEX PER TABLE. No row is deleted.
-- The primary keys 040 widened are untouched and still carry every column
-- the dropped keys did, plus workspace_id.

-- --- first, anything written at workspace 0 ---------------------------------
--
-- 040's backfill, run again, as 040 said it would be. Anything the
-- previously deployed code wrote after 040 and before the new code took
-- over carries workspace 0. While the old key stands such a row cannot
-- collide with anything; once it is gone, a draft row left at 0 would sit
-- beside the same key at the tenant's workspace and be invisible to the
-- editor. So the rows are assigned while the old key still guarantees they
-- are unique, and the key comes off after.
--
-- Only tenants holding exactly one workspace, as in 040: with several,
-- which one a row belongs to is not something a statement can know.
-- Read on dev on 22 October, before this was written: no row of any of the
-- thirteen tables is at workspace 0 outside tenant 0.

UPDATE config_revision c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE config_category c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE config_document_type c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE config_schema c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE config_type_schema c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE config_field c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE config_template c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE config_section c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE config_section_field c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE document c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE extracted_value c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE memo c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

UPDATE memo_rewrite c
  JOIN (SELECT tenant_id, MIN(workspace_id) AS workspace_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) w ON w.tenant_id = c.tenant_id
   SET c.workspace_id = w.workspace_id
 WHERE c.workspace_id = 0;

-- --- and which revision each workspace is using ---------------------------
--
-- The previously deployed code selects a revision - on publish, and on
-- Revert - by writing tenant.active_revision alone, and knows nothing of
-- workspace.active_revision. A tenant that published in that window has the
-- new number on its tenant row and the old one on its workspace, and the new
-- code reads the workspace's. Found on dev on 22 October: tenant 1 published
-- revision 46, and its workspace still said 45.
--
-- The tenant row is the one that was written last, so it is copied onto the
-- workspace - for tenants holding exactly one, for the same reason as above.
-- <=> so a NULL on either side is compared rather than skipped.

UPDATE workspace w
  JOIN tenant t ON t.tenant_id = w.tenant_id
  JOIN (SELECT tenant_id FROM workspace
         GROUP BY tenant_id HAVING COUNT(*) = 1) one ON one.tenant_id = w.tenant_id
   SET w.active_revision = t.active_revision
 WHERE NOT (w.active_revision <=> t.active_revision);

-- --- then the old key ------------------------------------------------------

ALTER TABLE config_revision DROP INDEX uq_single_workspace;
ALTER TABLE config_category DROP INDEX uq_single_workspace;
ALTER TABLE config_document_type DROP INDEX uq_single_workspace;
ALTER TABLE config_schema DROP INDEX uq_single_workspace;
ALTER TABLE config_type_schema DROP INDEX uq_single_workspace;
ALTER TABLE config_field DROP INDEX uq_single_workspace;
ALTER TABLE config_template DROP INDEX uq_single_workspace;
ALTER TABLE config_section DROP INDEX uq_single_workspace;
ALTER TABLE config_section_field DROP INDEX uq_single_workspace;


-- Verification
--
--   SELECT TABLE_NAME FROM information_schema.STATISTICS
--    WHERE TABLE_SCHEMA = 'arqedia' AND INDEX_NAME = 'uq_single_workspace'
--
-- Expect none.
--
--   SELECT 'config_revision', COUNT(*) FROM config_revision
--    WHERE workspace_id = 0 AND tenant_id <> 0
--   ... and the same for the other twelve tables
--
-- Expect 0 on every table.
--
--   SHOW CREATE TABLE config_section_field
--
-- Expect PRIMARY KEY (tenant_id, workspace_id, revision, template_key,
-- section_key, field_key) and no other unique key.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '041_workspace_drafts.sql'
--
-- Expect one row.
--
--
-- NO SEMICOLON ENDS A COMMENT LINE HERE. db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
