-- 048_config_field_index_workspace.sql
--
-- config_field's schema index, given the workspace (PACK-01 gap, listed in
-- the PACK-02 catch-up report).
--
-- 047 IS APPLIED, read before writing this:
--
--   SELECT filename FROM schema_migration ORDER BY applied_at DESC LIMIT 1
--   -> 047_workspace_deletion.sql
--
-- WHAT IS THERE, read 23 October 2026:
--
--   PRIMARY           (tenant_id, workspace_id, revision, field_key)
--   idx_field_schema  (tenant_id, revision, schema_key)
--
-- Every other config_* table is keyed (tenant_id, workspace_id, revision,
-- ...), and config_field's primary key is too. Only this index predates the
-- workspace. Revision 0 - the draft - is one per workspace, so a draft read
-- by schema walks every workspace's draft rows for that schema key. Today
-- that is a handful (EXPLAIN on tenant 5, workspace 15, revision 0: 2 rows),
-- which is why this is tidying and not a fix anyone would have noticed.
--
-- AN INDEX ONLY. No row is read differently, written or removed. The old
-- index is replaced rather than kept beside the new one: a second index on
-- the same leading columns costs every write and serves no read the new one
-- does not. 33,360 rows on dev.

ALTER TABLE config_field
  DROP INDEX idx_field_schema,
  ADD INDEX idx_field_schema (tenant_id, workspace_id, revision, schema_key);
