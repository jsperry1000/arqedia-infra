-- 015_wallet.sql
--
-- The wallet. What a tenant has, where it came from, and what became of it.
--
-- Four tables and one rule that shapes all of them: THE LEDGER IS
-- APPEND-ONLY. Nothing is ever updated or deleted, because a balance that can
-- be edited is not a record of anything. Unreadable material is blocked
-- before filing rather than charged and refunded, which is why there is no
-- reversal and no need for one.
--
-- Additive. Nothing here touches a table that exists.

-- --- what a thing costs ----------------------------------------------------
--
-- A price is data rather than a constant in code, for one reason: Enterprise
-- is negotiated, and a negotiated price must not be a release.
--
-- tenant_id NULL is the standard price. A row naming a tenant overrides it
-- for that tenant and nobody else.

CREATE TABLE meter_price (
  price_id      BIGINT       NOT NULL AUTO_INCREMENT,
  tenant_id     BIGINT       NULL,
  event_type    VARCHAR(32)  NOT NULL,   -- document_filed | memo_generated | provider_call
  unit_cents    INT          NOT NULL,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (price_id),
  UNIQUE KEY uq_tenant_event (tenant_id, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- The settled prices. provider_call is deliberately absent: it is unpriced,
-- and an absent price must refuse rather than charge nothing.
INSERT INTO meter_price (tenant_id, event_type, unit_cents) VALUES
  (NULL, 'document_filed',  25),
  (NULL, 'memo_generated', 100);

-- --- where money comes from ------------------------------------------------
--
-- Buckets, not a balance. A balance cannot express that $15 of credit expires
-- on the 28th while $25 of cash bought on the 2nd expires on the 2nd of next
-- month, and the difference decides which is spent first.
--
-- kind:
--   trial           granted once at signup, $5.00, expires with the trial
--   monthly_credit  granted each period, expires at the anniversary, no roll
--   purchased       bought in increments, expires 30 days from purchase
--   daily_test      the test allowance, its own money, expires end of day
--
-- spent_cents is a running total maintained beside the allocations below. It
-- is derivable from them and kept anyway, because reading a balance is the
-- most frequent question the wallet is asked and summing a ledger to answer
-- it does not stay cheap.

CREATE TABLE wallet_bucket (
  bucket_id     BIGINT       NOT NULL AUTO_INCREMENT,
  tenant_id     BIGINT       NOT NULL,
  kind          VARCHAR(24)  NOT NULL,
  granted_cents INT          NOT NULL,
  spent_cents   INT          NOT NULL DEFAULT 0,
  reference     VARCHAR(255) NULL,       -- the payment, where there was one
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at    DATETIME     NOT NULL,
  PRIMARY KEY (bucket_id),
  KEY idx_spend_order (tenant_id, expires_at, created_at),
  KEY idx_kind (tenant_id, kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- idx_spend_order is the spend rule made queryable: soonest expiry first,
-- then oldest. Credit normally goes before cash, but a cash tranche maturing
-- sooner is burned first rather than stranded - which falls out of this
-- ordering without a case for it in code.

-- --- what was charged ------------------------------------------------------
--
-- One row per chargeable act. DEBITED ON THE CLICK, not on completion: the
-- price is shown and accepted before anything is filed, and a person who has
-- accepted a price should not later find the work ran and the money did not.
--
-- idempotency_key is not optional. Filing eighteen documents is one click and
-- eighteen charges; a retried request, a double click or a network stall must
-- not charge twice. The client mints the key and the unique index enforces
-- it, because the only safe place to refuse a duplicate is the database.

CREATE TABLE wallet_ledger (
  entry_id        BIGINT       NOT NULL AUTO_INCREMENT,
  tenant_id       BIGINT       NOT NULL,
  event_type      VARCHAR(32)  NOT NULL,
  quantity        INT          NOT NULL DEFAULT 1,
  unit_cents      INT          NOT NULL,   -- as it stood, not as it stands
  amount_cents    INT          NOT NULL,
  reference       VARCHAR(255) NULL,       -- 'Meridian Trading Ltd', memo 412
  idempotency_key VARCHAR(64)  NOT NULL,
  created_by      VARCHAR(255) NULL,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (entry_id),
  UNIQUE KEY uq_idempotency (tenant_id, idempotency_key),
  KEY idx_tenant_time (tenant_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- unit_cents is copied onto the entry rather than joined to meter_price. A
-- price that changes must not rewrite what somebody was charged last March.

-- --- which money paid for it -----------------------------------------------
--
-- A single charge can span buckets: $0.50 left in credit and the rest from
-- cash. Without this table the ledger says what was charged and the buckets
-- say what is left, and nothing says how one became the other.
--
-- This is also what makes spent_cents auditable. If the sum of allocations
-- against a bucket ever disagrees with its spent_cents, something is wrong
-- and can be found.

CREATE TABLE wallet_allocation (
  allocation_id BIGINT NOT NULL AUTO_INCREMENT,
  entry_id      BIGINT NOT NULL,
  bucket_id     BIGINT NOT NULL,
  tenant_id     BIGINT NOT NULL,
  amount_cents  INT    NOT NULL,
  PRIMARY KEY (allocation_id),
  KEY idx_entry (entry_id),
  KEY idx_bucket (bucket_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --- what the two existing tenants get -------------------------------------
--
-- They were created by hand before any of this and have no buckets, which
-- would read as a zero balance and stop them filing. A trial bucket each,
-- expiring in thirty days, so the dev stack keeps working.
--
-- $5.00, the trial figure. Nobody paid for it and the ledger will say so.

INSERT INTO wallet_bucket (tenant_id, kind, granted_cents, expires_at, reference)
SELECT tenant_id, 'trial', 500,
       DATE_ADD(NOW(), INTERVAL 30 DAY),
       'granted by migration 015'
FROM tenant;
