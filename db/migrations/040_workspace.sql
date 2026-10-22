-- 040_workspace.sql
-- PACK-01. A tenant's configuration is partitioned into workspaces: one
-- industry-scoped slice each (Trade Finance, Real Estate, Private Credit
-- Corporate, Accounts Receivable Financing), each with its own draft, its own
-- publish and its own selected revision.
--
-- Decision record: docs/backlog-items/ARQEDIA_backlog_PACK01_multi_pack_tenants.md
-- (22 October 2026), and the three answers given before this was written
-- (same day): default 0 with the old key kept, column and index on the
-- runtime tables, tenant 0 at workspace 0.
--
-- NOT "pack". Live, a pack is what tenant 0 ships and a new tenant forks
-- from - config_revision.pack_key, pack_offer, tenant.forked_pack. None of
-- that changes here. A workspace is a slice of a tenant's OWN configuration.
--
-- 039 IS HEAD. Read before writing this, not assumed:
--
--   SELECT filename FROM schema_migration ORDER BY filename DESC LIMIT 1
--   -> 039_memo_rewrite_update.sql
--
-- ADDITIVE. One new table, one new column on thirteen tables, and a backfill
-- of that column. No row is deleted and no existing value is altered. The
-- nine config tables have their primary key WIDENED: the old key is dropped
-- as a primary key and re-added, unchanged, as a unique key, in the same
-- statement.
--
-- --- what 0 means -----------------------------------------------------------
--
-- workspace_id = 0 is "in no workspace". AUTO_INCREMENT never issues 0, so it
-- cannot collide with a real one. Two kinds of row carry it:
--
--   tenant 0, the pack tenant. Out of scope for workspaces: it holds what is
--     shipped, not a customer's configuration, and gets no workspace row.
--
--   any row written by code that predates this migration. The deployed
--     Lambdas name no workspace_id, so every row they insert takes the
--     DEFAULT. The backfill UPDATEs below are re-runnable for exactly this
--     reason - run them again once the code that writes workspace_id is
--     deployed, and anything written in between is assigned.
--
-- --- why the old key is kept ------------------------------------------------
--
-- editor.py and registry.py write the draft with ON DUPLICATE KEY UPDATE and
-- INSERT IGNORE, naming (tenant_id, revision, key) and no workspace_id. With
-- only the widened primary key, such an upsert against a row now holding
-- workspace 7 would insert a second row at workspace 0 instead of updating -
-- every edit duplicating the draft. uq_single_workspace keeps the old key
-- unique, so the deployed code collides exactly where it does today and
-- behaves exactly as it does today.
--
-- THE PRICE: while uq_single_workspace stands, two workspaces of one tenant
-- cannot both hold a draft, because each draft is revision 0. Published
-- revisions never collide - the counter is per tenant (below). A later
-- migration drops uq_single_workspace once the code names workspace_id
-- everywhere. Dropping it is what turns multiple drafts on.
--
-- --- the revision counter ---------------------------------------------------
--
-- Unchanged, and still unique within (tenant_id, workspace_id).
-- registry._latest_published takes MAX(revision) over the TENANT's published
-- revisions, so one series serves every workspace of a tenant and no two
-- workspaces are issued one number. Not touched here.

-- --- the workspace ----------------------------------------------------------
--
-- forked_from_revision_id is an INT revision number: there is no revision_id
-- anywhere to reference. It names a revision of the PACK tenant, which is the
-- only tenant anything is forked from today. forked_from_workspace_id would
-- name that revision's workspace - and the pack tenant has none (workspace 0),
-- so it is NULL on every row this migration writes.
--
-- active_revision is the revision this workspace files against. tenant.
-- active_revision stays, as a copy for readers that predate workspaces - the
-- pattern tenant.plan already follows (CLAUDE.md, Money).
--
-- No foreign key, here or on any workspace_id below. The schema holds one,
-- fk_subscription_plan, and this keeps to that.

CREATE TABLE workspace (
  workspace_id              BIGINT       NOT NULL AUTO_INCREMENT,
  tenant_id                 BIGINT       NOT NULL,
  name                      VARCHAR(128) NOT NULL,
  forked_from_workspace_id  BIGINT       NULL,
  forked_from_revision_id   INT          NULL,
  active_revision           INT          NULL,
  created_at                DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (workspace_id),
  KEY idx_workspace_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --- one workspace per existing tenant --------------------------------------
--
-- Every tenant but 0, named "Trade Finance" - which is what each one's live
-- configuration already does (decision of 22 October). On dev that is
-- tenants 1, 2, 5, 9 and 10.
--
-- forked_from_revision_id is read from the tenant's own record of its fork,
-- config_revision.forked_from, and only where that names the pack tenant in
-- the form pack:0:<n>. The earliest such revision wins. Anywhere else it is
-- NULL rather than guessed.
--
-- Guarded by NOT EXISTS, so running it twice writes nothing the second time.

INSERT INTO workspace
  (tenant_id, name, forked_from_workspace_id, forked_from_revision_id,
   active_revision)
SELECT t.tenant_id, 'Trade Finance', NULL,
       (SELECT CAST(SUBSTRING_INDEX(r.forked_from, ':', -1) AS UNSIGNED)
          FROM config_revision r
         WHERE r.tenant_id = t.tenant_id
           AND r.forked_from REGEXP '^pack:0:[0-9]+$'
         ORDER BY r.revision
         LIMIT 1),
       t.active_revision
  FROM tenant t
 WHERE t.tenant_id <> 0
   AND NOT EXISTS (SELECT 1 FROM workspace w WHERE w.tenant_id = t.tenant_id);

-- --- the nine config tables -------------------------------------------------
--
-- workspace_id goes in after tenant_id, in the column list and in the key.
-- The old key stays, as uq_single_workspace (above). One statement per
-- table, so a table is never left without a primary key between two calls.

ALTER TABLE config_revision
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_id, workspace_id, revision),
  ADD UNIQUE KEY uq_single_workspace (tenant_id, revision);

ALTER TABLE config_category
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_id, workspace_id, revision, category_key),
  ADD UNIQUE KEY uq_single_workspace (tenant_id, revision, category_key);

ALTER TABLE config_document_type
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_id, workspace_id, revision, type_key),
  ADD UNIQUE KEY uq_single_workspace (tenant_id, revision, type_key);

ALTER TABLE config_schema
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_id, workspace_id, revision, schema_key),
  ADD UNIQUE KEY uq_single_workspace (tenant_id, revision, schema_key);

ALTER TABLE config_type_schema
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_id, workspace_id, revision, type_key, schema_key),
  ADD UNIQUE KEY uq_single_workspace (tenant_id, revision, type_key, schema_key);

ALTER TABLE config_field
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_id, workspace_id, revision, field_key),
  ADD UNIQUE KEY uq_single_workspace (tenant_id, revision, field_key);

ALTER TABLE config_template
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_id, workspace_id, revision, template_key),
  ADD UNIQUE KEY uq_single_workspace (tenant_id, revision, template_key);

ALTER TABLE config_section
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_id, workspace_id, revision, template_key, section_key),
  ADD UNIQUE KEY uq_single_workspace (tenant_id, revision, template_key, section_key);

ALTER TABLE config_section_field
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (tenant_id, workspace_id, revision, template_key, section_key, field_key),
  ADD UNIQUE KEY uq_single_workspace (tenant_id, revision, template_key, section_key, field_key);

-- --- the four runtime tables ------------------------------------------------
--
-- Not a key change. Their primary key is a surrogate AUTO_INCREMENT id and
-- config_revision is an ordinary column on them, so workspace_id is a column
-- and an index beside tenant_id - the index every workspace-scoped list will
-- read through.
--
-- tenant.active_revision and pack_offer (tenant_id, revision) are likewise
-- column references, not keys (pack_offer's key is pack_key), and are left
-- as they are. pack_offer names revisions of tenant 0, which is workspace 0.

ALTER TABLE document
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  ADD INDEX idx_document_workspace (tenant_id, workspace_id);

ALTER TABLE extracted_value
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  ADD INDEX idx_value_workspace (tenant_id, workspace_id);

ALTER TABLE memo
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  ADD INDEX idx_memo_workspace (tenant_id, workspace_id);

ALTER TABLE memo_rewrite
  ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 0 AFTER tenant_id,
  ADD INDEX idx_memo_rewrite_workspace (tenant_id, workspace_id);

-- --- the backfill -----------------------------------------------------------
--
-- Every row at workspace 0 whose tenant holds EXACTLY ONE workspace is given
-- it. Not "the" workspace by tenant alone: once a tenant has two, which one
-- a row belongs to is a fact this statement cannot know, and it leaves the
-- row at 0 rather than guess. Tenant 0 has none and is never matched.
--
-- Re-runnable, and meant to be: see "what 0 means" above.

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


-- Verification
--
--   SELECT tenant_id, name, forked_from_workspace_id,
--          forked_from_revision_id, active_revision FROM workspace
--    ORDER BY tenant_id
--
-- Expect one row per tenant but 0, each "Trade Finance", forked_from_
-- workspace_id NULL, active_revision equal to tenant.active_revision. On dev,
-- read 22 October: tenants 1, 2, 5, 9, 10, forked from pack revisions 1, 1,
-- 9, 9 and 25.
--
--   SELECT 'config_revision', COUNT(*) FROM config_revision
--    WHERE workspace_id = 0 AND tenant_id <> 0
--   ... and the same for the other twelve tables
--
-- Expect 0 on every table. Above zero is a row written by the deployed code
-- between the ALTER and its table's UPDATE - run the UPDATEs again.
--
--   SELECT COUNT(*) FROM config_revision WHERE tenant_id = 0 AND workspace_id <> 0
--
-- Expect 0, and the same for the other eight config tables.
--
--   SHOW CREATE TABLE config_section_field
--
-- Expect PRIMARY KEY (tenant_id, workspace_id, revision, template_key,
-- section_key, field_key) and UNIQUE KEY uq_single_workspace on the same
-- columns without workspace_id.
--
--   SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
--    WHERE CONSTRAINT_SCHEMA = 'arqedia'
--
-- Expect 1, fk_subscription_plan, as before.
--
--   SELECT filename FROM schema_migration WHERE filename = '040_workspace.sql'
--
-- Expect one row.
--
--
-- DEPLOY ORDER. This first, the code second, and either order is safe for
-- the code that exists today: every new column has a default, and every old
-- key still holds. The code that writes workspace_id must not deploy before
-- this, because the column it names would not exist.
--
-- NO SEMICOLON ENDS A COMMENT LINE HERE. db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
