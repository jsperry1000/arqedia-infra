-- 044_offering_workspaces.sql
-- PACK-02. What ARQEDIA offers is a workspace: tenant 0's configuration
-- moves into a workspace of its own, "Trade Finance", the first offering.
-- pack_offer gains the offering's workspace, and today's client workspaces
-- are recorded as forked from it.
--
-- HELD. This file sits in db/migrations/held/, which db/migrate.ps1 does not
-- read. It moves up into db/migrations/ on the day it is due, as 043 did.
--
-- NOT TO BE APPLIED UNTIL THE PACK-02 CODE IS DEPLOYED. Order: the registry
-- and API branch merged, the layer rebuilt (build-layer.ps1), terraform
-- apply, the deployed layer confirmed to carry the new registry.py and
-- config.py - THEN move this file up and run it.
--
-- WHY IT WAITS. The code deployed today finds tenant 0's rows by revision
-- (registry._workspace_of_revision), so it goes on reading them after they
-- move. What it cannot do is write the offer: set_offer's inserts name no
-- workspace_id, so an offer set by the curator between this running and
-- the new code arriving lands at workspace 0, where the new code does not
-- look - the catalogue would read as empty. Run after the deploy, nothing
-- writes pack_offer without a workspace.
--
-- Read on dev on 23 October 2026, before this was written:
--   tenant 0 holds no workspace row. At workspace 0 it holds 34 revisions
--   (active 33), 130 templates, 5,722 facts - 25,358 config rows in the
--   nine config tables - and 2 engagements. No document, extracted value,
--   memo or rewrite. No other tenant holds a row at workspace 0.
--   pack_offer: 5 rows, all tenant 0 revision 33, primary key pack_key.
--   Client workspaces: 1, 2, 3, 4, 5 "Trade Finance", and 9 "AR FINANCING"
--   (tenant 2) and 10 "REAL ESTATE" (tenant 5). forked_from_workspace_id is
--   NULL on all seven.
--
-- ADDITIVE IN DATA. No row is deleted. Rows move from workspace 0 to the
-- new workspace, pack_offer gains a column, and its primary key widens to
-- carry it. Every statement can be run twice.

-- --- the first offering --------------------------------------------------
--
-- Named Trade Finance (PACK-02, settled item 3): that is what tenant 0's
-- configuration already is. Inserted once - a second run finds it and
-- inserts nothing. workspace.name has no unique key, so the guard is here.

INSERT INTO workspace (tenant_id, name, active_revision)
SELECT 0, 'Trade Finance', t.active_revision
  FROM tenant t
 WHERE t.tenant_id = 0
   AND NOT EXISTS (SELECT 1 FROM workspace w WHERE w.tenant_id = 0);

-- --- tenant 0's configuration, into it -----------------------------------
--
-- Every row tenant 0 holds at workspace 0. The workspace is found rather
-- than numbered: its id is whatever auto_increment gave it above.

UPDATE config_revision c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE config_category c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE config_document_type c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE config_schema c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE config_type_schema c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE config_field c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE config_template c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE config_section c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE config_section_field c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE engagement c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

-- The four runtime tables hold nothing for tenant 0. Moved all the same,
-- so that a row written between this being read and being run is not left
-- behind at workspace 0.

UPDATE document c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE extracted_value c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE memo c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

UPDATE memo_rewrite c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.workspace_id = w.workspace_id
 WHERE c.tenant_id = 0 AND c.workspace_id = 0;

-- The revision the offering is using, again: the curator may publish
-- between the insert above and this file being run, and the tenant row is
-- the one the deployed code writes.

UPDATE workspace w
  JOIN tenant t ON t.tenant_id = w.tenant_id
   SET w.active_revision = t.active_revision
 WHERE w.tenant_id = 0
   AND NOT (w.active_revision <=> t.active_revision);

-- --- the offer, per offering ---------------------------------------------
--
-- Each offering has its own base, so pack_key alone no longer identifies a
-- row: 'base' is a key in every offering. The key becomes
-- (workspace_id, pack_key). The column is added with a default so that the
-- rows already there are valid before they are backfilled, then every row
-- is given the Trade Finance workspace - all five are tenant 0's, at
-- revision 33.

ALTER TABLE pack_offer
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id;

UPDATE pack_offer o
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET o.workspace_id = w.workspace_id
 WHERE o.workspace_id = 0;

ALTER TABLE pack_offer
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (workspace_id, pack_key);

-- --- today's client workspaces, linked ------------------------------------
--
-- Recorded as forked from Trade Finance (PACK-02, settled item 5), so their
-- Catalogue goes on offering what it offers now. NAMED BY ID, not matched
-- by name: workspaces 9 (tenant 2, "AR FINANCING") and 10 (tenant 5,
-- "REAL ESTATE") hold the Trade Finance vocabulary but are left unlinked
-- (open item A, answered 23 October 2026), and a workspace made between
-- now and the day this runs is not linked by accident.
-- Only where nothing is recorded yet, so a second run changes nothing.

UPDATE workspace c
  JOIN (SELECT MIN(workspace_id) AS workspace_id FROM workspace
         WHERE tenant_id = 0) w
   SET c.forked_from_workspace_id = w.workspace_id
 WHERE c.workspace_id IN (1, 2, 3, 4, 5)
   AND c.tenant_id <> 0
   AND c.forked_from_workspace_id IS NULL;


-- Verification
--
--   SELECT workspace_id, name, active_revision FROM workspace
--    WHERE tenant_id = 0
--
-- Expect one row, Trade Finance, at tenant 0's active revision (33 when
-- this was written).
--
--   SELECT 'config_revision', COUNT(*) FROM config_revision
--    WHERE workspace_id = 0
--   ... and the same for the other twelve tables and engagement
--
-- Expect 0 on every table - no tenant holds anything at workspace 0 now.
--
--   SELECT workspace_id, pack_key, kind, revision FROM pack_offer
--
-- Expect five rows, every one at the Trade Finance workspace.
--
--   SELECT index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index)
--     FROM information_schema.statistics
--    WHERE table_schema = 'arqedia' AND table_name = 'pack_offer'
--    GROUP BY index_name
--
-- Expect PRIMARY on workspace_id,pack_key.
--
--   SELECT workspace_id, forked_from_workspace_id FROM workspace
--    WHERE tenant_id <> 0
--
-- Expect 1 to 5 naming Trade Finance, 9 and 10 NULL.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '044_offering_workspaces.sql'
--
-- Expect one row.
--
--
-- NO SEMICOLON ENDS A COMMENT LINE HERE. db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
