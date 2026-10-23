-- 045_seat_workspace.sql
-- PACK-02 C. Which workspaces a member may see.
--
-- An ADMINISTRATOR SEES EVERY WORKSPACE, with or without a row here
-- (PACK-01 settled item 4). A MEMBER SEES ONLY THE WORKSPACES ASSIGNED TO
-- THEIR SEAT. Decided 23 October 2026:
--   - the table's shape, seat_workspace(tenant_id, seat_id, workspace_id),
--     approved as proposed
--   - existing members get every workspace their tenant holds today, so
--     nothing changes for anybody on the day this ships
--   - an invitation names its workspaces, at least one for a member; they
--     wait in seat_invitation_workspace and are copied to the seat when the
--     invitation is accepted (the signup function), then deleted with it
--   - a new workspace is assigned to no member
--   - an administrator made a member keeps every current workspace
--
-- SAFE UNDER THE CODE DEPLOYED TODAY: two new tables, which nothing reads
-- until the PACK-02 C code ships. Apply it first; the backfill is INSERT
-- IGNORE, so it can be run again after the deploy to catch a member who
-- joined in between.
--
-- No foreign keys, as everywhere else in this schema. assigned_by records
-- who gave the access, as invited_by does on a seat.
--
-- Read on dev on 23 October 2026, before this was written: 2 member seats,
-- both tenant 2, which holds 2 workspaces; 0 open invitations.

CREATE TABLE IF NOT EXISTS seat_workspace (
  tenant_id     BIGINT       NOT NULL,
  seat_id       BIGINT       NOT NULL,
  workspace_id  BIGINT       NOT NULL,
  assigned_by   VARCHAR(255) NULL,
  assigned_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (seat_id, workspace_id),
  KEY idx_seat_workspace_tenant (tenant_id, workspace_id)
);

CREATE TABLE IF NOT EXISTS seat_invitation_workspace (
  invitation_id BIGINT NOT NULL,
  workspace_id  BIGINT NOT NULL,
  PRIMARY KEY (invitation_id, workspace_id)
);

-- Existing members: every workspace their tenant holds.
INSERT IGNORE INTO seat_workspace (tenant_id, seat_id, workspace_id, assigned_by)
SELECT s.tenant_id, s.seat_id, w.workspace_id, 'migration 045'
  FROM seat s
  JOIN workspace w ON w.tenant_id = s.tenant_id
 WHERE s.role = 'member';


-- Verification
--
--   SELECT s.tenant_id, s.email, COUNT(sw.workspace_id) assigned,
--          (SELECT COUNT(*) FROM workspace w WHERE w.tenant_id = s.tenant_id) held
--     FROM seat s LEFT JOIN seat_workspace sw ON sw.seat_id = s.seat_id
--    WHERE s.role = 'member' GROUP BY s.seat_id
--
-- Expect assigned = held on every row (2 and 2 for tenant 2's members).
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '045_seat_workspace.sql'
--
-- Expect one row.
--
--
-- NO SEMICOLON ENDS A COMMENT LINE HERE. db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
