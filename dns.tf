# dns.tf
#
# The hosted zone for arqedia.com.
#
# DELIBERATE: this is the only resource in the stack that does not derive its
# name from local.name_prefix.
#
# A hosted zone is authoritative for a domain, not for an environment. Applying
# with environment = "prod" against a prefixed zone would create a SECOND
# authoritative zone for arqedia.com, and the registrar can delegate to only
# one of them. Everything else stays prefixed; the environment is expressed in
# the HOSTNAMES instead.
#
# Recorded for ENV-01: when prod is built, prod takes arqedia.com and
# app.arqedia.com, and dev moves to dev.arqedia.com and app.dev.arqedia.com.
# Two alias records and two distribution aliases, not a rebuild.

locals {
  root_domain = "arqedia.com"

  # Dev holds the real hostnames today. See above.
  site_host = local.root_domain
  www_host  = "www.${local.root_domain}"
  app_host  = "app.${local.root_domain}"

  # CloudFront's hosted zone id. Fixed and global.
  cf_zone_id = "Z2FDTNDATAQYW2"
}

# Every origin a browser may call this deployment from. ONE LIST, read by the
# API gateway's CORS and by all three bucket CORS rules.
#
# WHY IT IS ONE LIST. It used to be two. api.tf gained app.arqedia.com when
# that hostname was introduced; the bucket rules in storage.tf and render.tf
# were never updated and still named only the CloudFront domain. Somebody
# added the missing origins to the buckets by hand, so uploads worked and
# Terraform held a pending removal of four origins it did not know about. The
# next apply - for an unrelated change - executed it, and every browser upload
# from app.arqedia.com failed its preflight with no Access-Control-Allow-Origin
# at all. A list maintained in two places is a list maintained in one.
#
# CORS GRANTS NOTHING. It says which pages a browser will permit to call the
# bucket; the signed link is the control, and it is one key, PUT only, fifteen
# minutes, inside the calling tenant's own prefix. The marketing site is on
# this list for signup's two unauthenticated routes and has no signed link to
# use, which is why one list costs nothing here.
locals {
  browser_origins = [
    "https://${aws_cloudfront_distribution.frontend.domain_name}",
    "https://${local.app_host}",
    "https://${local.site_host}",
    # Vite takes the next free port when 5173 is busy, which it is whenever
    # the marketing site is running too. Three, so a second dev server does
    # not look like a CORS fault.
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
  ]
}

resource "aws_route53_zone" "root" {
  name    = local.root_domain
  comment = "ARQEDIA — authoritative for all environments"

  # Destroying this issues four new nameservers on recreate, which means another
  # registrar change and another propagation wait. Removing it is a conscious
  # act, not a side effect of reverting something else.
  lifecycle {
    prevent_destroy = true
  }
}

# Set these four at Network Solutions, replacing theirs entirely.
output "route53_nameservers" {
  description = "Set at the registrar, then wait for delegation before the second apply."
  value       = aws_route53_zone.root.name_servers
}

output "hosted_zone_id" {
  value = aws_route53_zone.root.zone_id
}
