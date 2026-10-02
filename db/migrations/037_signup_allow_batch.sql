-- 037_signup_allow_batch.sql
--
-- A second batch of invited addresses, added to the gate seeded in
-- 027_signup_allow.sql. The gate is unchanged: signup stays invite-only,
-- one address at a time, each row an individual decision. This file only
-- lengthens the list.
--
-- ADDITIVE. One set of rows into an existing table. Nothing is touched,
-- nothing is removed, no column or policy changes.
--
-- INSERT IGNORE, not INSERT. Three addresses from the same batch were asked
-- for that already exist from 027 - markperry1000@gmail.com,
-- mgargaros@ebl-finance.com and lnees@fairleadmgt.com - and are deliberately
-- NOT repeated here, so 037 inserts only the six that are new. IGNORE is kept
-- anyway: if one of these six was added to the live table by hand before this
-- ran, the migration must still complete rather than fail on a duplicate key,
-- and IGNORE never overwrites an existing row's note or added_at.
--
-- LOWERCASED ON THE WAY IN, as 027 is and for the same reason: the lookup in
-- lambda/signup/app.py compares lowercased, and a mixed-case row is a trap for
-- the day somebody compares in Python. Every address below is already lower
-- case; LOWER() keeps that true if this file is ever edited.
--
-- TWO ADDRESSES AT mars8.co.uk. Both are invited, and _checks() lets an
-- allowlisted address past the one-trial-per-domain rule, so both may sign up.
-- Whichever signs up first claims mars8.co.uk in tenant_domain; the second
-- gets its own tenant with NO domain claim, which is the documented behaviour
-- for a second invited address at one firm. See verify() in signup/app.py.

INSERT IGNORE INTO signup_allow (email, note, added_by) VALUES
  (LOWER('jmpecoraro@mars8.co.uk'),          'mars8.co.uk',                      'migration 037'),
  (LOWER('aelkorde@mars8.co.uk'),            'mars8.co.uk (second at this firm)', 'migration 037'),
  (LOWER('j.stillwaggon@interportcap.com'),  'interportcap.com',                 'migration 037'),
  (LOWER('rene.baars@baarsconsultancy.ch'),  'baarsconsultancy.ch',              'migration 037'),
  (LOWER('ms@bellatrixadvisors.com'),        'bellatrixadvisors.com',            'migration 037'),
  (LOWER('mgargaros@vmac.com'),              'vmac.com',                         'migration 037');


-- Verification
--
--   SELECT email, note FROM signup_allow WHERE added_by = 'migration 037' ORDER BY email
--
-- Expect six rows, every address lower case:
--   aelkorde@mars8.co.uk
--   j.stillwaggon@interportcap.com
--   jmpecoraro@mars8.co.uk
--   mgargaros@vmac.com
--   ms@bellatrixadvisors.com
--   rene.baars@baarsconsultancy.ch
--
--   SELECT COUNT(*) FROM signup_allow WHERE added_by = 'migration 037'
--
-- Expect six (this batch). The table total is six higher than before 037; on
-- the live table at apply time that was twelve - four seeded by 027, two added
-- by hand (added_by 'sperry'), and these six. The two hand-added rows are not
-- tracked by any migration, which is why a total asserted here would drift.
--
--   SELECT COUNT(*) FROM signup_allow WHERE email <> LOWER(email)
--
-- Expect 0.
--
--   SELECT filename FROM schema_migration WHERE filename = '037_signup_allow_batch.sql'
--
-- Expect one row.
