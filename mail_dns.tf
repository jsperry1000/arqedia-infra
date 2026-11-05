# mail_dns.tf
#
# Mail for arqedia.com is RECEIVED by Microsoft 365, in the tenant that
# already runs ebl-finance.com. info@arqedia.com is an address on the shared
# mailbox info@ebl-finance.com: delivered there, not forwarded, so SPF and
# DMARC still pass for the original sender.
#
# The domain's mail is SENT by SES (auth.tf). The SES identity, its three
# DKIM records and _dmarc stay outside Terraform, as auth.tf decided: the
# domain is the account's, not this stack's. Only the root TXT record is
# managed here, because Microsoft's verification value has to share it with
# SPF, and Route53 holds one TXT record set per name.

# The root TXT record was created by hand alongside the SES identity. Adopted,
# not recreated: the first apply after this block imports it and changes
# nothing.
import {
  to = aws_route53_record.root_txt
  id = "${aws_route53_zone.root.zone_id}_${local.root_domain}_TXT"
}

# SPF names BOTH senders. Dropping amazonses.com would fail every message the
# product sends; dropping Outlook would fail every reply from the mailbox.
#
# MS= is Microsoft 365's proof that the tenant owns the domain. It stays after
# verification: removing it does not unverify the domain, but Microsoft asks
# for it again on any later re-check.
resource "aws_route53_record" "root_txt" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.root_domain
  type    = "TXT"
  ttl     = 600
  records = [
    "v=spf1 include:amazonses.com include:spf.protection.outlook.com ~all",
    "MS=ms45274366",
  ]

  lifecycle {
    prevent_destroy = true
  }
}

# Inbound mail goes to Microsoft 365. The host is the tenant's own, issued by
# the domain wizard on verification; priority 0, as Microsoft gives it. An
# address Microsoft 365 does not hold, such as no-reply@, is now refused with
# a bounce to the sender rather than going nowhere.
resource "aws_route53_record" "root_mx" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.root_domain
  type    = "MX"
  ttl     = 3600
  records = ["0 arqedia-com.mail.protection.outlook.com"]

  lifecycle {
    prevent_destroy = true
  }
}

# --- a MAIL FROM domain of our own (5 November 2026) --------------------------
#
# The envelope sender - the Return-Path a receiving server checks SPF against -
# was amazonses.com, so SPF passed for Amazon's domain and not ours, and DMARC
# rested on DKIM alone. With bounce.arqedia.com it passes as arqedia.com, which
# is what a receiving filter scores. Asked for as part of mail going to junk.
#
# THE IDENTITY STAYS OUTSIDE TERRAFORM; this sets one attribute of it. If the
# MX record below is ever missing, SES falls back to its own domain rather
# than refusing to send (UseDefaultValue): the product keeps sending, only the
# alignment is lost.
locals {
  mail_from_domain = "bounce.${local.root_domain}"
}

resource "aws_ses_domain_mail_from" "sender" {
  domain                 = data.aws_ses_domain_identity.sender.domain
  mail_from_domain       = local.mail_from_domain
  behavior_on_mx_failure = "UseDefaultValue"
}

# Where SES's own bounce handling receives for that domain, in this region.
resource "aws_route53_record" "mail_from_mx" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.mail_from_domain
  type    = "MX"
  ttl     = 600
  records = ["10 feedback-smtp.${var.aws_region}.amazonses.com"]
}

# SPF for the envelope domain: SES only. Nothing else sends as bounce.
resource "aws_route53_record" "mail_from_spf" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.mail_from_domain
  type    = "TXT"
  ttl     = 600
  records = ["v=spf1 include:amazonses.com ~all"]
}

# Lets Outlook clients find the mailbox settings for an @arqedia.com address.
resource "aws_route53_record" "autodiscover" {
  zone_id = aws_route53_zone.root.zone_id
  name    = "autodiscover.${local.root_domain}"
  type    = "CNAME"
  ttl     = 3600
  records = ["autodiscover.outlook.com"]

  lifecycle {
    prevent_destroy = true
  }
}
