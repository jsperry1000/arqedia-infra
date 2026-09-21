-- 030_engagement_and_memo_state.sql
--
-- An engagement becomes a row, and a memorandum gains a state. PROPOSED,
-- and not applied.
--
-- WRITTEN AS 029 AND RENUMBERED. 029_document_extraction_error.sql was
-- written the same day and is not yet pushed; two files claiming one number
-- is how a migration gets applied twice or not at all.
--
-- THE FIRST VERSION OF THE BACKFILL FAILED ON DEV, 21 September:
--
--   Error code: 1260; SQLState: HY000
--   Row 162 was cut by GROUP_CONCAT()
--
-- It picked the earliest uploader with
-- SUBSTRING_INDEX(GROUP_CONCAT(who ORDER BY at), 0x1F, 1), and
-- group_concat_max_len is 1024 bytes. Three engagements on dev hold
-- seventy-odd documents at twenty-three characters an address, which is
-- 1848 bytes for the largest - so the trick worked on every small
-- engagement and cut the one that mattered. It is replaced below by an
-- INSERT that takes no uploader and an UPDATE that reads the earliest
-- document's, which builds no string and has no length to exceed.
--
-- WHAT THE FAILURE LEFT: the empty `engagement` table and nothing else. The
-- statements after it never ran, `migrate.ps1` records a migration only
-- after every statement in it has succeeded, and no document or memo was
-- altered. The table was dropped by hand before the corrected version ran,
-- which is why CREATE TABLE below is unchanged and carries no IF NOT
-- EXISTS: this file describes an empty database and says so plainly.
--
-- EDITED, NOT SUPERSEDED. A merged migration is normally immutable, and
-- this one is the exception because it never applied anywhere: nothing
-- holds a row it wrote, no schema_migration names it, and a 031 repairing a
-- 030 that never ran would leave two files describing one intention and
-- invite somebody to apply the broken one first.
--
-- WHY. An engagement is a string somebody typed, cleaned by _clean(), and
-- thereafter a folder name in two buckets. Nothing records who opened it,
-- when, or whether it is finished; list_engagements derives the list by
-- SUBSTRING_INDEX over document keys, so an engagement with no documents
-- does not exist and cannot be created before a file is uploaded to it. A
-- memorandum has no state at all: 118 of them on dev, every one listed for
-- ever, with no way to put a finished matter away.
--
-- ADDITIVE THROUGHOUT. One new table, three new columns on memo, and two
-- columns that already exist and have never held a value - document.
-- engagement_id and memo.engagement_id, NULL on all 118 memos and every
-- document (001_stage1.sql:16,55). Nothing is dropped, nothing is deleted,
-- and the S3 keys do not move: the name stays in the key, because the key
-- is provenance and the normalizer parses it.

-- --- engagement ------------------------------------------------------------
--
-- name is the string as it appears in the S3 key, so it is bounded by
-- _clean()'s 120 characters and its [A-Za-z0-9._-] alphabet.
--
-- THE UNIQUE KEY FOLDS CASE, because the column's collation does
-- (utf8mb4_0900_ai_ci), and that is the decision of 21 September: two
-- spellings of one name are one engagement. Verified safe before writing
-- this - no tenant on dev holds two spellings of a name today:
--
--   GROUP BY tenant_id, LOWER(e) HAVING COUNT(DISTINCT e) > 1
--   (no rows; 0 updated)
--
-- From here, "Meridian" and "meridian" are one engagement in the database
-- and would be two folders in S3, which is why the API resolves a name to
-- this row rather than minting a second.
--
-- status is open | archived, and archiving hides an engagement from the
-- lists. It deletes nothing, blocks nothing addressed directly, and does
-- NOT cascade to the memoranda in it (decision of 21 September): each
-- memorandum keeps its own state, so unarchiving restores what was there.

CREATE TABLE engagement (
  engagement_id BIGINT       NOT NULL AUTO_INCREMENT,
  tenant_id     BIGINT       NOT NULL,
  name          VARCHAR(120) NOT NULL,
  status        VARCHAR(16)  NOT NULL DEFAULT 'open',
  created_by    VARCHAR(255) NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  archived_by   VARCHAR(255) NULL,
  archived_at   DATETIME     NULL,
  PRIMARY KEY (engagement_id),
  UNIQUE KEY uq_engagement_name (tenant_id, name),
  KEY idx_engagement_tenant_status (tenant_id, status),
  CONSTRAINT chk_engagement_status CHECK (status IN ('open', 'archived'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --- backfill, from the keys themselves --------------------------------------
--
-- Documents and memos together, because a memorandum's engagement must
-- survive the deletion of the last document in it (8.2 made that possible).
-- Today no such memorandum exists - checked, not assumed:
--
--   SELECT ... FROM memo m WHERE NOT EXISTS (SELECT 1 FROM document d ...)
--   (no rows; 0 updated)
--
-- created_at is the earliest thing seen in it. created_by follows in its own
-- statement: whoever uploaded that earliest document, NULL for anything
-- filed before uploaded_by was recorded, and NULL for an engagement known
-- only from a memo. Left NULL rather than guessed.
--
-- TWO STATEMENTS RATHER THAN ONE, and that is the fix. Picking the earliest
-- uploader inside the aggregate meant building a string of every uploader in
-- the engagement and taking its first field, which cut at 1024 bytes on the
-- three largest (see the header). A correlated read of one row has no length
-- to exceed and says what it means.

INSERT INTO engagement (tenant_id, name, created_at)
SELECT k.tenant_id, k.name, MIN(k.at)
FROM (
  SELECT tenant_id,
         SUBSTRING_INDEX(SUBSTRING_INDEX(s3_key, '/docs/', -1), '/', 1) AS name,
         filed_at AS at
  FROM document
  UNION ALL
  SELECT tenant_id,
         SUBSTRING_INDEX(SUBSTRING_INDEX(s3_key, '/memos/', -1), '/', 1),
         generated_at
  FROM memo
) k
GROUP BY k.tenant_id, k.name;

UPDATE engagement e
   SET created_by = (
       SELECT d.uploaded_by
       FROM document d
       WHERE d.tenant_id = e.tenant_id
         AND SUBSTRING_INDEX(
               SUBSTRING_INDEX(d.s3_key, '/docs/', -1), '/', 1) = e.name
       ORDER BY d.filed_at
       LIMIT 1)
 WHERE e.created_by IS NULL;

-- --- the two columns that were always there ---------------------------------

UPDATE document d
  JOIN engagement e
    ON e.tenant_id = d.tenant_id
   AND e.name = SUBSTRING_INDEX(SUBSTRING_INDEX(d.s3_key, '/docs/', -1), '/', 1)
   SET d.engagement_id = e.engagement_id
 WHERE d.engagement_id IS NULL;

UPDATE memo m
  JOIN engagement e
    ON e.tenant_id = m.tenant_id
   AND e.name = SUBSTRING_INDEX(SUBSTRING_INDEX(m.s3_key, '/memos/', -1), '/', 1)
   SET m.engagement_id = e.engagement_id
 WHERE m.engagement_id IS NULL;

CREATE INDEX idx_document_engagement ON document (tenant_id, engagement_id);
CREATE INDEX idx_memo_engagement     ON memo (tenant_id, engagement_id);

-- --- a memorandum's state ----------------------------------------------------
--
-- live | archived, and nothing else. Not draft: there is no such thing - a
-- memorandum exists the moment composition writes it, and an edit is a new
-- revision rather than a state (revise_memo).
--
-- THE STATE BELONGS TO THE LINE, NOT THE ROW. A memo and its revisions are
-- one document to the person who wrote it, so archiving writes every row of
-- the line in one statement - WHERE memo_id = :root OR parent_memo_id =
-- :root - which is the same shape revise_memo already uses to find the next
-- revision number. Stored on every row rather than only on the root so that
-- a list answers from the row it already has, with no join on the hot path;
-- a new revision inherits its parent's state at insert.
--
-- ARCHIVED IS NOT DELETED AND NOT HIDDEN. It filters lists. Anything that
-- addresses a memorandum directly - GET /memos/{id}, its PDF, a share grant
-- if one is ever built - still resolves it, because a link somebody was
-- given must not rot because a matter was tidied away.

ALTER TABLE memo
  ADD COLUMN state       VARCHAR(16)  NOT NULL DEFAULT 'live' AFTER revision,
  ADD COLUMN archived_by VARCHAR(255) NULL AFTER state,
  ADD COLUMN archived_at DATETIME     NULL AFTER archived_by,
  ADD CONSTRAINT chk_memo_state CHECK (state IN ('live', 'archived'));

CREATE INDEX idx_memo_state ON memo (tenant_id, engagement_id, state);


-- Verification
--
--   SELECT COUNT(*) FROM engagement
--
-- Expect 29 on dev at the time of writing - 28 when this was first drafted,
-- and one more uploaded into since. The number to check it against is this,
-- read at the moment of applying rather than taken from here:
--
--   SELECT COUNT(*) FROM (
--     SELECT tenant_id, SUBSTRING_INDEX(SUBSTRING_INDEX(s3_key,'/docs/',-1),'/',1) AS n
--     FROM document
--     UNION
--     SELECT tenant_id, SUBSTRING_INDEX(SUBSTRING_INDEX(s3_key,'/memos/',-1),'/',1)
--     FROM memo) k
--
--   SELECT COUNT(*) FROM document WHERE engagement_id IS NULL
--   SELECT COUNT(*) FROM memo     WHERE engagement_id IS NULL
--
-- Expect 0 and 0. Anything above zero is a key that did not match the
-- pattern, and must be looked at rather than defaulted.
--
--   SELECT COUNT(*) FROM memo WHERE state <> 'live'
--
-- Expect 0: nothing is archived by this migration.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '030_engagement_and_memo_state.sql'
--
-- Expect one row.
--
--
-- DEPLOY ORDER. This migration first, and the code that writes these columns
-- second. The writers insert `state` and `engagement_id` by name, so code
-- deployed against a database without them fails on every memo written and
-- every document analysed. Nothing reads them yet: the lists still match on
-- the S3 key, and switching them over is stage 4, which is not built.
