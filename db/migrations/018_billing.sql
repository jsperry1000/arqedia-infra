-- 018_billing.sql
--
-- Paying for a plan. Four tables, all new: the plan a tenant can buy, the
-- subscription it holds with Paddle, every Paddle event received, and every
-- top-up somebody clicked.
--
-- Additive. Nothing existing is altered. tenant.plan stays, and stays read by
-- seats, settings and the renderer - but it is now a COPY. subscription.plan_id
-- is authoritative, and tenant.plan is written from it for existing readers.
--
-- A tenant with no subscription row is on trial. No row is backfilled, and
-- signup is not changed.
--
-- Decision record: docs/specs/paddle_subscription_decisions_2026-09-16.md.
-- Columns not in Wallet spec section 3 are PROPOSED and say so.

-- --- plan ------------------------------------------------------------------
--
-- A plan is a row, not an enum (Plans section 1). Enterprise is a row per
-- contract and is not seeded here.
--
-- plan_key is PROPOSED. It is the value tenant.plan already holds, so the copy
-- can be written without a lookup table of display names. Small Business is
-- 'business' because that is what the live rows hold.

CREATE TABLE plan (
  plan_id              BIGINT       NOT NULL AUTO_INCREMENT,
  plan_key             VARCHAR(32)  NOT NULL,
  name                 VARCHAR(64)  NOT NULL,
  seat_count           INT          NOT NULL,
  monthly_price_cents  BIGINT       NOT NULL,
  monthly_credit_cents BIGINT       NOT NULL,
  share_allowance      INT          NULL,      -- NULL = unlimited
  active               TINYINT(1)   NOT NULL DEFAULT 1,
  PRIMARY KEY (plan_id),
  UNIQUE KEY uq_plan_key (plan_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO plan
  (plan_key, name, seat_count, monthly_price_cents, monthly_credit_cents,
   share_allowance)
VALUES
  ('base',     'Base',           2, 2500,  500, 5),
  ('business', 'Small Business', 5, 6500, 1500, NULL);

-- --- subscription ----------------------------------------------------------
--
-- One per tenant, written only by the Paddle processor.
--
-- status is trial | active | closed (Wallet section 3). closed is set only on
-- account deletion. capped is never stored: it is derived from the balance
-- and from paddle_status.
--
-- payment_method_ref is in the spec and is left NULL. Paddle holds the card,
-- and the subscription id is its own column rather than a repurposed one.
--
-- PROPOSED columns: paddle_customer_id, paddle_subscription_id, paddle_status,
-- current_period_ends_at, paddle_event_at, updated_at.
--
-- paddle_event_at is the occurred_at of the last event applied. Paddle does
-- not deliver in order, so an update older than it is skipped.

CREATE TABLE subscription (
  tenant_id              BIGINT       NOT NULL,
  plan_id                BIGINT       NOT NULL,
  status                 VARCHAR(16)  NOT NULL,
  billing_anchor_day     TINYINT      NULL,
  trial_ends_at          DATETIME     NULL,
  payment_method_ref     VARCHAR(64)  NULL,
  created_at             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  paddle_customer_id     VARCHAR(64)  NULL,
  paddle_subscription_id VARCHAR(64)  NULL,
  paddle_status          VARCHAR(16)  NULL,   -- active | past_due | paused | canceled | trialing
  current_period_ends_at DATETIME     NULL,
  paddle_event_at        DATETIME(6)  NULL,
  updated_at             DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                      ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id),
  UNIQUE KEY uq_paddle_subscription (paddle_subscription_id),
  CONSTRAINT fk_subscription_plan FOREIGN KEY (plan_id) REFERENCES plan (plan_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --- paddle_event (PROPOSED) -----------------------------------------------
--
-- Every event received, once. event_id is the key because Paddle delivers at
-- least once. The processor inserts this row and applies the event in ONE
-- transaction, so a failure rolls both back and a replay is not skipped as a
-- duplicate.
--
-- The payload is not stored. It carries the customer's email address.
--
-- needs_review is set for a refund or chargeback, which changes no bucket and
-- no ledger row (decision record item 15).

CREATE TABLE paddle_event (
  event_id         VARCHAR(64)  NOT NULL,
  event_type       VARCHAR(64)  NOT NULL,
  occurred_at      DATETIME(6)  NOT NULL,
  tenant_id        BIGINT       NULL,
  paddle_entity_id VARCHAR(64)  NULL,
  needs_review     TINYINT(1)   NOT NULL DEFAULT 0,
  received_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (event_id),
  KEY idx_tenant_time (tenant_id, occurred_at),
  KEY idx_review (needs_review)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --- topup_request (PROPOSED) ----------------------------------------------
--
-- One row per top-up click, written BEFORE Paddle is called. Paddle takes no
-- idempotency key, so the unique index here is what refuses a repeat
-- (Wallet section 6, requirement 2).
--
-- paddle_transaction_id is NULL until the matching transaction.completed
-- arrives. The purchased bucket is granted by that webhook, never here.

CREATE TABLE topup_request (
  request_id            BIGINT       NOT NULL AUTO_INCREMENT,
  tenant_id             BIGINT       NOT NULL,
  idempotency_key       VARCHAR(64)  NOT NULL,
  increments            INT          NOT NULL,
  requested_by          VARCHAR(255) NULL,
  created_at            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  paddle_transaction_id VARCHAR(64)  NULL,
  PRIMARY KEY (request_id),
  UNIQUE KEY uq_idempotency (tenant_id, idempotency_key),
  KEY idx_transaction (paddle_transaction_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


-- Verification
--
--   SELECT plan_key, seat_count, monthly_credit_cents, share_allowance
--     FROM plan ORDER BY plan_id
--
-- Expect two rows: base 2 500 5, business 5 1500 NULL.
--
--   SELECT COUNT(*) FROM subscription
--
-- Expect 0.
--
--   SHOW CREATE TABLE subscription
--
-- Expect fk_subscription_plan and uq_paddle_subscription.
--
--   SELECT filename FROM schema_migration WHERE filename = '018_billing.sql'
--
-- Expect one row.
