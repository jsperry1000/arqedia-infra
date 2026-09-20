-- 028_memo_source_filename.sql
--
-- The name a memo's source was filed under, kept on the link rather than only
-- on the document. PROPOSED, and not applied.
--
-- WHY IT EXISTS. A filed document can now be deleted, with the facts extracted
-- from it (decision of 20 September). Memoranda already generated are left
-- untouched: their text stands. But a memo resolves its citations by FILENAME
-- - the markdown carries no identifiers, and Memo.tsx builds a filename ->
-- document_id map out of what get_memo returns - so once the document row is
-- gone the filename is gone with it, and every citation naming that file
-- silently stops being a citation and becomes ordinary prose.
--
-- That is the one outcome the decision explicitly refused. Keeping the name on
-- memo_source is what lets a deleted source still appear in the memo's sources
-- marked as removed, and its citations render as present but not clickable.
--
-- WRITTEN ONLY BY THE DELETE. Composition does not fill this in: a source
-- whose document still exists reads its name from the document, which is the
-- one true copy. The delete copies the name across for the rows it is about to
-- orphan, immediately before it removes the row, inside the same transaction.
-- So the column is NULL for every source of every document that still exists,
-- which is the ordinary case and is not a gap.
--
-- No backfill for the same reason. Every existing row's document is still
-- there.
--
-- Additive. One nullable column, no default, no index: it is read only through
-- memo_source's existing primary key.

ALTER TABLE memo_source
  ADD COLUMN filename VARCHAR(255) NULL AFTER document_id;


-- Verification
--
--   SHOW COLUMNS FROM memo_source LIKE 'filename'
--
-- Expect one row: varchar(255), Null YES, Default NULL.
--
--   SELECT COUNT(*) FROM memo_source WHERE filename IS NOT NULL
--
-- Expect 0 until the first filed document is deleted.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '028_memo_source_filename.sql'
--
-- Expect one row.
