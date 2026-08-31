"""
textract.py - optical character recognition for scanned documents.

A certified scan carries only its stamp as text. The document underneath is an
image, so it must be read by OCR before anything can be extracted from it.

Three things govern how a document is read, and all three are properties of the
DOCUMENT TYPE rather than of the uploaded file:

  read_mode      text | forms | expense - which Textract API to use
  always_ocr     ignore any embedded text layer and OCR regardless
  page_range     which pages of the file this document occupies

The page range matters even though splitting is not yet built. One uploaded
file will eventually hold several documents - a certificate on page 1, articles
on pages 2-14, a resolution on 15-20 - each with its own type and therefore its
own read mode. Recording the job against the document rather than the file
means splitting needs no rework here.

Jobs are asynchronous. A twelve-page scan takes minutes; nothing waits. The job
starts, a notification arrives on completion, and the collector picks up the
result.
"""

import boto3

_textract = boto3.client("textract")

TEXT = "text"        # DetectDocumentText - cheapest, prose
FORMS = "forms"      # AnalyzeDocument FeatureTypes [TABLES, FORMS]
EXPENSE = "expense"  # AnalyzeExpense - invoices

# How each document type should be read. Forms-and-tables for anything with a
# labelled structure - questionnaires, registry filings, statements, identity
# documents. Plain text for narrative.
READ_MODE = {
    "cdd-questionnaire": FORMS,
    "beneficial-ownership": FORMS,
    "id-verification": FORMS,
    "regulatory-filings": FORMS,
    "cap-table": FORMS,
    "audited-statements": FORMS,
    "interim-statements": FORMS,
    "tax-returns": FORMS,
    "bank-statements": FORMS,
    "aging-reports": FORMS,
    "insurance-coverage": FORMS,
    "licenses-certificates": FORMS,
}

# Types whose embedded text layer is not to be trusted even when present. A
# garbled text layer corrupts numeric content worse than OCR does, and these
# are the types where a wrong number matters most.
ALWAYS_OCR = frozenset({
    "audited-statements",
    "interim-statements",
    "bank-statements",
    "aging-reports",
})


def read_mode_for(document_type):
    """Which Textract API reads this type. Unlisted types get plain text,
    which is the cheapest and never wrong, only sometimes incomplete."""
    return READ_MODE.get(document_type, TEXT)


def always_ocr(document_type):
    return document_type in ALWAYS_OCR


def start(s3_bucket, s3_key, document_type, topic_arn, role_arn,
          page_start=None, page_end=None, read_mode=None):
    """Start a job. Returns (job_id, mode). Does not wait.

    read_mode comes from the tenant's configuration, where it is a property of
    the document type - the thing a person confirms. The table below is the
    fallback for a type the configuration does not describe.

    page_start and page_end are for a split file: the document occupies only
    part of it. Absent, the whole file is read."""
    mode = read_mode or read_mode_for(document_type)

    document = {"S3Object": {"Bucket": s3_bucket, "Name": s3_key}}
    notify = {"SNSTopicArn": topic_arn, "RoleArn": role_arn}

    kwargs = {"DocumentLocation": document, "NotificationChannel": notify}
    if page_start and page_end:
        kwargs["DocumentLocation"] = {
            "S3Object": {"Bucket": s3_bucket, "Name": s3_key},
        }

    if mode == EXPENSE:
        job_id = _textract.start_expense_analysis(**kwargs)["JobId"]
    elif mode == FORMS:
        job_id = _textract.start_document_analysis(
            FeatureTypes=["TABLES", "FORMS"], **kwargs)["JobId"]
    else:
        job_id = _textract.start_document_text_detection(**kwargs)["JobId"]

    return job_id, mode


def _getter(mode):
    if mode == EXPENSE:
        return _textract.get_expense_analysis
    if mode == FORMS:
        return _textract.get_document_analysis
    return _textract.get_document_text_detection


def fetch(job_id, mode, page_start=None, page_end=None):
    """Collect a completed job. Returns (text, units, tables).

    The job has already succeeded - the notification said so. Results are
    paginated; all pages are collected before assembly.

    page_start and page_end trim the result to one document within a split
    file. Textract reads the whole file; the trim happens here."""
    getter = _getter(mode)

    response = getter(JobId=job_id)
    blocks = list(response.get("Blocks", []))
    token = response.get("NextToken")
    while token:
        response = getter(JobId=job_id, NextToken=token)
        blocks.extend(response.get("Blocks", []))
        token = response.get("NextToken")

    text, units = _blocks_to_pages(blocks, page_start, page_end)
    tables = _blocks_to_tables(blocks, page_start, page_end)
    return text, units, tables


def _in_range(page, page_start, page_end):
    if page_start and page < page_start:
        return False
    if page_end and page > page_end:
        return False
    return True


def _blocks_to_pages(blocks, page_start=None, page_end=None):
    """Lines grouped by page, then joined - producing the same text and unit
    shape as the digital-text path, so nothing downstream knows the
    difference."""
    by_page = {}
    for b in blocks:
        if b.get("BlockType") != "LINE":
            continue
        page = b.get("Page", 1)
        if not _in_range(page, page_start, page_end):
            continue
        by_page.setdefault(page, []).append(b.get("Text", ""))

    if not by_page:
        return "", [{"kind": "page", "index": 1, "char_start": 0,
                     "char_end": 0, "label": None}]

    units, cursor, parts = [], 0, []
    # Renumber from 1 so a split document's pages read 1..n, not 15..20.
    for ordinal, page in enumerate(sorted(by_page), start=1):
        body = "\n".join(by_page[page])
        start = cursor
        parts.append(body)
        cursor += len(body)
        units.append({
            "kind": "page",
            "index": ordinal,
            "char_start": start,
            "char_end": cursor,
            "label": None,
        })
        cursor += 1  # the newline used to join

    return "\n".join(parts), units


def _cell_text(cell, by_id):
    """A cell's text is its child words, plus any ticked selection box."""
    parts = []
    for rel in cell.get("Relationships", []) or []:
        if rel.get("Type") != "CHILD":
            continue
        for child_id in rel.get("Ids", []):
            child = by_id.get(child_id)
            if not child:
                continue
            if child.get("BlockType") == "WORD":
                parts.append(child.get("Text", ""))
            elif child.get("BlockType") == "SELECTION_ELEMENT":
                if child.get("SelectionStatus") == "SELECTED":
                    parts.append("[X]")
    return " ".join(parts).strip()


def _blocks_to_tables(blocks, page_start=None, page_end=None):
    """Resolve table blocks into rows of text, so nothing downstream needs to
    walk the block graph. Empty for the plain-text and expense modes."""
    by_id = {b.get("Id"): b for b in blocks}
    tables = []

    for b in blocks:
        if b.get("BlockType") != "TABLE":
            continue
        page = b.get("Page", 1)
        if not _in_range(page, page_start, page_end):
            continue

        grid = {}
        for rel in b.get("Relationships", []) or []:
            if rel.get("Type") != "CHILD":
                continue
            for cell_id in rel.get("Ids", []):
                cell = by_id.get(cell_id)
                if not cell or cell.get("BlockType") != "CELL":
                    continue
                row = cell.get("RowIndex", 1)
                col = cell.get("ColumnIndex", 1)
                grid.setdefault(row, {})[col] = _cell_text(cell, by_id)

        if not grid:
            continue

        width = max(max(cols) for cols in grid.values())
        rows = [[grid[r].get(c, "") for c in range(1, width + 1)]
                for r in sorted(grid)]

        tables.append({
            "page": page,
            "n_rows": len(rows),
            "n_cols": width,
            "headers": rows[0] if rows else [],
            "rows": rows[1:] if len(rows) > 1 else [],
        })

    return tables


def tables_as_text(tables):
    """Tables rendered for the extraction prompt. A form's content is in its
    tables, so without this a forms read produces labels and no values."""
    if not tables:
        return ""
    out = []
    for i, t in enumerate(tables, start=1):
        out.append("\n--- TABLE {} (page {}) ---".format(i, t["page"]))
        if t["headers"]:
            out.append(" | ".join(t["headers"]))
        for row in t["rows"]:
            out.append(" | ".join(row))
    return "\n".join(out)
