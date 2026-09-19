-- 027_signup_allow.sql
--
-- Who may create an account.
--
-- Signup was open to anyone. The checks in lambda/signup/app.py were about
-- ABUSE VOLUME AND DUPLICATION, never about identity: a disposable-domain
-- list, one trial per email domain, and two rate limits. Anyone with a real
-- mailbox on an unclaimed domain got a tenant, a fourteen-day trial and $5.00
-- of metered credit.
--
-- This table is the gate. An address in it may sign up; nothing else may.
--
-- FAILS SHUT. An empty table refuses everyone, including us, which is why the
-- seed is in this migration rather than left for afterwards. A gate that
-- defaults to open is not a gate.
--
-- NOTHING IS GRANTED BY DOMAIN. There is no domain column and there will not
-- be one: a domain entry admits everyone at a firm, which is the thing being
-- closed. Each row is an individual decision.
--
-- LOWERCASED ON THE WAY IN. The route already lowercases every address it
-- reads (app.py, begin/verify/accept), and the collation below is _ci so a
-- lookup would match either way - but a row stored in mixed case is a trap
-- for the day somebody compares in Python instead of in SQL, or changes the
-- collation to _bin. LOWER() here means the stored value is never the odd one
-- out.
--
-- Additive: one new table. Nothing existing is touched.

CREATE TABLE signup_allow (
  email      VARCHAR(255) NOT NULL,
  note       VARCHAR(255) NULL,
  added_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  added_by   VARCHAR(255) NULL,
  PRIMARY KEY (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- The seed. Without it nobody can sign up at all.

INSERT INTO signup_allow (email, note, added_by) VALUES
  (LOWER('admin@hnet.energy'), 'hnet.energy', 'migration 027'),
  (LOWER('markperry1000@gmail.com'), 'gmail - domain held by tenant 0', 'migration 027'),
  (LOWER('mgargaros@ebl-finance.com'), 'ebl-finance.com - domain held by tenant 5', 'migration 027'),
  (LOWER('lnees@fairleadmgt.com'), 'fairleadmgt.com', 'migration 027');


-- Verification
--
--   SELECT email, note, added_by FROM signup_allow ORDER BY email
--
-- Expect four rows, every address lower case:
--   admin@hnet.energy
--   lnees@fairleadmgt.com
--   markperry1000@gmail.com
--   mgargaros@ebl-finance.com
--
--   SELECT COUNT(*) FROM signup_allow WHERE email <> LOWER(email)
--
-- Expect 0. Any row here is one a lookup in Python would miss.
--
--   SELECT filename FROM schema_migration WHERE filename = '027_signup_allow.sql'
--
-- Expect one row.
--
-- TWO OF THE FOUR ARE AT DOMAINS THAT ARE ALREADY CLAIMED - gmail.com by
-- tenant 0 and ebl-finance.com by tenant 5. That is deliberate and is why
-- _checks() lets an allowlisted address past the one-trial-per-domain rule.
-- Their tenants will have NO row in tenant_domain, because the claim that
-- exists is never replaced. See verify() in lambda/signup/app.py.
