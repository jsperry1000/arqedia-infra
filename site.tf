# site.tf
#
# The marketing site: private bucket, origin access control, one distribution
# serving the apex and redirecting www to it at the edge.
#
# Follows the conventions in frontend.tf — local.name_prefix, the account id
# suffix on the bucket, the managed cache policy by id, and a Name tag.

resource "aws_s3_bucket" "site" {
  bucket = "${local.name_prefix}-site-${data.aws_caller_identity.current.account_id}"
  tags   = { Name = "${local.name_prefix}-site" }
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${local.name_prefix}-site"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# www -> apex, 301, at the edge. One distribution rather than a second bucket
# carrying a redirect rule.
resource "aws_cloudfront_function" "www_to_apex" {
  name    = "${local.name_prefix}-www-to-apex"
  runtime = "cloudfront-js-2.0"
  publish = true

    code = <<-JS
    function handler(event) {
      var req  = event.request;
      var host = req.headers.host.value;

      if (host === "www.arqedia.com") {
        return {
          statusCode: 301,
          statusDescription: "Moved Permanently",
          headers: { "location": { "value": "https://arqedia.com" + req.uri } }
        };
      }

      if (req.uri.endsWith("/")) { req.uri += "index.html"; }
      else if (req.uri.indexOf(".") === -1) { req.uri += "/index.html"; }

      return req;
    }
  JS
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  comment             = "${local.name_prefix} marketing site"
  price_class         = "PriceClass_100"

  aliases = [local.site_host, local.www_host]

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "s3-site"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-site"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS managed policy: CachingOptimized
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.www_to_apex.arn
    }
  }

  # No 403/404 rewrite here, unlike frontend.tf. The marketing site is static
  # pages rather than a single-page app, and a rewrite would turn every genuine
  # 404 into a silent home page.

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.web.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = { Name = "${local.name_prefix}-site" }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = "s3:GetObject"
      Resource  = "${aws_s3_bucket.site.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.site.arn
        }
      }
    }]
  })
}

resource "aws_route53_record" "site_a" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.site_host
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = local.cf_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "site_aaaa" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.site_host
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = local.cf_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "www_a" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.www_host
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site.domain_name
    zone_id                = local.cf_zone_id
    evaluate_target_health = false
  }
}

output "site_bucket" {
  value = aws_s3_bucket.site.id
}

output "site_distribution_id" {
  value = aws_cloudfront_distribution.site.id
}
