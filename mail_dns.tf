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
