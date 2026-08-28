-- 006_authorship_and_revisions.sql
--
-- Three additions, all additive.
--
-- 1. Authorship. Nothing recorded who did what. The token carries an email on
--    every request and it was being discarded. In a compliance record the
--    author of an act matters as much as the act.
--
-- 2. Active state on a filed document. A superseded file must be excluded
--    from the next memo without being deleted - the diligence file keeps
--    everything it was ever given, and records what was set aside.
--
-- 3. Memo revisions. An edited memo is a NEW row, not an update: the original
--    and its PDF stay exactly as generated. Each revision stores its own
--    markdown and its own PDF, so "the memo as it stood on the third" is a
--    file read rather than a reconstruction. A diff remains derivable from
--    any two versions, but it is not the record of authorship.

ALTER TABLE document
  ADD COLUMN uploaded_by VARCHAR(255) NULL AFTER filed_at,
  ADD COLUMN active TINYINT(1) NOT NULL DEFAULT 1 AFTER uploaded_by,
  ADD COLUMN deactivated_by VARCHAR(255) NULL AFTER active,
  ADD COLUMN deactivated_at DATETIME NULL AFTER deactivated_by,
  ADD INDEX idx_document_active (tenant_id, active);

ALTER TABLE memo
  ADD COLUMN generated_by VARCHAR(255) NULL AFTER generated_at,
  ADD COLUMN parent_memo_id BIGINT NULL AFTER generated_by,
  ADD COLUMN revision INT NOT NULL DEFAULT 1 AFTER parent_memo_id,
  ADD COLUMN modified_by VARCHAR(255) NULL AFTER revision,
  ADD COLUMN modified_at DATETIME NULL AFTER modified_by,
  ADD INDEX idx_memo_parent (tenant_id, parent_memo_id);
