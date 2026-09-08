# OCR-01 · A scanned part of a split file never leaves "reading"

| | |
|---|---|
| Status | Not built. Cause identified, not proven |
| Priority | **High.** It strands a document in a state the screen cannot clear |
| Type | Collector, and the IAM policy behind its error message |

---

## What happens

A PDF that the segmenter splits into parts, where one part is a scan, leaves
that part at `state = 'reading'` for ever. The screen shows it under **Ready to
file**, and File, Remove and Generate all refuse — correctly, because the
document has not finished being read. There is no way out from the interface.

Seen 7 September on tenant 2, engagement Knightsbridge-1. Document 568,
`Business-projections-Waste-products_M8-PL-projections323.pdf`, part 3 of 3,
pages 5-5, classified `audited-statements`, marked "will be read by OCR".

Cleared by hand:

    UPDATE document SET state = 'filed', active = 0 WHERE document_id = 568

---

## What the evidence shows

**The collector fails on every attempt and retries.**

    AccessDenied: ... not authorized to perform: s3:ListBucket on resource:
    "arn:aws:s3:::arqedia-dev-review-667523685221"

raised from `_s3.get_object` at `lambda/collector/app.py:123`.

**The key it asks for does not match the key that exists.** The collector
builds `document["s3_key"] + ".analysed.json"`. What is in the bucket is:

    ...M8-PL-projections323.pdf.p3.analysed.json

The part suffix `.p3` is in the stored key and not in what the collector asks
for — so either `s3_key` on the row omits the part, or the collector needs to
add it. **Which of the two has not been confirmed**, and the fix depends on it.

**The error names the wrong problem.** The collector holds `GetObject` on the
review bucket and not `ListBucket`. Without `ListBucket`, S3 answers 403 for an
object that is not there rather than 404 — so "no such key" arrives as "not
authorized", and an hour went into the wrong question.

---

## What to do

1. Confirm what `document.s3_key` holds for a split part, against what the
   normalizer writes. One is wrong; do not guess which.
2. Fix whichever it is, so the collector reads the envelope that exists.
3. **Give the collector `s3:ListBucket` on the review bucket regardless.** It
   changes no capability - the objects are already readable - and it makes a
   missing object report as missing.
4. Give a document stuck in `reading` a way out of the interface. Whatever the
   cause, a person should not need a SQL statement to clear their own upload.

---

## Why this is high

It is not the one document. It is that the interface has a state it cannot
leave: the engagement looks broken, nothing can be filed or generated, and the
only remedy is a hand-written update. A client cannot do that.

Item 3 is worth doing on its own even before the cause is settled: the next
occurrence will otherwise present as a permissions failure again.
