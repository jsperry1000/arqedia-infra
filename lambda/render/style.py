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

        "section": ParagraphStyle(
            "section", parent=base,
            fontName="Helvetica-Bold", fontSize=13, leading=17,
            textColor=deep, spaceBefore=18, spaceAfter=7),

        "subsection": ParagraphStyle(
            "subsection", parent=base,
            fontName="Helvetica-Bold", fontSize=9.5, leading=13,
            textColor=INK, spaceBefore=11, spaceAfter=4),

        "cell": ParagraphStyle(
            "cell", parent=base, fontSize=8.5, leading=11.5, spaceAfter=0),

        "cellhead": ParagraphStyle(
            "cellhead", parent=base,
            fontName="Helvetica-Bold", fontSize=7.5, leading=10,
            textColor=colors.white, spaceAfter=0),

        "label": ParagraphStyle(
            "label", parent=base,
            fontSize=6.5, leading=9, textColor=MUTED, spaceAfter=0),

        "value": ParagraphStyle(
            "value", parent=base,
            fontName="Helvetica-Bold", fontSize=9, leading=12,
            textColor=deep, spaceAfter=0),

        "citation": ParagraphStyle(
            "citation", parent=base,
            fontSize=7.5, leading=10, textColor=MUTED, spaceAfter=8),

        "callout": ParagraphStyle(
            "callout", parent=base,
            fontSize=8.5, leading=12, leftIndent=10, rightIndent=10,
            spaceBefore=2, spaceAfter=2),

        "bullet": ParagraphStyle(
            "bullet", parent=base,
            leftIndent=15, bulletIndent=5, spaceAfter=3),
    }
