--
-- 055_workspace_watermark.sql
--
-- A workspace's own text on the watermark of what it shares (decided 9
-- November 2026). PROPOSED, and not applied.
--
-- WHAT. The diagonal mark burned into a shared memorandum reads
-- "<recipient>  ·  shared by <tenant>". A workspace may now put its own text
-- in front of it - "STRICTLY CONFIDENTIAL", say. The recipient's address is
-- always kept, so an onward copy stays attributable (share_viewer_spec
-- section 4). The footer lines - shared on, downloaded on - are not touched.
--
-- Set by an administrator (workspaces.set_watermark). NULL is no text of the
-- workspace's own: the mark as it has always been.
--
-- READ AT SEND. A share is rendered and stamped once, when it is sent, and
-- never again, so a change reaches shares sent after it and none before.
--
-- APPLY BEFORE DEPLOYING THE CODE THAT READS IT. Sending a share and listing
-- workspaces both select this column; without it, both fail.
--
-- ADDITIVE. One nullable column; nothing is dropped and no row's value
-- changes.

ALTER TABLE workspace
  ADD COLUMN watermark_text VARCHAR(60) NULL AFTER name;
