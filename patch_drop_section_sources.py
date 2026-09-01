"""Stop listing every value a section was shown as if it had cited them.

At the foot of every section the memo appends:

    _Sources: <every distinct citation in block["values"]>._

block["values"] is what was FED to the section, not what it used. For a
composed section that is every value from every context section it read, so
section IV of the Manty memo ends with roughly seventy entries - all three
parts of the Carrinho consolidated financials, the H1 2026 investor
presentation, the 2025 trading stats - none of which appear anywhere in its
body. Fifteen pages of memo, forty-three numbered references, and every claim
in the body already carries its own citation inline.

The renderer drops this line already (_inline returns "" for a Sources: run),
so it never reached the PDF. It reached the markdown and the browser, which is
where a person edits.

Display only. claim_evidence is written from the same list a few lines further
down and is untouched: the deterministic evidence binding is what that list is
FOR, and it stays exactly as broad as it was.

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

s = once(
    s,
    r'''        sources = sorted\(\{_citation\(v\) for v in block\["values"\]\}\)
        if sources:
            parts\.append\("_Sources: " \+ "; "\.join\(sources\) \+ "\._"\)
            parts\.append\(""\)
''',
    '''        # No per-section source list. block["values"] is what the section was
        # SHOWN, not what it used, and for a composed section that is every
        # value from every context section it read. Listing them as sources
        # attributes to the section documents it never drew a word from, and
        # buries the citations that are real. Every claim in the body already
        # carries its own inline.
''',
    "section source list",
)

with io.open(P, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(s)

print("patched " + P)
