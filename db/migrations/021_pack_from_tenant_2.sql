-- 021_pack_from_tenant_2.sql
--
-- The pack becomes what tenant 2 has built. Tenant 0 is the repository of
-- every basic template, and every fact, document type and schema they draw
-- on; a new tenant forks from it.
--
-- GENERATED, NOT HAND-WRITTEN, from tenant 2 revision 53 on dev (published
-- 2026-09-15 22:20:49, "Updated config for receivables") by a read-only
-- script. Written as literal rows rather than INSERT ... SELECT FROM tenant 2,
-- because tenant 2 exists on dev only: the pack must arrive the same on every
-- environment (ENV-01).
--
-- Strings holding a newline, a double quote, a backslash or anything outside
-- printable ASCII are written as CONVERT(X'..' USING utf8mb4). Windows
-- PowerShell 5.1 escapes neither quote nor backslash when migrate.ps1 passes
-- a statement to aws.exe. migrate.ps1 splits statements on ";" at a
-- line end and strips lines beginning "--", and Windows PowerShell reads a
-- file without a byte-order mark as ANSI: none of that may touch the content.
--
-- ADDITIVE. Five new revisions of tenant 0:
--
--   4  base      base                         every category, document type,
--                                             schema, routing and fact of 2:53
--   5  template  TRADEFINANCE-Credit          credit-memorandum
--   6  template  TRADEFINANCE-KYC             kyc-customer-due-diligence-memorandum
--   7  template  TRADEFINANCE-Lender          lender-information-memorandum
--   8  template  RECEIVABLES FINANCE-Credit   trade-finance-credit-memo-duplicate
--
-- Deal Presentation (deal-presentation) is not shipped. Its facts are in the
-- base, as every fact of 2:53 is.
--
-- A new tenant's base is the newest published base with pack_key 'base', so
-- revision 4 replaces revision 3 for every fork from now on. Revisions 1 and 3
-- are left exactly as they are: tenants 1 and 2 record forked_from pack:0:1,
-- and what was forked is kept.
--
-- ONE ROW IS CHANGED, NOT ADDED. Revision 2, the "Due Diligence Memorandum"
-- template, is set to status 'retired'. packs() and template_packs() list
-- status 'published' only, so it is no longer offered. Nothing is deleted:
-- its sections and bindings stay, and its status can be set back.
--
-- Template labels, section titles and prompts are copied as tenant 2 has
-- them. They are edited in place on tenant 0 later, not here.

-- --- room for the five new revisions -----------------------------------------
--
-- Cleared first so the file can be run again against a database where it
-- stopped part way. Revisions 4 to 8 of tenant 0 have never held anything.
DELETE FROM config_section_field WHERE tenant_id = 0 AND revision IN (4, 5, 6, 7, 8);
DELETE FROM config_section WHERE tenant_id = 0 AND revision IN (4, 5, 6, 7, 8);
DELETE FROM config_template WHERE tenant_id = 0 AND revision IN (4, 5, 6, 7, 8);
DELETE FROM config_field WHERE tenant_id = 0 AND revision IN (4, 5, 6, 7, 8);
DELETE FROM config_type_schema WHERE tenant_id = 0 AND revision IN (4, 5, 6, 7, 8);
DELETE FROM config_schema WHERE tenant_id = 0 AND revision IN (4, 5, 6, 7, 8);
DELETE FROM config_document_type WHERE tenant_id = 0 AND revision IN (4, 5, 6, 7, 8);
DELETE FROM config_category WHERE tenant_id = 0 AND revision IN (4, 5, 6, 7, 8);
DELETE FROM config_revision WHERE tenant_id = 0 AND revision IN (4, 5, 6, 7, 8);

-- --- retire the old memorandum, revision 2 ----------------------------------

UPDATE config_revision SET status = 'retired'
 WHERE tenant_id = 0 AND revision = 2 AND kind = 'template';

-- --- the base, revision 4 -----------------------------------------------------

INSERT INTO config_revision
  (tenant_id, revision, status, kind, pack_key, forked_from, note,
   published_at, published_by)
VALUES (0, 4, 'published', 'base', 'base', 'tenant:2:53',
        'the base, copied from tenant 2 revision 53', UTC_TIMESTAMP(),
        'migration 021');
INSERT INTO config_category
  (tenant_id, revision, category_key, label, sort_order)
VALUES
  (0, 4, 'business', 'Business Model and Operations ', 3),
  (0, 4, 'corp', 'Corporate Governance', 0),
  (0, 4, 'financial', 'Financial Projections and Analyses', 2),
  (0, 4, 'kyc-aml-pep', 'KYC, AML and Screening', 1),
  (0, 4, 'transaction-data', 'Transaction Specific Data', 0);
INSERT INTO config_document_type
  (tenant_id, revision, type_key, label, category_key, description, read_mode, always_ocr, sort_order)
VALUES
  (0, 4, 'affiliate-information', 'Associated Company Info', 'corp', 'Information related to an enitity which is not a parent or a subsidiary of the subject entity, but is affiliated by virtue of ownership and/or control over the affiliate by either the parent, the subject company or any person directly associated with the parent, the subject company or its subsidiaries. ', 'text', 0, 0),
  (0, 4, 'aging-reports', 'Aged Debtors or Creditors', 'financial', 'An aged debtors or aged creditors schedule showing amounts outstanding by age.', 'forms', 1, 18),
  (0, 4, 'aml-policy', 'AML Policy', 'kyc-aml-pep', 'The entity''s own anti-money-laundering or counter-terrorist-financing policy document.', 'text', 0, 8),
  (0, 4, 'articles', 'Articles of Association', 'corp', 'The entity''s articles of association or constitutional document, setting out share classes, director powers and internal rules.', 'text', 0, 0),
  (0, 4, 'audited-statements', 'Audited Financial Statements', 'financial', 'Financial statements bearing an auditor''s report.', 'forms', 1, 14),
  (0, 4, 'bank-statements', 'Bank Statements', 'financial', 'Statements of account issued by a bank showing transactions over a period.', 'forms', 1, 17),
  (0, 4, 'banking-relationships', 'Bank Reference', 'business', 'A bank reference letter or confirmation of the entity''s banking relationships.', 'text', 0, 26),
  (0, 4, 'beneficial-ownership', 'Beneficial Ownership Declaration', 'corp', 'A declaration naming the ultimate beneficial owners and their percentage holdings.', 'forms', 0, 5),
  (0, 4, 'board-resolution', 'Board Resolution', 'corp', 'A minuted resolution of the board or members, typically authorising an act or appointing signatories.', 'text', 0, 4),
  (0, 4, 'bylaws', 'Bylaws', 'corp', 'Internal governance rules or bylaws adopted by the entity.', 'text', 0, 1),
  (0, 4, 'cap-table', 'Cap Table or Share Instrument', 'corp', 'A share register, cap table, or an instrument affecting share ownership: share purchase agreement, option, warrant or pledge.', 'forms', 0, 7),
  (0, 4, 'cdd-questionnaire', 'CDD Questionnaire', 'kyc-aml-pep', 'A completed questionnaire or information request in which the entity answers questions about ITSELF: legal name, ownership, directors, business activity, banking, trade flows, financing sought. Question-and-answer or form format, completed by or on behalf of the entity being reviewed.', 'forms', 0, 9),
  (0, 4, 'certificate-of-incorporation', 'Certificate of Incorporation', 'corp', 'The registry certificate recording that the entity was incorporated: legal name, registration number and date.', 'text', 0, 3),
  (0, 4, 'commercial-counterparties-list', 'Commercial Counterparties List', 'corp', CONVERT(X'4C697374206F6620616C6C20636F6D6D65726369616C20636F756E74657270617274696573206F6620746865206D656D6F207375626A6563743A0A4275796572732C20737570706C696572732C2073686970206F776E657273202F206F70657261746F72732C2077617265686F757365206F70657261746F72732C20636F6C6C61746572616C20706C6174666F726D206F70657261746F72732C20636F6C6C61746572616C206D616E6167656D656E74206167656E74732C20706F7274206167656E74732C20696E7370656374696F6E7320616E6420616363657074616E6365206167656E74732C2062616E6B732C206C6177206669726D7320616E64206163636F756E74696E67206669726D732E20' USING utf8mb4), 'text', 0, 0),
  (0, 4, 'counterparty-list', 'Customer or Supplier List', 'business', 'A schedule or list of the entity''s customers, buyers or suppliers - names, locations, volumes or terms, usually tabular. A list of third parties, not a questionnaire about the entity itself. ', 'text', 0, 19),
  (0, 4, 'engagement-letter', 'Engagement Letter', 'transaction-data', 'Letter documenting the engagement of eBL Finance as arranger or servicer, outlining roles, responsibilities, and fee arrangements.', 'text', 0, 0),
  (0, 4, 'facility-exposures', 'Facility Exposures', 'transaction-data', 'This would be a quantitative analyses of the exposures outstanding on the facility; outstanding draws', 'text', 0, 0),
  (0, 4, 'facility-master-agreement', 'Financing Agreement', 'transaction-data', 'This is the signed loan document of the memo subject;', 'text', 0, 0),
  (0, 4, 'financial-projections', 'Financial Projections', 'financial', 'These are documents related to financial projections of the subject counterparty', 'forms', 0, 0),
  (0, 4, 'good-standing', 'Certificate of Good Standing', 'corp', 'A certificate issued by a registry confirming the entity exists and is in good standing at a stated date.', 'text', 0, 2),
  (0, 4, 'id-verification', 'Identity Verification', 'kyc-aml-pep', 'Identity documents or verification evidence for a named individual: passport, national identity card, proof of address.', 'forms', 0, 10),
  (0, 4, 'insurance-coverage', 'Insurance Policy', 'business', 'An insurance policy, certificate or schedule: cargo, stock throughput, credit or liability cover.', 'forms', 0, 25),
  (0, 4, 'interim-statements', 'Interim Financial Statements', 'financial', 'Management-prepared or unaudited financial statements for a period.', 'forms', 1, 15),
  (0, 4, 'internal-risk-assessment', 'Internal Risk Assessment', 'kyc-aml-pep', 'These are an internal risks assessment document prepared on review of the memo, and added to final memos....', 'text', 0, 0),
  (0, 4, 'licenses-certificates', 'Licences and Certificates', 'business', 'A licence, permit, registration or certification held by a named party: regulatory licence, import permit, quality or scheme certification.', 'forms', 0, 24),
  (0, 4, 'market-analysis', 'Market Analysis', 'business', 'Analysis or commentary on the market, sector or commodity the entity trades in.', 'text', 0, 20);
INSERT INTO config_document_type
  (tenant_id, revision, type_key, label, category_key, description, read_mode, always_ocr, sort_order)
VALUES
  (0, 4, 'operations-memo', 'Operations Memorandum', 'business', 'A description of how the entity operates: sourcing, logistics, processing, warehousing, settlement.', 'text', 0, 21),
  (0, 4, 'parent-guarantee', 'Parent Guarantee', 'transaction-data', 'Guarantee from Parent Group providing recourse to the parent entity for the full facility amount, backed by the ultimate beneficial owners.', 'text', 0, 0),
  (0, 4, 'pep-screen', 'PEP Screening - Adverse Media', 'kyc-aml-pep', 'The output of a politically-exposed-person screening run against named individuals.  Also adverse media on the person and all entities related to that person. ', 'text', 0, 0),
  (0, 4, 'regulatory-filings', 'Regulatory Filings', 'corp', 'An extract or filing made to a company registry or regulator: annual return, register extract, officer or shareholder filing. Records what the registry holds, not what the entity says about itself.', 'forms', 0, 6),
  (0, 4, 'sanctions-screen', 'Sanctions Screening', 'kyc-aml-pep', 'The output of a sanctions list screening run against the entity or named individuals.', 'text', 0, 12),
  (0, 4, 'source-of-funds', 'Source of Funds', 'kyc-aml-pep', 'A statement or evidence of where the entity''s funds or a person''s wealth originated.', 'text', 0, 13),
  (0, 4, 'tax-returns', 'Tax Returns', 'financial', 'A filed tax return or tax assessment.', 'forms', 0, 16),
  (0, 4, 'trade-references', 'Trade References', 'business', 'A reference given by a trading partner, bank or customer about dealings with the entity.', 'text', 0, 22),
  (0, 4, 'trade-summary', 'Trade Summary', 'business', 'A summary of completed or planned trades, typically tabular: counterparties, commodities, volumes, values.', 'text', 0, 23);
INSERT INTO config_schema
  (tenant_id, revision, schema_key, label, instruction, sort_order)
VALUES
  (0, 4, 'aml-policies-summary', 'AML Programme', 'text', 5),
  (0, 4, 'business-overview', 'Business Overview', 'text', 0),
  (0, 4, 'capital-structure', 'Capital Structure', 'text', 2),
  (0, 4, 'corporate-structure', 'Corporate Structure', 'text', 1),
  (0, 4, 'financial-output', 'Financial Position', 'tables', 6),
  (0, 4, 'KYC', 'KYC and Screening', 'text', 4),
  (0, 4, 'licenses-certifications', 'Licences and Certifications', 'text', 3),
  (0, 4, 'set-02eddf08f7754e51', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-07a0d46e2e6c29d4', 'Fields found in 3 documents', NULL, 0),
  (0, 4, 'set-0976eeb94c0aaf44', 'Fields found in 8 documents', NULL, 0),
  (0, 4, 'set-1d3ad329fa97a88b', 'Fields found in 11 documents', NULL, 0),
  (0, 4, 'set-1dab2f05f91caf56', 'Fields found in 9 documents', NULL, 0),
  (0, 4, 'set-215ce9fc78f82d2a', 'Fields found in 3 documents', NULL, 0),
  (0, 4, 'set-2350ba07951d4ccf', 'Fields found in 3 documents', NULL, 0),
  (0, 4, 'set-258547ed5ef42ed9', 'Fields found in 1 document', NULL, 0),
  (0, 4, 'set-349706869bd112aa', 'Fields found in 1 document', NULL, 0),
  (0, 4, 'set-3530bf6f479b69b0', 'Fields found in 9 documents', NULL, 0),
  (0, 4, 'set-3b6934871fb65d44', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-3bd96ff5bcb18d0e', 'Fields found in 1 document', NULL, 0),
  (0, 4, 'set-4187e14e49b2d8ef', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-4b0176c5e8974e9b', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-5be6a0b276ddd29f', 'Fields found in 7 documents', NULL, 0),
  (0, 4, 'set-5ce679c7ec3002e2', 'Fields found in 6 documents', NULL, 0),
  (0, 4, 'set-7a7c8571644658f2', 'Fields found in 6 documents', NULL, 0),
  (0, 4, 'set-7fc0ba66c51eaf7e', 'Fields found in 8 documents', NULL, 0),
  (0, 4, 'set-8e29b318972d08aa', 'Fields found in 6 documents', NULL, 0),
  (0, 4, 'set-982ebe05e379cc56', 'Fields found in 1 document', NULL, 0),
  (0, 4, 'set-9854dd80a9a4c4c0', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-996ad70c6e81efa9', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-998475fa9f7f74bc', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-9e86cd1f3f271c48', 'Fields found in 1 document', NULL, 0),
  (0, 4, 'set-a98ccb657dc1db45', 'Fields found in 3 documents', NULL, 0),
  (0, 4, 'set-aa3c68847afcf4e7', 'Fields found in 3 documents', NULL, 0),
  (0, 4, 'set-ae36c86fa805ecec', 'Fields found in 3 documents', NULL, 0),
  (0, 4, 'set-b3e62f504fe720f9', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-c29380c9143e4948', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-ce723dac2a0a8438', 'Fields found in 2 documents', NULL, 0),
  (0, 4, 'set-d24a415599f6fe5e', 'Fields found in 8 documents', NULL, 0),
  (0, 4, 'set-f41da6fb652dbb5d', 'Fields found in 1 document', NULL, 0),
  (0, 4, 'set-f4bddf21398e8180', 'Fields found in 9 documents', NULL, 0),
  (0, 4, 'set-f8aa0257067ff0fc', 'Fields found in 1 document', NULL, 0),
  (0, 4, 'trade-flow-profile', 'Trade Flow Profile', 'text', 7);
INSERT INTO config_type_schema
  (tenant_id, revision, type_key, schema_key)
VALUES
  (0, 4, 'aging-reports', 'financial-output'),
  (0, 4, 'aging-reports', 'set-ae36c86fa805ecec'),
  (0, 4, 'aml-policy', 'aml-policies-summary'),
  (0, 4, 'aml-policy', 'set-aa3c68847afcf4e7'),
  (0, 4, 'articles', 'corporate-structure'),
  (0, 4, 'articles', 'set-f4bddf21398e8180'),
  (0, 4, 'audited-statements', 'financial-output'),
  (0, 4, 'audited-statements', 'set-4b0176c5e8974e9b'),
  (0, 4, 'bank-statements', 'financial-output'),
  (0, 4, 'bank-statements', 'set-02eddf08f7754e51'),
  (0, 4, 'banking-relationships', 'KYC'),
  (0, 4, 'banking-relationships', 'set-1d3ad329fa97a88b'),
  (0, 4, 'banking-relationships', 'set-3530bf6f479b69b0'),
  (0, 4, 'banking-relationships', 'set-7a7c8571644658f2'),
  (0, 4, 'beneficial-ownership', 'corporate-structure'),
  (0, 4, 'beneficial-ownership', 'KYC'),
  (0, 4, 'beneficial-ownership', 'set-1d3ad329fa97a88b'),
  (0, 4, 'beneficial-ownership', 'set-1dab2f05f91caf56'),
  (0, 4, 'beneficial-ownership', 'set-3530bf6f479b69b0'),
  (0, 4, 'beneficial-ownership', 'set-7a7c8571644658f2'),
  (0, 4, 'beneficial-ownership', 'set-f4bddf21398e8180'),
  (0, 4, 'board-resolution', 'corporate-structure'),
  (0, 4, 'board-resolution', 'set-1d3ad329fa97a88b'),
  (0, 4, 'board-resolution', 'set-1dab2f05f91caf56'),
  (0, 4, 'board-resolution', 'set-f4bddf21398e8180'),
  (0, 4, 'bylaws', 'corporate-structure'),
  (0, 4, 'bylaws', 'set-1dab2f05f91caf56'),
  (0, 4, 'bylaws', 'set-f4bddf21398e8180'),
  (0, 4, 'cap-table', 'capital-structure'),
  (0, 4, 'cap-table', 'set-1d3ad329fa97a88b'),
  (0, 4, 'cdd-questionnaire', 'business-overview'),
  (0, 4, 'cdd-questionnaire', 'corporate-structure'),
  (0, 4, 'cdd-questionnaire', 'KYC'),
  (0, 4, 'cdd-questionnaire', 'set-07a0d46e2e6c29d4'),
  (0, 4, 'cdd-questionnaire', 'set-0976eeb94c0aaf44'),
  (0, 4, 'cdd-questionnaire', 'set-1d3ad329fa97a88b'),
  (0, 4, 'cdd-questionnaire', 'set-1dab2f05f91caf56'),
  (0, 4, 'cdd-questionnaire', 'set-3530bf6f479b69b0'),
  (0, 4, 'cdd-questionnaire', 'set-5be6a0b276ddd29f'),
  (0, 4, 'cdd-questionnaire', 'set-5ce679c7ec3002e2'),
  (0, 4, 'cdd-questionnaire', 'set-7a7c8571644658f2'),
  (0, 4, 'cdd-questionnaire', 'set-7fc0ba66c51eaf7e'),
  (0, 4, 'cdd-questionnaire', 'set-8e29b318972d08aa'),
  (0, 4, 'cdd-questionnaire', 'set-998475fa9f7f74bc'),
  (0, 4, 'cdd-questionnaire', 'set-d24a415599f6fe5e'),
  (0, 4, 'cdd-questionnaire', 'set-f4bddf21398e8180'),
  (0, 4, 'cdd-questionnaire', 'trade-flow-profile'),
  (0, 4, 'certificate-of-incorporation', 'corporate-structure'),
  (0, 4, 'certificate-of-incorporation', 'set-1dab2f05f91caf56'),
  (0, 4, 'certificate-of-incorporation', 'set-f4bddf21398e8180'),
  (0, 4, 'commercial-counterparties-list', 'set-215ce9fc78f82d2a'),
  (0, 4, 'commercial-counterparties-list', 'set-7fc0ba66c51eaf7e'),
  (0, 4, 'commercial-counterparties-list', 'set-a98ccb657dc1db45'),
  (0, 4, 'counterparty-list', 'business-overview'),
  (0, 4, 'counterparty-list', 'set-07a0d46e2e6c29d4'),
  (0, 4, 'counterparty-list', 'set-0976eeb94c0aaf44'),
  (0, 4, 'counterparty-list', 'set-5be6a0b276ddd29f'),
  (0, 4, 'counterparty-list', 'set-5ce679c7ec3002e2'),
  (0, 4, 'counterparty-list', 'set-7fc0ba66c51eaf7e'),
  (0, 4, 'counterparty-list', 'set-8e29b318972d08aa'),
  (0, 4, 'counterparty-list', 'set-d24a415599f6fe5e'),
  (0, 4, 'counterparty-list', 'trade-flow-profile'),
  (0, 4, 'engagement-letter', 'set-0976eeb94c0aaf44'),
  (0, 4, 'engagement-letter', 'set-3b6934871fb65d44'),
  (0, 4, 'engagement-letter', 'set-5be6a0b276ddd29f'),
  (0, 4, 'engagement-letter', 'set-8e29b318972d08aa'),
  (0, 4, 'engagement-letter', 'set-9e86cd1f3f271c48'),
  (0, 4, 'engagement-letter', 'set-d24a415599f6fe5e'),
  (0, 4, 'facility-exposures', 'set-0976eeb94c0aaf44'),
  (0, 4, 'facility-exposures', 'set-f8aa0257067ff0fc'),
  (0, 4, 'facility-master-agreement', 'set-02eddf08f7754e51'),
  (0, 4, 'facility-master-agreement', 'set-2350ba07951d4ccf'),
  (0, 4, 'facility-master-agreement', 'set-3b6934871fb65d44'),
  (0, 4, 'facility-master-agreement', 'set-982ebe05e379cc56'),
  (0, 4, 'facility-master-agreement', 'set-9854dd80a9a4c4c0'),
  (0, 4, 'facility-master-agreement', 'set-b3e62f504fe720f9'),
  (0, 4, 'facility-master-agreement', 'set-ce723dac2a0a8438'),
  (0, 4, 'financial-projections', 'set-0976eeb94c0aaf44'),
  (0, 4, 'financial-projections', 'set-258547ed5ef42ed9'),
  (0, 4, 'financial-projections', 'set-4b0176c5e8974e9b'),
  (0, 4, 'financial-projections', 'set-5ce679c7ec3002e2'),
  (0, 4, 'good-standing', 'corporate-structure'),
  (0, 4, 'good-standing', 'set-1dab2f05f91caf56'),
  (0, 4, 'good-standing', 'set-f4bddf21398e8180'),
  (0, 4, 'id-verification', 'KYC'),
  (0, 4, 'id-verification', 'set-1d3ad329fa97a88b'),
  (0, 4, 'id-verification', 'set-3530bf6f479b69b0'),
  (0, 4, 'id-verification', 'set-7a7c8571644658f2'),
  (0, 4, 'id-verification', 'set-aa3c68847afcf4e7'),
  (0, 4, 'insurance-coverage', 'business-overview'),
  (0, 4, 'insurance-coverage', 'KYC'),
  (0, 4, 'insurance-coverage', 'set-1d3ad329fa97a88b'),
  (0, 4, 'insurance-coverage', 'set-3530bf6f479b69b0'),
  (0, 4, 'insurance-coverage', 'set-7a7c8571644658f2'),
  (0, 4, 'insurance-coverage', 'set-7fc0ba66c51eaf7e'),
  (0, 4, 'insurance-coverage', 'set-b3e62f504fe720f9'),
  (0, 4, 'insurance-coverage', 'set-d24a415599f6fe5e'),
  (0, 4, 'interim-statements', 'financial-output'),
  (0, 4, 'internal-risk-assessment', 'set-3530bf6f479b69b0'),
  (0, 4, 'internal-risk-assessment', 'set-9854dd80a9a4c4c0'),
  (0, 4, 'internal-risk-assessment', 'set-996ad70c6e81efa9'),
  (0, 4, 'internal-risk-assessment', 'set-c29380c9143e4948'),
  (0, 4, 'licenses-certificates', 'licenses-certifications'),
  (0, 4, 'licenses-certificates', 'set-215ce9fc78f82d2a'),
  (0, 4, 'licenses-certificates', 'set-996ad70c6e81efa9'),
  (0, 4, 'market-analysis', 'business-overview'),
  (0, 4, 'market-analysis', 'set-0976eeb94c0aaf44');
INSERT INTO config_type_schema
  (tenant_id, revision, type_key, schema_key)
VALUES
  (0, 4, 'market-analysis', 'set-5be6a0b276ddd29f'),
  (0, 4, 'market-analysis', 'set-5ce679c7ec3002e2'),
  (0, 4, 'market-analysis', 'set-7fc0ba66c51eaf7e'),
  (0, 4, 'market-analysis', 'set-8e29b318972d08aa'),
  (0, 4, 'market-analysis', 'set-d24a415599f6fe5e'),
  (0, 4, 'market-analysis', 'trade-flow-profile'),
  (0, 4, 'operations-memo', 'business-overview'),
  (0, 4, 'operations-memo', 'set-07a0d46e2e6c29d4'),
  (0, 4, 'operations-memo', 'set-0976eeb94c0aaf44'),
  (0, 4, 'operations-memo', 'set-1d3ad329fa97a88b'),
  (0, 4, 'operations-memo', 'set-1dab2f05f91caf56'),
  (0, 4, 'operations-memo', 'set-215ce9fc78f82d2a'),
  (0, 4, 'operations-memo', 'set-2350ba07951d4ccf'),
  (0, 4, 'operations-memo', 'set-349706869bd112aa'),
  (0, 4, 'operations-memo', 'set-4187e14e49b2d8ef'),
  (0, 4, 'operations-memo', 'set-5be6a0b276ddd29f'),
  (0, 4, 'operations-memo', 'set-5ce679c7ec3002e2'),
  (0, 4, 'operations-memo', 'set-7a7c8571644658f2'),
  (0, 4, 'operations-memo', 'set-7fc0ba66c51eaf7e'),
  (0, 4, 'operations-memo', 'set-8e29b318972d08aa'),
  (0, 4, 'operations-memo', 'set-998475fa9f7f74bc'),
  (0, 4, 'operations-memo', 'set-a98ccb657dc1db45'),
  (0, 4, 'operations-memo', 'set-aa3c68847afcf4e7'),
  (0, 4, 'operations-memo', 'set-ae36c86fa805ecec'),
  (0, 4, 'operations-memo', 'set-c29380c9143e4948'),
  (0, 4, 'operations-memo', 'set-d24a415599f6fe5e'),
  (0, 4, 'operations-memo', 'trade-flow-profile'),
  (0, 4, 'parent-guarantee', 'set-1dab2f05f91caf56'),
  (0, 4, 'parent-guarantee', 'set-f41da6fb652dbb5d'),
  (0, 4, 'parent-guarantee', 'set-f4bddf21398e8180'),
  (0, 4, 'pep-screen', 'KYC'),
  (0, 4, 'pep-screen', 'set-1d3ad329fa97a88b'),
  (0, 4, 'pep-screen', 'set-3530bf6f479b69b0'),
  (0, 4, 'pep-screen', 'set-3bd96ff5bcb18d0e'),
  (0, 4, 'regulatory-filings', 'corporate-structure'),
  (0, 4, 'regulatory-filings', 'set-1dab2f05f91caf56'),
  (0, 4, 'regulatory-filings', 'set-f4bddf21398e8180'),
  (0, 4, 'sanctions-screen', 'KYC'),
  (0, 4, 'sanctions-screen', 'set-1d3ad329fa97a88b'),
  (0, 4, 'sanctions-screen', 'set-3530bf6f479b69b0'),
  (0, 4, 'source-of-funds', 'KYC'),
  (0, 4, 'source-of-funds', 'set-1d3ad329fa97a88b'),
  (0, 4, 'source-of-funds', 'set-3530bf6f479b69b0'),
  (0, 4, 'tax-returns', 'financial-output'),
  (0, 4, 'trade-references', 'business-overview'),
  (0, 4, 'trade-references', 'set-0976eeb94c0aaf44'),
  (0, 4, 'trade-references', 'set-5be6a0b276ddd29f'),
  (0, 4, 'trade-references', 'set-5ce679c7ec3002e2'),
  (0, 4, 'trade-references', 'set-7fc0ba66c51eaf7e'),
  (0, 4, 'trade-references', 'set-8e29b318972d08aa'),
  (0, 4, 'trade-references', 'set-d24a415599f6fe5e'),
  (0, 4, 'trade-references', 'trade-flow-profile'),
  (0, 4, 'trade-summary', 'business-overview'),
  (0, 4, 'trade-summary', 'set-2350ba07951d4ccf'),
  (0, 4, 'trade-summary', 'set-4187e14e49b2d8ef'),
  (0, 4, 'trade-summary', 'set-5be6a0b276ddd29f'),
  (0, 4, 'trade-summary', 'set-7fc0ba66c51eaf7e'),
  (0, 4, 'trade-summary', 'set-a98ccb657dc1db45'),
  (0, 4, 'trade-summary', 'set-ae36c86fa805ecec'),
  (0, 4, 'trade-summary', 'set-ce723dac2a0a8438'),
  (0, 4, 'trade-summary', 'set-d24a415599f6fe5e');
INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type, cardinality, description, group_key, sort_order)
VALUES
  (0, 4, 'set-3bd96ff5bcb18d0e', 'f_adverse_media_matches', 'Adverse Media Matches', 'text', 'group', 'This is a listing of any person or entity for which we have an adverse media report.   it should not include any entity or person for which have have no report.    List Persons first then Entities', 'f_adverse_media_matches', 0),
  (0, 4, 'set-3bd96ff5bcb18d0e', 'f_adverse_media_matches.adverse_media', 'Adverse Media', 'text', 'group', 'Short paragraph pulled directly from document describing the report', 'f_adverse_media_matches', 1),
  (0, 4, 'set-3bd96ff5bcb18d0e', 'f_adverse_media_matches.person_or_entity', 'Person or Entity', 'text', 'group', 'Name of person or entity', 'f_adverse_media_matches', 0),
  (0, 4, 'set-1dab2f05f91caf56', 'f_affiliates_subsidiaries_parents', 'Affiliates Subsidiaries Parents', 'entity_name', 'group', 'named related entities (parents, subs, affiliates);  DO NOT INCLUDE names of associated entities nor names of commercial counterparties', 'f_affiliates_subsidiaries_parents', 0),
  (0, 4, 'set-1dab2f05f91caf56', 'f_affiliates_subsidiaries_parents.jursidiction', 'Jursidiction', 'text', 'group', 'Country of Jurisdiction', 'f_affiliates_subsidiaries_parents', 2),
  (0, 4, 'set-1dab2f05f91caf56', 'f_affiliates_subsidiaries_parents.kyc_status', 'KYC Status', 'text', 'group', 'Waived, Pending, Approved, or Rejected', 'f_affiliates_subsidiaries_parents', 3),
  (0, 4, 'set-1dab2f05f91caf56', 'f_affiliates_subsidiaries_parents.name', 'Name', 'text', 'group', 'Name of Entity', 'f_affiliates_subsidiaries_parents', 0),
  (0, 4, 'set-1dab2f05f91caf56', 'f_affiliates_subsidiaries_parents.role', 'Role', 'text', 'group', 'Affiliate, Subsidiary, Parent', 'f_affiliates_subsidiaries_parents', 1),
  (0, 4, 'set-3b6934871fb65d44', 'f_agency_and_servicing_fee', 'Agency and Servicing Fee', 'text', 'one', 'The electronic Bill of Lading finance agency and servicing fee charged per annum on average drawn amounts.', NULL, 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_approved_digital_platforms', 'Approved Digital Platforms', 'text', 'one', 'List of approved digital platforms for registering electronic bills of lading, including ICE Digital Trade, SECRO, WaveBL or lender-approved alternatives.', NULL, 0),
  (0, 4, 'KYC', 'f_associated_entities', 'Associated Entities', 'entity_name', 'group', CONVERT(X'456E746974696573206F72206F7267616E697A6174696F6E7320636F6E6E656374656420746F20616E7920706572736F6E206F7220656E74697479206469726563746C792072656C6174656420746F20746865206D656D6F207375626A6563742E200A546869732073686F756C6420696E636C75646520616E7920656E7469747920696E20776869636820616E792072656C6174656420706572736F6E20686F6C6473206D6F7265207468616E203130252065717569747920636F6E74726F6C2E200A205468697320646F6573206E6F74206164647265737320636F6D6D65726369616C20636F756E7465727061727469657320616E642073686F756C64206E6F74206C697374207468656D2C206E6F7220646F657320697420696E636C7564652074686520706172656E74732C20636F6D70616E7920616666696C6961746573206F72207375626973646961726965732E202020' USING utf8mb4), 'f_associated_entities', 0),
  (0, 4, 'KYC', 'f_associated_entities.association', 'Association', 'text', 'group', 'Describe association; common shareholders, directors, same markets etc.   ', 'f_associated_entities', 1),
  (0, 4, 'KYC', 'f_associated_entities.conflict', 'Conflict', 'text', 'group', 'Indicate if any conflicts are noted in the source material related to the person or entity', 'f_associated_entities', 3),
  (0, 4, 'KYC', 'f_associated_entities.control', 'Control', 'text', 'group', 'Indicate level of control the memo subject person or entity has over the connectied associated entity (this is not about the parent, or subsidiary)', 'f_associated_entities', 2),
  (0, 4, 'KYC', 'f_associated_entities.person_or_entity', 'Entity', 'text', 'group', 'Name of entity', 'f_associated_entities', 0),
  (0, 4, 'capital-structure', 'f_authorized_issued_capital', 'Authorized Issued Capital', 'text', 'one', 'authorised and issued share capital, class and nominal value, as stated', NULL, 20),
  (0, 4, 'corporate-structure', 'f_authorized_signatories', 'Authorized Signatories', 'entity_name', 'many', 'Who can bind the entity, as stated in a board resolution, bylaws or mandate. Do NOT include a person who signed only as witness, certifier, notary or registry official.', NULL, 16),
  (0, 4, 'business-overview', 'f_business_model', 'Business Model', 'text', 'one', ' one paragraph on how it operates / makes money', NULL, 1),
  (0, 4, 'set-8e29b318972d08aa', 'f_buyers', 'Buyers', 'group', 'group', 'One record per buyer or customer the source identifies, whether the source lists them in a table or describes them in prose. Capture every buyer it identifies, in the order given. Where a buyer is identified only by a positional or placeholder label rather than a company name (e.g. ''Buyer 1'' in an anonymised schedule), still capture the record and put that label in `name` exactly as written: whether such a label counts as a name is not a judgement to make here, and the remaining details are needed either way. Never substitute or infer a name. Do not add buyers the source does not identify.', 'f_buyers', 0),
  (0, 4, 'set-8e29b318972d08aa', 'f_buyers.commodity', 'Commodity', 'text', 'group', 'what is sold to this buyer, if stated', 'f_buyers', 2),
  (0, 4, 'set-8e29b318972d08aa', 'f_buyers.location', 'Location', 'text', 'group', 'Destination location port of ultimate buyer; where the products get delivered; can list more than one here.', 'f_buyers', 1),
  (0, 4, 'set-8e29b318972d08aa', 'f_buyers.name', 'Name', 'entity_name', 'group', 'buyer identifier exactly as the source gives it: the company name where named, or the row label verbatim (e.g. ''Buyer 1'') where the source uses positional labels. Transcribe; never substitute, infer or blank it.', 'f_buyers', 0);
INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type, cardinality, description, group_key, sort_order)
VALUES
  (0, 4, 'set-8e29b318972d08aa', 'f_buyers.payment_terms', 'Payment Terms', 'text', 'group', 'payment terms sought or in place with this buyer (e.g. CAD, LC, open account, days credit), if stated', 'f_buyers', 3),
  (0, 4, 'set-8e29b318972d08aa', 'f_buyers.relationship_length', 'Relationship Length', 'text', 'group', 'how long the entity has traded with them, if stated', 'f_buyers', 4),
  (0, 4, 'set-b3e62f504fe720f9', 'f_cargo_insurance_arrangement', 'Cargo Insurance Policy Details', 'text', 'one', 'Insurance policy details covering financed cargo, including coverage percentage, loss payee designation, and endorsement to lender.', NULL, 0),
  (0, 4, 'set-b3e62f504fe720f9', 'f_cargo_insurance_requirements', 'Cargo Insurance Requirements', 'text', 'one', 'Insurance coverage requirements for cargo, including minimum coverage percentage and loss payee designation.', NULL, 0),
  (0, 4, 'set-ce723dac2a0a8438', 'f_carriers', 'Vessel Owner', 'text', 'group', 'Named shipping carriers or transportation providers used to move cargo under the facility.  Named approved carriers', 'f_carriers', 0),
  (0, 4, 'set-ce723dac2a0a8438', 'f_carriers.carrier_name', 'Carrier Name', 'text', 'group', 'Name of Ocean Carrier', 'f_carriers', 0),
  (0, 4, 'set-ce723dac2a0a8438', 'f_carriers.jurisdiction', 'Jurisdiction', 'text', 'group', 'Country of Carrier', 'f_carriers', 1),
  (0, 4, 'capital-structure', 'f_change_of_control_triggers', 'Change Of Control Triggers', 'text', 'many', 'events or instruments under which control of the entity could pass, as stated', NULL, 26),
  (0, 4, 'set-982ebe05e379cc56', 'f_closing_conditions', 'Closing Conditions', 'text', 'many', CONVERT(X'4C697374206F6620636F6E646974696F6E732074686174206D75737420626520736174697366696564206265666F72652074686520666163696C69747920636C6F7365732C20696E636C7564696E672063726564697420617070726F76616C2C20646F63756D656E746174696F6E20657865637574696F6E2C206475652064696C6967656E636520636F6D706C6574696F6E2C20616E64206C656E646572206964656E74696669636174696F6E2E0A' USING utf8mb4), NULL, 0),
  (0, 4, 'set-9854dd80a9a4c4c0', 'f_collateral_description', 'Collateral Description', 'text', 'one', 'Details of collateral securing the facility, including type (e.g., electronic Bill of Lading), transfer mechanism, and security interest held by lender.', NULL, 0),
  (0, 4, 'set-4187e14e49b2d8ef', 'f_collateral_management_agreement', 'Collateral Management Agreement', 'text', 'one', 'Details of legal, formal agreement governing collateral verification, release, and management procedures.', NULL, 0),
  (0, 4, 'set-a98ccb657dc1db45', 'f_commercial_counterparties', 'Commercial Counterparties', 'text', 'group', 'Commercial counterparties connected to the entity, including buyers with whom the entity has documented trading relationships and contracts.  Commercial Counterparties specifically DO NOT include parents, affiliates or subsidiaries of the subject entity', 'f_commercial_counterparties', 0),
  (0, 4, 'set-a98ccb657dc1db45', 'f_commercial_counterparties.contract_details', 'Contract Details', 'text', 'group', '', 'f_commercial_counterparties', 3),
  (0, 4, 'set-a98ccb657dc1db45', 'f_commercial_counterparties.counterparty_name', 'Counterparty Name', 'text', 'group', '', 'f_commercial_counterparties', 0),
  (0, 4, 'set-a98ccb657dc1db45', 'f_commercial_counterparties.location', 'Location', 'text', 'group', '', 'f_commercial_counterparties', 1),
  (0, 4, 'set-a98ccb657dc1db45', 'f_commercial_counterparties.relationship_type', 'Relationship Type', 'text', 'group', '', 'f_commercial_counterparties', 2),
  (0, 4, 'financial-output', 'f_commissions', 'Commissions', 'text', 'many', '3 years.', NULL, 68),
  (0, 4, 'set-7fc0ba66c51eaf7e', 'f_company_summary', 'Company Summary', 'text', 'one', 'one-paragraph description of the entity stating what they do, where they do it, who they do it with, how they are financed', NULL, 0),
  (0, 4, 'set-aa3c68847afcf4e7', 'f_compliance_officer', 'Compliance Officer', 'text', 'one', 'The named compliance officer, MLRO, or responsible person, with title, if the document states one.', NULL, 62),
  (0, 4, 'set-996ad70c6e81efa9', 'f_conditions_restrictions', 'Conditions Restrictions', 'text', 'many', 'conditions, limitations or suspensions recorded on the document', NULL, 34),
  (0, 4, 'set-4187e14e49b2d8ef', 'f_container_specifications', 'Container Specifications', 'text', 'one', 'The size and weight capacity of containers used for shipment, as stated.', NULL, 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_control_account_deposit_requirement', 'Control Account Deposit Requirement', 'text', 'one', 'Requirement that invoiced amounts in excess of agreed facility advances be deposited by the company to a designated control account prior to supplier payment.', NULL, 0),
  (0, 4, 'financial-output', 'f_cost_of_goods', 'Cost Of Goods', 'text', 'many', '3 years.', NULL, 66),
  (0, 4, 'financial-output', 'f_deferred_income', 'Deferred Income', 'text', 'many', '3 years.', NULL, 80),
  (0, 4, 'set-8e29b318972d08aa', 'f_destinations', 'Destinations', 'text', 'many', 'Countries, regions, or ports the goods are delivered TO, as stated.', NULL, 87),
  (0, 4, 'set-215ce9fc78f82d2a', 'f_digital_collateral_platform', 'Digital Collateral Platform', 'text', 'group', 'List of digital collateral platforms on which the memo subject is recording collateral controls', 'f_digital_collateral_platform', 0),
  (0, 4, 'set-215ce9fc78f82d2a', 'f_digital_collateral_platform.collateral_type', 'Collateral Type', 'text', 'group', '', 'f_digital_collateral_platform', 1),
  (0, 4, 'set-215ce9fc78f82d2a', 'f_digital_collateral_platform.platform', 'Platform', 'text', 'group', '', 'f_digital_collateral_platform', 0);
INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type, cardinality, description, group_key, sort_order)
VALUES
  (0, 4, 'set-982ebe05e379cc56', 'f_direct_payment_mechanism', 'Direct Payment Mechanism', 'text', 'one', 'Requirement that the lender or control account servicer make direct payment to approved suppliers in full against receipt of shipping documents and unconditional release of title.', NULL, 0),
  (0, 4, 'corporate-structure', 'f_directors_officers', 'Directors Officers', 'entity_name', 'many', 'Directors, officers and company secretary OF THE ENTITY, with their roles, exactly as stated. Statutory and governance roles only. Do NOT include operational or management staff (country manager, logistics manager, sourcing manager) - those are business information, not corporate governance. Do NOT include a person who certified, witnessed, stamped or filed the document.', NULL, 14),
  (0, 4, 'set-982ebe05e379cc56', 'f_draw_level_transaction_documentation', 'Draw Transaction Documentation', 'text', 'group', 'Individual transaction terms, counterparty details, cargo specifications, pricing, and settlement mechanics for specific facility draws.  total outstanding draws', 'f_draw_level_transaction_documentation', 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_draw_level_transaction_documentation.amount', 'Amount', 'text', 'group', '', 'f_draw_level_transaction_documentation', 3),
  (0, 4, 'set-982ebe05e379cc56', 'f_draw_level_transaction_documentation.cargo', 'Cargo', 'text', 'group', '', 'f_draw_level_transaction_documentation', 2),
  (0, 4, 'set-982ebe05e379cc56', 'f_draw_level_transaction_documentation.counterparty', 'Counterparty', 'text', 'group', '', 'f_draw_level_transaction_documentation', 1),
  (0, 4, 'set-982ebe05e379cc56', 'f_draw_level_transaction_documentation.draw_number', 'Draw Number', 'text', 'group', '', 'f_draw_level_transaction_documentation', 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_draw_level_transaction_documentation.status', 'Status', 'text', 'group', '', 'f_draw_level_transaction_documentation', 5),
  (0, 4, 'set-982ebe05e379cc56', 'f_draw_level_transaction_documentation.terms', 'Terms', 'text', 'group', '', 'f_draw_level_transaction_documentation', 4),
  (0, 4, 'set-982ebe05e379cc56', 'f_draw_mechanics', 'Draw Mechanics', 'text', 'one', 'Terms governing how and when individual draws can be made under the facility, including timing relative to bill of lading issuance and payment terms.', NULL, 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_electronic_bill_of_lading_requirement', 'Electronic Bill of Lading Requirement', 'text', 'one', 'Requirement that an electronic bill of lading in approved form be transferred to the lender''s digital wallet prior to loan disbursement.', NULL, 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_electronic_bills_of_lading_transfer', 'Electronic Bills of Lading Transfer', 'text', 'one', 'The process and platforms through which electronic Bills of Lading are transferred to the lender prior to disbursement.', NULL, 0),
  (0, 4, 'corporate-structure', 'f_entity_type', 'Entity Type', 'text', 'one', 'legal form (SA, GmbH, Ltd, etc.)', NULL, 11),
  (0, 4, 'capital-structure', 'f_equity_instruments', 'Equity Instruments', 'text', 'many', 'options, warrants, convertibles, call or put options, subscription rights: holder, quantity or percentage, exercise terms, consideration, expiry', NULL, 23),
  (0, 4, 'business-overview', 'f_existing_bank_lines', 'Existing Bank Lines', 'text', 'many', 'existing bank lines / facilities, if stated', NULL, 8),
  (0, 4, 'financial-output', 'f_expenses', 'Expenses', 'text', 'many', CONVERT(X'3320796561727320C3A2E282ACE2809D20776974682064657461696C20696620676976656E2E' USING utf8mb4), NULL, 70),
  (0, 4, 'set-3b6934871fb65d44', 'f_facility_structure_and_transaction_types', 'Facility Structure and Transaction Types', 'text', 'many', 'Description of the proposed facility structure, including transaction types (CAD, LC, Open Account, TCI) and assumptions about counterparty payment discipline, interest rate and fees, restrictions and conditions, maximum draw, maximum total facility size and other relevant data', NULL, 0),
  (0, 4, 'corporate-structure', 'f_filings_status', 'Filings Status', 'text', 'many', 'statutory filings made, pending or in remediation, as stated: register extracts, officer or UBO filings, corrective filings, tax-record amendments', NULL, 19),
  (0, 4, 'set-0976eeb94c0aaf44', 'f_financing_requested', 'Financing Requested', 'text', 'one', 'The financing being sought: amount, currency, tenor, facility type, advance rate, and pricing expectation, to the extent stated.', NULL, 92),
  (0, 4, 'set-9e86cd1f3f271c48', 'f_financing_terms', 'Financing Terms', 'text', 'one', 'the proposed interest rate, rate type and fee schedule for  a given facility', NULL, 0),
  (0, 4, 'set-5ce679c7ec3002e2', 'f_flow_stages_sought', 'Funding Request Details', 'text', 'many', CONVERT(X'466F722074726164652066696E616E63653A20576869636820737461676573206F6620746865207472616465206379636C652066696E616E63696E6720697320736F7567687420666F722E20557365206F6E6C79207374616765732074686520646F63756D656E742061637475616C6C79206964656E7469666965732C2066726F6D3A20757073747265616D2077617265686F7573652C20696E6C616E64207472616E73706F72742C20736561626F726E65207472616E7369742C20646F776E73747265616D2077617265686F7573652C2072656365697661626C65732E2053746174652065616368207769746820616E792064657461696C20676976656E20286475726174696F6E2C2076616C75652C206C6F636174696F6E292E0A0A466F72206F74686572207479706573206F662066696E616E63653A206174207768617420737461676520696E2074686520627573696E657373206379636C652069732066756E64696E672072657175697265642C20616E64207768656E20697320697420657870656374656420746F20626520726570616964' USING utf8mb4), NULL, 0),
  (0, 4, 'business-overview', 'f_geographies', 'Geographies', 'text', 'many', 'countries/regions of operation', NULL, 5);
INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type, cardinality, description, group_key, sort_order)
VALUES
  (0, 4, 'financial-output', 'f_gross_profit', 'Gross Profit', 'text', 'many', CONVERT(X'3320796561727320C3A2E282ACE2809D20746F74616C20616E642061732070657263656E74616765206F662073616C65732E' USING utf8mb4), NULL, 69),
  (0, 4, 'financial-output', 'f_gross_revenue', 'Gross Revenue', 'text', 'many', '3 years (one entry per year, with year and currency).', NULL, 65),
  (0, 4, 'set-f4bddf21398e8180', 'f_group_relationships', 'Group Relationships', 'text', 'one', 'nature of group/parent/subsidiary ties, in prose', NULL, 18),
  (0, 4, 'trade-flow-profile', 'f_headquarters', 'Headquarters', 'address', 'one', 'Where the business is actually headquartered or principally operates from, if stated. This may differ from the registered office.', NULL, 91),
  (0, 4, 'set-7a7c8571644658f2', 'f_id_verified', 'Id Verified', 'text', 'group', CONVERT(X'4D6574686F6420616E6420636F6E6669726D6174696F6E206F66206964656E7469747920766572696669636174696F6E206F6620616C6C20706572736F6E7320616E6420656E7469746965732028706172656E74732C207375627369646961726965732C20636F6D70616E79206F7220616666696C6961746573292E202073686F7720746865207461626C6520696E2073656374696F6E732E200A416666696C69617465732061726520616C6C20656E746974696573207768657265206120706572736F6E20686173206D6F7265207468616E2031302520636F6E74726F6C' USING utf8mb4), 'f_id_verified', 0),
  (0, 4, 'set-7a7c8571644658f2', 'f_id_verified.document', 'Document', 'text', 'group', 'Passport number or registration number of entity', 'f_id_verified', 2),
  (0, 4, 'set-7a7c8571644658f2', 'f_id_verified.jurisdiction', 'Jurisdiction', 'text', 'group', 'Country of person''s residency or entity''s registered address', 'f_id_verified', 3),
  (0, 4, 'set-7a7c8571644658f2', 'f_id_verified.person_or_entity', 'Person or Entity', 'text', 'group', 'Name of person or entity', 'f_id_verified', 0),
  (0, 4, 'set-7a7c8571644658f2', 'f_id_verified.relationship', 'Relationship', 'text', 'group', 'What is person''s or entity''s relationship to subject of the memo.', 'f_id_verified', 4),
  (0, 4, 'set-7a7c8571644658f2', 'f_id_verified.verification', 'Verification', 'text', 'group', 'Method of confirming identity of person or entity', 'f_id_verified', 1),
  (0, 4, 'licenses-certifications', 'f_identifier', 'Identifier', 'identifier', 'one', 'licence, registration, operator or scheme number as stated', NULL, 31),
  (0, 4, 'corporate-structure', 'f_incorporation_details', 'Incorporation Details', 'text', 'one', CONVERT(X'64617465206F6620696E636F72706F726174696F6E2C20726567697374726174696F6E206E756D6265722C2072656769737465726564206F666669636520616464726573732C20746178206964656E74696669636174696F6E206E756D6265722C206C6567616C206E616D65206F66207375626A65637420656E746974790A0A50726573656E742061732061206C6973743B206C696D6974207468697320746F206F6E6C7920746865207375626A656374206F6620746865206D656D6F2C20646F206E6F742067617468657220666F7220616666696C69617465732C20706172656E74732C20737562736964696172696573206F7220636F6D6D65726369616C20636F756E74657270617274696573' USING utf8mb4), NULL, 0),
  (0, 4, 'set-2350ba07951d4ccf', 'f_incoterms', 'Incoterms', 'text', 'one', 'The stated terms of sale governing the transfer of goods and risk between buyer and seller.', NULL, 0),
  (0, 4, 'business-overview', 'f_industry_context', 'Industry Context', 'text', 'one', 'sector / market positioning', NULL, 6),
  (0, 4, 'financial-output', 'f_intercompany_payables', 'Intercompany Payables', 'text', 'many', CONVERT(X'3320796561727320C3A2E282ACE2809D20776974682077686F6D2E' USING utf8mb4), NULL, 82),
  (0, 4, 'financial-output', 'f_intercompany_receivables', 'Intercompany Receivables', 'text', 'many', CONVERT(X'3320796561727320C3A2E282ACE2809D20776974682077686F6D2E' USING utf8mb4), NULL, 81),
  (0, 4, 'corporate-structure', 'f_jurisdiction', 'Jurisdiction', 'text', 'one', 'country/state of incorporation', NULL, 12),
  (0, 4, 'corporate-structure', 'f_legal_name', 'Legal Name', 'entity_name', 'one', 'full legal entity name', NULL, 10),
  (0, 4, 'set-c29380c9143e4948', 'f_letter_of_credit_covered_receivables_by_jurisdiction', 'LC Backed Receivables by Country', 'text', 'group', 'Amount of receivables covered by letter of credit by country, with date and currency.', 'f_letter_of_credit_covered_receivables_by_jurisdiction', 0),
  (0, 4, 'set-c29380c9143e4948', 'f_letter_of_credit_covered_receivables_by_jurisdiction.amount', 'Amount', 'text', 'group', 'USD amount', 'f_letter_of_credit_covered_receivables_by_jurisdiction', 1),
  (0, 4, 'set-c29380c9143e4948', 'f_letter_of_credit_covered_receivables_by_jurisdiction.bank', 'Bank', 'text', 'group', 'LC Bank', 'f_letter_of_credit_covered_receivables_by_jurisdiction', 4),
  (0, 4, 'set-c29380c9143e4948', 'f_letter_of_credit_covered_receivables_by_jurisdiction.currency', 'Currency', 'text', 'group', 'USD', 'f_letter_of_credit_covered_receivables_by_jurisdiction', 2),
  (0, 4, 'set-c29380c9143e4948', 'f_letter_of_credit_covered_receivables_by_jurisdiction.date', 'Date', 'text', 'group', 'As of date', 'f_letter_of_credit_covered_receivables_by_jurisdiction', 3),
  (0, 4, 'set-c29380c9143e4948', 'f_letter_of_credit_covered_receivables_by_jurisdiction.jurisdiction', 'Jurisdiction', 'text', 'group', 'Country Name', 'f_letter_of_credit_covered_receivables_by_jurisdiction', 0),
  (0, 4, 'set-4b0176c5e8974e9b', 'f_leverage_and_debt_service_metrics', 'Leverage and Debt Service Metrics', 'text', 'one', 'Debt service coverage ratio, interest coverage ratio, leverage covenant framework, or other metrics assessing the entity''s ability to service debt.', NULL, 0),
  (0, 4, 'licenses-certifications', 'f_licence_or_certificate', 'Licence Or Certificate', 'text', 'one', 'what the document is, as titled', NULL, 28),
  (0, 4, 'financial-output', 'f_liens_on_assets', 'Liens On Assets', 'text', 'many', 'With whom.', NULL, 84);
INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type, cardinality, description, group_key, sort_order)
VALUES
  (0, 4, 'financial-output', 'f_long_term_debt', 'Long Term Debt', 'text', 'many', CONVERT(X'3320796561727320C3A2E282ACE2809D20776974682077686F6D2E' USING utf8mb4), NULL, 85),
  (0, 4, 'trade-flow-profile', 'f_margins_stated', 'Margins Stated', 'text', 'one', 'Gross or trading margin as NARRATED in this document, per unit or per percentage, with the basis stated.', NULL, 90),
  (0, 4, 'financial-output', 'f_operating_profit', 'Operating Profit', 'text', 'many', '3 years.', NULL, 71),
  (0, 4, 'set-8e29b318972d08aa', 'f_origins', 'Origins', 'text', 'many', 'Countries, regions, or ports the goods are sourced or shipped FROM, as stated.', NULL, 86),
  (0, 4, 'business-overview', 'f_other_debt', 'Other Debt', 'text', 'many', 'other debt obligations, if stated', NULL, 9),
  (0, 4, 'set-f8aa0257067ff0fc', 'f_outstanding_draws_by_jurisdiction', 'Outstanding Draws by Jurisdiction', 'text', 'one', 'Sum of outstanding draws from the client by jurisdicition (meaning country)', NULL, 0),
  (0, 4, 'set-1d3ad329fa97a88b', 'f_ownership_and_control', 'Ownership And Control', 'entity_name', 'group', CONVERT(X'4E616D656420696E646976696475616C7320616E6420656E746974696573207768696368206F776E20616E642F6F7220636F6E74726F6C2074686520636F6D70616E792E2073686F7720746865207461626C6520696E207468652073656374696F6E732E0A47726F7570207461626C6520627920656E746974792C2073746172742077697468206D61696E20636F6D70616E792C207468656E20706172656E742C207468656E20737562732C207468656E20616666696C6961746573' USING utf8mb4), 'f_ownership_and_control', 0),
  (0, 4, 'set-1d3ad329fa97a88b', 'f_ownership_and_control.entity', 'Entity', 'text', 'group', 'Name of company, parent of company, affiliate or subsidiary ', 'f_ownership_and_control', 1),
  (0, 4, 'set-1d3ad329fa97a88b', 'f_ownership_and_control.jurisdiction', 'Jurisdiction', 'text', 'group', 'Jurisdiction of Entity', 'f_ownership_and_control', 2),
  (0, 4, 'set-1d3ad329fa97a88b', 'f_ownership_and_control.percent', 'Percent', 'text', 'group', 'Percent control by person over entity', 'f_ownership_and_control', 3),
  (0, 4, 'set-1d3ad329fa97a88b', 'f_ownership_and_control.person', 'Person', 'text', 'group', 'Name of UBO', 'f_ownership_and_control', 0),
  (0, 4, 'corporate-structure', 'f_ownership_as_stated', 'Ownership As Stated', 'entity_name', 'many', 'Owners and their holdings exactly as the source states them, including percentages or share counts where given. Registered holders and beneficial owners both, each attributed to the source''s own wording.', NULL, 15),
  (0, 4, 'capital-structure', 'f_paid_up_status', 'Paid Up Status', 'text', 'one', 'whether capital is paid up, partly paid or unpaid, and any date given for payment', NULL, 21),
  (0, 4, 'set-f41da6fb652dbb5d', 'f_parent_guarantee', 'Parent Guarantee', 'text', 'many', 'description of a parent guarantee if it exists describing who the parent is, the amount and nature of the guarantee.', NULL, 0),
  (0, 4, 'set-02eddf08f7754e51', 'f_payment_control_account', 'Payment Control Account', 'text', 'one', 'The designated bank account and institution through which buyer payments are routed and controlled.', NULL, 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_payment_terms', 'Payment Terms', 'text', 'one', 'Terms for payment by buyers, including payment methods (CAD, LC, Open Account) and timing.', NULL, 0),
  (0, 4, 'KYC', 'f_pep_matches', 'Pep Matches', 'entity_name', 'group', 'PEP status of all named persons; a named person is someone related directly to the company, any of its parents, subsidiaries or affiliates; THIS DO NOT include persons related to commercial counterparties or the preparer of this memo or the provider of financing.  ', 'f_pep_matches', 0),
  (0, 4, 'KYC', 'f_pep_matches.notes', 'NOTES', 'text', 'group', CONVERT(X'526573756C7473206F66205045502070726F6365737320696620617661696C61626C653B20224E2F4122206966206E6F7420617661696C61626C65' USING utf8mb4), 'f_pep_matches', 2),
  (0, 4, 'KYC', 'f_pep_matches.pep_status', 'PEP STATUS', 'text', 'group', 'One of ''Pending'', ''Waived'', ''Processed''; default to Pending if no data available', 'f_pep_matches', 1),
  (0, 4, 'KYC', 'f_pep_matches.person', 'PERSON', 'text', 'group', 'Name of subject person', 'f_pep_matches', 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_per_draw_conditions', 'Per-Draw Conditions', 'text', 'one', 'List of conditions that must be satisfied for each individual draw or disbursement under the facility, including bill of lading requirements, platform registration, and payment procedures.', NULL, 0);
INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type, cardinality, description, group_key, sort_order)
VALUES
  (0, 4, 'KYC', 'f_persons', 'Persons', 'group', 'group', CONVERT(X'4F6E65207265636F726420706572206E61747572616C20706572736F6E202855424F2C206469726563746F722C206F666669636572206F7220617574686F7269736564207369676E61746F727929204F4620544845204173736F636961746520456E746974696573206E616D656420696E2074686520646F63756D656E742E20496E636C756465206F6E6C7920706572736F6E732061637475616C6C79206E616D65643B20646F206E6F7420696E76656E742E20446F204E4F5420696E636C756465206120706572736F6E2077686F206D6572656C79206365727469666965642C207769746E65737365642C207374616D7065642C206E6F74617269736564206F722066696C65642074686520646F63756D656E742C206F722061207265676973747279206F6666696369616C2070726F63657373696E67206974202D207468657920617265206E6F74207061727469657320746F2074686520656E746974792E0A0A444F204E4F5420696E636C75646520616E796F6E652077686F206973206E6F74206469726563746C79206173736F636961746564207769746820746865207072696E636970616C2074617267657473206F662074686973206D656D6F2028636F6D70616E792C20616666696C69617465732C2073756273696469617269657320616E6420706172656E7429206F662074686973206D656D6F3B20646F206E6F7420696E636C75646520616E796F6E65206173736F6369617465642077697468206C656E6465722C20636F6D6D65726369616C20636F756E74657270617274696573206F72207375626D6974746572206F66206D656D6F2E202020444F2073686F772074686520656E74697265207461626C6520696E207468652073656374696F6E7320696E20776869636820697420697320666F756E642E' USING utf8mb4), 'f_persons', 0),
  (0, 4, 'KYC', 'f_persons.date_of_birth', 'Date Of Birth', 'date', 'group', 'date of birth, if stated', 'f_persons', 3),
  (0, 4, 'KYC', 'f_persons.full_name', 'Full Name', 'entity_name', 'group', 'full legal name as stated', 'f_persons', 0),
  (0, 4, 'KYC', 'f_persons.id_document', 'Id Document', 'identifier', 'group', 'ID document type and number, if stated', 'f_persons', 6),
  (0, 4, 'KYC', 'f_persons.nationality', 'Nationality', 'text', 'group', 'nationality/nationalities, if stated', 'f_persons', 4),
  (0, 4, 'KYC', 'f_persons.ownership_pct', 'Ownership Pct', 'number', 'group', 'percentage owned, if stated for this person', 'f_persons', 2),
  (0, 4, 'KYC', 'f_persons.pep_status', 'Pep Status', 'text', 'group', 'PEP status/flag for this person, if stated', 'f_persons', 7),
  (0, 4, 'KYC', 'f_persons.residential_address', 'Residential Address', 'address', 'group', 'residential address, if stated', 'f_persons', 5),
  (0, 4, 'KYC', 'f_persons.role', 'Role', 'text', 'group', 'role/capacity: UBO, director, signatory, or as stated', 'f_persons', 1),
  (0, 4, 'set-982ebe05e379cc56', 'f_pledged_assets', 'Pledged Assets', 'text', 'one', 'Description of assets pledged as collateral for the facility, including the form of the assets and how they are transferred to the lender.', NULL, 0),
  (0, 4, 'aml-policies-summary', 'f_policy_document', 'AML Policy Document', 'text', 'one', 'Identification of the document as stated: title, issuing entity, version, effective or approval date, and review cycle, to the extent given.', NULL, 0),
  (0, 4, 'aml-policies-summary', 'f_policy_provided', 'AML Policy Provided', 'text', 'one', CONVERT(X'57686574686572207468697320646F63756D656E742069732C206F7220636F6E7461696E732C20616E20414D4C2F43544620706F6C696379206F722070726F6772616D6D65206465736372697074696F6E2E20416E73776572202779657327206F7220276E6F27206261736564206F6E6C79206F6E20776861742074686520646F63756D656E742069732E20446F206E6F7420636F6D6D656E74206F6E20776865746865722074686520636F756E74657270617274792068617320612070726F6772616D6D6520C3A2E282ACE2809D206F6E6C79206F6E2077686174207468697320646F63756D656E7420636F6E7461696E732E' USING utf8mb4), NULL, 0),
  (0, 4, 'aml-policies-summary', 'f_policy_summary', 'AML Policy Summary', 'text', 'one', CONVERT(X'412073756D6D6172792C20696E2070726F73652C206F6620746865207465726D732074686520706F6C6963792061637475616C6C792073657473206F757420C3A2E282ACE2809D20746865206F626C69676174696F6E732C20636F6E74726F6C732C20616E642070726F63656475726573206974206465736372696265732E2053756D6D617269736520776861742069732074686572653B20646F206E6F74206C697374207768617420697320616273656E742E' USING utf8mb4), NULL, 0),
  (0, 4, 'set-3b6934871fb65d44', 'f_pricing_structure', 'Pricing Structure', 'text', 'group', 'The pricing terms for each transaction type, including base rate, spread, and all-in target rates.', 'f_pricing_structure', 0),
  (0, 4, 'set-3b6934871fb65d44', 'f_pricing_structure.all_in_target_rate', 'All-in Target Rate', 'text', 'group', '', 'f_pricing_structure', 3),
  (0, 4, 'set-3b6934871fb65d44', 'f_pricing_structure.base_rate', 'Base Rate', 'text', 'group', '', 'f_pricing_structure', 1),
  (0, 4, 'set-3b6934871fb65d44', 'f_pricing_structure.spread_bps', 'Spread (bps)', 'text', 'group', '', 'f_pricing_structure', 2),
  (0, 4, 'set-3b6934871fb65d44', 'f_pricing_structure.transaction_type', 'Transaction Type', 'text', 'group', '', 'f_pricing_structure', 0),
  (0, 4, 'set-5be6a0b276ddd29f', 'f_product_and_port', 'Product And Port', 'text', 'group', 'This is a listing of the ports of origin and destination for the products traded by the subject of the memo. ', 'f_product_and_port', 0),
  (0, 4, 'set-5be6a0b276ddd29f', 'f_product_and_port.port', 'Port', 'text', 'group', 'Port Name and Country', 'f_product_and_port', 0),
  (0, 4, 'set-5be6a0b276ddd29f', 'f_product_and_port.product', 'Product', 'text', 'group', 'Products traded at the Port', 'f_product_and_port', 1),
  (0, 4, 'set-5be6a0b276ddd29f', 'f_product_and_port.route', 'Route', 'text', 'group', 'Origin or Destination', 'f_product_and_port', 2),
  (0, 4, 'set-d24a415599f6fe5e', 'f_products_commodities', 'Products Commodities', 'text', 'many', 'goods/commodities it trades or produces', NULL, 2);
INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type, cardinality, description, group_key, sort_order)
VALUES
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_balance_sheet', 'Projected Balance Sheet', 'text', 'group', 'This is a three year projection os balance sheet', 'f_projected_balance_sheet', 0),
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_balance_sheet.category', 'Category', 'text', 'group', 'Balance sheet items', 'f_projected_balance_sheet', 0),
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_balance_sheet.year_1', 'Year 1', 'text', 'group', 'Value of Items year 1', 'f_projected_balance_sheet', 1),
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_balance_sheet.year_2', 'Year 2', 'text', 'group', 'Value of Items year 2', 'f_projected_balance_sheet', 2),
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_balance_sheet.year_3', 'Year 3', 'text', 'group', 'Value of Items year 3', 'f_projected_balance_sheet', 3),
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_financial_pnl', 'Projected Financial PnL', 'text', 'group', 'this is a table of projected profit and loss for 3 years', 'f_projected_financial_pnl', 0),
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_financial_pnl.category', 'Category', 'text', 'group', 'Revenue, Sales Charges / commissions, net sales, expenses, taxes,etc', 'f_projected_financial_pnl', 0),
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_financial_pnl.year_1', 'Year 1', 'text', 'group', 'Data  values related to Category for first year projection', 'f_projected_financial_pnl', 1),
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_financial_pnl.year_2', 'Year 2', 'text', 'group', 'Data values for projections year 2', 'f_projected_financial_pnl', 2),
  (0, 4, 'set-258547ed5ef42ed9', 'f_projected_financial_pnl.year_3', 'Year 3', 'text', 'group', 'Data values for projections year 3', 'f_projected_financial_pnl', 3),
  (0, 4, 'set-ae36c86fa805ecec', 'f_receivables_financing_source', 'Receivables Financing Source', 'text', 'one', 'The named entity currently financing receivables and the mechanism by which repayment is triggered.', NULL, 0),
  (0, 4, 'capital-structure', 'f_recent_transfers', 'Recent Transfers', 'text', 'many', 'share transfers recorded in the instrument, with date, parties and consideration', NULL, 27),
  (0, 4, 'set-3530bf6f479b69b0', 'f_risk_notes', 'Risk Notes', 'text', 'one', 'Any stated risk commentary, disposition, or analyst note.', NULL, 45),
  (0, 4, 'KYC', 'f_sanctions_matches', 'Sanctions Matches', 'entity_name', 'group', 'Named individuals and entities flagged as sanctioned.  Do not list persons or entities for which no sanctions data is present.', 'f_sanctions_matches', 0),
  (0, 4, 'KYC', 'f_sanctions_matches.person_or_entity', 'Person or Entity', 'text', 'group', 'Name of Person or Entity', 'f_sanctions_matches', 0),
  (0, 4, 'KYC', 'f_sanctions_matches.sanction', 'Sanction', 'text', 'group', 'List positive sanction result here in detail.', 'f_sanctions_matches', 1),
  (0, 4, 'set-07a0d46e2e6c29d4', 'f_screening_coverage', 'Screening Coverage', 'text', 'group', 'Parties covered by the screening: the entity itself, beneficial owners, directors, or associated parties.', 'f_screening_coverage', 0),
  (0, 4, 'set-07a0d46e2e6c29d4', 'f_screening_coverage.date_of_screening', 'Date of Screening', 'text', 'group', 'Date report is receive from screening provider', 'f_screening_coverage', 3),
  (0, 4, 'set-07a0d46e2e6c29d4', 'f_screening_coverage.result', 'Result', 'text', 'group', CONVERT(X'22436C65616E22206F72202253656520526573756C74202D2073686F7720746578742073756D6D617279206F6620746865207265706F7274206966206E6F7420636C65616E22' USING utf8mb4), 'f_screening_coverage', 2),
  (0, 4, 'set-07a0d46e2e6c29d4', 'f_screening_coverage.screening_provider', 'Screening Provider', 'text', 'group', 'Which entity or entities (there can be more than one listed in this column) provided the result', 'f_screening_coverage', 1),
  (0, 4, 'set-07a0d46e2e6c29d4', 'f_screening_coverage.type_of_screening', 'Type of Screening', 'text', 'group', CONVERT(X'6F6E65206F66202241647665727365204D65646961222C202253616E6374696F6E73222C202250455022' USING utf8mb4), 'f_screening_coverage', 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_set_off_rights', 'Set-Off Rights', 'text', 'one', 'Rights of the lender to withhold or offset payments between multiple draws or transactions under the facility.', NULL, 0),
  (0, 4, 'set-02eddf08f7754e51', 'f_settlement_account_details', 'Settlement Account Details', 'text', 'one', 'Designated bank account through which payments are routed, including bank name, location, and regulatory status.', NULL, 0),
  (0, 4, 'set-982ebe05e379cc56', 'f_settlement_bank', 'Settlement Bank', 'text', 'one', 'Named bank or banks designated to hold control accounts and settle payments under the facility.', NULL, 0),
  (0, 4, 'capital-structure', 'f_shareholder_register', 'Shareholder Register', 'text', 'many', 'holders and holdings as recorded in the instrument, with share numbers or percentages if stated', NULL, 22),
  (0, 4, 'set-998475fa9f7f74bc', 'f_short_introduction', 'Short Introduction - KYC / DD', 'text', 'one', 'No more that three paragraphs TOTAL describing business model, financial ask by the memo subject and intent of the memo = KYC on subject and all releveant commercial and UBO entities.  do NOT list the relevant commercial or UBO entities here.  do not present any proposed financing details here, just present the ask', NULL, 0),
  (0, 4, 'set-349706869bd112aa', 'f_short_introduction_lender', 'Short Introduction - LENDER', 'text', 'one', 'No more that three paragraphs TOTAL describing business model, financial ask by the memo subject and intent of the memo = Describing opportunity to a potential lender.  do NOT list the relevant commercial or UBO entities here.  do not present any proposed financing details here, just present the ask and intent of memo', NULL, 0);
INSERT INTO config_field
  (tenant_id, revision, schema_key, field_key, label, field_type, cardinality, description, group_key, sort_order)
VALUES
  (0, 4, 'financial-output', 'f_short_term_bank_debt', 'Short Term Bank Debt', 'text', 'many', CONVERT(X'3320796561727320C3A2E282ACE2809D20776974682077686F6D2E' USING utf8mb4), NULL, 83),
  (0, 4, 'KYC', 'f_source_of_funds', 'Source Of Funds', 'text', 'one', 'Description of source of wealth and of equity in the company.', NULL, 39),
  (0, 4, 'set-8e29b318972d08aa', 'f_suppliers', 'Suppliers', 'group', 'group', 'One record per supplier the source identifies, whether the source lists them in a table or describes them in prose. Capture every supplier it identifies, in the order given. Where a supplier is identified only by a positional or placeholder label rather than a company name (e.g. ''Supplier 1'' in an anonymised schedule), still capture the record and put that label in `name` exactly as written: whether such a label counts as a name is not a judgement to make here, and the remaining details are needed either way. Never substitute or infer a name. Do not add suppliers the source does not identify.', 'f_suppliers', 0),
  (0, 4, 'set-8e29b318972d08aa', 'f_suppliers.commodity', 'Commodity', 'text', 'group', 'what is bought from this supplier, if stated', 'f_suppliers', 2),
  (0, 4, 'set-8e29b318972d08aa', 'f_suppliers.location', 'Location', 'text', 'group', 'locatio of supply purchases, port of origin, can list several here', 'f_suppliers', 1),
  (0, 4, 'set-8e29b318972d08aa', 'f_suppliers.name', 'Name', 'entity_name', 'group', 'supplier identifier exactly as the source gives it: the company name where named, or the row label verbatim (e.g. ''Supplier 1'') where the source uses positional labels. Transcribe; never substitute, infer or blank it.', 'f_suppliers', 0),
  (0, 4, 'set-8e29b318972d08aa', 'f_suppliers.payment_terms', 'Payment Terms', 'text', 'group', 'payment terms expected or in place with this supplier (e.g. CAD, prepayment, 30 days, LC), if stated', 'f_suppliers', 3),
  (0, 4, 'set-8e29b318972d08aa', 'f_suppliers.relationship_length', 'Relationship Length', 'text', 'group', 'how long the entity has traded with them, if stated', 'f_suppliers', 4),
  (0, 4, 'financial-output', 'f_taxes', 'Taxes', 'text', 'many', '3 years.', NULL, 72),
  (0, 4, 'financial-output', 'f_total_assets', 'Total Assets', 'text', 'many', '3 years.', NULL, 75),
  (0, 4, 'financial-output', 'f_total_equity', 'Total Equity', 'text', 'many', '3 years.', NULL, 74),
  (0, 4, 'financial-output', 'f_total_other_payables_accrued', 'Total Other Payables Accrued', 'text', 'many', CONVERT(X'3320796561727320C3A2E282ACE2809D206F746865722070617961626C657320616E64206163637275656420657870656E7365732E' USING utf8mb4), NULL, 79),
  (0, 4, 'financial-output', 'f_total_other_receivables', 'Total Other Receivables', 'text', 'many', '3 years of non-operating accounts receivable', NULL, 77),
  (0, 4, 'financial-output', 'f_total_trade_payables', 'Total Trade Payables', 'text', 'many', '3 years.', NULL, 78),
  (0, 4, 'financial-output', 'f_total_trade_receivables', 'Total Accounts Receivables', 'text', 'many', '3 years of operating accounts receivable', NULL, 76),
  (0, 4, 'set-b3e62f504fe720f9', 'f_trade_credit_insurance_provider_and_terms', 'Trade Credit Insurance Provider and Terms', 'text', 'one', 'Identity of the TCI provider, policy terms, coverage limits, exclusions, claims procedures, and financial strength of the insurer used as credit mitigation.', NULL, 0),
  (0, 4, 'business-overview', 'f_trade_flows', 'Trade Flows', 'text', 'one', 'how goods/payments move, if described', NULL, 7),
  (0, 4, 'financial-output', 'f_trade_history_notes', 'Trade History Notes', 'text', 'many', 'Stated history, volume, length of dealing; commodities, origins/destinations, suppliers/buyers.', NULL, 67),
  (0, 4, 'capital-structure', 'f_transfer_restrictions', 'Transfer Restrictions', 'text', 'one', 'pre-emption rights, board approval, drag or tag, lock-up or other restriction on transfer', NULL, 24),
  (0, 4, 'trade-flow-profile', 'f_turnover_stated', 'Turnover Stated', 'text', 'one', 'Annual turnover or trading volume as NARRATED in this document (not from financial statements). Include the period and currency stated and how many turns per year this represents;', NULL, 89),
  (0, 4, 'set-4187e14e49b2d8ef', 'f_upstream_warehouse_collateral_manager', 'Upstream Warehouse Collateral Manager', 'text', 'one', 'The named entity responsible for independent verification and collateral management of inventory at the warehouse stage.', NULL, 0),
  (0, 4, 'set-349706869bd112aa', 'f_vessel_charter', 'Vessel Charter', 'text', 'one', 'Information about vessels chartered by the entity for cargo transportation.', NULL, 0),
  (0, 4, 'set-4187e14e49b2d8ef', 'f_vessel_operators', 'Vessel Operators', 'text', 'group', 'Named shipping companies or carriers used to transport goods between ports.', 'f_vessel_operators', 0),
  (0, 4, 'set-4187e14e49b2d8ef', 'f_vessel_operators.jurisdiction', 'Jurisdiction', 'text', 'group', 'Country of operator', 'f_vessel_operators', 1),
  (0, 4, 'set-4187e14e49b2d8ef', 'f_vessel_operators.operator_name', 'Operator', 'text', 'group', 'Name of operator', 'f_vessel_operators', 0),
  (0, 4, 'set-4187e14e49b2d8ef', 'f_warehouse_location_and_operator', 'Warehouse Location and Operator', 'text', 'one', 'The named warehouse facility where inventory is stored under collateral management, including its location and operator.', NULL, 0);

-- --- template TRADEFINANCE-Credit, revision 5 ---

INSERT INTO config_revision
  (tenant_id, revision, status, kind, pack_key, forked_from, note,
   published_at, published_by)
VALUES (0, 5, 'published', 'template', 'TRADEFINANCE-Credit', 'tenant:2:53',
        'credit-memorandum, copied from tenant 2 revision 53', UTC_TIMESTAMP(), 'migration 021');
INSERT INTO config_template
  (tenant_id, revision, template_key, label)
VALUES
  (0, 5, 'credit-memorandum', 'TRADE FINANCE - Credit Memo');
INSERT INTO config_section
  (tenant_id, revision, template_key, section_key, numeral, title, kind, shape_key, prompt, context_sections, sort_order)
VALUES
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'I', 'Executive Summary & Credit Request', 'extract', 'executive-summary-credit-request', CONVERT(X'5374617465207468652066696E616E63696E672072657175657374656420616E64202F206F7220616C72656164792070726F766964653B2073746174652074686520746F74616C206578706F7375726573206F6E2074686520666163696C6974792069662064726177732065786973742E0A44657363726962652074686520627573696E657373206D6F64656C206F6620746865207375626A656374206F6620746865206D656D6F3B2074686569722073616C65733B2067726F7373206D617267696E73202825293B207475726E7320706572207965617220616E64206E657420696E636F6D653B2073746174652074686569722065717569747920616E6420746F74616C20646562742E0A0A73746174652074686520707572706F7365206F6620746865206D656D6F3A207468697320697320612066756C736F6D652063726564697420726576696577206F662074686520636C69656E742E20204B59432069732068616E646C65642073657061726174656C7920616E642070726F7669646564206173206174746163686D656E74732E200A0A5573652073686F727420636F6E63697365206C616E67756167652C20696620646F696E20612070726F7365206C6973742C207573652062756C6C65747320776974682065736320616E7465636564656E74' USING utf8mb4), NULL, 1),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'II', 'Purpose & Trade Flow', 'extract', 'purpose-trade-flow', CONVERT(X'5265616420616C6C20746865206669656C647320616E642070726F6475636520546872656520706172616772617068733A20200A0A526573746174652074686520627573696E657373206D6F64656C2C20666F637573696E67206F6E207768792074686579206E656564206361706974616C0A5374617465207768656E20746865206361706974616C20617474616368657320286965207768656E20646F2074686579206D616B652061206472617720616E6420616761696E7374207768617420636F6C6C61746572616C290A446573637269626520746865697220747261646520666C6F772077686572652074686579206275792066726F6D20616E642073656C6C20746F2E200A0A55736520636F6E636973652073686F72742070726F66657373696F6E616C206C616E67756167652C20616E64206966206C697374696E67206974656D7320696E2070726F73652C207573652062756C6C6574732C20776974682065736320616E7465636564656E742E' USING utf8mb4), NULL, 2),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'III', 'Borrower Overview', 'extract', 'borrower-overview', CONVERT(X'4769766520612074687265652070617261677261706873206F7665727669657720544F54414C2E20206E6F206D6F7265207468617420746872656520706172616772617068732064697363757373696E672074686520626F72726F7765722C2077686174207468657920646F2C2077686F206F776E73207468656D2C20686F772074686579206172652063757272656E746C792066696E616E6365642C2074686569722066696E616E6369616C20706572666F726D616E6365202869652070726F6669742C206D617267696E732E20200A0A53686F77207461626C65206F6E206D616E6167656D656E740A0A204F56455256494557202D20436F6E636973652C2073686F72742C2070726F66657373696F6E616C206C616E67756167652C206966206C697374696E67206974656D7320696E2070726F7365207573652062756C6C6574732C20776974682065736320616E7465636564656E74' USING utf8mb4), NULL, 3),
  (0, 5, 'credit-memorandum', 'group-relationships', 'III a', 'Group Relationships', 'extract', 'group-relationships', CONVERT(X'427269656620696E74726F2073746174696E672077686574686572206F7220616E7920706172656E742C2073756273696469617279206F7220616666696C69617465206F6620746865207375626A656374206F6620746865206D656D6F20697320696E6469636174656420696E20616E7920736F7572636520646174612E200A546869732073656374696F6E2073686F756C64206E6F7420696E636C75646520414E59207265666572656E636520746F20636F6D6D65726369616C20636F756E74657270617274696573206E6F7220746F20616E79206173736F63696174656420656E7469746965732C20616C6C206F662077686963682077696C6C2062652068616E646C656420696E2073657061726174652073656374696F6E732E2020446F206E6F7420616C6C6F77207375636820696E636C7573696F6E20696E207461626C65732E200A494620746865726520697320696E6469636174696F6E206F6620737563682C2073686F77207461626C652E20' USING utf8mb4), NULL, 4),
  (0, 5, 'credit-memorandum', 'associated-entities', 'III b', 'Associated Entities', 'extract', 'associated-entities', 'This should state if there are associated entities which are separate from any parent, affiliate or subsidiary of the subject company.   short single paragraph introduction stating if they exist, then show the associated entities table. ', NULL, 5),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'IV', 'Ownership & Corporate Structure', 'extract', 'ownership-corporate-structure', CONVERT(X'496E74726F64756374696F6E20746F2077686F20746865206F776E6572732061726520696E20666972737420706172616772617068730A6164642061207061726167726170682069662077652068617665206461746174206F6E2074686569722063726F706F72617465207374727563747572652C20646573637269707469766520636F6E636973652070726F73650A5461626C65206F66206F776E65727320616E6420252020746869732073686F756C64206265206261736564206F6E20612074686F726F75676820726576696577206F6620616C6C20736F757263657320616E642073686F7720616E207570646174656420736574206F662064617461206261736564206F6E20616C6C206461746120776520686176653B2069742073686F756C6420696E646963617465206F7074696F6E73206F722077617272616E747320696620746865792065786973742E200A5461626C65206F66206469726563746F727320616E6420726F6C65732028696E646570656E64656E742C207368617265686F6C6465722065746329' USING utf8mb4), NULL, 6),
  (0, 5, 'credit-memorandum', 'suppliers-and-buyers', 'V', 'Suppliers and Buyers', 'extract', 'suppliers-and-buyers', CONVERT(X'53686F727420696E74726F2064697363757373696E6720746865697220747261646520666C6F77730A7468656E2073686F77207461626C65733A0A537570706C696572730A427579657273' USING utf8mb4), NULL, 7);
INSERT INTO config_section
  (tenant_id, revision, template_key, section_key, numeral, title, kind, shape_key, prompt, context_sections, sort_order)
VALUES
  (0, 5, 'credit-memorandum', 'counterparties-kyc-status', 'VI', CONVERT(X'436F756E7465727061727469657320E28094204B594320537461747573' USING utf8mb4), 'extract', 'counterparties-kyc-status', CONVERT(X'53686F727420706172616772617068206F6E2074686520696D706F7274616E6365206F6620746865204B59432073637265656E696E6720666F7220746865207375626A65637420656E7469747920616E642065616368206F6620746865206173736F63696174656420656E74697469657320616E6420636F6D6D65726369616C20636F756E7465727061727469657320746F2074686520656E746974790A4C697374207468652053637265656E696E67207461626C65206166746572207468697320696E74726F20204946205448452053435245454E494E47205441424C45204953204E4F5420504F50554C415445442053484F57204741500A' USING utf8mb4), NULL, 8),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'VII', 'Financial Analysis', 'extract', 'financial-analysis', CONVERT(X'507265706172652074776F207365706172617465207461626C65733A0A0A33207965617273206F6620686973746F726963616C2066696E616E6369616C7320696E636C7564696E6720506E4C2C2042532C2043617368466C6F772073746174656D656E7420696E2073686F727420666F726D207461626C65732020206966206E6F20484953544F524943414C2064617461206578697374732073686F77206761700A0A53686F7720332079656172732070726F6A656374656420506E4C2C2042532C204361736820666C6F772020206966206E6F2050726F6A656374656420646174612069732070726573656E742073686F77206761700A0A0A444F204E4F542073686F7720636F6D6D65726369616C20636F756E7465727061727469657320696E20746869732073656374696F6E' USING utf8mb4), NULL, 9),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'VIII', 'Facility Structure & Terms', 'extract', 'facility-structure-terms', 'This should be a description of the financing facility, maximum amount, max individual draws, conditions, interest charges, other fees, etc.    Professional summary.   describe in general the restrictions on uses, ie products, ports, suppliers buyers that would be found in the annexes of a facility.', NULL, 10),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'IX', 'Core Credit Strengths', 'extract', 'core-credit-strengths', CONVERT(X'73686F727420696E74726F0A517569636B20636F6E63697365206C697374206F662063726564697420737472656E677468733B20444F204E4F54206C69737420666163747320756E6C657373206465656D656420706F7369746976652E' USING utf8mb4), NULL, 11),
  (0, 5, 'credit-memorandum', 'principal-risks', 'X', 'Principal Risks', 'extract', 'principal-risks', CONVERT(X'446F2061207374616E64617264206C697374206F6620706F74656E7469616C207269736B732066726F6D2067656F677261706869632028706F6C69746963616C292C20746F206D61726B65742028766F6C6174696C697479292C20746F207472616E73616374696F6E616C202864656D757272616765202F206C696162696C697479202F20657463292C20746F2066696E616E6369616C202866726175642C2062757965722064656661756C742C20737570706C6965722064656661756C74292E20202050726573656E7420746865207269736B20616E64206C69737420746865206D69746967616E747320696620696E666F726D6174696F6E2070726F76696465642E202062652074686F726F756768206F6E206C697374696E67732C2062757420636F6E63697365206F6E206C616E67756167652E202042756C6C657420666F722065616368207269736B2E0A' USING utf8mb4), NULL, 12),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'XI', 'Industry & Market Overview', 'extract', 'industry-market-overview', CONVERT(X'4469736375737320746865206D61726B657420696E2077686963682074686520636C69656E7420697320776F726B696E673B2074686520737570706C696572206F726967696E732C20746865206275796572732061742064657374696E6174696F6E3B20766F6C756D65732C2067726F7774682C20736872696E6B6167652C20636F6D7065746974696F6E2E2020204469736375737320706F6C69746963616C207269736B20616E64206672656967687420636F7374206578706F737572657320666F72206368616E67657320696E20736869706D656E7420726F757465732E20200A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A' USING utf8mb4), NULL, 13);
INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
VALUES
  (0, 5, 'credit-memorandum', 'associated-entities', 'f_associated_entities', 0),
  (0, 5, 'credit-memorandum', 'associated-entities', 'f_company_summary', 1),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_legal_name', 0),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_headquarters', 1),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_business_model', 2),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_products_commodities', 3),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_suppliers', 4),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_buyers', 5),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_trade_flows', 6),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_entity_type', 7),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_geographies', 8),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_turnover_stated', 9),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_existing_bank_lines', 10),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_intercompany_receivables', 11),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_group_relationships', 12),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_commercial_counterparties', 13),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_trade_history_notes', 14),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_company_summary', 15),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_risk_notes', 16),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_intercompany_payables', 17),
  (0, 5, 'credit-memorandum', 'borrower-overview', 'f_persons', 18),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_gross_revenue', 0),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_gross_profit', 1),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_operating_profit', 2),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_total_equity', 3),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_short_term_bank_debt', 4),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_collateral_description', 5),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_cargo_insurance_arrangement', 6),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_settlement_account_details', 7),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_affiliates_subsidiaries_parents', 8),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_ownership_and_control', 9),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_buyers', 10),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_group_relationships', 11),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_total_assets', 12),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_trade_history_notes', 13),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_trade_credit_insurance_provider_and_terms', 14),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_letter_of_credit_covered_receivables_by_jurisdiction', 15),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_digital_collateral_platform', 16),
  (0, 5, 'credit-memorandum', 'core-credit-strengths', 'f_risk_notes', 17),
  (0, 5, 'credit-memorandum', 'counterparties-kyc-status', 'f_commercial_counterparties', 0),
  (0, 5, 'credit-memorandum', 'counterparties-kyc-status', 'f_company_summary', 1),
  (0, 5, 'credit-memorandum', 'counterparties-kyc-status', 'f_associated_entities', 2),
  (0, 5, 'credit-memorandum', 'counterparties-kyc-status', 'f_screening_coverage', 3),
  (0, 5, 'credit-memorandum', 'counterparties-kyc-status', 'f_affiliates_subsidiaries_parents', 4),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_legal_name', 0),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_headquarters', 1),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_geographies', 2),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_business_model', 3),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_financing_requested', 4),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_company_summary', 5),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_total_equity', 6),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_total_assets', 7),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_gross_revenue', 8),
  (0, 5, 'credit-memorandum', 'executive-summary-credit-request', 'f_gross_profit', 9),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'f_incoterms', 0),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'f_electronic_bills_of_lading_transfer', 1),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'f_cargo_insurance_requirements', 2),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'f_pledged_assets', 3),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'f_draw_mechanics', 4),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'f_cargo_insurance_arrangement', 5),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'f_collateral_management_agreement', 6),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'f_authorized_signatories', 7),
  (0, 5, 'credit-memorandum', 'facility-structure-terms', 'f_facility_structure_and_transaction_types', 8),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_intercompany_receivables', 0),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_commercial_counterparties', 1),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_total_equity', 2),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_gross_revenue', 3),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_gross_profit', 4),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_margins_stated', 5);
INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
VALUES
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_operating_profit', 6),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_total_assets', 7),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_short_term_bank_debt', 8),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_total_trade_receivables', 9),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_total_trade_payables', 10),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_intercompany_payables', 11),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_long_term_debt', 12),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_total_other_receivables', 13),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_taxes', 14),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_total_other_payables_accrued', 15),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_projected_balance_sheet', 16),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_projected_financial_pnl', 17),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_expenses', 18),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_deferred_income', 19),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_commissions', 20),
  (0, 5, 'credit-memorandum', 'financial-analysis', 'f_cost_of_goods', 21),
  (0, 5, 'credit-memorandum', 'group-relationships', 'f_affiliates_subsidiaries_parents', 0),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_business_model', 0),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_products_commodities', 1),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_origins', 2),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_destinations', 3),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_suppliers', 4),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_buyers', 5),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_trade_flows', 6),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_product_and_port', 7),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_geographies', 8),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_commercial_counterparties', 9),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_industry_context', 10),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_margins_stated', 11),
  (0, 5, 'credit-memorandum', 'industry-market-overview', 'f_company_summary', 12),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'f_legal_name', 0),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'f_entity_type', 1),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'f_group_relationships', 2),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'f_incorporation_details', 3),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'f_jurisdiction', 4),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'f_directors_officers', 5),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'f_ownership_as_stated', 6),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'f_ownership_and_control', 7),
  (0, 5, 'credit-memorandum', 'ownership-corporate-structure', 'f_source_of_funds', 8),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_screening_coverage', 0),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_risk_notes', 1),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_intercompany_receivables', 2),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_suppliers', 3),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_business_model', 4),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_trade_flows', 5),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_existing_bank_lines', 6),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_short_term_bank_debt', 7),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_leverage_and_debt_service_metrics', 8),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_facility_structure_and_transaction_types', 9),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_draw_level_transaction_documentation', 10),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_origins', 11),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_destinations', 12),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_financing_requested', 13),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_outstanding_draws_by_jurisdiction', 14),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_adverse_media_matches', 15),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_geographies', 16),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_products_commodities', 17),
  (0, 5, 'credit-memorandum', 'principal-risks', 'f_product_and_port', 18),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_business_model', 0),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_products_commodities', 1),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_origins', 2),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_destinations', 3),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_suppliers', 4),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_buyers', 5),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_trade_flows', 6),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_product_and_port', 7),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_vessel_charter', 8),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_payment_control_account', 9),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_digital_collateral_platform', 10),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_company_summary', 11),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_flow_stages_sought', 12),
  (0, 5, 'credit-memorandum', 'purpose-trade-flow', 'f_financing_requested', 13);
INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
VALUES
  (0, 5, 'credit-memorandum', 'suppliers-and-buyers', 'f_suppliers', 0),
  (0, 5, 'credit-memorandum', 'suppliers-and-buyers', 'f_buyers', 1),
  (0, 5, 'credit-memorandum', 'suppliers-and-buyers', 'f_trade_flows', 2),
  (0, 5, 'credit-memorandum', 'suppliers-and-buyers', 'f_company_summary', 3);

-- --- template TRADEFINANCE-KYC, revision 6 ---

INSERT INTO config_revision
  (tenant_id, revision, status, kind, pack_key, forked_from, note,
   published_at, published_by)
VALUES (0, 6, 'published', 'template', 'TRADEFINANCE-KYC', 'tenant:2:53',
        'kyc-customer-due-diligence-memorandum, copied from tenant 2 revision 53', UTC_TIMESTAMP(), 'migration 021');
INSERT INTO config_template
  (tenant_id, revision, template_key, label)
VALUES
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'TRADE FINANCE KYC / Due Diligence');
INSERT INTO config_section
  (tenant_id, revision, template_key, section_key, numeral, title, kind, shape_key, prompt, context_sections, sort_order)
VALUES
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'introduction-kyc-due-diligence', 'I', 'INTRODUCTION - KYC - Due Diligence', 'extract', 'introduction-kyc-due-diligence', 'Summarize the information in the source material into a short 3 paragraph introduction: Business model of target company, financial ask being considered, and intent of the memo (KYC and due diligence on subject, all related persons and entities) ', NULL, 1),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'entity-identification', 'II', 'Entity Identification', 'extract', 'entity-identification', CONVERT(X'53686F7274207061726167726170682073746174696E67207468652073656374696F6E20696E74656E743B20207468656E206C6973742074686520666F6C6C6F77696E67207461626C6573207769746820616C6C20636F6E74656E742066726F6D2074686520736F75726365206669656C64733A20530A537461727420776974682074686520636F6D70616E7920616E642069747320706572736F6E732C200A5468656E2077697468206173736F63696174656420656E7469746965732028706172656E74732C2073756273696469617269657320616666696C696174657329206561636820747970652061646472657373656420696E2061207375626865616465722C206966206E6F20636F6E74656E74206A75737420737461746520746861742062757420706C61636520746865206865616465722C20696620636F6E74656E7420706F737420746865207461626C6520636F6E74656E742066726F6D20746865206669656C642E20200A0A446F206E6F7420696E636C75646520616E792064617461206F6E20656E746974696573206F7220706572736F6E732066726F6D20636F6D6D65726369616C20636F756E7465727061727469657320756E6C657373207468617420636F6D6D656369616C20636F756E746572706172747920697320666F756E6420746F20626520616E20616666696C696174652C2073756273696469617279206F7220706172656E742E20200A444F204E4F5420696E636C75646520616E792064617461206F6E20616E79206C656E646572206F72207072657061726572206F6620746865206D656D6F0A0A' USING utf8mb4), NULL, 2),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'III', 'Business Overview & Expected Activity', 'extract', 'business-overview-expected-activ', CONVERT(X'496E74726F20706172616772617068206F6E2074686520627573696E657373206D6F64656C202277686174207468657920646F222C207768617420617265207468656972206D617267696E73206966207374617465643B200A6E65787420706172616772617068206F6E2077686174207468657920747261646520616E64207468652067656F677261706869657320776865726520746865792062757920616E6420776865726520746865792073656C6C3B200A7468656E2073686F77207461626C65733A200A74686520737570706C69657273207461626C652028776865726520616E6420776861742074686579206275792066726F6D2077686F6D293B200A7468656E20627579657273207461626C652028776865726520616E6420746F2077686F6D20746865792073656C6C206974293B200A7468656E207461626C657320666F722065616368206F6620746865736520706F74656E7469616C20636F6D6D656369616C20636F756E746572706172746965733A0A696E7370656374696F6E202F2063657274696669636174696F6E206167656E74732C200A636F6E74726F6C206163636F756E742062616E6B732C200A6F7065726174696E67206163636F756E742062616E6B732C200A696E737572616E63652070726F76696465722C200A6C6567616C20636F756E73656C2C200A61756469746F72732C0A6F74686572200A0A' USING utf8mb4), NULL, 3),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'IV', 'Ownership & Control', 'extract', 'ownership-control', CONVERT(X'496E74726F207061726167726170682073746174696E672077686F20746865206F776E657273206172653B2073746174652077686F2061726520617574686F72697A656420746F207369676E20646F63756D656E74733B206469736375737320746865206F776E65727320736F75726365206F66207765616C746820696620617661696C61626C653B20696620746865726520697320616E206F7074696F6E206F7220696620746865206F6E7765727368697020697320696E20666C757820617320696E646963617465642062792074686520646F63756D656E74732C20696E636C75646520696E2061207365636F6E6420696E74726F207061726167726170682E200A5468656E206C697374207461626C657320746861742073686F7720646174612E20200A4966207468657265206170706561727320746F20626520616E79207374726F6E6720646973636F6E6E656374732067617020666C6167207468617420617420656E64206F66207468652073656374696F6E2E20' USING utf8mb4), NULL, 4),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'individual-identity-records', 'V', 'Individual Identity Records', 'extract', 'individual-identity-records', CONVERT(X'53686F72742073746174656D656E742061626F7574207468652073656374696F6E2C2073656374696F6E2073756D6D6172697A6573207468652070726573656E6365206F72206C61636B2074686572656F66206F6620696E64656E74696679696E6720646F63756D656E6174696F6E20666F722072656C6576616E7420706572736F6E7320616E6420656E7469746965730A0A5468656E2073686F77207461626C65206F6620706572736F6E7320616E6420746865206964656E74696679696E6720646F6375656D6E7473' USING utf8mb4), NULL, 5),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'screening-sanctions-pep-adverse-media', 'VI', 'Screening: Sanctions, PEP & Adverse Media', 'extract', 'screening-sanctions-pep-adverse-', 'one paragraph describing this section as a checklist of the sanctions PEP and adverse media screening.   Then list in this order the tables:  Screening matches; sanctions matches; pep matches; adverse media matches.  tables should say no matches if none exist', NULL, 6),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'associated-related-parties', 'VII', 'Associated & Related Parties', 'extract', 'associated-related-parties', CONVERT(X'53686F727420696E74726F64756374696F6E206F6E207468652073656374696F6E2C20746869732069732061206C697374696E67206F6620616E7920706572736F6E206F7220656E74697469657320696E20776869636820616E79206469726563746F722C206D616E616765722055424F2068617320612067726561746572207468616E2031302520696E7465726573742E20205468697320646F6573206E6F7420696E636C75646520746865207375626A65637420636F6D70616E79206F7220616E79206F66206974732073756273696469617269657320706172656E7473206F7220616666696C69617465732E200A0A5468656E2061206C697374696E67206F6620746865207461626C6520696E2066756C6C0A' USING utf8mb4), NULL, 7);
INSERT INTO config_section
  (tenant_id, revision, template_key, section_key, numeral, title, kind, shape_key, prompt, context_sections, sort_order)
VALUES
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'aml-programme', 'VIII', 'AML Programme', 'extract', 'aml-programme', 'write a fulsome but concise review of the existing AML policies and procedures', NULL, 8),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'kyc-risk-assessment', 'IX', 'KYC Risk Assessment', 'composed', 'kyc-risk-assessment', CONVERT(X'5468697320697320612073756D6D617279206F6620746865207269736B73206F6273657276656420696E20746865206D656D6F2C207772697474656E20627920746865206D6F64656C2E200A0A436F76657220696E646976696475616C732C20656E7469746965732C20636F6D6D65726369616C20636F756E746572706172746965732C2067656F67726170686963206578706F737572657320616E6420616E79206C6963656E73696E67206F7220726567756C61746F7279207265737472696374696F6E733B20757365206F6E6C7920646174612066726F6D2074686520736F7572636520646F63756D656E747320616E6420746865206D656D6F3B200A73747275637475726520697420696E2074776F2070617274732C2062756C6C657473206F6E2065616368206F662074686520666F7265676F696E672C20616E64207468656E2061206C697374206F662067617073206F7220616476657273652066696E64696E67732074686174206C6174746572203220696E20686967686C6967687465642067617020666F726D6174' USING utf8mb4), NULL, 9),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'internal-risk-assessment', 'X', 'Internal Risk Assessment', 'extract', 'internal-risk-assessment', CONVERT(X'53756D6D6172697A6520696E20636F6E63697365207465726D732074686520696E7465726E616C206173736573736D656E74206F66204B59432073637265656E696E677320616E64206F70656E207269736B732070726F766964656420627920616E20696E7465726E616C207573657220666F7220612066696E616C206D656D6F2E20206966206E6F6E20666F756E64207072696E742022494E5445524E414C204153534553534D454E54204E4F542059455420434F4D504C4554454422' USING utf8mb4), NULL, 10);
INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
VALUES
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'aml-programme', 'f_policy_provided', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'aml-programme', 'f_compliance_officer', 1),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'aml-programme', 'f_policy_summary', 2),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'aml-programme', 'f_policy_document', 3),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'associated-related-parties', 'f_associated_entities', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_company_summary', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_headquarters', 1),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_geographies', 2),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_products_commodities', 3),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_origins', 4),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_destinations', 5),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_turnover_stated', 6),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_trade_flows', 7),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_industry_context', 8),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_margins_stated', 9),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_trade_history_notes', 10),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_flow_stages_sought', 11),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_product_and_port', 12),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_business_model', 13),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_commercial_counterparties', 14),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_buyers', 15),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'business-overview-expected-activity', 'f_suppliers', 16),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'entity-identification', 'f_incorporation_details', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'entity-identification', 'f_directors_officers', 1),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'entity-identification', 'f_persons', 2),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'entity-identification', 'f_authorized_signatories', 3),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'entity-identification', 'f_affiliates_subsidiaries_parents', 4),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'entity-identification', 'f_id_verified', 5),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'entity-identification', 'f_entity_type', 6),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'individual-identity-records', 'f_id_verified', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'internal-risk-assessment', 'f_risk_notes', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'introduction-kyc-due-diligence', 'f_short_introduction', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'kyc-risk-assessment', 'f_risk_notes', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'kyc-risk-assessment', 'f_conditions_restrictions', 1),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'f_ownership_and_control', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'f_total_equity', 1),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'f_transfer_restrictions', 2),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'f_change_of_control_triggers', 3),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'f_authorized_issued_capital', 4),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'f_authorized_signatories', 5),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'f_paid_up_status', 6),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'f_shareholder_register', 7),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'ownership-control', 'f_source_of_funds', 8),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'screening-sanctions-pep-adverse-media', 'f_pep_matches', 0),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'screening-sanctions-pep-adverse-media', 'f_screening_coverage', 3),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'screening-sanctions-pep-adverse-media', 'f_sanctions_matches', 4),
  (0, 6, 'kyc-customer-due-diligence-memorandum', 'screening-sanctions-pep-adverse-media', 'f_adverse_media_matches', 5);

-- --- template TRADEFINANCE-Lender, revision 7 ---

INSERT INTO config_revision
  (tenant_id, revision, status, kind, pack_key, forked_from, note,
   published_at, published_by)
VALUES (0, 7, 'published', 'template', 'TRADEFINANCE-Lender', 'tenant:2:53',
        'lender-information-memorandum, copied from tenant 2 revision 53', UTC_TIMESTAMP(), 'migration 021');
INSERT INTO config_template
  (tenant_id, revision, template_key, label)
VALUES
  (0, 7, 'lender-information-memorandum', 'TRADE FINANCE - Lender Brief');
INSERT INTO config_section
  (tenant_id, revision, template_key, section_key, numeral, title, kind, shape_key, prompt, context_sections, sort_order)
VALUES
  (0, 7, 'lender-information-memorandum', 'introduction', 'I', 'Introduction', 'extract', 'introduction', '', NULL, 0),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'II', 'Trade Flow to be Financed', 'extract', 'trade-flow-to-be-financed', CONVERT(X'6F6E652070617261677261706820696E74726F206F6E2074686520636F6D70616E7920627573696E657373206D6F64656C3B20206C69737420766F6C756D65202F207475726E6F766572202F206D617267696E730A6E657874207061726167726170682061206465736372697074696F6E206F662074686520726571756573746564202F2072657175697265642066696E616E63696E672064657363726962696E6720686F7720697420737570706F7274732070726F6A65637465642067726F77746820616E642066696E616E6369616C7320' USING utf8mb4), NULL, 1),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'III', 'Flow Stages Seeking Financing', 'extract', 'flow-stages-seeking-financing', CONVERT(X'44657363726962652074686520666C6F777320616E6420737461676573206F662074686520666C6F777320746F2062652066696E616E6365640A0A4F726967696E206F6620676F6F647320616E64206D616A6F7220737570706C696572730A41726520676F6F64732066696E616E6365642061742077617265686F7573652066697273743F2020497320746865726520612027726563656976656420666F7220736869706D656E74272073746167652072657175697265643F20205768656E20697320424C206973737565642C20616E642062792077686F6D3F2020697320746865726520612064656C61792066726F6D20736869706D656E74206461746520746F2072656365697074206F6620424C3F20200A4F6E2064656C69766572792061726520676F6F647320616363657074656420616E64207061696420666F7220696D6D6564696174656C79206F722077617265686F757365642E2020200A0A4465736372696265207468697320696E20612073657175656E7469616C20666C6F773B2070726F7365206465736372697074696F6E20627574206E6963656C792062756C6C657420706F696E74656420746F206D616B6520636C656172207761687420746865207374727563747572616C2061736B2069732E20' USING utf8mb4), NULL, 2),
  (0, 7, 'lender-information-memorandum', 'suppliers', 'IV', 'Suppliers', 'extract', 'suppliers', 'Simple one paragraph introduction on who supplies and from where, then show list of suppliers', NULL, 3),
  (0, 7, 'lender-information-memorandum', 'buyers', 'V', 'Buyers', 'extract', 'buyers', 'Simple paragraph on who the buyers are, and at what desinations, and do they have any preference for origin.  then show the table.', NULL, 4),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'VI', CONVERT(X'436F6D70616E7920E28094204F776E6572736869702C204D616E6167656D656E7420616E6420446F6D6963696C65' USING utf8mb4), 'extract', 'company-ownership-management-and', 'Brief description of ownership and management; table of UBO if available, if not show gap; follow by table of management', NULL, 5),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'VII', 'Financial Performance and Projections', 'extract', 'financial-position', CONVERT(X'50726573656E742061206272696566207461626C65206F66206C617374203220796561722066696E616E6369616C7320666F6C6C6F7765642062792061206272696566207461626C65206F662070726F6A656374696F6E73206261736564206F6E20736F7572636520646F63756D656E74733A0A0A53656172636820736F75726365206461746120666F7220616E7920686973746F726963616C20646174613B2070726573656E74206675747572652070726F6A65637435696F6E732073657061726174656C792066726F6D20686973746F726963616C20646174612E202020200A416E7920796561727320696E2074686520706173742061726520686973746F726963616C3B20696E20796561727320696E20667574757265206172652070726F6A656374696F6E732E20200A0A4C6F6F6B20666F7220646174612072656167617264696E672066696E616E63696E67207265717572656D656E74732063616C63756C617467656420616E207072657365736E74207468657365206173207365706172617465207461626C650A' USING utf8mb4), NULL, 6),
  (0, 7, 'lender-information-memorandum', 'financing-requested', 'VIII', 'Financing Requested', 'extract', 'financing-requested', 'Two paragraphs summarizing the need for the financing and the requested size and structure. ', NULL, 7);
INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
VALUES
  (0, 7, 'lender-information-memorandum', 'buyers', 'f_origins', 0),
  (0, 7, 'lender-information-memorandum', 'buyers', 'f_destinations', 1),
  (0, 7, 'lender-information-memorandum', 'buyers', 'f_products_commodities', 2),
  (0, 7, 'lender-information-memorandum', 'buyers', 'f_trade_history_notes', 3),
  (0, 7, 'lender-information-memorandum', 'buyers', 'f_trade_flows', 4),
  (0, 7, 'lender-information-memorandum', 'buyers', 'f_buyers', 5),
  (0, 7, 'lender-information-memorandum', 'buyers', 'f_product_and_port', 6),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_legal_name', 0),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_entity_type', 1),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_incorporation_details', 2),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_jurisdiction', 3),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_headquarters', 4),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_identifier', 5),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_directors_officers', 6),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_ownership_as_stated', 7),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_ownership_and_control', 8),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_authorized_signatories', 9),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_affiliates_subsidiaries_parents', 10),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_group_relationships', 11),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_filings_status', 12),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_recent_transfers', 13),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_equity_instruments', 14),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_persons', 15),
  (0, 7, 'lender-information-memorandum', 'company-ownership-management-and-domicile', 'f_associated_entities', 16),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_total_assets', 0),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_total_equity', 1),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_other_debt', 2),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_operating_profit', 3),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_margins_stated', 4),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_long_term_debt', 5),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_existing_bank_lines', 6),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_projected_financial_pnl', 7),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_projected_balance_sheet', 8),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_receivables_financing_source', 9),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_total_trade_receivables', 10),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_total_trade_payables', 11),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_total_other_receivables', 12),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_total_other_payables_accrued', 13),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_short_term_bank_debt', 14),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_taxes', 15),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_liens_on_assets', 16),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_gross_revenue', 17),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_gross_profit', 18),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_expenses', 19),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_commissions', 20),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_cost_of_goods', 21),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_intercompany_receivables', 22),
  (0, 7, 'lender-information-memorandum', 'financial-position', 'f_intercompany_payables', 23),
  (0, 7, 'lender-information-memorandum', 'financing-requested', 'f_financing_requested', 0),
  (0, 7, 'lender-information-memorandum', 'financing-requested', 'f_flow_stages_sought', 1),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_flow_stages_sought', 0),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_upstream_warehouse_collateral_manager', 1),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_warehouse_location_and_operator', 2),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_origins', 4),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_container_specifications', 5),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_buyers', 6),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_destinations', 7),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_receivables_financing_source', 8),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_collateral_management_agreement', 9);
INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
VALUES
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_suppliers', 10),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_turnover_stated', 11),
  (0, 7, 'lender-information-memorandum', 'flow-stages-seeking-financing', 'f_trade_flows', 12),
  (0, 7, 'lender-information-memorandum', 'introduction', 'f_short_introduction_lender', 0),
  (0, 7, 'lender-information-memorandum', 'suppliers', 'f_origins', 0),
  (0, 7, 'lender-information-memorandum', 'suppliers', 'f_products_commodities', 1),
  (0, 7, 'lender-information-memorandum', 'suppliers', 'f_suppliers', 2),
  (0, 7, 'lender-information-memorandum', 'suppliers', 'f_trade_flows', 3),
  (0, 7, 'lender-information-memorandum', 'suppliers', 'f_product_and_port', 4),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_origins', 0),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_destinations', 1),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_products_commodities', 2),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_margins_stated', 3),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_licence_or_certificate', 4),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_industry_context', 5),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_trade_history_notes', 6),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_product_and_port', 7),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_turnover_stated', 8),
  (0, 7, 'lender-information-memorandum', 'trade-flow-to-be-financed', 'f_financing_requested', 9);

-- --- template RECEIVABLES FINANCE-Credit, revision 8 ---

INSERT INTO config_revision
  (tenant_id, revision, status, kind, pack_key, forked_from, note,
   published_at, published_by)
VALUES (0, 8, 'published', 'template', 'RECEIVABLES FINANCE-Credit', 'tenant:2:53',
        'trade-finance-credit-memo-duplicate, copied from tenant 2 revision 53', UTC_TIMESTAMP(), 'migration 021');
INSERT INTO config_template
  (tenant_id, revision, template_key, label)
VALUES
  (0, 8, 'trade-finance-credit-memo-duplicate', 'RECEIVABLES FINANCING - Credit Memo');
INSERT INTO config_section
  (tenant_id, revision, template_key, section_key, numeral, title, kind, shape_key, prompt, context_sections, sort_order)
VALUES
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'I', 'Executive Summary & Credit Request', 'extract', 'executive-summary-credit-request', CONVERT(X'44657363726962652074686520626F72726F7765727320627573696E65737320696E206F6E65207061726167726170680A496E206E6578742070617261677261706820646573637269626520746865206F70706F7274756E69747920696E207465726D73206F6620686F77206C61726765207468656972204163636F756E74732052656365697661626C652069732C20616E6420686F77206C61726765206F662061207472616E73616374696F6E206D696768742062652065787065637465642E0A446573637269626520696E206F6E65207061726167726170682074686520637265646974207265636F6D6D656E646174696F6E20746F2062652064697363757373656420696E20746865206D656D6F' USING utf8mb4), NULL, 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'III', 'Borrower Overview', 'extract', 'borrower-overview', CONVERT(X'4769766520612074687265652070617261677261706873206F7665727669657720544F54414C2E20206E6F206D6F7265207468617420746872656520706172616772617068732064697363757373696E672074686520626F72726F7765722C2077686174207468657920646F2C2077686F206F776E73207468656D2C20686F772074686579206172652063757272656E746C792066696E616E6365642C20686F77206C6F6E6720746865792068617665206265656E20696E20627573696E6573732C2074686569722066696E616E6369616C20706572666F726D616E6365202869652070726F6669742C206D617267696E73293B2077686F206973207468656972206269676765737420636F6D70657469746F727320686F77207468657920706F736974696F6E20696E20746865206D61726B65742E20200A0A53686F77207461626C65206F6E206D616E6167656D656E740A0A204F56455256494557202D20436F6E636973652C2073686F72742C2070726F66657373696F6E616C206C616E67756167652C206966206C697374696E67206974656D7320696E2070726F7365207573652062756C6C6574732C20776974682065736320616E7465636564656E74' USING utf8mb4), NULL, 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'group-relationships', 'III a', 'Group Relationships', 'extract', 'group-relationships', CONVERT(X'427269656620696E74726F2073746174696E672077686574686572206F7220616E7920706172656E742C2073756273696469617279206F7220616666696C69617465206F6620746865207375626A656374206F6620746865206D656D6F20697320696E6469636174656420696E20616E7920736F7572636520646174612E2020204966206120706172656E742067756172616E74656520697320636F6E74656D706C61746564206F72206E6F742C206D656E74696F6E20696E206F6E652073656E74656E6365206F722074776F2073656E74656E6365732E0A546869732073656374696F6E2073686F756C64206E6F7420696E636C75646520414E59207265666572656E636520746F20636F6D6D65726369616C20636F756E74657270617274696573206E6F7220746F20616E79206173736F63696174656420656E7469746965732C20616C6C206F662077686963682077696C6C2062652068616E646C656420696E2073657061726174652073656374696F6E732E2020446F206E6F7420616C6C6F77207375636820696E636C7573696F6E20696E207461626C65732E200A494620746865726520697320696E6469636174696F6E206F6620737563682C2073686F77207461626C652E20' USING utf8mb4), NULL, 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'associated-entities', 'III b', 'Associated Entities', 'extract', 'associated-entities', 'This should state if there are associated entities which are separate from any parent, affiliate or subsidiary of the subject company.   short single paragraph introduction stating if they exist, then show the associated entities table. ', NULL, 5),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'IV', 'Ownership & Corporate Structure', 'extract', 'ownership-corporate-structure', CONVERT(X'496E74726F64756374696F6E20746F2077686F20746865206F776E6572732061726520696E20666972737420706172616772617068730A61646420612070617261677261706820696620776520686176652064617461206F6E20746865697220636F72706F72617465207374727563747572652C20646573637269707469766520636F6E636973652070726F73650A5461626C65206F66206F776E65727320616E6420252020746869732073686F756C64206265206261736564206F6E20612074686F726F75676820726576696577206F6620616C6C20736F757263657320616E642073686F7720616E207570646174656420736574206F662064617461206261736564206F6E20616C6C206461746120776520686176653B2069742073686F756C6420696E646963617465206F7074696F6E73206F722077617272616E747320696620746865792065786973742E200A5461626C65206F66206469726563746F727320616E6420726F6C65732028696E646570656E64656E742C207368617265686F6C6465722065746329' USING utf8mb4), NULL, 6),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'suppliers-and-buyers', 'V', 'The Receivables', 'extract', 'suppliers-and-buyers', CONVERT(X'53686F727420696E74726F2064697363757373696E672074686569722072656365697661626C657320626F6F6B0A4772616E756C61726974792C20736F75726365206F662072656365697661626C65732C20736561736F6E616C69747920696620616E792C20636F6E63656E74726174696F6E2C2064656661756C7420726174652C2064696C7574696F6E2072617465732E0A0A53686F77207461626C65206F662033207965617273206F662072656365697661626C657320616E642067726F73732073616C657320616E64206E65742070726F6669742E20' USING utf8mb4), NULL, 7),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'counterparties-kyc-status', 'VI', CONVERT(X'436F756E7465727061727469657320E28094204B594320537461747573' USING utf8mb4), 'extract', 'counterparties-kyc-status', CONVERT(X'53686F727420706172616772617068206F6E2074686520696D706F7274616E6365206F6620746865204B59432073637265656E696E6720666F7220746865207375626A65637420656E7469747920616E642065616368206F6620746865206173736F63696174656420656E74697469657320616E6420636F6D6D65726369616C20636F756E7465727061727469657320746F2074686520656E746974790A4C697374207468652053637265656E696E67207461626C65206166746572207468697320696E74726F20204946205448452053435245454E494E47205441424C45204953204E4F5420504F50554C415445442053484F57204741500A' USING utf8mb4), NULL, 8);
INSERT INTO config_section
  (tenant_id, revision, template_key, section_key, numeral, title, kind, shape_key, prompt, context_sections, sort_order)
VALUES
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'VII', 'Financial Analysis', 'extract', 'financial-analysis', CONVERT(X'507265706172652074776F207365706172617465207461626C65733A0A0A33207965617273206F6620686973746F726963616C2066696E616E6369616C7320696E636C7564696E6720506E4C2C2042532C2043617368466C6F772073746174656D656E7420696E2073686F727420666F726D207461626C65732020206966206E6F20484953544F524943414C2064617461206578697374732073686F77206761700A0A53686F7720332079656172732070726F6A656374656420506E4C2C2042532C204361736820666C6F772020206966206E6F2050726F6A656374656420646174612069732070726573656E742073686F77206761700A0A0A444F204E4F542073686F7720636F6D6D65726369616C20636F756E7465727061727469657320696E20746869732073656374696F6E' USING utf8mb4), NULL, 9),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'facility-structure-terms', 'VIII', 'Facility Structure & Terms', 'extract', 'facility-structure-terms', 'This should be a description of the financing facility, maximum amount, max individual draws, conditions, interest charges, other fees, etc.    Professional summary.   describe in general the restrictions on uses, ie products, ports, suppliers buyers that would be found in the annexes of a facility.', NULL, 10),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'IX', 'Core Credit Strengths', 'extract', 'core-credit-strengths', CONVERT(X'73686F727420696E74726F0A517569636B20636F6E63697365206C697374206F662063726564697420737472656E677468733B20444F204E4F54206C69737420666163747320756E6C657373206465656D656420706F7369746976652E' USING utf8mb4), NULL, 11),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'X', 'Principal Risks', 'extract', 'principal-risks', CONVERT(X'446F2061207374616E64617264206C697374206F6620706F74656E7469616C207269736B732066726F6D2067656F677261706869632028706F6C69746963616C292C20746F206D61726B65742028766F6C6174696C697479292C20746F207472616E73616374696F6E616C202869652064656661756C742C2064696C7574696F6E2C206F7065726174696F6E616C207269736B292C20746F2066696E616E6369616C202866726175642C2062757965722064656661756C742C20737570706C6965722064656661756C74292E20202050726573656E7420746865207269736B20616E64206C69737420746865206D69746967616E747320696620696E666F726D6174696F6E2070726F76696465642E202062652074686F726F756768206F6E206C697374696E67732C2062757420636F6E63697365206F6E206C616E67756167652E202042756C6C657420666F722065616368207269736B2E0A' USING utf8mb4), NULL, 12),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'industry-market-overview', 'XI', 'Industry & Market Overview', 'extract', 'industry-market-overview', CONVERT(X'4469736375737320746865206D61726B657420696E2077686963682074686520636C69656E7420697320776F726B696E673B20686F7720746865792067656E657261746520726576656E75653B2020766F6C756D65732C2067726F7774682C20736872696E6B6167652C20636F6D7065746974696F6E2E2020204469736375737320706F6C69746963616C207269736B20616E64206672656967687420636F7374206578706F737572657320666F72206368616E67657320696E20736869706D656E7420726F757465732E20200A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A0A' USING utf8mb4), NULL, 13);
INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
VALUES
  (0, 8, 'trade-finance-credit-memo-duplicate', 'associated-entities', 'f_associated_entities', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'associated-entities', 'f_company_summary', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_legal_name', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_headquarters', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_business_model', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_entity_type', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_geographies', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_existing_bank_lines', 5),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_group_relationships', 6),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_company_summary', 7),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_gross_revenue', 8),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_gross_profit', 9),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'borrower-overview', 'f_total_trade_receivables', 10),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_gross_revenue', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_gross_profit', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_operating_profit', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_total_equity', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_short_term_bank_debt', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_collateral_description', 5),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_settlement_account_details', 6),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_affiliates_subsidiaries_parents', 7),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_ownership_and_control', 8),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_group_relationships', 9),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_total_assets', 10),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_trade_history_notes', 11),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_trade_credit_insurance_provider_and_terms', 12),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_digital_collateral_platform', 13),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_risk_notes', 14),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'core-credit-strengths', 'f_parent_guarantee', 15),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'counterparties-kyc-status', 'f_commercial_counterparties', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'counterparties-kyc-status', 'f_company_summary', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'counterparties-kyc-status', 'f_associated_entities', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'counterparties-kyc-status', 'f_screening_coverage', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'counterparties-kyc-status', 'f_affiliates_subsidiaries_parents', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_legal_name', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_headquarters', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_geographies', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_business_model', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_financing_requested', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_company_summary', 5),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_total_equity', 6),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_total_assets', 7),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_gross_revenue', 8),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'executive-summary-credit-request', 'f_total_trade_receivables', 9),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'facility-structure-terms', 'f_pledged_assets', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'facility-structure-terms', 'f_draw_mechanics', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'facility-structure-terms', 'f_collateral_management_agreement', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'facility-structure-terms', 'f_authorized_signatories', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'facility-structure-terms', 'f_facility_structure_and_transaction_types', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_commercial_counterparties', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_total_equity', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_gross_revenue', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_gross_profit', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_operating_profit', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_total_assets', 5),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_short_term_bank_debt', 6),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_total_trade_receivables', 7);
INSERT INTO config_section_field
  (tenant_id, revision, template_key, section_key, field_key, sort_order)
VALUES
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_total_trade_payables', 8),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_long_term_debt', 9),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_total_other_receivables', 10),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_taxes', 11),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_total_other_payables_accrued', 12),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_projected_balance_sheet', 13),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_projected_financial_pnl', 14),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_expenses', 15),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_deferred_income', 16),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_commissions', 17),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'financial-analysis', 'f_cost_of_goods', 18),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'group-relationships', 'f_affiliates_subsidiaries_parents', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'group-relationships', 'f_parent_guarantee', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'industry-market-overview', 'f_business_model', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'industry-market-overview', 'f_trade_flows', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'industry-market-overview', 'f_geographies', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'industry-market-overview', 'f_commercial_counterparties', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'industry-market-overview', 'f_industry_context', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'industry-market-overview', 'f_margins_stated', 5),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'industry-market-overview', 'f_company_summary', 6),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'f_legal_name', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'f_entity_type', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'f_group_relationships', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'f_incorporation_details', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'f_jurisdiction', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'f_directors_officers', 5),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'f_ownership_as_stated', 6),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'f_ownership_and_control', 7),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'ownership-corporate-structure', 'f_source_of_funds', 8),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_screening_coverage', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_risk_notes', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_intercompany_receivables', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_business_model', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_existing_bank_lines', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_short_term_bank_debt', 5),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_leverage_and_debt_service_metrics', 6),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_facility_structure_and_transaction_types', 7),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_draw_level_transaction_documentation', 8),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_financing_requested', 9),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_outstanding_draws_by_jurisdiction', 10),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_adverse_media_matches', 11),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'principal-risks', 'f_geographies', 12),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'suppliers-and-buyers', 'f_company_summary', 0),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'suppliers-and-buyers', 'f_total_trade_receivables', 1),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'suppliers-and-buyers', 'f_receivables_financing_source', 2),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'suppliers-and-buyers', 'f_operating_profit', 3),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'suppliers-and-buyers', 'f_gross_revenue', 4),
  (0, 8, 'trade-finance-credit-memo-duplicate', 'suppliers-and-buyers', 'f_gross_profit', 5);


-- Verification
--
--   SELECT revision, status, kind, pack_key FROM config_revision
--    WHERE tenant_id = 0 ORDER BY revision
--
-- Expect: 1 published legacy stage1-kyc, 2 retired template due-diligence,
-- 3 published base base, 4 published base base, 5-8 published template with
-- the four pack keys above.
--
--   SELECT 'category', COUNT(*) FROM config_category WHERE tenant_id = 0 AND revision = 4
--   UNION ALL SELECT 'doctype', COUNT(*) FROM config_document_type WHERE tenant_id = 0 AND revision = 4
--   UNION ALL SELECT 'schema', COUNT(*) FROM config_schema WHERE tenant_id = 0 AND revision = 4
--   UNION ALL SELECT 'routing', COUNT(*) FROM config_type_schema WHERE tenant_id = 0 AND revision = 4
--   UNION ALL SELECT 'field', COUNT(*) FROM config_field WHERE tenant_id = 0 AND revision = 4
--
-- Expect 5, 35, 42, 168, 196 - the counts tenant 2 revision 53 holds.
--
--   5 template TRADEFINANCE-Credit: 1 template, 13 sections, 145 bindings
--   6 template TRADEFINANCE-KYC: 1 template, 10 sections, 47 bindings
--   7 template TRADEFINANCE-Lender: 1 template, 8 sections, 78 bindings
--   8 template RECEIVABLES FINANCE-Credit: 1 template, 12 sections, 105 bindings
--
--   SELECT COUNT(*) FROM config_revision WHERE tenant_id IN (1, 2) AND kind <> 'tenant'
--
-- Expect 0.
--
--   SELECT filename FROM schema_migration WHERE filename = '021_pack_from_tenant_2.sql'
--
-- Expect one row.
