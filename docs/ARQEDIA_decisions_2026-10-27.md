# ARQEDIA — Decisions, 27 Oct 2026

Additive. Records the legal-pages decisions made on 27 October 2026. Nothing
in earlier records is changed; where this differs from them, this applies from
this date.

---

## 1. The legal documents

- **Three documents, one Agreement:** Terms of Service, Privacy Policy and
  Refund Policy, split from the combined draft of 20 October 2026. Version 1
  of each takes effect 27 October 2026. Text: `docs/legal/*_v1.md`.
- **Contracting party:** Chase Creek LLC, a Delaware limited liability
  company doing business as ARQEDIA, replacing eBL Finance Inc. Paddle has
  been notified of the entity.
- **Counsel:** reviewed and approved, for Chase Creek LLC.
- **Governing law and eligibility:** Texas. Disputes go to state or federal
  courts in Texas. A Delaware entity contracting under Texas law is
  deliberate.
- **Contact:** info@arqedia.com, replacing info@ebl-finance.com.
- **Data Processing Agreement:** exists in draft, unpublished, available on
  request. Left out of the first build. The Privacy Policy does not mention
  it.

## 2. What the Privacy Policy now commits to

| Item | Decision |
| --- | --- |
| Region choice at sign-up | Kept. §3 changes when other regional stacks exist |
| AI models | AWS named alone (Bedrock), for now |
| Backups and earlier versions of a deleted document | 7 days, covering the facts read from it and memoranda built from them |
| Sign-up IP addresses | Kept while the account is active, deleted one year after cancellation |
| Share, view and download records | 3 years |

**Not yet true of the product, and must be built:** DynamoDB point-in-time
recovery is 35 days, earlier S3 versions never expire, and nothing deletes
sign-up IP addresses after cancellation or share records after 3 years.

## 3. What the Refund Policy now says

- Credit is returned for four failures: filing a document that cannot be
  read, reading the facts from a filed document, generating a memorandum,
  updating a memorandum. Terms §4 says the same.
- The month in which a subscription is cancelled is not refunded in part.
- A mid-month downgrade returns nothing to the wallet; Paddle may leave a
  credit on the customer's Paddle balance.
- Paddle's standard refund policy was read: ours differs, so it is linked
  from checkout.

## 4. Where the documents appear

- **Addresses:** arqedia.com/terms, /privacy, /refunds.
- **Public but unlinked:** no footer links. Each page is marked noindex.
  Reaching them only from sign-up or the app is not possible while they stay
  public, which Paddle's verification requires.
- **Reached from:** the last step of sign-up, the seat-invitation page, the
  recipient registration form, a link in the signed-in app, and the checkout
  and top-up controls.
- **Acceptance:** at the last step of sign-up and when an invited member
  accepts a seat, as well as at recipient registration. Each acceptance
  records the Agreement's version number.
- **Still open:** where the homepage shows info@arqedia.com, which Paddle's
  go-live checklist asks for.
