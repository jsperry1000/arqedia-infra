-- 049_terms_acceptance.sql
--
-- Who accepted the Agreement, which version, and when (27 October 2026).
-- PROPOSED, and not applied.
--
-- WHY. The Terms of Service, Privacy Policy and Refund Policy are published
-- at version 1 (docs/legal), and it was decided on 27 October 2026 that each
-- acceptance records the version accepted. Until now nothing recorded that a
-- customer accepted anything: sign-up showed no terms, and an invited member
-- was asked nothing. A recipient's acceptance is recorded on their viewer
-- account in DynamoDB (share.tf), not here.
--
-- ONE ROW PER ACCEPTANCE, NEVER UPDATED. A person who accepts version 2 later
-- gets a second row; the first stays, because it is what they agreed to then.
--
-- WRITTEN BY lambda/signup only: verify() inside the transaction that makes
-- the tenant, and accept() beside the seat it writes. Both refuse a request
-- that does not accept, or names a version other than AGREEMENT_VERSION.
--
-- NO IP ADDRESS. The Privacy Policy lists what is collected; an acceptance's
-- address is not on that list, and adding it is a policy change first.
--
-- tenant_id IS RECORDED, and docs/runbooks/tenant_inventory.py counts it.
-- An account deletion keeps these rows, as the wallet ledger is kept:
-- decided 27 October 2026 (docs/ARQEDIA_decisions_2026-10-27.md, section 5).

CREATE TABLE terms_acceptance (
  acceptance_id     BIGINT       NOT NULL AUTO_INCREMENT,
  email             VARCHAR(255) NOT NULL,
  tenant_id         BIGINT       NOT NULL,
  context           VARCHAR(16)  NOT NULL,
  agreement_version INT          NOT NULL,
  accepted_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (acceptance_id),
  KEY idx_terms_acceptance_tenant (tenant_id),
  KEY idx_terms_acceptance_email (email),
  CONSTRAINT chk_terms_acceptance_context CHECK (context IN ('signup', 'invitation')),
  CONSTRAINT chk_terms_acceptance_version CHECK (agreement_version >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Verification
--
--   SHOW COLUMNS FROM terms_acceptance
--
-- Expect six columns, as above.
--
--   SELECT COUNT(*) FROM terms_acceptance
--
-- Expect 0: nothing is backfilled. Accounts made before this have accepted
-- nothing on record, and saying otherwise would be inventing it.
--
--   SELECT filename FROM schema_migration
--    WHERE filename = '049_terms_acceptance.sql'
--
-- Expect one row.
--
--
-- DEPLOY ORDER. THIS MIGRATION FIRST, THE SIGNUP LAMBDA SECOND, AND IT IS NOT
-- OPTIONAL. verify() and accept() insert into this table; deployed against a
-- database without it, every sign-up and every invitation fails.
--
-- NO SEMICOLON ENDS A COMMENT LINE HERE. db/migrate.ps1 splits statements on
-- a semicolon at the end of a line, comments included.
