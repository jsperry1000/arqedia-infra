"""
style.py - page furniture and typography for the rendered memorandum.

Follows the house masthead: a white strip carrying the logo and a
confidentiality line, a deep band beneath it with a kicker, the subject and a
detail line, and a highlight rule closing it. Later pages carry a slim band
with a running title.

The palette is an argument, not a constant. A tenant on Business or Enterprise
supplies three colours - deep, mid and highlight - and those drive every rule,
band and heading. Base takes the platform default.

Built-in fonts only. Bundling a typeface would mean a licence per tenant and a
larger layer for no gain a reader would notice; Helvetica renders identically
everywhere and never fails to load.
"""

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch

PAGESIZE = letter
MARGIN = 0.75 * inch
CONTENT_WIDTH = PAGESIZE[0] - 2 * MARGIN

STRIP_H = 0.72 * inch     # white strip carrying the logo
BAND_H = 1.05 * inch      # deep band with the subject
RULE_H = 3                # highlight rule closing the band
RUN_BAND_H = 0.34 * inch  # running band on later pages
FOOTER_Y = 0.52 * inch

LOGO_H = 0.30 * inch

# Table type sizes. Named because the column widths are measured against
# them: measuring at one size and rendering at another gives every column
# the wrong width, and the error grows with the number of columns.
CELL_SIZE = 7.5
CELLHEAD_SIZE = 7

# The pill. Measured here as well as drawn, because a pill is only as wide
# as its own words.
PILL_SIZE = 8.5

CONFIDENTIAL = "CONFIDENTIAL  \u00b7  PREPARED FOR THE ADDRESSEE"

# Platform default. A tenant without branding, or on Base, renders in these.
DEFAULT_PALETTE = {
    "deep": "#002561",
    "mid": "#278ACA",
    "highlight": "#FFDD00",
}

INK = colors.HexColor("#0d1b2a")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")
GAP_FILL = colors.HexColor("#FDF6DA")

FOOTER_PLAIN = "Prepared with ARQEDIA  \u00b7  "
FOOTER_LATIN = "quod erat demonstrandum"
FOOTER_LINK = "https://arqedia.com"


def palette_for(tenant):
    """Three colours, falling back per colour rather than all-or-nothing - a
    tenant setting only its deep colour still gets a coherent page."""
    out = {}
    for key in ("deep", "mid", "highlight"):
        value = (tenant or {}).get("brand_" + key)
        try:
            out[key] = colors.HexColor(value) if value else \
                colors.HexColor(DEFAULT_PALETTE[key])
        except Exception:
            out[key] = colors.HexColor(DEFAULT_PALETTE[key])
    return out


def build_styles(palette):
    """Built per render, because the headings carry the tenant's colour."""
    deep = palette["deep"]

    base = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=9.5,
        leading=13.5,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=7,
    )

    return {
        "body": base,

        # Headings sit on a band rather than on the page, so their text is
        # reversed out. The spacing lives on the band, not here: a paragraph
        # inside a table cell keeps no space of its own.
        "section": ParagraphStyle(
            "section", parent=base,
            fontName="Helvetica-Bold", fontSize=13, leading=17,
            textColor=colors.white, spaceBefore=0, spaceAfter=0),

        # A fourth level, lighter than the sub-heading above it.
        "pill": ParagraphStyle(
            "pill", parent=base,
            fontName="Helvetica-Bold", fontSize=PILL_SIZE, leading=11,
            textColor=colors.white, spaceBefore=0, spaceAfter=0),

        "subsection": ParagraphStyle(
            "subsection", parent=base,
            fontName="Helvetica-Bold", fontSize=9.5, leading=13,
            textColor=colors.white, spaceBefore=0, spaceAfter=0),

        # Smaller than the body. A table of seven columns is a different
        # reading task from a paragraph, and the size that suits prose leaves
        # a name breaking across four lines.
        "cell": ParagraphStyle(
            "cell", parent=base, fontSize=CELL_SIZE, leading=10, spaceAfter=0),

        # On the page above a highlight rule, not reversed out of a band.
        "cellhead": ParagraphStyle(
            "cellhead", parent=base,
            fontName="Helvetica-Bold", fontSize=CELLHEAD_SIZE, leading=9,
            textColor=deep, spaceAfter=0),

        "label": ParagraphStyle(
            "label", parent=base,
            fontSize=6.5, leading=9, textColor=MUTED, spaceAfter=0),

        "value": ParagraphStyle(
            "value", parent=base,
            fontName="Helvetica-Bold", fontSize=9, leading=12,
            textColor=deep, spaceAfter=0),

        # A citation line beneath a table. Same colour and near enough the
        # same size as an inline citation, so the two read as one thing.
        "citation": ParagraphStyle(
            "citation", parent=base,
            fontSize=8, leading=11, textColor=palette["mid"], spaceAfter=8),

        "callout": ParagraphStyle(
            "callout", parent=base,
            fontSize=8.5, leading=12, leftIndent=10, rightIndent=10,
            spaceBefore=2, spaceAfter=2),

        "bullet": ParagraphStyle(
            "bullet", parent=base,
            leftIndent=15, bulletIndent=5, spaceAfter=3),
    }
