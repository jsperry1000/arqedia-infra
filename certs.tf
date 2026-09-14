# certs.tf
#
# One certificate covering the apex, www and the application, issued in
# us-east-1 and validated by records written into the zone above.
#
# On the FIRST apply this will sit in PENDING_VALIDATION, because the registrar
# is still delegating elsewhere and the validation records are unreachable.
# That is expected. The validation resource below is what blocks the
# distributions from attaching a certificate that has not issued.

resource "aws_acm_certificate" "web" {
  provider = aws.use1

  domain_name = local.site_host
  subject_alternative_names = [
    local.www_host,
    local.app_host,
  ]
  validation_method = "DNS"

  # Renewals issue a new certificate before the old one is detached.
  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = "arqedia-web"
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.web.domain_validation_options : dvo.domain_name => {
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

resource "aws_acm_certificate_validation" "web" {
  provider = aws.use1

  certificate_arn         = aws_acm_certificate.web.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}
