-- 011_document_parts.sql
-- One uploaded file may hold several documents. Pipeline spec §4 requires the
-- classifier to detect boundaries and propose parts; stage 2 was built without
-- it, so every upload has been one document regardless of what it contained.
--
-- Additive only. Three nullable columns, no defaults, no backfill. Every
-- existing row stays valid with all three NULL, which reads correctly: the
-- file held one document and was filed whole.
--
-- No parent row and no parent_document_id. Nothing is cut - every part points
-- at the same s3_key as the file it came from, so the uploaded file is
-- openable because it never went anywhere. Parts of one upload are grouped by
-- (tenant_id, s3_key), which the new index serves.
--
-- Page numbers stay the FILE's own, not the part's. A part covering pages 21
-- to 30 records page_from 21, and a value read from its tenth page cites page
-- 30. That is what keeps a citation resolving against the file a reader was
-- given, and it is why these columns are page numbers rather than an offset.

ALTER TABLE document
  ADD COLUMN part_index INT NULL
    COMMENT 'Ordinal of this part within its file, from 1. NULL = filed whole.'
    AFTER page_count,
  ADD COLUMN page_from INT NULL
    COMMENT 'First page of this part in the FILE, 1-based inclusive. NULL = filed whole.'
    AFTER part_index,
  ADD COLUMN page_to INT NULL
    COMMENT 'Last page of this part in the FILE, 1-based inclusive. NULL = filed whole.'
    AFTER page_from;

-- Both or neither, and a range that runs forwards. A part with one bound
-- cannot be sliced from the envelope and cannot be drilled back to; enforcing
-- it here means no caller has to remember.
ALTER TABLE document
  ADD CONSTRAINT chk_document_page_range CHECK (
    (page_from IS NULL AND page_to IS NULL)
    OR (page_from IS NOT NULL AND page_to IS NOT NULL
        AND page_from >= 1 AND page_from <= page_to)
  );

-- "Every part of this upload." Serves the review screen, which groups parts
-- under the file they came from, and the source viewer.
ALTER TABLE document
  ADD INDEX idx_document_source (tenant_id, s3_key(255));

-- Classification is inference that is never charged, and pipeline spec §8.1
-- open item 2 says the notional price of the daily allowance must be set from
-- measured token cost during build rather than assumed. classify.py reads
-- usage off the Bedrock response today and discards it, so there is nothing to
-- measure from. Segmentation is a bigger call than classification was; this is
-- the cheapest moment to start recording what it costs.
ALTER TABLE document
  ADD COLUMN classify_tokens_in INT NULL
    COMMENT 'Input tokens for the segmentation and classification pass.'
    AFTER type_reason,
  ADD COLUMN classify_tokens_out INT NULL
    COMMENT 'Output tokens for the same pass.'
    AFTER classify_tokens_in;


-- Verification
--
--   SHOW CREATE TABLE document;
--
-- Expect part_index, page_from, page_to, classify_tokens_in and
-- classify_tokens_out all nullable with no default, chk_document_page_range
-- present, and idx_document_source on (tenant_id, s3_key(255)).
--
--   SELECT COUNT(*) FROM document WHERE page_from IS NOT NULL;
--
-- Expect 0. Nothing is backfilled; every document filed before this migration
-- was filed whole and stays that way.
