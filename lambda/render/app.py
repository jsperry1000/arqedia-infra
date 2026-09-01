"""
app.py - render a memorandum as a branded PDF.

Takes the consolidated markdown composition produces and lays it out. The
markdown remains the intermediate; the PDF is what a customer receives.

Branding is gated by plan:
  base        platform colours and mark, footer fixed
  business    tenant logo and three colours, footer fixed
  enterprise  as business, and the footer may be removed

The footer reads "Prepared with ARQEDIA - quod erat demonstrandum", the Latin
in italics, linked to the site. It is drawn by the page template rather than
added to the content, so it cannot be pushed off by a long section.

Invoke with:
    {"tenant_id": 1, "memo_id": 11}
"""

import io
import os
import re
import time

import boto3
from botocore.exceptions import ClientError

from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

import style

_s3 = boto3.client("s3")
_rds = boto3.client("rds-data")

CURATED_BUCKET = os.environ["CURATED_BUCKET"]
BRAND_BUCKET = os.environ["BRAND_BUCKET"]
CLUSTER_ARN = os.environ["CLUSTER_ARN"]
SECRET_ARN = os.environ["SECRET_ARN"]
DATABASE = os.environ["DATABASE"]


# A short memo in the shape of a real one: masthead, status bar, a section
# heading, prose carrying citations, a table and a gap callout. Enough to show
# every place a colour lands, and nothing more - a preview that takes a minute
# to render is not a preview.
PREVIEW_MARKDOWN = """
| | |
|---|---|
| **Subject** | Example Counterparty Limited |
| **Engagement** | Preview |
| **Generated** | Sample |
| **Documents reviewed** | 4 |

> **Coverage.** This memorandum was generated without the following material,
> and any section depending on it is incomplete: Financial Position.

## I. Entity Identification

Example Counterparty Limited is a private company limited by shares,
incorporated on 4 March 2019 under registration number 128456, with its
registered office at 44 Esplanade, St Helier.
*certificate-of-incorporation.pdf, page 1*

**Directors and Officers.** The sources identify the following individuals in
governance roles:

| Role | Name | Holding |
|---|---|---|
| **Director** | Maria Santos | 60 per cent |
| **Secretary** | John Reilly | 40 per cent |

*Sources: certificate-of-incorporation.pdf, page 1; shareholder-register.pdf, page 2.*

## II. Ownership and Control

> **Gap.** No beneficial ownership declaration has been provided, so ultimate
> control cannot be confirmed from the registered position alone.

This is a preview of how your memoranda will look. It is not a real
memorandum and is not recorded against any engagement.
"""


def _sql(statement, params=None):
    for _ in range(12):
        try:
            return _rds.execute_statement(
                resourceArn=CLUSTER_ARN, secretArn=SECRET_ARN,
                database=DATABASE, sql=statement, parameters=params or [])
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in (
                "DatabaseResumingException", "ThrottlingException"
            ):
                time.sleep(5)
                continue
            raise
    raise RuntimeError("cluster did not resume")


def _p(name, value):
    if value is None:
        return {"name": name, "value": {"isNull": True}}
    if isinstance(value, int):
        return {"name": name, "value": {"longValue": value}}
    return {"name": name, "value": {"stringValue": str(value)}}


def _col(record, i):
    cell = record[i]
    for kind in ("stringValue", "longValue", "doubleValue", "booleanValue"):
        if kind in cell:
            return cell[kind]
    return None


# --- markdown -> flowables -------------------------------------------------

_BOLD = re.compile(r"\*\*(.+?)\*\*")
# Asterisk emphasis, and underscore emphasis ONLY when the underscores are
# bounded by whitespace or a line edge. A filename like
# CE_AML_Policy_v1_signed_with_annex.pdf is not emphasis, and treating it as
# such deleted every underscore - producing a citation to a file that does not
# exist.
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_ITALIC_U = re.compile(r"(?:(?<=\s)|(?<=^))_([^_\n]+?)_(?=\s|$|[.,;:)])")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


_CITE_COLOUR = "#278ACA"

# Citations numbered in the order they appear, collected at the end.
#
# A reader of a finished memorandum is not checking references - that is what
# they engaged the person who signed it to do. A filename in every second
# sentence is noise to them. A superscript is not, and the full citation is
# there at the end for the reader who does want it.
#
# The same document cited twice takes the same number, or a memo citing one
# file thirty times ends with thirty identical entries.
#
# Module-level for the same reason as the colour: _inline is called from a
# dozen places and threading a register through all of them would obscure
# what it does. Reset at the start of every render.
_CITATIONS = []
_CITATION_INDEX = {}


def _reference_section(styles):
    """Every citation, numbered, at the end.

    Built after the body, because the numbers are assigned as the body is
    rendered. Empty when a memo carries no citations, which would itself be
    worth noticing."""
    if not _CITATIONS:
        return []

    out = [Spacer(1, 18),
           Paragraph("References", styles["section"])]

    for number, text in enumerate(_CITATIONS, start=1):
        out.append(Paragraph(
            '<super><font size="6.5">%d</font></super>  [%s]' % (number, text),
            styles["citation"]))

    return out


# What composition calls a citation. It masks citations before consolidation
# using a regex requiring one of these extensions, so an italic run without one
# was never a citation on the way in and must not become one here.
_CITATION_FILE = re.compile(r"\.(?:pdf|docx|xlsx|txt|json|xml)\b", re.I)


def _reset_citations():
    del _CITATIONS[:]
    _CITATION_INDEX.clear()


def _cite_number(text):
    """The number for one citation, assigning a new one if unseen."""
    key = " ".join(text.split())
    if key not in _CITATION_INDEX:
        _CITATIONS.append(key)
        _CITATION_INDEX[key] = len(_CITATIONS)
    return _CITATION_INDEX[key]


def _set_cite_colour(palette):
    """Inline citations take the tenant's mid colour. Module-level because
    _inline is called from a dozen places and threading a palette through all
    of them would obscure what it does."""
    global _CITE_COLOUR
    _CITE_COLOUR = "#%02X%02X%02X" % (
        int(palette["mid"].red * 255),
        int(palette["mid"].green * 255),
        int(palette["mid"].blue * 255))


def _inline(text):
    """Markdown emphasis to the small markup Paragraph understands. Escaped
    first, so a stray ampersand in a company name cannot break the layout."""
    text = (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))
    text = _BOLD.sub(r"<b>\1</b>", text)
    # Italic in a memo is a citation, not emphasis. In the PDF it becomes a
    # superscript number and the full reference is collected at the end. The
    # browser keeps the bracketed form, where a reader IS checking sources
    # while reviewing and editing - different readers, different surfaces.
    #
    # A "Sources:" line is dropped entirely: every citation it lists is
    # already numbered inline and collected at the end.
    def numbered(m):
        body = m.group(1).strip()
        if re.match(r"^sources?\s*:", body, re.I):
            return ""
        # Emphasis, not a citation. An extracted value carrying its own
        # italics - a French term from a trade register, a document title -
        # arrives here looking exactly like a citation, and numbering it takes
        # the word out of the sentence and adds a reference to something that
        # is not a document.
        if not _CITATION_FILE.search(body):
            return "<i>" + body + "</i>"
        return '<super><font size="6.5" color="%s">%d</font></super>' % (
            _CITE_COLOUR, _cite_number(body))

    text = _ITALIC.sub(numbered, text)
    text = _ITALIC_U.sub(numbered, text)

    # Take back the space left where a citation stood before a stop.
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\s+([.,;:)])", r"\1", text)
    text = text.strip()
    text = _LINK.sub(r"\1", text)
    return text


def _split_row(line):
    return [c.strip().replace("\\|", "|")
            for c in line.strip().strip("|").split("|")]


def _is_divider(line):
    return bool(re.match(r"^\s*\|?[\s:-]+\|[\s:|-]*$", line))


def _status_bar(rows, styles, palette):
    """The front matter, rendered as the house status bar: small grey labels
    over emphasised values, in boxed columns across the page."""
    pairs = [(r[0], r[1]) for r in rows if len(r) >= 2 and r[0].strip()]
    if not pairs:
        return None

    # Four across reads well on Letter; more than that and the values wrap.
    pairs = pairs[:4]
    labels = [Paragraph(_inline(a).upper(), styles["label"]) for a, _ in pairs]
    values = [Paragraph(_inline(b), styles["value"]) for _, b in pairs]

    width = style.CONTENT_WIDTH / len(pairs)
    table = Table([labels, values], colWidths=[width] * len(pairs))
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, style.LINE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, style.LINE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.5, style.LINE),
    ]))
    return table


_SOURCE_HEAD = re.compile(r"^\s*sources?(\(s\))?\s*$", re.I)


def _lift_sources(header, rows):
    """A citation column repeating the same filenames on every row crowds out
    the content it is meant to support. Lift it out, and return the distinct
    citations for a single line beneath the table."""
    if not header:
        return header, rows, []

    index = None
    for c, h in enumerate(header):
        if _SOURCE_HEAD.match(re.sub(r"[*_`]", "", h or "")):
            index = c
            break
    if index is None:
        return header, rows, []

    seen, citations = set(), []
    for r in rows:
        if index >= len(r):
            continue
        for part in re.split(r";|\n", r[index]):
            part = part.strip().strip(".")
            if part and part not in seen:
                seen.add(part)
                citations.append(part)

    header = [h for c, h in enumerate(header) if c != index]
    rows = [[v for c, v in enumerate(r) if c != index] for r in rows]
    return header, rows, citations


def _table(header, rows, styles, palette):
    """A markdown table. Column widths reserve the longest word in each column
    before sharing the remainder, so a narrow label column beside long prose
    does not split a one-word label across two lines."""
    width = max([len(header)] + [len(r) for r in rows]) if (header or rows) else 0
    if width == 0:
        return None

    def pad(r):
        return (r + [""] * width)[:width]

    header = pad(header) if header else []
    rows = [pad(r) for r in rows]

    def visible(text):
        """Text as it will render. Measuring raw markdown counts the emphasis
        markers, which starved narrow columns."""
        return re.sub(r"[*_`]", "", text or "")

    def breakable(text):
        """A slash is a natural break the layout engine does not treat as one,
        so "Country Director / General Manager" measures as three long words
        and claims more width than it needs."""
        return re.sub(r"([/\-])", r"\1 ", text or "")

    # Two measures per column: the longest single word, which is the width
    # below which that word must break mid-way, and the total text, which is
    # how much room the column deserves. Reserve the first, share the rest
    # proportionally to the second. Without the reservation a column of short
    # labels beside a column of long prose gets so little room that a word
    # like "Secretary" splits across two lines.
    PADDING = 14.0
    mins, shares = [], []
    for c in range(width):
        cells = ([visible(header[c])] if header else []) \
            + [visible(r[c]) for r in rows]
        longest_word = 0.0
        for cell in cells:
            for word in breakable(cell or " ").split():
                longest_word = max(
                    longest_word, stringWidth(word, "Helvetica-Bold", 8.5))
        mins.append(longest_word + PADDING)
        shares.append(max(sum(len(x) for x in cells), 1))

    spare = style.CONTENT_WIDTH - sum(mins)
    if spare <= 0:
        total = float(sum(mins)) or 1.0
        widths = [style.CONTENT_WIDTH * (m / total) for m in mins]
    else:
        total = float(sum(shares)) or 1.0
        widths = [mins[c] + spare * (shares[c] / total) for c in range(width)]

    data = []
    if header:
        data.append([Paragraph(_inline(c).upper(), styles["cellhead"])
                     for c in header])
    for r in rows:
        data.append([Paragraph(_inline(c), styles["cell"]) for c in r])

    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, style.LINE),
    ]
    if header:
        commands.append(("BACKGROUND", (0, 0), (-1, 0), palette["deep"]))
    table.setStyle(TableStyle(commands))
    return table


def _callout(text, styles, palette):
    """A gap note. Highlight edge, pale fill, so absence is visible at a
    glance rather than read for."""
    table = Table([[Paragraph(_inline(text), styles["callout"])]],
                  colWidths=[style.CONTENT_WIDTH])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), style.GAP_FILL),
        ("LINEBEFORE", (0, 0), (0, -1), 3, palette["highlight"]),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
    ]))
    return table


_DIVIDER = re.compile(r"\|(?:\s*:?-{2,}:?\s*\|)+")


def _unwrap_tables(markdown):
    """Split a table emitted on one line back into rows.

    The consolidation sometimes returns a whole table as a single line -
    "| Item | Status | |---|---| | ... |" - which renders as a run of pipes
    rather than a table. Telling it not to did not hold, so it is repaired
    here instead: the divider is an unambiguous anchor, since "|---|---|"
    cannot occur in prose, and its column count gives the width of a row.

    Deterministic, and it repairs memos already written rather than only the
    next one."""
    out = []
    for line in markdown.split("\n"):
        stripped = line.strip()
        m = _DIVIDER.search(stripped)

        # A line is only broken if the divider has content after it.
        if not m or not stripped.startswith("|") or not stripped[m.end():].strip():
            out.append(line)
            continue

        width = m.group(0).count("|") - 1
        if width < 1:
            out.append(line)
            continue

        out.append(stripped[:m.start()].strip())
        out.append(m.group(0))

        cells = [c for c in re.split(r"\s*\|\s*", stripped[m.end():].strip())
                 if c != ""]
        for i in range(0, len(cells), width):
            row = cells[i:i + width]
            if row:
                out.append("| " + " | ".join(row) + " |")

    return "\n".join(out)


def _take_trailing_heading(flow):
    """Remove and return a heading sitting at the end of the flow.

    A heading and the thing it introduces belong on the same page. Only a
    heading is taken - a paragraph of prose above a table is not orphaned by a
    break, and binding it would push whole paragraphs onto the next page for
    no gain."""
    if not flow:
        return None

    # A spacer between the heading and the table is layout, not content.
    trailing = []
    while flow and isinstance(flow[-1], Spacer):
        trailing.insert(0, flow.pop())

    if flow and isinstance(flow[-1], Paragraph) and \
            getattr(flow[-1].style, "name", "") in ("section", "subsection"):
        heading = flow.pop()
        flow.extend(trailing)
        return heading

    flow.extend(trailing)
    return None


def to_flowables(markdown, styles, palette):
    """Markdown to flowables. Handles the shapes the consolidation produces:
    headings, paragraphs, tables, blockquote gaps, bullets."""
    flow = []
    lines = _unwrap_tables(markdown).split("\n")
    i = 0
    front_matter_done = False

    while i < len(lines):
        stripped = lines[i].strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) \
                and _is_divider(lines[i + 1]):
            header = _split_row(stripped)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1

            # The first table with an empty header is the front matter; it
            # becomes the status bar rather than an ordinary table.
            if not front_matter_done and not any(h.strip() for h in header):
                front_matter_done = True
                bar = _status_bar(rows, styles, palette)
                if bar is not None:
                    flow.append(bar)
                    flow.append(Spacer(1, 12))
                continue

            header, rows, citations = _lift_sources(
                [] if not any(header) else header, rows)
            table = _table(header, rows, styles, palette)
            if table is not None:
                # A heading immediately above a table moves with it. Left
                # alone, "Corporate Identity and Constitution" sat at the foot
                # of one page with its table on the next, which reads as a
                # fault rather than a break.
                lead = _take_trailing_heading(flow)
                if lead is not None:
                    flow.append(KeepTogether([lead, table]))
                else:
                    flow.append(table)
                if citations:
                    # Numbered, like every other citation. A list of filenames
                    # under a table is the thing this change removes.
                    marks = ", ".join(
                        str(_cite_number(c)) for c in citations)
                    flow.append(Spacer(1, 3))
                    flow.append(Paragraph("Sources " + marks,
                                          styles["citation"]))
                flow.append(Spacer(1, 9))
            continue

        if stripped.startswith(">"):
            body = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                body.append(lines[i].strip().lstrip(">").strip())
                i += 1
            text = " ".join(b for b in body if b)
            if text:
                callout = _callout(text, styles, palette)
                lead = _take_trailing_heading(flow)
                if lead is not None:
                    flow.append(KeepTogether([lead, callout]))
                else:
                    flow.append(callout)
                flow.append(Spacer(1, 9))
            continue

        # The title is drawn in the masthead, so h1 is dropped rather than
        # repeated in the body.
        if stripped.startswith("### "):
            flow.append(Paragraph(_inline(stripped[4:]), styles["subsection"]))
            i += 1
            continue
        if stripped.startswith("## "):
            flow.append(Paragraph(_inline(stripped[3:]), styles["section"]))
            i += 1
            continue
        if stripped.startswith("# ") or stripped.startswith("---"):
            i += 1
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            flow.append(Paragraph(_inline(stripped[2:]), styles["bullet"],
                                  bulletText="\u2022"))
            i += 1
            continue

        # A markdown paragraph runs until a blank line. Treating each line as
        # its own paragraph broke any wrapped text into separate lines with a
        # paragraph gap between them - invisible while the model emitted one
        # long line per paragraph, and wrong the moment it did not.
        block = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                break
            if (nxt.startswith(("#", ">", "- ", "* ", "|", "---"))):
                break
            block.append(nxt)
            i += 1
        paragraph = " ".join(block)

        if paragraph.startswith("_") and paragraph.endswith("_") \
                and len(paragraph) > 2:
            flow.append(Paragraph(_inline(paragraph), styles["citation"]))
        else:
            flow.append(Paragraph(_inline(paragraph), styles["body"]))

    return flow


# --- page furniture --------------------------------------------------------

class NumberedCanvas(pdfcanvas.Canvas):
    """Two-pass so the footer can say "Page 2 of 11". The page count is not
    known until the document is finished, so pages are held and written at
    the end with the total substituted in."""

    def __init__(self, *args, **kwargs):
        self._footer_fn = kwargs.pop("footer_fn", None)
        pdfcanvas.Canvas.__init__(self, *args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        # Restoring a page's saved state also restores the annotation counter,
        # which names each annotation. The footer link on page two would then
        # take page one's name and the document would refuse to build. The
        # counter is kept monotonic across the replay instead.
        annotations = getattr(self, "_annotationCount", 0)
        for state in self._saved:
            self.__dict__.update(state)
            self._annotationCount = annotations
            if self._footer_fn:
                self._footer_fn(self, total)
            annotations = self._annotationCount
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)


class MemoDoc(BaseDocTemplate):
    """A first page carrying the full masthead, and a running page with a slim
    band. The footer is drawn by the template, not the content."""

    def __init__(self, buffer, palette, subject, kicker, detail, runner,
                 logo_bytes, show_footer, **kwargs):
        BaseDocTemplate.__init__(self, buffer, pagesize=style.PAGESIZE,
                                 leftMargin=style.MARGIN,
                                 rightMargin=style.MARGIN,
                                 topMargin=style.MARGIN,
                                 bottomMargin=style.MARGIN, **kwargs)
        self.palette = palette
        self.subject = subject
        self.kicker = kicker
        self.detail = detail
        self.runner = runner
        self.logo = logo_bytes
        self.show_footer = show_footer

        head_h = style.STRIP_H + style.BAND_H + style.RULE_H
        first = Frame(style.MARGIN, style.MARGIN, style.CONTENT_WIDTH,
                      style.PAGESIZE[1] - head_h - 0.30 * inch - style.MARGIN,
                      id="first")
        later = Frame(style.MARGIN, style.MARGIN, style.CONTENT_WIDTH,
                      style.PAGESIZE[1] - style.RUN_BAND_H - 0.30 * inch
                      - style.MARGIN,
                      id="later")

        self.addPageTemplates([
            PageTemplate(id="first", frames=[first], onPage=self._first_page),
            PageTemplate(id="later", frames=[later], onPage=self._later_page),
        ])

    def _draw_logo(self, canvas, x, y, height):
        """Right edge at x, baseline at y. A bad logo is a cosmetic loss and
        must never stop a memo rendering."""
        if not self.logo:
            return
        try:
            image = ImageReader(io.BytesIO(self.logo))
            iw, ih = image.getSize()
            width = height * (float(iw) / float(ih))
            canvas.drawImage(image, x, y, width=width, height=height,
                             mask="auto")
        except Exception:
            pass

    def footer(self, canvas, page_count):
        canvas.saveState()
        canvas.setStrokeColor(style.LINE)
        canvas.setLineWidth(0.4)
        canvas.line(style.MARGIN, style.FOOTER_Y + 11,
                    style.PAGESIZE[0] - style.MARGIN, style.FOOTER_Y + 11)

        canvas.setFillColor(style.MUTED)

        if self.show_footer:
            x = style.MARGIN
            canvas.setFont("Helvetica", 7.5)
            canvas.drawString(x, style.FOOTER_Y, style.FOOTER_PLAIN)
            x += canvas.stringWidth(style.FOOTER_PLAIN, "Helvetica", 7.5)
            canvas.setFont("Helvetica-Oblique", 7.5)
            canvas.drawString(x, style.FOOTER_Y, style.FOOTER_LATIN)
            end = x + canvas.stringWidth(style.FOOTER_LATIN,
                                         "Helvetica-Oblique", 7.5)
            canvas.linkURL(style.FOOTER_LINK,
                           (style.MARGIN, style.FOOTER_Y - 2,
                            end, style.FOOTER_Y + 8),
                           relative=0, thickness=0)

        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(style.PAGESIZE[0] - style.MARGIN, style.FOOTER_Y,
                               "Page %d of %d" % (canvas.getPageNumber(),
                                                  page_count))
        canvas.restoreState()

    def _first_page(self, canvas, doc):
        canvas.saveState()
        top = style.PAGESIZE[1]

        # White strip: logo left, confidentiality line right.
        self._draw_logo(canvas, style.MARGIN,
                        top - 0.30 * inch - style.LOGO_H, style.LOGO_H)

        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(style.MUTED)
        canvas.drawRightString(style.PAGESIZE[0] - style.MARGIN,
                               top - 0.42 * inch, style.CONFIDENTIAL)

        # Deep band.
        band_top = top - style.STRIP_H
        canvas.setFillColor(self.palette["deep"])
        canvas.rect(0, band_top - style.BAND_H, style.PAGESIZE[0],
                    style.BAND_H, stroke=0, fill=1)
        canvas.setFillColor(self.palette["highlight"])
        canvas.rect(0, band_top - style.BAND_H - style.RULE_H,
                    style.PAGESIZE[0], style.RULE_H, stroke=0, fill=1)

        canvas.setFillColor(self.palette["highlight"])
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawString(style.MARGIN, band_top - 0.24 * inch,
                          self.kicker.upper())

        canvas.setFillColor(colors.white)
        size = 19 if len(self.subject) <= 38 else 15
        canvas.setFont("Helvetica-Bold", size)
        canvas.drawString(style.MARGIN, band_top - 0.58 * inch, self.subject)

        canvas.setFillColor(self.palette["mid"])
        canvas.setFont("Helvetica", 9)
        canvas.drawString(style.MARGIN, band_top - 0.83 * inch, self.detail)

        canvas.restoreState()

    def _later_page(self, canvas, doc):
        canvas.saveState()
        top = style.PAGESIZE[1]
        canvas.setFillColor(self.palette["deep"])
        canvas.rect(0, top - style.RUN_BAND_H, style.PAGESIZE[0],
                    style.RUN_BAND_H, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(style.MARGIN, top - 0.22 * inch, self.runner)
        canvas.restoreState()

    def handle_pageBegin(self):
        BaseDocTemplate.handle_pageBegin(self)
        if self.page == 1:
            self.handle_nextPageTemplate("later")


# --- data ------------------------------------------------------------------

def _tenant(tenant_id):
    result = _sql(
        """
        SELECT name, plan, brand_logo_key, brand_deep, brand_mid,
               brand_highlight
        FROM tenant WHERE tenant_id = :t
        """,
        [_p("t", tenant_id)],
    )
    records = result.get("records", [])
    if not records:
        return None
    r = records[0]
    return {
        "name": _col(r, 0),
        "plan": _col(r, 1) or "base",
        "brand_logo_key": _col(r, 2),
        "brand_deep": _col(r, 3),
        "brand_mid": _col(r, 4),
        "brand_highlight": _col(r, 5),
    }


def _memo(tenant_id, memo_id):
    result = _sql(
        """
        SELECT s3_bucket, s3_key, generated_at
        FROM memo WHERE tenant_id = :t AND memo_id = :m
        """,
        [_p("t", tenant_id), _p("m", memo_id)],
    )
    records = result.get("records", [])
    if not records:
        return None
    return {
        "bucket": _col(records[0], 0),
        "key": _col(records[0], 1),
        "generated_at": _col(records[0], 2),
    }


def _front(markdown, field):
    m = re.search(r"\|\s*\*\*%s\*\*\s*\|\s*([^|]+?)\s*\|" % field, markdown)
    return m.group(1).strip() if m else ""


def _branding(tenant):
    """Plan decides. Base takes the platform's; Business and Enterprise may
    set their own; only Enterprise may remove the footer."""
    plan = (tenant.get("plan") or "base").lower()
    branded = plan in ("business", "enterprise")

    palette = style.palette_for(tenant if branded else {})

    key = tenant.get("brand_logo_key") if branded else None
    logo = None
    try:
        logo = _s3.get_object(
            Bucket=BRAND_BUCKET,
            Key=key or "platform/logo.png")["Body"].read()
    except Exception:
        logo = None

    return palette, logo, plan != "enterprise"


# --- handler ---------------------------------------------------------------

def lambda_handler(event, context):
    tenant_id = int(event["tenant_id"])
    preview = bool(event.get("preview"))

    tenant = _tenant(tenant_id)
    if not tenant:
        return {"status": "not-found"}

    # A preview renders a sample against the tenant's current branding. It is
    # written to the brand bucket rather than the curated one, and recorded
    # against nothing: an existing memo's PDF is a record of what was issued
    # and is never rewritten because a colour changed.
    if preview:
        memo = {"key": "tenants/%d/preview.md" % tenant_id,
                "generated_at": "Sample"}
        markdown = PREVIEW_MARKDOWN
    else:
        memo_id = int(event["memo_id"])
        memo = _memo(tenant_id, memo_id)
        if not memo:
            return {"status": "not-found"}
        markdown = _s3.get_object(
            Bucket=memo["bucket"],
            Key=memo["key"])["Body"].read().decode("utf-8")

    palette, logo, show_footer = _branding(tenant)
    styles = style.build_styles(palette)
    _set_cite_colour(palette)

    subject = _front(markdown, "Subject") or "Subject not stated"
    engagement = _front(markdown, "Engagement")
    generated = _front(markdown, "Generated")

    detail = "  \u00b7  ".join(x for x in (engagement, generated) if x)
    runner = "%s  \u00b7  Due Diligence Memorandum" % subject

    buffer = io.BytesIO()
    doc = MemoDoc(buffer, palette, subject,
                  "Due Diligence Memorandum", detail, runner,
                  logo, show_footer,
                  title=subject, author=tenant["name"])

    def make_canvas(*args, **kwargs):
        kwargs["footer_fn"] = doc.footer
        return NumberedCanvas(*args, **kwargs)

    _reset_citations()
    flow = to_flowables(markdown, styles, palette)
    flow.extend(_reference_section(styles))

    doc.build(flow, canvasmaker=make_canvas)

    pdf = buffer.getvalue()
    pdf_key = memo["key"].rsplit(".", 1)[0] + ".pdf"

    if preview:
        _s3.put_object(Bucket=BRAND_BUCKET, Key=pdf_key, Body=pdf,
                       ContentType="application/pdf")
        url = _s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BRAND_BUCKET, "Key": pdf_key},
            ExpiresIn=3600)
        print("[preview] tenant=%d plan=%s bytes=%d" % (
            tenant_id, tenant["plan"], len(pdf)))
        return {"status": "ok", "preview": True, "url": url,
                "bytes": len(pdf), "plan": tenant["plan"]}

    put = _s3.put_object(Bucket=CURATED_BUCKET, Key=pdf_key, Body=pdf,
                         ContentType="application/pdf")

    _sql(
        "UPDATE memo SET pdf_key = :k, pdf_version_id = :v "
        "WHERE tenant_id = :t AND memo_id = :m",
        [_p("k", pdf_key), _p("v", put.get("VersionId")),
         _p("t", tenant_id), _p("m", memo_id)],
    )

    print("[rendered] memo=%d tenant=%d plan=%s bytes=%d key=%s" % (
        memo_id, tenant_id, tenant["plan"], len(pdf), pdf_key))

    return {
        "status": "ok",
        "memo_id": memo_id,
        "pdf_key": pdf_key,
        "bytes": len(pdf),
        "plan": tenant["plan"],
        "branded": tenant["plan"].lower() in ("business", "enterprise"),
    }
