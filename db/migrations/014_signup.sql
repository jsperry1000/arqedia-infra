-- 014_signup.sql
--
-- What a tenant needs in order to have been created by somebody rather than
-- by us, and the two tables that make the abuse controls possible.
--
-- Additive only. Every column is nullable with no default, so the two tenants
-- already in the table stay valid and nothing is backfilled - they were
-- created by hand and did not declare anything.

-- --- what was declared at signup -------------------------------------------
--
-- The declared jurisdiction binds, not the address the request came from. It
-- decides the terms the tenant contracts on, so it is recorded rather than
-- inferred.
--
-- region already exists and is already immutable in practice. Nothing here
-- changes it.

ALTER TABLE tenant
  ADD COLUMN jurisdiction   VARCHAR(64)  NULL AFTER region,
  ADD COLUMN trial_ends_at  DATETIME     NULL AFTER plan,
  ADD COLUMN signup_ip      VARCHAR(45)  NULL AFTER created_at,
  ADD COLUMN forked_pack    VARCHAR(64)  NULL AFTER active_revision;

-- --- one trial per email domain --------------------------------------------
--
-- The rule, and the lift. A holding company with three trading names on one
-- domain, or a consultant wanting a tenant per client, is a real case and not
-- a reason to abandon the rule. Support sets multi_allowed and the domain may
-- hold more than one tenant.
--
-- The lift exists from the same day the rule does. Without it the first real
-- customer the rule catches is a support incident with no resolution.

CREATE TABLE tenant_domain (
  domain         VARCHAR(255) NOT NULL,
  tenant_id      BIGINT       NOT NULL,
  multi_allowed  TINYINT(1)   NOT NULL DEFAULT 0,
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (domain),
  KEY idx_tenant (tenant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --- what was attempted, and what came of it -------------------------------
--
-- Every signup attempt, whether it succeeded or not. Two jobs:
--
--   rate limiting  - count recent rows for an address or a domain
--   review         - when an abuse flag fires, a person can see that nine
--                    attempts came from one connection
--
-- THE IP ADDRESS IS A SIGNAL AND NEVER A GATE. Blocking on it fails in both
-- directions: a VPN defeats it in seconds, while a shared office connection
-- blocks strangers who have nothing to do with each other. It is recorded so
-- a human can look, and nothing decides on it alone.
--
-- An IP address is personal data in the EU and the UK. This column needs a
-- lawful basis stated in the privacy policy and a retention limit - see
-- ONB-01. Ninety days is the usual answer and there is no job to enforce it
-- yet.

CREATE TABLE signup_attempt (
  attempt_id    BIGINT       NOT NULL AUTO_INCREMENT,
  email_domain  VARCHAR(255) NOT NULL,
  email_hash    CHAR(64)     NOT NULL,   -- sha256; the address itself is not kept
  ip            VARCHAR(45)  NULL,
  outcome       VARCHAR(32)  NOT NULL,   -- created | domain_taken | disposable | rate_limited | failed
  detail        VARCHAR(255) NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (attempt_id),
  KEY idx_domain_time (email_domain, created_at),
  KEY idx_ip_time (ip, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- The address is hashed rather than stored. Rate limiting needs to know that
-- the same address tried twice; it does not need to know the address. A
-- failed attempt is not a customer and we should not be holding a list of
-- people who did not sign up.

-- --- a signup part way through ---------------------------------------------
--
-- Between "tell us who you are" and "here is the code from your email".
--
-- Nothing is created until the code comes back. That is what stops a
-- throwaway address taking a trial, and it is why this table exists rather
-- than a half-made tenant.
--
-- THE PASSWORD IS NOT HERE. The browser holds what the person typed and sends
-- it with the code. We never store a password, not even for ninety seconds,
-- and there is nothing in this table worth stealing.
--
-- The code is stored as a hash for the same reason a password would be: a
-- read of this table must not let somebody complete a signup that is not
-- theirs.

CREATE TABLE pending_signup (
  pending_id    BIGINT       NOT NULL AUTO_INCREMENT,
  email         VARCHAR(255) NOT NULL,
  email_domain  VARCHAR(255) NOT NULL,
  code_hash     CHAR(64)     NOT NULL,
  attempts      INT          NOT NULL DEFAULT 0,
  org_name      VARCHAR(255) NULL,
  jurisdiction  VARCHAR(64)  NULL,
  region        VARCHAR(32)  NULL,
  pack          VARCHAR(64)  NULL,
  second_admin  VARCHAR(255) NULL,
  ip            VARCHAR(45)  NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at    DATETIME     NOT NULL,
  PRIMARY KEY (pending_id),
  UNIQUE KEY uq_email (email),
  KEY idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- One row per address, replaced on a second attempt. Asking for the code
-- again should send a new one rather than leave two valid.
