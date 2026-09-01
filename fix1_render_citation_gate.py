"""FIX 1 - the PDF renderer numbers things that are not citations.

lambda/composition/app.py decides what a citation is with a regex requiring a
file extension:

    _CITATION = re.compile(r"\\*([^*\\n]+?\\.(?:pdf|docx|xlsx|txt|json|xml)[^*\\n]*?)\\*")

lambda/render/app.py decides with no test at all. _inline() numbers every
italic run it meets, excluding only a "Sources:" line. So an extracted VALUE
that carries italics is numbered as a reference, and the word leaves the
sentence:

    The entity is Manty SA, a .(1)
    Each of the four directors holds .(9)

Reference 1 is "Societe anonyme". It is a value, not a document.

This applies composition's test in the renderer. An italic run naming a file is
a citation; anything else renders as italic text, which is what it was.

Run from c:\\terraform\\arqedia.
"""

import io
import re
import sys

P = "lambda/render/app.py"


def once(text, pattern, replacement, label, flags=0):
    found = re.findall(pattern, text, flags)
    if len(found) != 1:
        sys.exit("ANCHOR %s matched %d times, expected 1" % (label, len(found)))
    return re.sub(pattern, lambda _m: replacement, text, count=1, flags=flags)


with io.open(P, encoding="utf-8") as fh:
    s = fh.read()

if "_CITATION_FILE" in s:
    sys.exit("already patched - _CITATION_FILE is present")

GATE = '''# What composition calls a citation. It masks citations before consolidation
# using a regex requiring one of these extensions, so an italic run without one
# was never a citation on the way in and must not become one here.
_CITATION_FILE = re.compile(r"\\.(?:pdf|docx|xlsx|txt|json|xml)\\b", re.I)


'''

s = once(
    s,
    r"\ndef _reset_citations\(\):",
    "\n" + GATE + "def _reset_citations():",
    "citation gate insertion point",
)

s = once(
    s,
    r'''    def numbered\(m\):
        body = m\.group\(1\)\.strip\(\)
        if re\.match\(r"\^sources\?\\s\*:", body, re\.I\):
            return ""
        return '<super><font size="6\.5" color="%s">%d</font></super>' % \(
            _CITE_COLOUR, _cite_number\(body\)\)''',
    '''    def numbered(m):
        body = m.group(1).strip()
        if re.match(r"^sources?\\s*:", body, re.I):
            return ""
        # Emphasis, not a citation. An extracted value carrying its own
        # italics - a French term from a trade register, a document title -
        # arrives here looking exactly like a citation, and numbering it takes
        # the word out of the sentence and adds a reference to something that
        # is not a document.
        if not _CITATION_FILE.search(body):
            return "<i>" + body + "</i>"
        return '<super><font size="6.5" color="%s">%d</font></super>' % (
            _CITE_COLOUR, _cite_number(body))''',
    "numbered function",
)

with io.open(P, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(s)

print("FIX 1 applied to " + P)
