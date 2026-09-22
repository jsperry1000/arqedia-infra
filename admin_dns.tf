# admin_dns.tf
#
# admin.arqedia.com -> the staff console's distribution in admin_frontend.tf.
#
# WHAT THIS CHANGES. Until now the console answered only on its CloudFront
# hostname: the alias was claimed and the certificate attached, but nothing
# resolved the name. These two records are the moment it becomes findable by
# the name people will use.
#
# NOTHING ELSE IS NEEDED FIRST, unlike app_dns.tf. That file warns that its
# records depend on two edits to the front-end distribution made elsewhere;
# here the distribution already carries aliases = [local.admin_host] and the
# admin certificate, both applied on 21 September, so these records point at
# something already serving that name.
#
# BEING FINDABLE IS NOT BEING OPEN. The console is behind the staff pool with
# MFA required, its API refuses any token not issued by that pool, and its
# CORS allows one origin. A resolvable name adds a door to knock on; it does
# not add a way in.

resource "aws_route53_record" "admin_a" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.admin_host
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.admin.domain_name
    zone_id                = local.cf_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "admin_aaaa" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.admin_host
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.admin.domain_name
    zone_id                = local.cf_zone_id
    evaluate_target_health = false
  }
}
