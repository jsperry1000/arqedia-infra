"""FIX 2 - the per-section source list attributes documents the section never used.

At the foot of every section lambda/composition/app.py appends:

    *Sources: <every distinct citation in block["values"]>.*

block["values"] is what the section was FED, not what it used. For a composed
section that is every value from every context section it read, so section IV
of the Manty memo ends with roughly seventy entries - all three parts of the
Carrinho consolidated financials, the H1 2026 investor presentation, the 2025
trading stats - none of which appear anywhere in its body.

Display only. claim_evidence is written from the same list further down the
handler and is untouched: the deterministic evidence binding is what that list
is FOR, and it stays exactly as broad as it was. Every claim in the body
already carries its own citation inline.

Anchored on lines 472-475 as they stand on disk. An earlier attempt used an
underscore-italic form from a stale copy of the file and matched nothing.

Run from c:\\terraform\\arqedia.
"""

import io
import re
import sys

P = "lambda/composition/app.py"


def once(text, pattern, replacement, label, flags=0):
    found = re.findall(pattern, text, flags)
    if len(found) != 1:
        sys.exit("ANCHOR %s matched %d times, expected 1" % (label, len(found)))
    return re.sub(pattern, lambda _m: replacement, text, count=1, flags=flags)


with io.open(P, encoding="utf-8") as fh:
    s = fh.read()

if "No per-section source list" in s:
    sys.exit("already patched")

s = once(
    s,
    r'''        sources = sorted\(\{_citation\(v\) for v in block\["values"\]\}\)
        if sources:
            parts\.append\("\*Sources: " \+ "; "\.join\(sources\) \+ "\.\*"\)
            parts\.append\(""\)
''',
    '''        # No per-section source list. block["values"] is what the section was
        # SHOWN, not what it used, and for a composed section that is every
        # value from every context section it read. Listing them as sources
        # attributes to the section documents it never drew a word from, and
        # buries the citations that are real.
''',
    "section source list",
)

with io.open(P, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(s)

print("FIX 2 applied to " + P)
