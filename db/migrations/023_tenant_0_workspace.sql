-- 023_tenant_0_workspace.sql
--
-- Tenant 0 becomes a workspace that can be edited, and holds ONE WHOLE
-- revision rather than five partial ones.
--
-- WHY. Revisions 4 to 8 are packs: a base with no memoranda, and four
-- memoranda with no facts. The editor is built for a whole configuration -
-- open_draft copies one revision, validate judges one revision, and publish
-- writes one revision. Opening a draft from revision 8 gives a memorandum
-- whose every binding names a fact that revision does not hold, and it can
-- never publish. So curation needs a revision shaped like a tenant's own.
--
-- Revision selection decision record, 17 September 2026: publishing makes a
-- revision available, tenant.active_revision selects which one is in use, and
-- it applies to every tenant including tenant 0. What is ON OFFER to new
-- tenants becomes a mark, which a later migration adds; until then packs()
-- and the forks keep reading revisions 4 to 8 and nothing a customer sees
-- changes.
--
-- Additive. Revisions 1 to 8 are left exactly as they are: they are the record
-- of what has been shipped, and tenants 1 and 2 record forking from
-- revision 1.
--
-- Numbered 023: 022 is taken by the retire-base-3 branch, which is not merged.

-- --- a tenant row for 0 ----------------------------------------------------
--
-- tenant.active_revision is the selection tick, and it is a column on a row
-- that has never existed. tenant_id is AUTO_INCREMENT, and MySQL gives an
-- inserted 0 the next id instead unless NO_AUTO_VALUE_ON_ZERO is set - which
-- db/migrate.ps1 cannot do, because it sends every statement as its own Data
-- API call and the session does not carry. So the row is inserted normally
-- and its primary key is then moved to 0. No table declares a foreign key to
-- tenant, and this was proved on dev inside a transaction that was rolled
-- back.
--
-- The insert consumes an id: after this runs, the next tenant created is one
-- higher than it would have been. Ids carry no meaning and nothing reads them
-- for order.
--
-- plan is 'base'. Tenant 0 is not a paying customer; the value is read by
-- seats.seats_bought and by whether branding is offered.
--
-- Both statements can be run again. The insert writes nothing where tenant 0
-- exists, and the update matches nothing once the row is at 0. The update is
-- guarded on the columns a signed-up tenant would have filled, so a customer
-- who happens to be called ARQEDIA is never moved.

INSERT INTO tenant (name, region, jurisdiction, plan)
SELECT 'ARQEDIA', 'us-east-2', NULL, 'base' FROM DUAL
 WHERE NOT EXISTS (SELECT 1 FROM tenant WHERE tenant_id = 0);

UPDATE tenant SET tenant_id = 0
 WHERE name = 'ARQEDIA' AND tenant_id <> 0
   AND plan = 'base' AND active_revision IS NULL
   AND signup_ip IS NULL AND trial_ends_at IS NULL;

-- --- revision 9, whole -----------------------------------------------------
--
-- The facts of revision 4 and the four memoranda of revisions 5 to 8, in one
-- revision. Copied from tenant 0's own rows, so this runs the same on every
-- environment (ENV-01).
--
-- kind is 'tenant': it is a workspace's own configuration, not a pack. What
-- is on offer is the mark, not the kind.
--
-- Cleared first so the file can be run again against a database where it
-- stopped part way. Revision 9 has never held anything.

DELETE FROM config_section_field WHERE tenant_id = 0 AND revision = 9;
DELETE FROM config_section WHERE tenant_id = 0 AND revision = 9;
DELETE FROM config_template WHERE tenant_id = 0 AND revision = 9;
DELETE FROM config_field WHERE tenant_id = 0 AND revision = 9;
DELETE FROM config_type_schema WHERE tenant_id = 0 AND revision = 9;
DELETE FROM config_schema WHERE tenant_id = 0 AND revision = 9;
DELETE FROM config_document_type WHERE tenant_id = 0 AND revision = 9;
DELETE FROM config_category WHERE tenant_id = 0 AND revision = 9;
DELETE FROM config_revision WHERE tenant_id = 0 AND revision = 9;

INSERT INTO config_revision
  (tenant_id, revision, status, kind, pack_key, forked_from, note,
   published_at, published_by)
VALUES (0, 9, 'published', 'tenant', NULL, 'pack:0:4+5,6,7,8',
        'the base of revision 4 and the four memoranda of 5 to 8, in one revision',
        UTC_TIMESTAMP(), 'migration 023');

-- The base: categories, document types, schemas, the routing between them,
-- and the facts. From revision 4.

INSERT INTO config_category
  (tenant_id, revision, category_key, label, sort_order)
SELECT 0, 9, category_key, label, sort_order
  FROM config_category WHERE tenant_id = 0 AND revision = 4;

INSERT INTO config_document_type
  (tenant_id, revision, type_key, label, category_key, description,
   read_mode, always_ocr, sort_order)
SELECT 0, 9, type_key, label, category_key, description,
       read_mode, always_ocr, sort_order
  FROM config_document_type WHERE tenant_id = 0 AND revision = 4;

INSERT INTO config_schema
  (tenant_id, revision, schema_key, label, instruction, sort_order)
SELECT 0, 9, schema_key, label, instruction, sort_order
  FROM config_schema WHERE tenant_id = 0 AND revision = 4;

INSERT INTO config_type_schema
  (tenant_id, revision, type_key, schema_key)
SELECT 0, 9, type_key, schema_key
  FROM config_type_schema WHERE tenant_id = 0 AND revision = 4;

INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type,
   cardinality, description, group_key, sort_order)
SELECT 0, 9, schema_key, field_key, label, field_type,
       cardinality, description, group_key, sort_order
  FROM config_field WHERE tenant_id = 0 AND revision = 4;

-- The four memoranda, their sections and their bindings. From revisions 5 to
-- 8, one memorandum each and no template_key shared between them.

INSERT INTO config_template
  (tenant_id, revision, template_key, label)
SELECT 0, 9, template_key, label
  FROM config_template WHERE tenant_id = 0 AND revision IN (5, 6, 7, 8);

INSERT INTO config_section
  (tenant_id, revision, template_key, section_key, numeral, title, kind,
   shape_key, prompt, context_sections, sort_order)
SELECT 0, 9, template_key, section_key, numeral, title, kind,
       shape_key, prompt, context_sections, sort_order
  FROM config_section WHERE tenant_id = 0 AND revision IN (5, 6, 7, 8);

INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
SELECT 0, 9, template_key, section_key, field_key, sort_order
  FROM config_section_field WHERE tenant_id = 0 AND revision IN (5, 6, 7, 8);

-- --- the tick --------------------------------------------------------------
--
-- Revision 9 is what tenant 0 works against. A draft opens from it, and
-- publishing writes revision 10 beside it.

UPDATE tenant SET active_revision = 9 WHERE tenant_id = 0;


-- Verification
--
--   SELECT tenant_id, name, region, plan, active_revision FROM tenant
--    WHERE tenant_id = 0
--
-- Expect one row: 0, ARQEDIA, us-east-2, base, 9.
--
--   SELECT revision, status, kind, pack_key FROM config_revision
--    WHERE tenant_id = 0 ORDER BY revision
--
-- Expect revisions 1 to 8 unchanged, and 9 published tenant with no pack_key.
--
--   SELECT 'category', COUNT(*) FROM config_category WHERE tenant_id = 0 AND revision = 9
--   UNION ALL SELECT 'doctype', COUNT(*) FROM config_document_type WHERE tenant_id = 0 AND revision = 9
--   UNION ALL SELECT 'schema', COUNT(*) FROM config_schema WHERE tenant_id = 0 AND revision = 9
--   UNION ALL SELECT 'routing', COUNT(*) FROM config_type_schema WHERE tenant_id = 0 AND revision = 9
--   UNION ALL SELECT 'field', COUNT(*) FROM config_field WHERE tenant_id = 0 AND revision = 9
--   UNION ALL SELECT 'template', COUNT(*) FROM config_template WHERE tenant_id = 0 AND revision = 9
--   UNION ALL SELECT 'section', COUNT(*) FROM config_section WHERE tenant_id = 0 AND revision = 9
--   UNION ALL SELECT 'binding', COUNT(*) FROM config_section_field WHERE tenant_id = 0 AND revision = 9
--
-- Expect 5, 35, 42, 168, 196, 4, 43, 375 - what revisions 4 to 8 hold between
-- them.
--
--   SELECT COUNT(*) FROM config_section_field sf
--    LEFT JOIN config_field f ON f.tenant_id = 0 AND f.revision = 9
--          AND f.field_key = sf.field_key
--    WHERE sf.tenant_id = 0 AND sf.revision = 9 AND f.field_key IS NULL
--
-- Expect 0: every binding in revision 9 names a fact revision 9 holds. This
-- is what revisions 5 to 8 could not say on their own.
--
--   SELECT filename FROM schema_migration WHERE filename = '023_tenant_0_workspace.sql'
--
-- Expect one row.
