# admin_certs.tf
#
# The certificate for admin.arqedia.com, issued in us-east-1 and validated by
# records written into the same zone as everything else.
#
# ITS OWN CERTIFICATE, NOT A NAME ON THE WEB ONE. The staff console shares
# nothing with the customer path except the database (Group 16). A subject
# alternative name on aws_acm_certificate.web would tie the two together at
# renewal: one certificate, one validation set, and a failure on either name
# takes both surfaces down. Separate certificates fail separately, and the
# staff console can be withdrawn by deleting its own resources rather than by
# editing the customer's.
#
# THE HOSTNAME LIVES HERE, not beside site_host and app_host in dns.tf,
# because nothing resolves it yet. Stage 1 issues a certificate and no A
# record; the distribution that would answer on this name is a later stage.

locals {
  admin_host = "admin.${local.root_domain}"
}

resource "aws_acm_certificate" "admin" {
  provider = aws.use1

  domain_name       = local.admin_host
  validation_method = "DNS"

  # Renewals issue a new certificate before the old one is detached.
  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "arqedia-admin"
  }
}

resource "aws_route53_record" "admin_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.admin.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id         = aws_route53_zone.root.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "admin" {
  provider = aws.use1

  certificate_arn         = aws_acm_certificate.admin.arn
  validation_record_fqdns = [for r in aws_route53_record.admin_cert_validation : r.fqdn]
}

output "admin_certificate_arn" {
  value = aws_acm_certificate.admin.arn
}
