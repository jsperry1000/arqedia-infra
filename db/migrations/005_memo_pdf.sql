-- 005_memo_pdf.sql
-- The PDF is the deliverable; the markdown remains the intermediate it is
-- rendered from.

ALTER TABLE memo
  ADD COLUMN pdf_key VARCHAR(1024) NULL AFTER s3_version_id,
  ADD COLUMN pdf_version_id VARCHAR(255) NULL AFTER pdf_key;
