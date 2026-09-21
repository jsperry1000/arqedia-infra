-- 029_document_extraction_error.sql
--
-- Why a document was not extracted, on the document itself.
--
-- extracted_at answers one question - has extraction run - and was asked to
-- answer two. A document that ran and failed part way looks identical to one
-- that has not started: both carry NULL, and the review screen says
-- "extracting..." about both, for ever. 102 rows in tenant 2 have said it
-- since 5 September.
--
-- WHAT HAPPENED, since the next person will look for it. Revisions 2 and 3
-- each carry three fields with cardinality 'group' and no group_key.
-- config.py reads a row with no group_key as a single value, so such a field
-- arrives in the extractor as a FIVE-part tuple calling itself a group, and
-- _build_prompt asking it for field[5] raises IndexError. The exception left
-- the handler before it could stamp extracted_at, so values already written
-- by earlier schemas stayed and the document never finished. registry.py
-- refuses that shape at publish now (cc0f141, 5 September), which is why no
-- revision after 3 carries it.
--
-- NOT A SECOND refusal_code. That column means the document could not be
-- READ - the normalizer's answer, written before filing. This one means it
-- was read and the extraction over it failed. A scan can carry both, and one
-- column cannot hold two meanings - the same argument migration 025 made for
-- keeping refusal_code apart from type_reason.
--
-- extracted_at IS NOT SET BY THIS MIGRATION and is not set by the backfill
-- below. Stamping it would say these documents finished, which is the
-- untruth being closed rather than a different one. A row now reads: no
-- extracted_at, an extraction_error - extraction ran, failed, and is not
-- coming back on its own.
--
-- Additive: one nullable column, and an UPDATE confined to the 102 rows that
-- are demonstrably this failure. No other row, column or table is touched,
-- no extracted_value is written or removed, and nothing is deleted.

ALTER TABLE document
  ADD COLUMN extraction_error VARCHAR(32) NULL AFTER extracted_at;

-- The 102. Scoped by tenant AND revision AND a null extracted_at, all three:
-- revision 2 and 3 are where the malformed fields live, and a document of
-- those revisions that DID finish has its timestamp and is not this failure.
UPDATE document
SET extraction_error = 'group_key_missing'
WHERE tenant_id = 2
  AND config_revision IN (2, 3)
  AND extracted_at IS NULL;


-- Verification
--
--   SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
--     FROM information_schema.COLUMNS
--    WHERE TABLE_SCHEMA = 'arqedia' AND TABLE_NAME = 'document'
--      AND COLUMN_NAME = 'extraction_error'
--
-- Expect one row: extraction_error varchar(32) YES.
--
--   SELECT extraction_error, COUNT(*) FROM document
--    WHERE extraction_error IS NOT NULL GROUP BY extraction_error
--
-- Expect exactly one row: group_key_missing, 102.
--
--   SELECT COUNT(*) FROM document
--    WHERE extraction_error IS NOT NULL AND tenant_id <> 2
--
-- Expect 0. Nothing outside tenant 2 is marked.
--
--   SELECT COUNT(*) FROM document
--    WHERE extraction_error IS NOT NULL AND extracted_at IS NOT NULL
--
-- Expect 0. The backfill marks only rows that never finished.
--
--   SELECT COUNT(*) FROM document WHERE tenant_id = 2 AND extracted_at IS NULL
--
-- Expect 111, unchanged. Nine of them are the documents extraction was never
-- invoked for at all (EXT-01); they are a different failure and are not
-- marked here.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '029_document_extraction_error.sql'
--
-- Expect one row.
