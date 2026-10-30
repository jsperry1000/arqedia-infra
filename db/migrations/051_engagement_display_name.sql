-- 051_engagement_display_name.sql
--
-- An engagement can be renamed on the screen without moving anything
-- (29 October 2026). PROPOSED, and not applied.
--
-- WHY NOT RENAME engagement.name. name is the string in every storage key
-- under docs/ and memos/, and the normalizer resolves a new upload to its
-- row by it (engagement_id(), mirrored in lambda/normalizer/app.py). Changing
-- it would send the next upload under the old folder to a new, empty
-- engagement. name stays what it is; display_name is what people see.
--
-- DECIDED 29 October 2026:
--   - shown on every screen, and in the Engagement row of a memorandum
--     generated after the rename. A memorandum already generated keeps the
--     name it was written with: its text is what it said.
--   - any seat may rename, as any seat sets the subject or archives.
--   - unique within a workspace, against every other engagement's shown
--     name, so the list never holds two identical rows. Checked by the API;
--     the folded collation makes the check case-blind, as uq_engagement_name
--     is.
--
-- NULL means "shown as name", and clearing a display name sets it back to
-- NULL. renamed_by and renamed_at say who set what is shown now.
--
-- ADDITIVE. Three nullable columns; nothing is dropped and no row's value
-- changes.

ALTER TABLE engagement
  ADD COLUMN display_name VARCHAR(120) NULL AFTER name,
  ADD COLUMN renamed_by   VARCHAR(255) NULL,
  ADD COLUMN renamed_at   DATETIME     NULL;
