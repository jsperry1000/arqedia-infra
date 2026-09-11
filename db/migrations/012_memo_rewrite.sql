-- 012_memo_rewrite.sql
-- A section of a memo rewritten by the model, at a person's prompt.
--
-- Additive only. One new table, no change to memo and no backfill.
--
-- One row per section per Go, written when the rewrite starts and completed
-- when the model returns. Rewrites that are discarded stay on record with
-- their token counts, which is the per-tenant cost record while rewriting is
-- free.
--
-- The revision itself is still an ordinary memo row made by revise. A row
-- here with accepted_in_memo_id set says that revision carries model-written
-- text, which section, at whose prompt and with which model. The revision
-- note is read from this table, so memo needs no new column.
--
-- input_text keeps what the model was given, so a rewrite can be checked
-- against its input afterwards rather than trusted.

CREATE TABLE memo_rewrite (
  rewrite_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  tenant_id           BIGINT        NOT NULL,
  memo_id             BIGINT        NOT NULL COMMENT 'The memo the section was rewritten from.',
  section_heading     VARCHAR(512)  NOT NULL,
  prompt              TEXT          NOT NULL,
  prompted_by         VARCHAR(255)  NOT NULL,
  model_id            VARCHAR(255)  NULL,
  input_text          MEDIUMTEXT    NOT NULL COMMENT 'What the model was given.',
  output_text         MEDIUMTEXT    NULL     COMMENT 'What it returned, citations restored.',
  citations_dropped   INT           NULL,
  tokens_in           INT           NULL,
  tokens_out          INT           NULL,
  status              VARCHAR(16)   NOT NULL,
  error               VARCHAR(1024) NULL,
  created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at        DATETIME      NULL,
  accepted_in_memo_id BIGINT        NULL COMMENT 'The revision it was saved into. NULL = not accepted.',
  INDEX idx_memo_rewrite_memo (tenant_id, memo_id),
  INDEX idx_memo_rewrite_accepted (tenant_id, accepted_in_memo_id),
  CONSTRAINT chk_memo_rewrite_status CHECK (status IN ('running', 'done', 'failed'))
);


-- Verification
--
--   SHOW CREATE TABLE memo_rewrite
--
-- Expect seventeen columns, both indexes and chk_memo_rewrite_status.
--
--   SELECT filename FROM schema_migration WHERE filename = '012_memo_rewrite.sql'
--
-- Expect one row.
