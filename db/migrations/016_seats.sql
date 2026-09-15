-- 016_seats.sql
--
-- Who belongs to a tenant, and what they may do.
--
-- Until now a tenant was whoever held a token carrying its id, and a role was
-- a claim on that token with nothing behind it. This is the table that claim
-- refers to.
--
-- Additive. Nothing existing is touched, and the two hand-made tenants are
-- backfilled from the Cognito users that already exist for them at the foot
-- of this file.

-- --- a seat ----------------------------------------------------------------
--
-- The plan buys a fixed number and the count is what matters, so a seat is
-- either taken or it is not. There is no half state.
--
-- role:
--   admin    everything, including the plan, the card, the brand and seats
--   member   the work itself - upload, file, generate, configure, share
--
-- Two roles and not five. A Member can publish configuration and share a
-- memorandum, because those are the job; what they cannot do is spend money
-- in a way that recurs or change who else has access. Any further division is
-- a permission system, and nobody has asked for one.

CREATE TABLE seat (
  seat_id      BIGINT       NOT NULL AUTO_INCREMENT,
  tenant_id    BIGINT       NOT NULL,
  email        VARCHAR(255) NOT NULL,
  role         VARCHAR(16)  NOT NULL DEFAULT 'member',
  invited_by   VARCHAR(255) NULL,
  accepted_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (seat_id),
  UNIQUE KEY uq_email (email),
  KEY idx_tenant (tenant_id, role)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- uq_email is on the address alone, not on (tenant, address). One address
-- belongs to one tenant. Somebody who genuinely works for two firms uses two
-- addresses, which is also how every other system they use behaves.

-- --- an invitation ---------------------------------------------------------
--
-- A SEAT IS TAKEN ON ACCEPTANCE, NOT ON INVITATION. An invitation reserves
-- one, and the reservation lapses.
--
-- The failure this avoids: an administrator invites three people, two never
-- reply, and the firm has paid for five seats and can use three. A
-- reservation that expires returns the seat without anybody having to notice
-- it was gone.
--
-- Seven days, which is long enough to survive a holiday and short enough that
-- nobody has to chase.

CREATE TABLE seat_invitation (
  invitation_id BIGINT       NOT NULL AUTO_INCREMENT,
  tenant_id     BIGINT       NOT NULL,
  email         VARCHAR(255) NOT NULL,
  role          VARCHAR(16)  NOT NULL DEFAULT 'member',
  token_hash    CHAR(64)     NOT NULL,
  invited_by    VARCHAR(255) NOT NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at    DATETIME     NOT NULL,
  revoked_at    DATETIME     NULL,
  PRIMARY KEY (invitation_id),
  UNIQUE KEY uq_open (email),
  KEY idx_tenant (tenant_id),
  KEY idx_expiry (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- The token is stored as a hash, as a password would be. It arrives in a link
-- somebody clicks, so a read of this table must not let anybody accept an
-- invitation that is not theirs.
--
-- uq_open is on the address, so inviting the same person twice replaces the
-- first invitation rather than leaving two live. Revoked and expired rows are
-- cleared by the accept path before a new one is written; keeping history of
-- who was invited and never joined is not worth a second table.

-- --- what exists already ---------------------------------------------------
--
-- The tenants created by hand have Cognito users and no seats, which would
-- read as nobody belonging to them and lock their own administrators out.
--
-- Named rather than derived: the Cognito pool cannot be read from SQL, and
-- guessing is worse than stating it. These three are the users that exist in
-- us-east-2_AcsEyzDLL as at 15 September 2026, each already carrying
-- custom:role = admin.
--
-- Tenant 2 has two, which is the isolation-test pair from the 9 September
-- handoff. Both are seated, or the test stops working.
--
-- Anyone else on either tenant is invited through the product, like
-- everybody else will be.

INSERT INTO seat (tenant_id, email, role, invited_by) VALUES
  (1, 'sperry@vmac.com',              'admin', 'migration 016'),
  (2, 'jonathanscottperry@gmail.com', 'admin', 'migration 016'),
  (2, 'joeschmoe1000@gmail.com',      'admin', 'migration 016');
