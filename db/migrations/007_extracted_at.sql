-- 007_extracted_at.sql
--
-- Without this the document list cannot tell a document still being read from
-- one that yielded nothing. Both show as zero values, and they mean very
-- different things: one is in progress, the other is a finding.
--
-- Set by extraction on completion. Null means extraction has not run.

ALTER TABLE document
  ADD COLUMN extracted_at DATETIME NULL AFTER filed_at;
