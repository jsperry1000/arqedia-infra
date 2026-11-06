-- 054_memo_workspace_name.sql
--
-- A memorandum keeps the workspace name it was generated under (decided 6
-- November 2026, with workspace renaming). PROPOSED, and not applied.
--
-- WHY. A memo's Workspace row - on the memo page and in the PDF's masthead -
-- is not in its stored text. It is filled from the workspace row each time
-- the memo is read (app.py _with_identity, render/app.py _memo), so renaming
-- a workspace would rename it on every memorandum already written in it.
-- A memorandum from March must read in September as it did in March.
--
-- HOW. NULL means "the workspace's name now". Renaming a workspace first
-- stamps the old name on every memo of that workspace still NULL
-- (workspaces.rename), then renames. A memo generated under a name therefore
-- keeps it through every later rename; a memo generated since the last
-- rename reads the current name, which is the one it was generated under.
-- A revision takes its parent's value (app.py revise_memo).
--
-- APPLY BEFORE DEPLOYING THE CODE THAT READS IT. Every memo read selects this
-- column; without it, no memorandum opens.
--
-- ADDITIVE. One nullable column; nothing is dropped and no row's value
-- changes.

ALTER TABLE memo
  ADD COLUMN workspace_name VARCHAR(128) NULL AFTER workspace_id;
