# ---------------------------------------------------------------------------
# Storage. Three buckets:
#   docs    - uploaded source documents
#   review  - normalized envelopes and extracted values
#   curated - generated memos
# One platform KMS key, tenant separation by encryption context and key prefix.
# Per-tenant keys are an Enterprise/regulated feature, not the default: a
# customer-managed key is $1/month rising to $3 with rotation, which is 4-12%
# of a $25 subscription before anything is processed.
# ---------------------------------------------------------------------------

resource "aws_kms_key" "data" {
  description             = "${local.name_prefix} document data"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  # Setting a policy replaces the default, so the account root statement must
  # be restated - without it nobody can administer the key, including us.
  #
  # Textract reads an encrypted document under its own service identity, so it
  # needs to decrypt with this key. The condition limits that to calls made on
  # behalf of this account.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AccountRoot"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "AllowTextractDecrypt"
        Effect    = "Allow"
        Principal = { Service = "textract.amazonaws.com" }
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService"    = "s3.${var.aws_region}.amazonaws.com"
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      },
    ]
  })

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

# The browser uploads straight to S3, so the bucket must accept requests from
# the application origin - including the encryption header the signed link
# requires. Without this the browser blocks the upload before it is sent.
resource "aws_s3_bucket_cors_configuration" "docs" {
  bucket = aws_s3_bucket.data["docs"].id

  cors_rule {
    allowed_origins = ["https://${aws_cloudfront_distribution.frontend.domain_name}",
    "http://localhost:5173"]
    allowed_methods = ["PUT"]
    allowed_headers = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket_ownership_controls" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

# Refuse any request not over TLS. The docs bucket additionally permits
# Textract to read a document under its own service identity - optical
# character recognition is performed by AWS, not by our code, so the
# permission has to sit on the bucket rather than on a role of ours.
resource "aws_s3_bucket_policy" "data" {
  for_each = aws_s3_bucket.data
  bucket   = each.value.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [{
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
      }],
      each.key != "docs" ? [] : [{
        Sid       = "AllowTextractRead"
        Effect    = "Allow"
        Principal = { Service = "textract.amazonaws.com" }
        Action    = "s3:GetObject"
        Resource  = "${each.value.arn}/*"
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = data.aws_caller_identity.current.account_id
          }
        }
      }]
    )
  })
}

output "data_buckets" {
  value = { for k, v in aws_s3_bucket.data : k => v.id }
}

output "data_kms_key_arn" {
  value = aws_kms_key.data.arn
}
