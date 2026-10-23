-- 047_workspace_deletion.sql
--
-- An administrator deletes a workspace (PACK-02 D, settled 23 October 2026):
-- hidden at once and restorable for six months, then removed for good. This
-- migration is the hiding and the record of it. The removal is a branch of
-- its own, due before the first date can arrive (April 2027).
--
-- 046 IS APPLIED, read before writing this:
--
--   SELECT filename FROM schema_migration ORDER BY applied_at DESC LIMIT 1
--   -> 046_workspace_limit.sql
--
-- ADDITIVE. Three nullable columns and one new table. Nothing is removed by
-- deleting a workspace until its date: its rows, documents, memoranda and
-- shares stay where they are, out of sight.

-- --- the workspace -----------------------------------------------------------
--
-- deleted_at NULL is a live workspace. Set, it is hidden: out of every list,
-- refused by number, its shares suspended. remove_after is six months on,
-- written at the moment of deleting so the date said on screen is the date
-- kept. A restore clears all three, and workspace_deletion keeps the history.

ALTER TABLE workspace
  ADD COLUMN deleted_at DATETIME NULL,
  ADD COLUMN deleted_by VARCHAR(255) NULL,
  ADD COLUMN remove_after DATETIME NULL;

-- --- the record --------------------------------------------------------------
--
-- One row per attempt, from the emailed code onward. The code is held only as
-- a hash, lives fifteen minutes and is good for five tries. deleted_at is set
-- when the deletion went through, with the workspace members were moved to,
-- and restored_at and restored_by if it was brought back. Never updated
-- otherwise and never deleted: this is who deleted what, and when.

CREATE TABLE IF NOT EXISTS workspace_deletion (
  deletion_id BIGINT NOT NULL AUTO_INCREMENT,
  tenant_id BIGINT NOT NULL,
  workspace_id BIGINT NOT NULL,
  requested_by VARCHAR(255) NOT NULL,
  requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  code_hash CHAR(64) NOT NULL,
  code_expires_at DATETIME NOT NULL,
  tries INT NOT NULL DEFAULT 0,
  deleted_at DATETIME NULL,
  members_moved_to BIGINT NULL,
  restored_at DATETIME NULL,
  restored_by VARCHAR(255) NULL,
  PRIMARY KEY (deletion_id),
  KEY idx_workspace_deletion_ws (tenant_id, workspace_id)
);
