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
