-- 007_extracted_at.sql
--
-- Without this the document list cannot tell a document still being read from
-- one that yielded nothing. Both show as zero values, and they mean very
-- different things: one is in progress, the other is a finding.
--
-- Set by extraction on completion. Null means extraction has not run.

ALTER TABLE document
  ADD COLUMN extracted_at DATETIME NULL AFTER filed_at;

-- Backfill. A column whose null means "in progress" leaves every historical
-- row looking in progress, so documents extracted before this column existed
-- reported "extracting" permanently. Only documents that actually produced
-- values are backfilled: one with genuinely no values stays null, which is
-- the honest answer for a document that was never extracted.
UPDATE document d
SET extracted_at = filed_at
WHERE state = 'filed'
  AND extracted_at IS NULL
  AND EXISTS (SELECT 1 FROM extracted_value v
              WHERE v.document_id = d.document_id);
