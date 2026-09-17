-- 024_pack_offer.sql
--
-- What is on offer to a new tenant, marked rather than inferred.
--
-- Revision selection decision record, 17 September 2026, items 6 and 7: in
-- tenant 0 a tick marks a memorandum as on offer, and what is on offer is the
-- mark, never the highest revision. Until now the answer was derived -
-- _pack_revision took MAX(revision) for a pack_key, and packs() took the
-- newest published base - which meant publishing a revision changed what
-- every new tenant got, with nothing said and nothing to undo it.
--
-- A MARK CANNOT LIVE INSIDE A REVISION. A revision is immutable and cached
-- for the life of a container (config.load), so a flag on config_template
-- would be a mutable value inside an immutable thing. It lives here instead.
--
-- ONE ROW PER pack_key. Replacing the row is how the offer moves to another
-- revision; deleting it takes the pack off offer. Nothing is retired and no
-- revision is touched either way.
--
-- Additive: one new table, and five rows naming what tenant 0 already offers.

CREATE TABLE pack_offer (
  pack_key     VARCHAR(64)  NOT NULL,
  kind         VARCHAR(16)  NOT NULL,   -- base | template
  tenant_id    BIGINT       NOT NULL,   -- whose revision it is: the pack tenant
  revision     INT          NOT NULL,
  template_key VARCHAR(64)  NULL,       -- the memorandum; NULL for a base
  marked_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  marked_by    VARCHAR(255) NULL,
  PRIMARY KEY (pack_key),
  KEY idx_kind (kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- tenant_id is written rather than assumed. registry.PACK_TENANT is 0 today,
-- and a row saying which tenant a revision belongs to is what lets that move
-- without a second migration.
--
-- template_key is NULL for a base: a base is the whole vocabulary of its
-- revision, and a memorandum is one template_key inside it.

-- --- the five marks --------------------------------------------------------
--
-- Revision 9 is tenant 0's whole configuration (migration 023): the base of
-- revision 4 and the four memoranda of revisions 5 to 8 in one revision. The
-- marks name it, so the same rows a customer is offered today are offered
-- from the revision that can be edited.
--
-- Cleared first so the file can be run again.

DELETE FROM pack_offer;

INSERT INTO pack_offer (pack_key, kind, tenant_id, revision, template_key, marked_by)
VALUES
  ('base', 'base', 0, 9, NULL, 'migration 024'),
  ('TRADEFINANCE-Credit', 'template', 0, 9, 'credit-memorandum', 'migration 024'),
  ('TRADEFINANCE-KYC', 'template', 0, 9, 'kyc-customer-due-diligence-memorandum', 'migration 024'),
  ('TRADEFINANCE-Lender', 'template', 0, 9, 'lender-information-memorandum', 'migration 024'),
  ('RECEIVABLES FINANCE-Credit', 'template', 0, 9, 'trade-finance-credit-memo-duplicate', 'migration 024');


-- Verification
--
--   SELECT pack_key, kind, tenant_id, revision, IFNULL(template_key, '-')
--     FROM pack_offer ORDER BY kind, pack_key
--
-- Expect five rows, all tenant 0 revision 9: one base with no template_key,
-- and four templates naming credit-memorandum,
-- kyc-customer-due-diligence-memorandum, lender-information-memorandum and
-- trade-finance-credit-memo-duplicate.
--
--   SELECT o.pack_key FROM pack_offer o
--    LEFT JOIN config_revision r ON r.tenant_id = o.tenant_id
--          AND r.revision = o.revision AND r.status = 'published'
--    WHERE r.revision IS NULL
--
-- Expect none: every mark names a published revision.
--
--   SELECT o.pack_key FROM pack_offer o
--    LEFT JOIN config_template t ON t.tenant_id = o.tenant_id
--          AND t.revision = o.revision AND t.template_key = o.template_key
--    WHERE o.kind = 'template' AND t.template_key IS NULL
--
-- Expect none: every marked memorandum exists in the revision it names.
--
--   SELECT filename FROM schema_migration WHERE filename = '024_pack_offer.sql'
--
-- Expect one row.
