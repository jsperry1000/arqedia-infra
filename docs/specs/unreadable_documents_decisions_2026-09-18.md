# Unreadable Documents — Decision Record

**18 September 2026**
Additive to the pipeline specification. Where this record differs from anything
earlier about what happens to a document that cannot be read, this record
applies from this date.

---

## 1. What was found

A new tenant on `deus-ex.co` uploaded a scanned PDF. The screen waited six
minutes and told them nothing. Nothing was charged, nothing was created, and
nothing anywhere said why.

**The upload worked.** The object reached
`s3://arqedia-dev-docs-.../tenants/9/docs/...`, EventBridge matched, and the
normalizer ran twice in 86 ms and 84 ms with no error. It logged:

    [unreadable] key=tenants/9/docs/.../Manty-SA-Articles-of-Incorporation.pdf reason=no_text_layer

`extract_pdf` refuses a PDF averaging fewer than `PDF_MIN_CHARS_PER_PAGE`
(50) characters a page. The normalizer catches that refusal, prints a line and
returns a dict to EventBridge, which discards it. **No document row, no
Textract job, no message.** The Review screen then waits for a row that no
process will ever create, polls every five seconds, and after ten minutes says
"Nothing has changed for ten minutes" - which describes the symptom and not
the cause.

**This is not a regression.** The threshold and the refusal are unchanged since
`3d7639a`, 26 August, the first commit of the pipeline. Deployed code matches
the repository byte for byte; rules, targets and permissions match Terraform.

**It is a hole nobody had stepped in.** Of 603 document rows, 31 carry
`thin_text = true` and all 31 fall on 28 August. Those are scans that cleared
because they carried a residual text layer - a stamp or a footer - of 69 to 155
characters a page. The lowest characters-per-page ever accepted from a PDF is
**69.0**. A clean image scan, carrying nothing at all, has never produced a
row. Tenants 1 and 2 had been uploading digital PDFs; the first pure scan found
the hole on its first day.

**The perverse part, and the reason this is worth a record.** A scan with a
token text layer gets the best treatment - row, `thin_text`, Textract, 584
characters where there were 77, filed and extracted. A scan with none gets the
worst. The input that most needs OCR is the only one that cannot reach it.

---

## 2. Approved

1. **No upload may end in silence.** Every object landing under `tenants/`
   finishes in a state a person can see: a row to act on, or a refusal saying
   why. Today the normalizer has exits that write nothing, and anything taking
   one of them is invisible. `no_text_layer` is the door that was walked
   through; the hole is the class.

2. **The character threshold routes; it does not refuse.** Two numbers were
   doing incompatible jobs - 200 sent a document to OCR, 50 threw it away.
   That cliff is the defect. There is one ladder: plenty of text reads
   directly, some text reads then OCRs, no text OCRs. A document with zero
   characters is the extreme case of thin, not a different kind of thing.

3. **A text-free scan is accepted unclassified and OCRs at filing.** It gets a
   row with `thin_text = true`, no proposed type, and an honest page count. The
   person chooses the type by hand and files; filing sends it to OCR exactly as
   it sends any thin document today. Nothing is spent until they commit, so
   "debit on the click" is untouched.

   Classifying by hand is the price. It is the honest price: with no text there
   is nothing to classify from, and proposing a type from a filename would put
   a guess where a reading belongs.

4. **Reasons are separated, because they are not alike.**

       no_text_layer        a scan. OCR is the remedy - route to it
       pdf-parse-failed     corrupt, or not a PDF. OCR cannot help - refuse
       no-pages             nothing in it - refuse
       anything unexpected  refuse, and say what happened

5. **A refused document costs nothing.** It is not read, so there is nothing to
   charge for. This holds however the refusal arises, including a document that
   reaches OCR and fails there.

6. **A corrupt file is told what to do about it.** The wording says the file
   carries nothing readable, and asks the person to put it through an OCR
   process and upload the result. Not an error code, and not silence.

7. **Filing refuses a document with no type, before any money moves.** Today a
   proposed type always exists so nothing checks. Under item 3 it may not, and
   `_start_ocr` asks the registry for the read mode of the confirmed type - a
   null would fail there, after the charge. This is the one new failure mode
   item 3 creates and it is not to be left to a later pass.

8. **Nothing is built beside the existing path.** A text-free scan joins the
   route 176 documents have already taken. `_start_ocr`, the collector,
   extraction, the charging rule and the EventBridge wiring are untouched. The
   one constraint that shapes the work: the collector READS the
   `.analysed.json` envelope the normalizer wrote, and overwrites `raw_text`,
   `units`, `tables`, `extraction_method` and `thin_text` in it. So the
   envelope must exist before OCR runs, even when it holds no text.

9. **The order of work.**

       1  make every failure visible          independent of everything below
       2  catch failures that never reach     on-failure destination, and a
          the code                            check for objects with no row
       3  decided: accept and OCR at filing   this record
       4  build it                            items 3, 4, 7, 8
       5  observability                       API Gateway access logging, and
                                              the route in the API's own log

   One is first because it is independent, small, and converts every future
   failure of this shape from a forensic exercise into a sentence on screen.
   Five is cheap and parallel: there is no access logging on the `$default`
   stage, and the API Lambda logs no route, which is why this took an afternoon
   to find.

10. **The boundary is walked, not unit-tested.** On dev, end to end: today's
    file; a corrupt PDF; a zero-page PDF; a thin scan of 69 to 155 characters a
    page, proving the 31 documents already on that route did not move; an
    ordinary digital PDF, proving the common path is untouched; and a file
    submitted with no type chosen, proving item 7. The last three are the ones
    that get skipped in a hurry, and they are the ones that matter - this hole
    survived three weeks because nobody exercised the boundary.

11. **Item 5 is confirmed, explicitly.** No charge for any refused document,
    including one that reaches OCR and fails there. Confirmed by the owner on
    18 September rather than inferred from the wallet rule, because the wallet
    rule is the thing item 14 amends.

12. **An OCR failure is a loud failure.** A document sent to OCR that comes
    back unreadable is told so, in these words:

        This file could not be read, even with OCR. It can't be used in its
        current state. Please fix it on your side and upload it again.

    Not a status, not a code, and not a row left sitting in `reading` for ever.
    This is the wording item 5's open question asked for.

13. **There is no separate price for OCR.** A scan is OCR'd at filing, inside
    the $0.25 `document_filed` charge. OCR is how some documents are read, not
    a different product, and a person choosing a type cannot be expected to
    know which engine will read it. `meter_price` gains no OCR row.

14. **The charge stands at filing; a failure is compensated, not reversed.**
    The debit happens at filing exactly as it does today - the act is
    deliberate, the price is shown first, and the idempotency key is minted on
    the click. Where OCR then fails, a compensating ledger entry is written.

    **This amends the wallet specification**, which says at §4:

        Ledger is append-only and monotonic. No negative entries, no credits,
        no reversals - unreadable material is blocked before filing (§5.2), so
        there is nothing to refund.

    Recorded as an amendment, not an overwrite: the wallet specification is not
    edited, and everything else in that rule stands. What has changed is its
    stated premise. Item 3 stops blocking unreadable material before filing -
    that is the whole point of it - so "there is nothing to refund" is no
    longer true, and the conclusion cannot outlive the reason given for it.

    The ledger stays append-only. A compensating entry is a new row, not an
    edited one, so a person reading the ledger months later sees the charge and
    the compensation side by side rather than a figure that quietly changed.

    **PROPOSED:** a refund event type in `meter_price`. Note the table is
    `meter_price`, not `price_book`; it holds `document_filed` at 25 and
    `memo_generated` at 100 today, with `tenant_id IS NULL` as the standard
    price.

---

## 3. Open

- **ARQEDIA should do the OCR upgrade itself.** Telling a person to run their
  own file through an OCR process and come back is a stopgap, not the product.
  The promise is that a client file can be uploaded as it stands, and a
  document we cannot read is one we should be able to remediate in place - a
  state adjustment on the upload rather than a refusal with homework. Recorded
  as intended, not scheduled, and not part of the work above.

- **Proposing a type from the first page.** Item 3 makes the person classify a
  scan by hand. Running OCR over page one alone would buy an automatic
  proposal for a fraction of the cost, at the price of spending money before
  anybody has committed to filing. Available later without undoing item 3.

- **What a scan that fails INSIDE OCR is told.** Item 5 settles the money; the
  wording is not written. **Answered by item 12.**

- **Where a compensating entry lands.** A refund under item 14 can go back to
  the bucket the charge was spent from - which may since have expired - or into
  a new credit bucket with an expiry of its own. Returning money to an expired
  bucket returns nothing; creating a new one hands back credit with a life the
  original did not have. Undecided.

- **Whether `PDF_MIN_CHARS_PER_PAGE` survives item 2.** Under one ladder it
  stops being a floor and becomes a band boundary.

  **The thin rule above it was examined**, contrary to what this item first
  said. `ARQEDIA_upload_review_screen_spec_v1.md` §9.3 proposes flagging a page
  that yields under ~200 characters AND sits in a file over ~100 KB a page,
  "which is the signature of an image with a stamp". It was proposed there as
  an open question and adopted: `_is_thin` in the normalizer implements exactly
  that pair - `_THIN_CHARS_PER_PAGE = 200` and `_IMAGE_BYTES_PER_PAGE = 100000`,
  joined by AND so a genuinely short text file is never mistaken for a scan.

  That spec was aimed at the opposite failure. §1 and §5 are about 68
  characters being ACCEPTED as a readable page and classified from; §5 says the
  rule "replaces the current gate, which silently accepted 68 characters as a
  readable page". Nothing in it considers a page yielding nothing at all.

  The 50-character floor is a different number in a different function
  (`extract_pdf`), carries no weight test, and has no such examination behind
  it. It has never been changed since it was written. Whether it is still the
  right band boundary is what remains open.
