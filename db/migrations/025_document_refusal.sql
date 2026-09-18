-- 025_document_refusal.sql
--
-- Why a document could not be read, on the document itself.
--
-- Unreadable documents decision record, 18 September 2026, item 1: no upload
-- may end in silence. Until now the normalizer had exits that wrote nothing -
-- a refused file produced no row, no message and no trace, and the review
-- screen waited ten minutes for something no process would ever create.
--
-- A refusal now writes a row like any other, in state 'unreadable', carrying
-- these two columns.
--
-- TWO COLUMNS, NOT ONE. The code is what the machine reads: Stage 4 branches
-- on it to send a scan to OCR rather than refuse it, and an operator counts
-- it. The reason is what a person reads, and it is a sentence rather than an
-- error. Neither does the other's job.
--
-- NOT type_reason. That column means why the CLASSIFIER proposed the type it
-- did. After Stage 4 a scan will carry both a refusal history and a type
-- reason, and one column cannot hold two meanings (decision of 18 September).
--
-- NO CHANGE TO state. It is varchar(16) with no CHECK and no enum - 'analysed',
-- 'filed' and 'rejected' are values, not a type - so 'unreadable' needs no
-- migration. Recorded here because the next person will look for it.
--
-- Additive: two nullable columns, no backfill, no constraint touched. Every
-- row already written keeps NULL in both, which is the truth about them.

ALTER TABLE document
  ADD COLUMN refusal_code VARCHAR(32) NULL AFTER state,
  ADD COLUMN refusal_reason VARCHAR(512) NULL AFTER refusal_code;


-- Verification
--
--   SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
--     FROM information_schema.COLUMNS
--    WHERE TABLE_SCHEMA = 'arqedia' AND TABLE_NAME = 'document'
--      AND COLUMN_NAME IN ('refusal_code', 'refusal_reason')
--
-- Expect two rows: refusal_code varchar(32) YES, refusal_reason varchar(512)
-- YES.
--
--   SELECT COUNT(*) FROM document WHERE refusal_code IS NOT NULL
--
-- Expect 0 immediately after this runs. Nothing is backfilled: a document
-- refused before this migration left no row to backfill onto, which is the
-- defect being closed.
--
--   SELECT state, COUNT(*) FROM document GROUP BY state
--
-- Expect analysed, filed and rejected only. 'unreadable' appears once the
-- normalizer carrying Stage 1 is deployed, not before.
--
--   SELECT filename FROM schema_migration WHERE filename = '025_document_refusal.sql'
--
-- Expect one row.
