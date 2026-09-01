"""Split an uploaded file into the documents it holds.

Five files. Every edit asserts its anchor first, so a file that has moved on
since it was read fails loudly rather than being patched wrongly.
Run from c:\\terraform\\arqedia, after saving segment.py into lambda/normalizer.
"""

import io
import os
import re
import sys


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def once(text, pattern, replacement, label, flags=0):
    found = re.findall(pattern, text, flags)
    if len(found) != 1:
        sys.exit("ANCHOR %s matched %d times, expected 1" % (label, len(found)))
    return re.sub(pattern, lambda _m: replacement, text, count=1, flags=flags)


if not os.path.exists("lambda/normalizer/segment.py"):
    sys.exit("lambda/normalizer/segment.py is missing - save it there first")


# --- lambda/normalizer/app.py ----------------------------------------------

NORM = "lambda/normalizer/app.py"
s = read(NORM)

s = once(
    s,
    r"import classify\nimport config\nimport extractors\n",
    "import config\nimport extractors\nimport segment\n",
    "normalizer imports",
)

HELPERS = '''def _has_thin_page(text, units, byte_size):
    """True when any single page is a scan.

    Distinct from _is_thin, which averages across the file and decides whether
    the DOCUMENT goes to OCR. This asks a narrower question: does the file
    contain a page that cannot be read? A file averaging well can still hold
    three scanned pages in the middle, and those pages are why the file must
    not be split - see the guard in lambda_handler."""
    if not units:
        return False
    heavy = (byte_size / len(units)) > _IMAGE_BYTES_PER_PAGE
    if not heavy:
        return False
    for u in units:
        chars = min(u["char_end"], len(text)) - min(u["char_start"], len(text))
        if chars < _THIN_CHARS_PER_PAGE:
            return True
    return False


def _slice(raw_text, units, part):
    """The part's own text and units.

    Page numbers stay the FILE's own. A value read from the first page of a
    part covering pages 21 to 30 cites page 21, because that is where a reader
    opening the file will find it. Character offsets are re-based to the sliced
    text, because that is what the extractor will be reading."""
    if part["page_from"] is None:
        return units, raw_text

    kept = [u for u in units
            if part["page_from"] <= u["index"] <= part["page_to"]]
    if not kept:
        return units, raw_text

    origin = kept[0]["char_start"]
    text = raw_text[origin:kept[-1]["char_end"]]

    rebased = []
    for u in kept:
        v = dict(u)
        v["char_start"] = u["char_start"] - origin
        v["char_end"] = u["char_end"] - origin
        rebased.append(v)
    return rebased, text


'''

s = once(
    s,
    r"\ndef _now\(\):",
    "\n" + HELPERS + "def _now():",
    "normalizer helper insertion point",
)

# The envelope key has to distinguish parts of one file, since they share an
# s3_key. Keyed on page_from so there is one rule: a range means a part.
s = once(
    s,
    r'''def _write_envelope\(key, envelope\):
    """\.analysed\.json, not \.normalized\.json\. Extraction listens for the latter,
    so writing this does not start extraction - filing does, by renaming the
    envelope once a person has confirmed what the document is\."""
    review_key = key \+ "\.analysed\.json"''',
    '''def envelope_suffix(page_from, part_index):
    """Where a document's envelope lives, relative to the file's own key.

    Parts of one file share an s3_key, so the part number is what tells their
    envelopes apart. A file holding one document keeps the unsuffixed name it
    has always had, so nothing already filed moves."""
    if page_from is None:
        return ".analysed.json"
    return ".p" + str(part_index) + ".analysed.json"


def _write_envelope(key, envelope):
    """.analysed.json, not .normalized.json. Extraction listens for the latter,
    so writing this does not start extraction - filing does, by renaming the
    envelope once a person has confirmed what the document is."""
    review_key = key + envelope_suffix(envelope.get("page_from"),
                                       envelope.get("part_index"))''',
    "normalizer envelope key",
)

# _record_document gains the part columns and the classification token counts.
s = once(
    s,
    r"def _record_document\(envelope\):.*?\n    return result\.get\(\"generatedFields\", \[\{\}\]\)\[0\]\.get\(\"longValue\"\)\n",
    '''def _record_document(envelope):
    result = _sql(
        """
        INSERT INTO document
          (tenant_id, engagement_id, s3_bucket, s3_key, s3_version_id,
           sha256, filename, page_count, part_index, page_from, page_to,
           extraction_method, document_type,
           state, thin_text, char_count, byte_size,
           type_confidence, type_reason,
           classify_tokens_in, classify_tokens_out,
           uploaded_by, config_revision)
        VALUES
          (:tenant_id, :engagement_id, :s3_bucket, :s3_key, :s3_version_id,
           :sha256, :filename, :page_count, :part_index, :page_from, :page_to,
           :extraction_method, :document_type,
           :state, :thin_text, :char_count, :byte_size,
           :type_confidence, :type_reason,
           :classify_tokens_in, :classify_tokens_out,
           :uploaded_by, :config_revision)
        """,
        [
            _p("tenant_id", envelope["tenant_id"]),
            _p("engagement_id", None),
            _p("s3_bucket", envelope["source_bucket"]),
            _p("s3_key", envelope["source_key"]),
            _p("s3_version_id", envelope["source_version_id"]),
            _p("sha256", envelope["sha256_source"]),
            _p("filename", envelope["filename"]),
            _p("page_count", len(envelope["units"])),
            _p("part_index", envelope.get("part_index")),
            _p("page_from", envelope.get("page_from")),
            _p("page_to", envelope.get("page_to")),
            _p("extraction_method", envelope["extraction_method"]),
            _p("document_type", envelope.get("document_type")),
            _p("state", "analysed"),
            _p("thin_text", 1 if envelope.get("thin_text") else 0),
            _p("char_count", len(envelope.get("raw_text") or "")),
            _p("byte_size", envelope.get("byte_size")),
            _p("type_confidence", envelope.get("document_type_confidence")),
            _p("type_reason", envelope.get("document_type_reason")),
            _p("classify_tokens_in", envelope.get("classify_tokens_in")),
            _p("classify_tokens_out", envelope.get("classify_tokens_out")),
            _p("uploaded_by", envelope.get("uploaded_by")),
            _p("config_revision", envelope.get("config_revision") or 1),
        ],
    )
    return result.get("generatedFields", [{}])[0].get("longValue")
''',
    "normalizer _record_document",
    re.S,
)

# Everything from classification to the end of the handler becomes a loop.
TAIL = '''    parts, usage = segment.segment(raw_text, units, registry)

    # A scanned page cannot be sent to OCR on its own: Textract's asynchronous
    # API takes an object, not a page range. Splitting a file that holds one
    # would produce a part nothing can ever read. So a file with any thin page
    # is filed whole and follows today's OCR path untouched, keeping whatever
    # type segmentation proposed for its first part.
    if len(parts) > 1 and _has_thin_page(raw_text, units, len(body)):
        head = parts[0]
        parts = [{"part_index": 1, "page_from": None, "page_to": None,
                  "document_type": head["document_type"],
                  "confidence": head["confidence"],
                  "why": head["why"]}]
        print("[not-split] key=%s reason=thin-page pages=%d" % (
            src_key, len(units)))

    thin = _is_thin(raw_text, len(units), len(body))
    written = []

    for part in parts:
        part_units, part_text = _slice(raw_text, units, part)

        envelope = {
            "tenant_id": tenant_id,
            "document_type": part["document_type"],
            "document_type_proposed": part["document_type"],
            "document_type_confidence": part["confidence"],
            "document_type_reason": part["why"],
            "document_type_confirmed": False,
            "part_index": part["part_index"],
            "page_from": part["page_from"],
            "page_to": part["page_to"],
            "byte_size": len(body),
            "thin_text": thin,
            "state": "analysed",
            "uploaded_by": uploaded_by,
            "engagement": engagement,
            "filename": filename,
            "source_bucket": src_bucket,
            "source_key": src_key,
            "source_version_id": obj.get("VersionId"),
            "sha256_source": sha,
            "extraction_method": method,
            "extracted_at": _now(),
            "config_revision": revision,
            "raw_text": part_text,
            "units": part_units,
            "extracted_values": [],
            "extraction_complete": False,
        }

        # One segmentation call covers the whole file, so its cost is recorded
        # once. Summing this column across a file's parts would count the same
        # call several times, and the point of the column is to price the
        # classification allowance from what it actually costs.
        if part["part_index"] == 1:
            envelope["classify_tokens_in"] = usage.get("input_tokens")
            envelope["classify_tokens_out"] = usage.get("output_tokens")

        document_id = _record_document(envelope)
        envelope["document_id"] = document_id
        review_key = _write_envelope(src_key, envelope)
        written.append({"document_id": document_id,
                        "review_key": review_key,
                        "document_type": part["document_type"],
                        "page_from": part["page_from"],
                        "page_to": part["page_to"],
                        "units": len(part_units)})

        print("[analysed] doc=%s part=%s of %s pages=%s-%s method=%s "
              "type=%s by=%s key=%s" % (
                  document_id, part["part_index"], len(parts),
                  part["page_from"] or 1, part["page_to"] or len(units),
                  method, part["document_type"], uploaded_by, src_key))

    return {
        "status": "ok",
        "tenant_id": tenant_id,
        "extraction_method": method,
        "pages": len(units),
        "documents": written,
    }
'''

s = once(
    s,
    r"    document_type, confidence, why = classify\.classify\(raw_text, registry\).*$",
    TAIL,
    "normalizer handler tail",
    re.S,
)

write(NORM, s)
print("patched " + NORM)


# --- lambda/extraction/app.py ----------------------------------------------

EXT = "lambda/extraction/app.py"
s = read(EXT)

s = once(
    s,
    r"    units = envelope\[\"units\"\]\n    word = _unit_word\(units\)\n    count = len\(units\)\n",
    '''    units = envelope["units"]
    word = _unit_word(units)
    count = len(units)

    # A part of a larger file keeps that file's own page numbers, so what the
    # model is told must come from the units rather than from how many there
    # are. Telling it "1 to 10" while the markers below read PAGE 21 is how a
    # citation ends up pointing at a page the value was never on.
    first_index = units[0]["index"] if units else 1
    last_index = units[-1]["index"] if units else 1
''',
    "extraction unit numbering",
)

s = once(
    s,
    r'''        "The document has " \+ str\(count\) \+ " " \+ word \+ "s, numbered 1 to "
        \+ str\(count\) \+ ", marked in the text below\.\\n"''',
    '''        "The document has " + str(count) + " " + word + "s, numbered "
        + str(first_index) + " to " + str(last_index)
        + ", marked in the text below.\\n"''',
    "extraction numbering sentence",
)

write(EXT, s)
print("patched " + EXT)


# --- lambda/api/app.py ------------------------------------------------------

API = "lambda/api/app.py"
s = read(API)

s = once(
    s,
    r"  DELETE /documents/\{document_id\}         discard one not yet filed\n",
    "  DELETE /documents/{document_id}         discard one not yet filed\n"
    "\n"
    "One uploaded file may hold several documents. Each is a row of its own\n"
    "sharing the file's s3_key and carrying its page range, so a citation still\n"
    "names the file a reader was given. See db/migrations/011_document_parts.sql.\n",
    "api header note",
)

SUFFIX_FN = '''def _envelope_suffix(page_from, part_index):
    """Where a document's envelope lives, relative to the file's own key.

    Parts of one file share an s3_key, so the part number is what tells their
    envelopes apart. A file holding one document keeps the unsuffixed name it
    has always had. Mirrors envelope_suffix in the normalizer, which writes
    them - the two must not drift."""
    if page_from is None:
        return ".analysed.json"
    return ".p" + str(part_index) + ".analysed.json"


'''

s = once(
    s,
    r"\ndef _start_ocr\(registry, tenant_id, document_id, s3_key, document_type\):",
    "\n" + SUFFIX_FN
    + "def _start_ocr(registry, tenant_id, document_id, s3_key, document_type):",
    "api suffix helper insertion point",
)

s = once(
    s,
    r'''        row = _sql\("SELECT s3_key, thin_text FROM document "
                   "WHERE tenant_id = :t AND document_id = :d",
                   \[_p\("t", tenant_id\), _p\("d", document_id\)\]\)
        records = row\.get\("records", \[\]\)
        if not records:
            continue
        s3_key = _col\(records\[0\], 0\)
        thin = bool\(_col\(records\[0\], 1\)\)''',
    '''        row = _sql("SELECT s3_key, thin_text, page_from, part_index "
                   "FROM document "
                   "WHERE tenant_id = :t AND document_id = :d",
                   [_p("t", tenant_id), _p("d", document_id)])
        records = row.get("records", [])
        if not records:
            continue
        s3_key = _col(records[0], 0)
        thin = bool(_col(records[0], 1))
        suffix = _envelope_suffix(_col(records[0], 2), _col(records[0], 3))''',
    "api filing row read",
)

s = once(
    s,
    r'''        body = _s3\.get_object\(Bucket=REVIEW_BUCKET,
                              Key=s3_key \+ "\.analysed\.json"\)\["Body"\]\.read\(\)''',
    '''        body = _s3.get_object(Bucket=REVIEW_BUCKET,
                              Key=s3_key + suffix)["Body"].read()''',
    "api filing envelope read",
)

s = once(
    s,
    r'''            Bucket=REVIEW_BUCKET, Key=s3_key \+ "\.normalized\.json",''',
    '''            Bucket=REVIEW_BUCKET,
            Key=s3_key + suffix.replace(".analysed.", ".normalized."),''',
    "api filing envelope write",
)

# Removing one part must not delete the file its siblings are read from.
s = once(
    s,
    r'''    row = _sql\("SELECT s3_key, state FROM document "
               "WHERE tenant_id = :t AND document_id = :d",
               \[_p\("t", tenant_id\), _p\("d", document_id\)\]\)
    records = row\.get\("records", \[\]\)
    if not records:
        return None

    s3_key = _col\(records\[0\], 0\)
    state = _col\(records\[0\], 1\)
    if state != "analysed":
        return \{"refused": state\}''',
    '''    row = _sql("SELECT s3_key, state, page_from, part_index FROM document "
               "WHERE tenant_id = :t AND document_id = :d",
               [_p("t", tenant_id), _p("d", document_id)])
    records = row.get("records", [])
    if not records:
        return None

    s3_key = _col(records[0], 0)
    state = _col(records[0], 1)
    page_from = _col(records[0], 2)
    suffix = _envelope_suffix(page_from, _col(records[0], 3))
    if state != "analysed":
        return {"refused": state}

    # One uploaded file can hold several documents, all reading from the same
    # object. Removing one part must not take the file its siblings are read
    # from, so the upload goes only when the last of them does.
    siblings = _sql(
        "SELECT COUNT(*) FROM document "
        "WHERE tenant_id = :t AND s3_key = :k AND document_id <> :d",
        [_p("t", tenant_id), _p("k", s3_key), _p("d", document_id)])
    remaining = _col(siblings.get("records", [[{}]])[0], 0) or 0''',
    "api remove read",
)

s = once(
    s,
    r'''    _s3\.delete_object\(Bucket=DOCS_BUCKET, Key=s3_key\)
    _s3\.delete_object\(Bucket=REVIEW_BUCKET, Key=s3_key \+ "\.analysed\.json"\)''',
    '''    _s3.delete_object(Bucket=REVIEW_BUCKET, Key=s3_key + suffix)
    if not remaining:
        _s3.delete_object(Bucket=DOCS_BUCKET, Key=s3_key)''',
    "api remove deletes",
)

# The review screen needs to say which pages a card covers.
s = once(
    s,
    r'''        SELECT document_id, filename, document_type, page_count,
               thin_text, char_count, type_confidence, type_reason, state,
               uploaded_by''',
    '''        SELECT document_id, filename, document_type, page_count,
               thin_text, char_count, type_confidence, type_reason, state,
               uploaded_by, part_index, page_from, page_to''',
    "api pending select",
)

s = once(
    s,
    r'''         "state": _col\(r, 8\),
         "uploaded_by": _col\(r, 9\)\}''',
    '''         "state": _col(r, 8),
         "uploaded_by": _col(r, 9),
         "part_index": _col(r, 10),
         "page_from": _col(r, 11),
         "page_to": _col(r, 12)}''',
    "api pending dict",
)

write(API, s)
print("patched " + API)


# --- ui/src/api.ts ----------------------------------------------------------

TS = "ui/src/api.ts"
s = read(TS)

s = once(
    s,
    r"  state: string;\n  uploaded_by: string \| null;\n\};",
    "  state: string;\n"
    "  uploaded_by: string | null;\n"
    "  // A file may hold several documents. page_from is null when it holds one.\n"
    "  part_index: number | null;\n"
    "  page_from: number | null;\n"
    "  page_to: number | null;\n"
    "};",
    "api.ts Pending type",
)

write(TS, s)
print("patched " + TS)


# --- ui/src/Review.tsx ------------------------------------------------------

RV = "ui/src/Review.tsx"
s = read(RV)

s = once(
    s,
    r'<span className="muted">\{p\.pages \?\? "\?"\} pages</span>',
    '''<span className="muted">
                    {p.page_from
                      ? `pages ${p.page_from}\\u2013${p.page_to}`
                      : `${p.pages ?? "?"} pages`}
                  </span>''',
    "Review.tsx page range",
)

write(RV, s)
print("patched " + RV)
print("all five files patched")
