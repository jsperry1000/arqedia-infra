-- 017_base_and_template.sql
-- TPL-02 step 1. One base, and templates over it.
--
-- A pack has been one revision holding everything - categories, document
-- types, facts, their routing, and one memorandum with its sections. Six packs
-- would have meant six duplicated sets of facts, and forking two of them was
-- impossible: two bases cannot be merged and nothing decides which wins on a
-- shared key.
--
-- It is not the facts that differ between a KYC file and a trade credit file.
-- It is what gets said about them. So a pack becomes a BASE - the facts, the
-- document types and the routing between them - and TEMPLATES over it, each a
-- named memorandum with its sections and its bindings.
--
-- Additive. This migration adds two columns and writes two new revisions to
-- the reserved pack tenant. It changes no row of any tenant's configuration.
--
-- NOTHING IS SPLIT IN PLACE. Revision 1 of the pack tenant is left exactly as
-- it was written by 009, because splitting it would mean deleting its template
-- rows, and what was forked into the two live tenants is recorded there. It is
-- marked kind = 'legacy' instead: it says what it was, and step 2's packs()
-- selects on kind IN ('base', 'template') so it is never offered again.

-- --- the two columns -------------------------------------------------------
--
-- kind
--   'tenant'    a tenant's own configuration. The default, so every row that
--               exists today keeps its meaning without being touched.
--   'base'      facts, document types, and the routing between them.
--   'template'  one memorandum - its sections and their bindings.
--   'legacy'    a whole pack as packs used to be written. Revision 1 of the
--               pack tenant, and nothing else.
--
-- pack_key names the PACK a revision came from. It is not a template_key:
-- template_key names a memorandum inside a tenant's configuration and is
-- carried by every memo written from it, while pack_key names what we ship.
-- The memorandum below keeps template_key 'stage1-kyc' and is shipped as
-- pack_key 'due-diligence'. They are different things and must not be made to
-- match.
--
-- pack_key is also what signup should have stored. It stores a display string
-- today, and nothing maps that to a revision. A key is stable; a label is not,
-- and config_revision.note is editable free text that must not become the
-- mapping.

ALTER TABLE config_revision
  ADD COLUMN kind     VARCHAR(16) NOT NULL DEFAULT 'tenant' AFTER status,
  ADD COLUMN pack_key VARCHAR(64) NULL AFTER kind;

-- --- what revision 1 of the pack tenant is ---------------------------------

UPDATE config_revision
   SET kind = 'legacy', pack_key = 'stage1-kyc'
 WHERE tenant_id = 0 AND revision = 1;

-- --- room for the two new revisions ----------------------------------------
--
-- Cleared first so the file can be run again against a database where it
-- stopped part way. Revisions 2 and 3 of the pack tenant have never held
-- anything else: 009 wrote revision 1 alone.

DELETE FROM config_section_field WHERE tenant_id = 0 AND revision IN (2, 3);
DELETE FROM config_section WHERE tenant_id = 0 AND revision IN (2, 3);
DELETE FROM config_template WHERE tenant_id = 0 AND revision IN (2, 3);
DELETE FROM config_field WHERE tenant_id = 0 AND revision IN (2, 3);
DELETE FROM config_type_schema WHERE tenant_id = 0 AND revision IN (2, 3);
DELETE FROM config_schema WHERE tenant_id = 0 AND revision IN (2, 3);
DELETE FROM config_document_type WHERE tenant_id = 0 AND revision IN (2, 3);
DELETE FROM config_category WHERE tenant_id = 0 AND revision IN (2, 3);
DELETE FROM config_revision WHERE tenant_id = 0 AND revision IN (2, 3);

-- --- the template, revision 2 ----------------------------------------------
--
-- The memorandum 009 wrote: one template, eight sections, and the bindings of
-- those sections. Its bindings name facts that live in the base, which is why
-- a fork takes the base first.
--
-- A template revision is NOT a whole configuration and does not load as one.
-- See the specification, "What breaks when a revision is not whole".

INSERT INTO config_revision
  (tenant_id, revision, status, kind, pack_key, forked_from, note,
   published_at, published_by)
VALUES (0, 2, 'published', 'template', 'due-diligence', 'pack:0:1',
        'the built-in memorandum, split from revision 1', UTC_TIMESTAMP(),
        'migration 017');

INSERT INTO config_template
  (tenant_id, revision, template_key, label)
SELECT 0, 2, template_key, label
  FROM config_template WHERE tenant_id = 0 AND revision = 1;

INSERT INTO config_section
  (tenant_id, revision, template_key, section_key, numeral, title, kind,
   shape_key, prompt, context_sections, sort_order)
SELECT 0, 2, template_key, section_key, numeral, title, kind,
       shape_key, prompt, context_sections, sort_order
  FROM config_section WHERE tenant_id = 0 AND revision = 1;

INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
SELECT 0, 2, template_key, section_key, field_key, sort_order
  FROM config_section_field WHERE tenant_id = 0 AND revision = 1;

-- --- the base, revision 3 --------------------------------------------------
--
-- Facts, the document types they are sought in, and the routing between them.
-- There is no fact-to-document-type table: a fact belongs to a schema through
-- config_field.schema_key, and a document type feeds schemas through
-- config_type_schema. Both travel with the base, so the routing is preserved
-- exactly as 009 wrote it.
--
-- NUMBERED ABOVE THE TEMPLATE DELIBERATELY. registry.packs() orders by
-- revision descending and the front end's first run forks packs[0], so the
-- base must be the highest-numbered revision of the pack tenant. Until step 2
-- selects packs by pack_key, this ordering is what makes first run fork the
-- base, which is what it should fork.

INSERT INTO config_revision
  (tenant_id, revision, status, kind, pack_key, forked_from, note,
   published_at, published_by)
VALUES (0, 3, 'published', 'base', 'base', 'pack:0:1',
        'the built-in base, split from revision 1', UTC_TIMESTAMP(),
        'migration 017');

INSERT INTO config_category
  (tenant_id, revision, category_key, label, sort_order)
SELECT 0, 3, category_key, label, sort_order
  FROM config_category WHERE tenant_id = 0 AND revision = 1;

INSERT INTO config_document_type
  (tenant_id, revision, type_key, label, category_key, description,
   read_mode, always_ocr, sort_order)
SELECT 0, 3, type_key, label, category_key, description,
       read_mode, always_ocr, sort_order
  FROM config_document_type WHERE tenant_id = 0 AND revision = 1;

INSERT INTO config_schema
  (tenant_id, revision, schema_key, label, instruction, sort_order)
SELECT 0, 3, schema_key, label, instruction, sort_order
  FROM config_schema WHERE tenant_id = 0 AND revision = 1;

INSERT INTO config_type_schema
  (tenant_id, revision, type_key, schema_key)
SELECT 0, 3, type_key, schema_key
  FROM config_type_schema WHERE tenant_id = 0 AND revision = 1;

INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type,
   cardinality, description, group_key, sort_order)
SELECT 0, 3, schema_key, field_key, label, field_type,
       cardinality, description, group_key, sort_order
  FROM config_field WHERE tenant_id = 0 AND revision = 1;


-- Verification
--
--   SELECT revision, kind, pack_key, note FROM config_revision
--    WHERE tenant_id = 0 ORDER BY revision
--
-- Expect three rows: 1 legacy stage1-kyc, 2 template due-diligence, 3 base
-- base.
--
--   SELECT 'category' AS t, COUNT(*) FROM config_category
--    WHERE tenant_id = 0 AND revision = 3
--   UNION ALL SELECT 'doctype', COUNT(*) FROM config_document_type
--    WHERE tenant_id = 0 AND revision = 3
--   UNION ALL SELECT 'schema', COUNT(*) FROM config_schema
--    WHERE tenant_id = 0 AND revision = 3
--   UNION ALL SELECT 'typeschema', COUNT(*) FROM config_type_schema
--    WHERE tenant_id = 0 AND revision = 3
--   UNION ALL SELECT 'field', COUNT(*) FROM config_field
--    WHERE tenant_id = 0 AND revision = 3
--
-- Expect 4, 27, 8, 36, 105 - the counts revision 1 holds.
--
--   SELECT 'template' AS t, COUNT(*) FROM config_template
--    WHERE tenant_id = 0 AND revision = 2
--   UNION ALL SELECT 'section', COUNT(*) FROM config_section
--    WHERE tenant_id = 0 AND revision = 2
--   UNION ALL SELECT 'binding', COUNT(*) FROM config_section_field
--    WHERE tenant_id = 0 AND revision = 2
--
-- Expect 1, 8, 63.
--
--   SELECT COUNT(*) FROM config_revision
--    WHERE tenant_id IN (1, 2) AND kind <> 'tenant'
--
-- Expect 0. Both live tenants keep every revision as kind 'tenant'.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '017_base_and_template.sql'
--
-- Expect one row.
