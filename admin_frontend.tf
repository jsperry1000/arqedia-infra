# ---------------------------------------------------------------------------
# Hosting for the staff console. Its own bucket, its own distribution, its own
# certificate; nothing shared with frontend.tf but the pattern.
#
# NO DNS RECORD. admin.arqedia.com is an alias on the distribution and there
# is no A or AAAA record pointing at it, so the name does not resolve and the
# console is reachable only by its CloudFront hostname. That is deliberate for
# this stage: the record is one line, and adding it is a decision about when
# this becomes findable rather than a step in building it.
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "admin" {
  bucket = "${local.name_prefix}-admin-${data.aws_caller_identity.current.account_id}"
  tags   = { Name = "${local.name_prefix}-admin" }
}

resource "aws_s3_bucket_public_access_block" "admin" {
  bucket                  = aws_s3_bucket.admin.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "admin" {
  bucket = aws_s3_bucket.admin.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# The only identity permitted to read the bucket.
resource "aws_cloudfront_origin_access_control" "admin" {
  name                              = "${local.name_prefix}-admin"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "admin" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = "${local.name_prefix} staff console"
  price_class         = "PriceClass_100"

  # Claimed now so the certificate has something to be attached to. Nothing
  # resolves it until a record is added.
  aliases = [local.admin_host]

  origin {
    domain_name              = aws_s3_bucket.admin.bucket_regional_domain_name
    origin_id                = "s3-admin"
    origin_access_control_id = aws_cloudfront_origin_access_control.admin.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-admin"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS managed policy: CachingOptimized
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # Single-page app: unknown paths are routes, not missing files.
  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # THE ADMIN CERTIFICATE, not the web one. aws_acm_certificate.web covers the
  # apex, www and the application; this distribution serves a name that is on
  # neither, and attaching the web certificate would fail on the alias.
  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.admin.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = { Name = "${local.name_prefix}-admin" }
}

resource "aws_s3_bucket_policy" "admin" {
  bucket = aws_s3_bucket.admin.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.admin.arn}/*"
      Condition = {
        StringEquals = {
          # THIS distribution and no other. Without the condition, any
          # CloudFront distribution in any account could read the bucket.
          "AWS:SourceArn" = aws_cloudfront_distribution.admin.arn
        }
      }
    }]
  })
}

output "admin_bucket" {
  value = aws_s3_bucket.admin.id
}

output "admin_distribution_id" {
  value = aws_cloudfront_distribution.admin.id
}

# What the console answers on until a record is added for local.admin_host.
output "admin_url" {
  value = "https://${aws_cloudfront_distribution.admin.domain_name}"
}
