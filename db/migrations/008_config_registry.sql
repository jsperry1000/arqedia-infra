-- 008_config_registry.sql
--
-- The configuration a tenant authors: categories, document types, schemas and
-- templates, plus the mapping between types and schemas.
--
-- VERSIONING IS A WHOLE-REGISTRY SNAPSHOT. One mutable draft per tenant and an
-- append-only series of immutable revisions. Editors write revision 0, the
-- draft. Extraction and composition read a published revision and never the
-- draft. Publishing copies the draft into a new revision, which is then never
-- touched again.
--
-- Versioning each object separately would mean a memo pinning a SET of
-- versions and resolving cross-object references at each of them - a
-- dependency graph that worsens with every edit. A snapshot is one integer,
-- and `document.config_revision` already carries it.
--
-- RETIREMENT FALLS OUT OF SNAPSHOTS. There is no retired flag anywhere below.
-- A document type present in revision 11 and absent from revision 12 is
-- retired going forward, and everything filed under 11 still resolves against
-- 11. Non-destructive by construction, with no tombstones to maintain.
--
-- IDENTITY IS STABLE. field_key, type_key and the rest are minted at creation
-- and never change; labels are display metadata. Renaming a field is free and
-- orphans nothing, because extracted_value references the key.

-- The revision itself. Revision 0 is the draft and is mutable; every other
-- revision is written once at publish and never updated.
CREATE TABLE config_revision (
  tenant_id        BIGINT       NOT NULL,
  revision         INT          NOT NULL,
  status           VARCHAR(16)  NOT NULL DEFAULT 'draft',
  forked_from      VARCHAR(128) NULL,
  note             VARCHAR(512) NULL,
  created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_by       VARCHAR(255) NULL,
  published_at     DATETIME     NULL,
  published_by     VARCHAR(255) NULL,
  PRIMARY KEY (tenant_id, revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- A grouping of document types, for the review screen's dropdown and nothing
-- more. Categories carry no behaviour.
CREATE TABLE config_category (
  tenant_id      BIGINT       NOT NULL,
  revision       INT          NOT NULL,
  category_key   VARCHAR(64)  NOT NULL,
  label          VARCHAR(128) NOT NULL,
  sort_order     INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, revision, category_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- What a document IS. The description is not decoration: it is what the
-- classifier reads to propose a type, and Stage 1 showed that the same
-- document classified differently as a PDF and a Word file until each type
-- carried a sentence describing it.
--
-- read_mode and always_ocr decide how a confirmed document is read. They
-- belong to the type because the type is what a person confirms, and because
-- a split file will one day give each part its own type and therefore its own
-- reading.
CREATE TABLE config_document_type (
  tenant_id      BIGINT       NOT NULL,
  revision       INT          NOT NULL,
  type_key       VARCHAR(64)  NOT NULL,
  label          VARCHAR(128) NOT NULL,
  category_key   VARCHAR(64)  NOT NULL,
  description    TEXT         NOT NULL,
  read_mode      VARCHAR(16)  NOT NULL DEFAULT 'text',
  always_ocr     TINYINT(1)   NOT NULL DEFAULT 0,
  sort_order     INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, revision, type_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- A set of fields extracted together, with the instruction that governs them.
CREATE TABLE config_schema (
  tenant_id      BIGINT       NOT NULL,
  revision       INT          NOT NULL,
  schema_key     VARCHAR(64)  NOT NULL,
  label          VARCHAR(128) NOT NULL,
  instruction    TEXT         NULL,
  sort_order     INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, revision, schema_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Which types feed which schemas. MANY-TO-MANY, and the only link that needs
-- its own editing surface: a type feeding no schema extracts nothing, and a
-- schema no type feeds runs never. Both are silent failures, and both are
-- visible only here.
CREATE TABLE config_type_schema (
  tenant_id      BIGINT       NOT NULL,
  revision       INT          NOT NULL,
  type_key       VARCHAR(64)  NOT NULL,
  schema_key     VARCHAR(64)  NOT NULL,
  PRIMARY KEY (tenant_id, revision, type_key, schema_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- One field. field_key is the identity extracted_value references and never
-- changes; label is display only.
--
-- group_key binds fields that repeat together as a row. A shareholder's name
-- means nothing without the percentage beside it, and a row_ordinal is what
-- keeps the third name attached to the third percentage. Without it two
-- parallel lists have no reliable correspondence and a memo can put the wrong
-- percentage against the wrong shareholder with nothing flagging it.
CREATE TABLE config_field (
  tenant_id      BIGINT       NOT NULL,
  revision       INT          NOT NULL,
  schema_key     VARCHAR(64)  NOT NULL,
  field_key      VARCHAR(128) NOT NULL,
  label          VARCHAR(128) NOT NULL,
  field_type     VARCHAR(32)  NOT NULL DEFAULT 'text',
  cardinality    VARCHAR(16)  NOT NULL DEFAULT 'one',
  description    TEXT         NULL,
  group_key      VARCHAR(64)  NULL,
  sort_order     INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, revision, field_key),
  INDEX idx_field_schema (tenant_id, revision, schema_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- A memo. One row per template; sections hang off it.
CREATE TABLE config_template (
  tenant_id      BIGINT       NOT NULL,
  revision       INT          NOT NULL,
  template_key   VARCHAR(64)  NOT NULL,
  label          VARCHAR(128) NOT NULL,
  PRIMARY KEY (tenant_id, revision, template_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- A memo section. `kind` is 'extract' - assembled from values, no model call -
-- or 'composed', drafted by the model from other sections named in
-- context_sections.
--
-- shape_key selects a presentation directive for the consolidation pass:
-- people render as tables that never disappear, financials with the period in
-- the heading. Absent, the generic rules apply.
CREATE TABLE config_section (
  tenant_id         BIGINT       NOT NULL,
  revision          INT          NOT NULL,
  template_key      VARCHAR(64)  NOT NULL,
  section_key       VARCHAR(64)  NOT NULL,
  numeral           VARCHAR(8)   NOT NULL,
  title             VARCHAR(255) NOT NULL,
  kind              VARCHAR(16)  NOT NULL DEFAULT 'extract',
  shape_key         VARCHAR(32)  NULL,
  prompt            TEXT         NULL,
  context_sections  VARCHAR(255) NULL,
  sort_order        INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, revision, template_key, section_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Which fields a section renders. THE LINK THAT BROKE IN STAGE 1: a template
-- naming a field the pack did not define produced a memo confidently
-- reporting facts as absent when they had been extracted and stored. Validated
-- at publish, and this binding alone is also checked at save.
CREATE TABLE config_section_field (
  tenant_id      BIGINT       NOT NULL,
  revision       INT          NOT NULL,
  template_key   VARCHAR(64)  NOT NULL,
  section_key    VARCHAR(64)  NOT NULL,
  field_key      VARCHAR(128) NOT NULL,
  sort_order     INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, revision, template_key, section_key, field_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Which revision a tenant's new work files against. Null until the tenant has
-- published one, and the loader sets it.
ALTER TABLE tenant
  ADD COLUMN active_revision INT NULL AFTER plan;
