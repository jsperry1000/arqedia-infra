-- 022_retire_base_3.sql
--
-- Revision 3 of tenant 0, the base split from the built-in pack by migration
-- 017, is retired. Migration 021 published revision 4 as the base, copied from
-- tenant 2 revision 53, and a tenant should be offered that one only.
--
-- WHY IT MATTERS. registry.packs() lists every published revision of kind
-- 'base', so revisions 3 and 4 both appear, both with pack_key 'base'.
-- Get started is not affected: fork_base takes the newest published base by
-- key, which is 4. But the first-run screen in Configure.tsx offers every base
-- in a dropdown and falls back to packs[0], and two rows sharing a pack_key
-- come back in no guaranteed order. A tenant reaching that screen could start
-- on the 27-type base instead of the 35-type one.
--
-- ONE ROW IS CHANGED, NOTHING IS DELETED, as 021 did for revision 2.
-- packs() and template_packs() list status 'published' only. Its categories,
-- document types, schemas, routing and facts stay, and its status can be set
-- back. No tenant records forking from it: tenants 1 and 2 record pack:0:1,
-- and revisions 2 and 3 of tenant 0 were split from that same revision.
--
-- Guarded on kind and pack_key, so it changes nothing if revision 3 is ever
-- something else. Running it twice changes nothing the second time.

UPDATE config_revision SET status = 'retired'
 WHERE tenant_id = 0 AND revision = 3 AND kind = 'base' AND pack_key = 'base';


-- Verification
--
--   SELECT revision, status, kind, pack_key FROM config_revision
--    WHERE tenant_id = 0 ORDER BY revision
--
-- Expect: 1 published legacy stage1-kyc, 2 retired template due-diligence,
-- 3 retired base base, 4 published base base, 5-8 published template.
--
--   SELECT COUNT(*) FROM config_revision
--    WHERE tenant_id = 0 AND status = 'published' AND kind = 'base'
--
-- Expect 1.
--
--   SELECT COUNT(*) FROM config_field WHERE tenant_id = 0 AND revision = 3
--
-- Expect 105: retiring keeps the rows.
--
--   SELECT filename FROM schema_migration WHERE filename = '022_retire_base_3.sql'
--
-- Expect one row.
