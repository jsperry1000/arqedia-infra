# Objects with no document row, recorded 19 September 2026

Eighty-eight objects in the dev docs bucket have no `document` row. Found by
the reconciler built in Stage 2, on its first run.

**All of them predate the Stage 1 apply of 2026-09-18 19:45 UTC**, verified
against S3 `LastModified` rather than inferred from age:

    oldest   2026-08-28 14:25:03 UTC
    newest   2026-09-18 15:47:26 UTC   (three hours before the apply, inside
                                        the incident window of that day)
    at or after the apply: none

So these are historical. They are the documents the old readability gate
refused before Stage 1 began writing a row for every refusal - a refusal that
by definition left no trace, which is the hole Stage 1 closed and Stage 4
turned into a route. Nothing uploaded since has been orphaned.

**They have not been touched or read.** The reconciler lists object metadata
and asks the database which keys have a row; it never calls GetObject, and
neither did the check that produced this file. What is in them is unknown and
was not looked at.

## Why they are not being cleaned up

Deciding what to do with them means knowing what they are, and knowing that
means reading somebody's documents. Two honest options, neither taken here:

- **Leave them.** They belong to tenants 1, 2, 5 and 9; the engagements they
  sat in have moved on, and the files are still in the bucket if anyone wants
  them.
- **Re-upload a sample through the new path** and see how many now succeed.
  That would measure what the hole cost, and it is a decision for the owner
  rather than a diagnosis.

## Why the reconciler no longer lists them

A backstop that reports eighty-eight known-historical rows every fifteen
minutes is a backstop nobody reads. `HISTORICAL_BEFORE` is set to the Stage 1
apply, so only objects newer than it are reported as orphans.

**The count is not hidden.** Every run still prints `historical=88` on its
summary line, so the number is in front of whoever reads it and a change in
it would show.

## The keys

Listed as `LastModified  key`.

```
2026-08-31T15:14:53+00:00  tenants/1/docs/COCOA-EMPIRE/09.-Cocoa-Certificate-Cocoa-Empire-Uganda-Ltd.pdf
2026-08-31T15:15:04+00:00  tenants/1/docs/COCOA-EMPIRE/10.-REX-Registered-Exporter-Decision-UGREX2026040-valid-from-2026-08-06.pdf
2026-08-31T15:16:20+00:00  tenants/1/docs/COCOA-EMPIRE/13.-Certified-Passport-Frank-Arrigazzi.pdf
2026-08-31T15:13:19+00:00  tenants/1/docs/COCOA-EMPIRE/KCCA-Trade-Licence-2026.pdf
2026-08-31T15:16:19+00:00  tenants/1/docs/COCOA-EMPIRE/Notarised-Passport-Ivan-Arrigazzi.pdf
2026-08-31T15:16:31+00:00  tenants/1/docs/COCOA-EMPIRE/Notarised_TIN_Cert.pdf
2026-08-31T15:16:31+00:00  tenants/1/docs/COCOA-EMPIRE/Notary_Certificate_of_incorporation.pdf
2026-08-31T15:13:18+00:00  tenants/1/docs/COCOA-EMPIRE/Purchase-order-P20264093-CE-GF-2026-001-GoodFlow-signed.pdf
2026-08-31T15:13:18+00:00  tenants/1/docs/COCOA-EMPIRE/REX-Registered-Exporter-UGREX2026040.pdf
2026-08-28T15:51:39+00:00  tenants/1/docs/COCOAEMPIRE/KCCA-Trade-Licence-2026.pdf
2026-08-28T14:25:03+00:00  tenants/1/docs/COCOAEMPIRE/KCCATradeLicence2026.pdf
2026-08-28T14:25:03+00:00  tenants/1/docs/COCOAEMPIRE/Purcha-eorderP20264093CE-GF-2026-001GoodFlow-igned.pdf
2026-08-28T15:51:39+00:00  tenants/1/docs/COCOAEMPIRE/Purchase-order-P20264093-CE-GF-2026-001-GoodFlow-signed.pdf
2026-08-28T15:51:39+00:00  tenants/1/docs/COCOAEMPIRE/REX-Registered-Exporter-UGREX2026040.pdf
2026-08-28T14:25:03+00:00  tenants/1/docs/COCOAEMPIRE/REXRegi-teredExporterUGREX2026040.pdf
2026-08-28T16:13:09+00:00  tenants/1/docs/Cocoa-Test/09.-Cocoa-Certificate-Cocoa-Empire-Uganda-Ltd.pdf
2026-08-28T16:13:09+00:00  tenants/1/docs/Cocoa-Test/10.-REX-Registered-Exporter-Decision-UGREX2026040-valid-from-2026-08-06.pdf
2026-08-28T16:13:34+00:00  tenants/1/docs/Cocoa-Test/13.-Certified-Passport-Frank-Arrigazzi.pdf
2026-08-28T16:14:16+00:00  tenants/1/docs/Cocoa-Test/15.-CE-_-Company-Deck.pdf
2026-08-28T16:08:40+00:00  tenants/1/docs/Cocoa-Test/KCCA-Trade-Licence-2026.pdf
2026-08-28T16:13:35+00:00  tenants/1/docs/Cocoa-Test/Notarised-Passport-Ivan-Arrigazzi.pdf
2026-08-28T16:13:22+00:00  tenants/1/docs/Cocoa-Test/Notarised_TIN_Cert.pdf
2026-08-28T16:13:22+00:00  tenants/1/docs/Cocoa-Test/Notary_Certificate_of_incorporation.pdf
2026-08-28T16:08:41+00:00  tenants/1/docs/Cocoa-Test/Purchase-order-P20264093-CE-GF-2026-001-GoodFlow-signed.pdf
2026-08-28T16:08:41+00:00  tenants/1/docs/Cocoa-Test/REX-Registered-Exporter-UGREX2026040.pdf
2026-08-28T22:21:34+00:00  tenants/1/docs/Cocoa-test-4/KCCA-Trade-Licence-2026.pdf
2026-08-28T22:21:34+00:00  tenants/1/docs/Cocoa-test-4/Purchase-order-P20264093-CE-GF-2026-001-GoodFlow-signed.pdf
2026-08-28T22:21:34+00:00  tenants/1/docs/Cocoa-test-4/REX-Registered-Exporter-UGREX2026040.pdf
2026-09-03T15:47:37+00:00  tenants/1/docs/Manty/2025.07.07-STAR-TRADING-COMPANY-LIMITED-Certificate-of-Incumbency.pdf
2026-09-03T15:49:26+00:00  tenants/1/docs/Manty/Avgerinos-Panagiotis-Passport-Greece-Exp.-30.05.27.pdf
2026-09-03T15:49:26+00:00  tenants/1/docs/Manty/Corporate-Structure-2025.pdf
2026-09-01T19:36:46+00:00  tenants/1/docs/Manty/Manty-SA-Articles-of-Incorporation.pdf
2026-09-03T15:49:26+00:00  tenants/1/docs/Manty/Manty-Star-KYC-form.pdf
2026-09-03T15:49:26+00:00  tenants/1/docs/Manty/Star-Trading-FS-2024.pdf
2026-09-01T19:36:37+00:00  tenants/1/docs/Manty/flourmill-report-31-10-24.pdf
2026-09-10T18:53:31+00:00  tenants/2/docs/COCOA-EIMPIRE-5/09.-Cocoa-Certificate-Cocoa-Empire-Uganda-Ltd.pdf
2026-09-10T18:53:31+00:00  tenants/2/docs/COCOA-EIMPIRE-5/10.-REX-Registered-Exporter-Decision-UGREX2026040-valid-from-2026-08-06.pdf
2026-09-10T18:47:02+00:00  tenants/2/docs/COCOA-EIMPIRE-5/CE-_-KCCA-Trade-Licence-Certificate-_-2026-exp-10-Jun-2027.pdf
2026-09-10T18:47:03+00:00  tenants/2/docs/COCOA-EIMPIRE-5/Contract_22664_Amendment_2_SIGNED-1-1.pdf
2026-09-10T18:47:04+00:00  tenants/2/docs/COCOA-EIMPIRE-5/Frank-_-Certified-Passport-4.pdf
2026-09-10T18:48:01+00:00  tenants/2/docs/COCOA-EIMPIRE-5/KCCA-Trade-Licence-2026.pdf
2026-09-12T13:29:26+00:00  tenants/2/docs/COCOA-EIMPIRE-5/Notarised-Passport-Ivan-Arrigazzi.pdf
2026-09-10T18:48:20+00:00  tenants/2/docs/COCOA-EIMPIRE-5/Notarised_TIN_Cert.pdf
2026-09-10T18:48:20+00:00  tenants/2/docs/COCOA-EIMPIRE-5/Notary_Certificate_of_incorporation.pdf
2026-09-10T18:48:02+00:00  tenants/2/docs/COCOA-EIMPIRE-5/Purchase-order-P20264093-CE-GF-2026-001-GoodFlow-signed.pdf
2026-09-10T18:48:02+00:00  tenants/2/docs/COCOA-EIMPIRE-5/REX-Registered-Exporter-UGREX2026040.pdf
2026-09-05T15:36:55+00:00  tenants/2/docs/COCOA-EMPIRE-2/09.-Cocoa-Certificate-Cocoa-Empire-Uganda-Ltd.pdf
2026-09-05T15:36:55+00:00  tenants/2/docs/COCOA-EMPIRE-2/10.-REX-Registered-Exporter-Decision-UGREX2026040-valid-from-2026-08-06.pdf
2026-09-05T15:36:34+00:00  tenants/2/docs/COCOA-EMPIRE-2/13.-Certified-Passport-Frank-Arrigazzi.pdf
2026-09-05T15:37:57+00:00  tenants/2/docs/COCOA-EMPIRE-2/KCCA-Trade-Licence-2026.pdf
2026-09-05T15:36:35+00:00  tenants/2/docs/COCOA-EMPIRE-2/Notarised-Passport-Ivan-Arrigazzi.pdf
2026-09-05T15:36:26+00:00  tenants/2/docs/COCOA-EMPIRE-2/Notarised_TIN_Cert.pdf
2026-09-05T15:36:26+00:00  tenants/2/docs/COCOA-EMPIRE-2/Notary_Certificate_of_incorporation.pdf
2026-09-05T15:37:57+00:00  tenants/2/docs/COCOA-EMPIRE-2/Purchase-order-P20264093-CE-GF-2026-001-GoodFlow-signed.pdf
2026-09-05T15:37:57+00:00  tenants/2/docs/COCOA-EMPIRE-2/REX-Registered-Exporter-UGREX2026040.pdf
2026-09-05T17:46:47+00:00  tenants/2/docs/COCOA-EMPIRE-3/09.-Cocoa-Certificate-Cocoa-Empire-Uganda-Ltd.pdf
2026-09-05T17:46:47+00:00  tenants/2/docs/COCOA-EMPIRE-3/10.-REX-Registered-Exporter-Decision-UGREX2026040-valid-from-2026-08-06.pdf
2026-09-06T17:32:03+00:00  tenants/2/docs/COCOA-EMPIRE-3/CE-_-KCCA-Trade-Licence-Certificate-_-2026-exp-10-Jun-2027.pdf
2026-09-06T17:21:59+00:00  tenants/2/docs/COCOA-EMPIRE-3/Contract_22664_Amendment_2_SIGNED-1-1.pdf
2026-09-06T17:32:03+00:00  tenants/2/docs/COCOA-EMPIRE-3/Frank-_-Certified-Passport-4.pdf
2026-09-05T17:45:58+00:00  tenants/2/docs/COCOA-EMPIRE-3/KCCA-Trade-Licence-2026.pdf
2026-09-05T17:46:24+00:00  tenants/2/docs/COCOA-EMPIRE-3/Notarised-Passport-Ivan-Arrigazzi.pdf
2026-09-05T17:46:13+00:00  tenants/2/docs/COCOA-EMPIRE-3/Notarised_TIN_Cert.pdf
2026-09-05T17:46:13+00:00  tenants/2/docs/COCOA-EMPIRE-3/Notary_Certificate_of_incorporation.pdf
2026-09-06T17:22:00+00:00  tenants/2/docs/COCOA-EMPIRE-3/Purchase-order-P20264093-CE-GF-2026-001-GoodFlow-signed.pdf
2026-09-05T17:45:59+00:00  tenants/2/docs/COCOA-EMPIRE-3/REX-Registered-Exporter-UGREX2026040.pdf
2026-09-06T18:31:14+00:00  tenants/2/docs/COCOA-EMPIRE-4/09.-Cocoa-Certificate-Cocoa-Empire-Uganda-Ltd.pdf
2026-09-06T18:31:14+00:00  tenants/2/docs/COCOA-EMPIRE-4/10.-REX-Registered-Exporter-Decision-UGREX2026040-valid-from-2026-08-06.pdf
2026-09-06T18:28:15+00:00  tenants/2/docs/COCOA-EMPIRE-4/CE-_-KCCA-Trade-Licence-Certificate-_-2026-exp-10-Jun-2027.pdf
2026-09-06T18:28:15+00:00  tenants/2/docs/COCOA-EMPIRE-4/Contract_22664_Amendment_2_SIGNED-1-1.pdf
2026-09-06T18:28:16+00:00  tenants/2/docs/COCOA-EMPIRE-4/Frank-_-Certified-Passport-4.pdf
2026-09-06T18:32:24+00:00  tenants/2/docs/COCOA-EMPIRE-4/KCCA-Trade-Licence-2026.pdf
2026-09-06T18:29:58+00:00  tenants/2/docs/COCOA-EMPIRE-4/Notarised-Passport-Ivan-Arrigazzi.pdf
2026-09-06T18:30:13+00:00  tenants/2/docs/COCOA-EMPIRE-4/Notarised_TIN_Cert.pdf
2026-09-06T18:30:13+00:00  tenants/2/docs/COCOA-EMPIRE-4/Notary_Certificate_of_incorporation.pdf
2026-09-06T18:32:24+00:00  tenants/2/docs/COCOA-EMPIRE-4/Purchase-order-P20264093-CE-GF-2026-001-GoodFlow-signed.pdf
2026-09-06T18:32:25+00:00  tenants/2/docs/COCOA-EMPIRE-4/REX-Registered-Exporter-UGREX2026040.pdf
2026-09-05T13:54:41+00:00  tenants/2/docs/COCOA-EMPIRE/09.-Cocoa-Certificate-Cocoa-Empire-Uganda-Ltd.pdf
2026-09-05T13:54:41+00:00  tenants/2/docs/COCOA-EMPIRE/10.-REX-Registered-Exporter-Decision-UGREX2026040-valid-from-2026-08-06.pdf
2026-09-05T13:53:47+00:00  tenants/2/docs/COCOA-EMPIRE/13.-Certified-Passport-Frank-Arrigazzi.pdf
2026-09-05T13:51:29+00:00  tenants/2/docs/COCOA-EMPIRE/KCCA-Trade-Licence-2026.pdf
2026-09-05T13:53:48+00:00  tenants/2/docs/COCOA-EMPIRE/Notarised-Passport-Ivan-Arrigazzi.pdf
2026-09-05T13:54:03+00:00  tenants/2/docs/COCOA-EMPIRE/Notarised_TIN_Cert.pdf
2026-09-05T13:54:03+00:00  tenants/2/docs/COCOA-EMPIRE/Notary_Certificate_of_incorporation.pdf
2026-09-05T13:51:28+00:00  tenants/2/docs/COCOA-EMPIRE/Purchase-order-P20264093-CE-GF-2026-001-GoodFlow-signed.pdf
2026-09-05T13:51:28+00:00  tenants/2/docs/COCOA-EMPIRE/REX-Registered-Exporter-UGREX2026040.pdf
2026-09-18T15:47:26+00:00  tenants/5/docs/MANTY/Carrinho-Group-Management-figures-30.06.2025.pdf
2026-09-18T15:19:58+00:00  tenants/9/docs/Test-Engagement-One/Manty-SA-Articles-of-Incorporation.pdf
```
