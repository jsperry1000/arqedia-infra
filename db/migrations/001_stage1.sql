-- 001_stage1.sql
-- Stage 1 schema. Single hard-coded pack, no editors, no billing.
-- tenant_id and config_revision are present from the start: both are
-- impossible to retrofit once customer data exists.

CREATE TABLE tenant (
  tenant_id   BIGINT AUTO_INCREMENT PRIMARY KEY,
  name        VARCHAR(255) NOT NULL,
  region      VARCHAR(32)  NOT NULL,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document (
  document_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
  tenant_id         BIGINT       NOT NULL,
  engagement_id     BIGINT       NULL,
  s3_bucket         VARCHAR(255) NOT NULL,
  s3_key            VARCHAR(1024) NOT NULL,
  s3_version_id     VARCHAR(255) NULL,
  sha256            CHAR(64)     NOT NULL,
  filename          VARCHAR(512) NOT NULL,
  document_type     VARCHAR(128) NULL,
  page_count        INT          NULL,
  extraction_method VARCHAR(32)  NULL,
  config_revision   INT          NOT NULL,
  filed_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_document_tenant (tenant_id),
  INDEX idx_document_sha (tenant_id, sha256)
);

-- The evidence table. locator_* is EV-01: where in the document a value
-- came from. locator_kind = 'none' is a legitimate outcome, never a null gap.
CREATE TABLE extracted_value (
  value_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  tenant_id       BIGINT       NOT NULL,
  document_id     BIGINT       NOT NULL,
  field_id        VARCHAR(64)  NOT NULL,
  value           TEXT         NULL,
  row_ordinal     INT          NOT NULL DEFAULT 0,
  config_revision INT          NOT NULL,
  locator_kind    VARCHAR(16)  NOT NULL,
  locator_index   INT          NULL,
  char_start      INT          NULL,
  char_end        INT          NULL,
  cell_range      VARCHAR(64)  NULL,
  confidence      DECIMAL(4,3) NULL,
  extracted_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_value_document (tenant_id, document_id),
  INDEX idx_value_field (tenant_id, field_id)
);

CREATE TABLE memo (
  memo_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  tenant_id       BIGINT       NOT NULL,
  engagement_id   BIGINT       NULL,
  template_key    VARCHAR(64)  NOT NULL,
  config_revision INT          NOT NULL,
  s3_bucket       VARCHAR(255) NOT NULL,
  s3_key          VARCHAR(1024) NOT NULL,
  s3_version_id   VARCHAR(255) NULL,
  sha256          CHAR(64)     NOT NULL,
  generated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_memo_tenant (tenant_id)
);

CREATE TABLE memo_source (
  memo_id     BIGINT NOT NULL,
  document_id BIGINT NOT NULL,
  tenant_id   BIGINT NOT NULL,
  PRIMARY KEY (memo_id, document_id),
  INDEX idx_memo_source_doc (tenant_id, document_id)
);

CREATE TABLE claim (
  claim_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  tenant_id         BIGINT      NOT NULL,
  memo_id           BIGINT      NOT NULL,
  section_key       VARCHAR(64) NOT NULL,
  statement_ordinal INT         NOT NULL,
  statement_text    TEXT        NULL,
  INDEX idx_claim_memo (tenant_id, memo_id)
);

CREATE TABLE claim_evidence (
  claim_id  BIGINT NOT NULL,
  value_id  BIGINT NOT NULL,
  tenant_id BIGINT NOT NULL,
  PRIMARY KEY (claim_id, value_id),
  INDEX idx_claim_evidence_value (tenant_id, value_id)
);


