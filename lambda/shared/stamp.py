"""
stamp.py - burn a watermark into every page of a PDF.

Shared by two functions, which is why it is in the layer: the renderer
stamps a share's two PDFs when the grant is made, and the viewer function
stamps a download's time onto one of them every time somebody downloads.
Two copies of how a watermark looks is how the view and the download come to
disagree.

BURNED IN, NOT LAID OVER. The overlay is drawn by reportlab as a page of its
own and merged into each page's content stream with pypdf - it becomes part
of what the page draws, not an annotation, a form field or an optional
content layer a reader can switch off (share_viewer_spec section 4). It is
not tamper-proof, and no PDF watermark is: anybody with an editor can remove
text from a content stream. What it does is make an onward copy attributable,
which is the honest claim and the only one the product makes.

NOTHING HERE READS A DATABASE OR A BUCKET. Bytes in, bytes out, so the viewer
function can call it with the cluster asleep.
"""

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color, HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# The diagonal mark: faint enough to read through, there on every page.
_DIAGONAL = Color(0.39, 0.45, 0.55, alpha=0.14)
_DIAGONAL_SIZE = 17
_DIAGONAL_ANGLE = 33
_DIAGONAL_PITCH = 120

# The line along the foot. Below the memorandum's own footer rule, which the
# renderer draws at 0.52 inch plus eleven points (render/style.py), so the two
# never touch.
_LINE = HexColor("#64748b")
_LINE_SIZE = 6.5
_LINE_Y = 18


def _overlay(width, height, diagonal, line):
    """One page of watermark, the size of the page it goes onto."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))

    if diagonal:
        c.saveState()
        c.setFillColor(_DIAGONAL)
        c.setFont("Helvetica-Bold", _DIAGONAL_SIZE)
        c.translate(width / 2.0, height / 2.0)
        c.rotate(_DIAGONAL_ANGLE)
        # Tiled across the whole page rather than once in the middle, so
        # cropping a page does not crop the mark off it. Rows alternate by
        # half a step, so the gaps do not line up into a clear channel.
        reach = int(max(width, height))
        step = int(stringWidth(diagonal, "Helvetica-Bold", _DIAGONAL_SIZE)) + 70
        for row, y in enumerate(range(-reach, reach + 1, _DIAGONAL_PITCH)):
            shift = (step // 2) if row % 2 else 0
            for x in range(-reach - shift, reach + 1, step):
                c.drawCentredString(x, y, diagonal)
        c.restoreState()

    if line:
        c.setFillColor(_LINE)
        c.setFont("Helvetica", _LINE_SIZE)
        c.drawCentredString(width / 2.0, _LINE_Y, line)

    c.showPage()
    c.save()
    return PdfReader(io.BytesIO(buffer.getvalue())).pages[0]


def stamp(pdf_bytes, diagonal=None, line=None):
    """The same PDF with `diagonal` across every page and `line` along the
    foot of every page. Either may be None.

    Called twice on the way to a download: once at send with the recipient
    and the tenant, and again at download with the time - so a downloaded copy
    carries both, and the second call adds a line without repeating the
    diagonal."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    overlays = {}
    for page in reader.pages:
        box = page.mediabox
        size = (float(box.width), float(box.height))
        if size not in overlays:
            overlays[size] = _overlay(size[0], size[1], diagonal, line)
        page.merge_page(overlays[size])
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata({k: v for k, v in reader.metadata.items()
                             if isinstance(v, str)})

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# --- what the marks say ----------------------------------------------------
#
# Written here once, for both functions, so a view and a download name the
# same people the same way.

def diagonal_text(recipient_email, tenant_name):
    return "%s  ·  shared by %s" % (recipient_email, tenant_name)


def shared_line(recipient_email, tenant_name, shared_at):
    return ("Shared with %s by %s on %s UTC. Read in the ARQEDIA viewer."
            % (recipient_email, tenant_name, _when(shared_at)))


def downloaded_line(recipient_email, tenant_name, downloaded_at):
    return ("Downloaded by %s on %s UTC. Shared by %s through ARQEDIA."
            % (recipient_email, _when(downloaded_at), tenant_name))


def _when(iso):
    """2026-10-01T14:03:22Z as 2026-10-01 14:03."""
    text = str(iso or "")
    return text[:16].replace("T", " ") if len(text) >= 16 else text
