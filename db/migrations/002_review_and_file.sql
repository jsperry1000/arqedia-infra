-- 002_review_and_file.sql
-- Filing becomes a deliberate act. A document is analysed on upload and only
-- extracted once a person confirms what it is.
--
-- thin_text marks a document whose extracted text is implausibly short for
-- its page count - a scan carrying only a certification stamp. The previous
-- gate averaged characters per page and let 68 characters through as readable.

ALTER TABLE document
  ADD COLUMN state VARCHAR(16) NOT NULL DEFAULT 'filed' AFTER document_type,
  ADD COLUMN thin_text TINYINT(1) NOT NULL DEFAULT 0 AFTER state,
  ADD COLUMN char_count INT NULL AFTER thin_text,
  ADD COLUMN byte_size BIGINT NULL AFTER char_count,
  ADD COLUMN type_confidence VARCHAR(16) NULL AFTER byte_size,
  ADD COLUMN type_reason VARCHAR(512) NULL AFTER type_confidence,
  ADD COLUMN type_confirmed TINYINT(1) NOT NULL DEFAULT 0 AFTER type_reason,
  ADD COLUMN textract_job_id VARCHAR(128) NULL AFTER type_confirmed,
  ADD COLUMN textract_api VARCHAR(32) NULL AFTER textract_job_id,
  ADD INDEX idx_document_state (tenant_id, state);
