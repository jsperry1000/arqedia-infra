--
-- 056_tenant_organization_profile.sql
--
-- The organization profile (decided 9 November 2026): an administrator
-- keeps the organization's name, address, contact email and contact phone.
-- PROPOSED, and not applied.
--
-- WHY. tenant.name was set once, from "Your organisation" at sign-up, and
-- nothing could change it after; tenant 5 signed up as "eBL" and its shares
-- were watermarked "shared by eBL". The name already has its column; the
-- other three are new.
--
-- Only the name is required, and it already is (NOT NULL since sign-up).
-- The three new columns are NULL until an administrator fills them.
--
-- APPLY BEFORE DEPLOYING THE CODE THAT READS IT. GET /organization selects
-- these columns.
--
-- ADDITIVE. Three nullable columns; nothing is dropped and no row's value
-- changes.

ALTER TABLE tenant
  ADD COLUMN address       VARCHAR(500) NULL AFTER name,
  ADD COLUMN contact_email VARCHAR(255) NULL AFTER address,
  ADD COLUMN contact_phone VARCHAR(40)  NULL AFTER contact_email;
