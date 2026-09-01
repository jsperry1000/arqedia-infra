-- 010_widen_field_id.sql
--
-- extracted_value.field_id holds 64 characters. config_field.field_key holds
-- 128. They are the SAME identity, and the mismatch was mine: the registry
-- migration was written without reading the table it had to match.
--
-- The consequence was not a failed save. A field created in the editor was
-- accepted, published, and then failed hours later during extraction on a
-- document somebody had uploaded - with the values partly written and the
-- document left reporting "extracting" for ever.
--
-- Widening rather than truncating. Truncating would cap how descriptive a
-- field name may be, for no reason beyond an arbitrary width chosen in Stage
-- 1, and would silently rename identities that other rows already reference.
--
-- field_id carries no index (checked against information_schema before
-- writing this), so this is a metadata change rather than an index rebuild.

ALTER TABLE extracted_value
  MODIFY COLUMN field_id VARCHAR(128) NOT NULL;
