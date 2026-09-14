# Branch `site-dns` — read before the first apply

Four files: `providers.tf`, `dns.tf`, `certs.tf`, `site.tf`.

Nothing here touches an existing resource. The application distribution is
changed by hand in a later commit, once it has been read — see §3.

---

## 1. Two things to check in the repository first

**The default provider's authentication.** `providers.tf` adds an `aws.use1`
alias and sets only `region`. If the default provider block carries `profile`,
`assume_role` or `default_tags`, copy them onto the alias. Without that, the
certificate is issued into whichever account the ambient credentials resolve to,
which may not be 667523685221.

**Whether `name_prefix` is a local or a variable.** `ENV-01` records
`main.tf:2` as `name_prefix = "arqedia-${var.environment}"`. `site.tf` writes
`"arqedia-${var.environment}-site"` directly, which is correct either way but
duplicates the string. If `local.name_prefix` exists, substitute it.

---

## 2. Apply order

The first apply cannot complete the certificate, because the registrar is still
delegating to Network Solutions and the validation records are unreachable.
That is expected, not a failure.

```powershell
# 1. Zone only. Seconds.
terraform apply -target=aws_route53_zone.root

# 2. Read the four nameservers.
terraform output route53_nameservers
```

**3.** At Network Solutions, replace their nameservers with those four. All
four, not an addition. The domain has no mail, no verification records and
nothing else on it, so there is nothing to carry across.

**4.** Wait for delegation, then confirm from outside your own resolver:

```powershell
dig NS arqedia.com @8.8.8.8
nslookup -type=NS arqedia.com 8.8.8.8
```

Usually under an hour. Do not proceed until this returns the Route 53 four.

**5.** Full apply. ACM validates, the distribution builds, the records land.

```powershell
terraform apply
```

**6.** The distribution takes 10–20 minutes to reach `Deployed`. `arqedia.com`
serves nothing until the bucket has content — that is the `site-scaffold`
branch, not this one.

---

## 3. The application distribution — a separate commit

Not written here, because the resource must be read before it is edited.

Find the existing `aws_cloudfront_distribution` for the application — the one
behind `d2pco7fhb5wnod.cloudfront.net` — and add two things:

```hcl
  aliases = ["app.arqedia.com"]

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.web.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
```

If a `viewer_certificate` block already exists with
`cloudfront_default_certificate = true`, it is replaced, not appended to.

Then an alias record, alongside the ones in `site.tf`:

```hcl
resource "aws_route53_record" "app_a" {
  zone_id = aws_route53_zone.root.zone_id
  name    = local.app_host
  type    = "A"
  alias {
    name                   = <the app distribution>.domain_name
    zone_id                = local.cf_hosted_zone_id
    evaluate_target_health = false
  }
}
```

**The CloudFront hostname keeps working.** Adding an alias does not remove
`d2pco7fhb5wnod.cloudfront.net`, so the test accounts in the 9 September handoff
stay valid throughout. Nothing has to be coordinated and nothing is cut over.

---

## 4. SPA routing — required on the application, not on the site

The router merged on `ux-routing`, so a deep link to `/configure/3` is now a
real URL a person can bookmark or reload. S3 has no object at that key and
returns 403, which CloudFront serves as an error page.

On the **application** distribution only:

```hcl
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
```

Deliberately absent from the marketing distribution, which is static pages. A
rewrite there would turn every genuine 404 into a silent home page.

---

## 5. Verification, in the order from the deployment document

1. **Is it on disk?** `git diff --stat` names four new files.
2. **Is it deployed?** The plan summary names the zone, the certificate and the
   distribution. "No changes" means the files did not save where you think.
3. **Is DNS answering?** `dig NS arqedia.com @8.8.8.8` from outside your
   resolver, not from a browser address bar.
4. **Is the certificate issued?** `aws acm list-certificates --region us-east-1`
   shows `ISSUED`, not `PENDING_VALIDATION`.

Never conclude from a browser. A cached negative DNS answer and a broken
distribution look identical.

---

## 6. Rolling back

`git revert` and apply. The zone is `prevent_destroy` deliberately — destroying
it issues four new nameservers on recreate and means another registrar change
and another propagation wait. Removing the zone is a conscious act, not a
side effect of reverting a distribution.

---

## 7. Cost

Hosted zone $0.50/month. Certificate free. Bucket and distribution at this
volume are cents. Inside the noise on the existing budget alert.

---

## 8. Recorded for ENV-01

The hosted zone is the first resource in the stack that does not derive its
name from `name_prefix`, and the reason is in the header of `dns.tf`. When prod
is built, prod takes `arqedia.com` and `app.arqedia.com`; dev moves to
`dev.arqedia.com` and `app.dev.arqedia.com`. Two alias records and two
distribution aliases — no rebuild, but it must be a decision rather than a
discovery.
