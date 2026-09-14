# app_dns.tf
#
# app.arqedia.com -> the existing front-end distribution in frontend.tf.
#
# These records depend on two edits to aws_cloudfront_distribution.frontend
# that are NOT in this file. See NOTES.md §3. Applying this file before those
# edits produces a distribution serving the wrong certificate for the alias.

resource "aws_route53_record" "app_a" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.app_host
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = local.cf_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "app_aaaa" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.app_host
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.frontend.domain_name
    zone_id                = local.cf_zone_id
    evaluate_target_health = false
  }
}
