# ---------------------------------------------------------------------------
# Storage. Three buckets:
#   docs    - uploaded source documents
#   review  - normalized envelopes and extracted values
#   curated - generated memos
# One platform KMS key, tenant separation by encryption context and key prefix.
# Per-tenant keys are an Enterprise/regulated feature, not the default.
# ---------------------------------------------------------------------------

resource "aws_kms_key" "data" {
  description             = "${local.name_prefix} document data"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  tags = { Name = "${local.name_prefix}-data" }
}

resource "aws_kms_alias" "data" {
  name          = "alias/${local.name_prefix}-data"
  target_key_id = aws_kms_key.data.key_id
}

locals {
  buckets = {
    docs    = "uploaded source documents"
    review  = "normalized envelopes and extracted values"
    curated = "generated memos"
  }
}

resource "aws_s3_bucket" "data" {
  for_each = local.buckets
  bucket   = "${local.name_prefix}-${each.key}-${data.aws_caller_identity.current.account_id}"

  tags = {
    Name    = "${local.name_prefix}-${each.key}"
    Purpose = each.value
  }
}

resource "aws_s3_bucket_versioning" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  for_each                = aws_s3_bucket.data
  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Refuse any request not over TLS.
resource "aws_s3_bucket_policy" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource = [
        each.value.arn,
        "${each.value.arn}/*",
      ]
      Condition = {
        Bool = { "aws:SecureTransport" = "false" }
      }
    }]
  })
}

output "data_buckets" {
  value = { for k, v in aws_s3_bucket.data : k => v.id }
}

output "data_kms_key_arn" {
  value = aws_kms_key.data.arn
}
