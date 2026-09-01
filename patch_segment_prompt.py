"""Stop the segmentation prompt arguing itself out of a split.

The first version told the model that most files hold one document and that
splitting one in two is as damaging as missing a boundary. It obeyed: a 37-page
file of four Outlook thread exports, page footers restarting at 1/20, 1/10, 1/3
and 1/4, came back as one document with the rationale "no document boundaries
or subject changes indicating separate documents".

The caution stays, because over-splitting files a document twice and charges
for both. What goes is the thumb on the scale, and in its place are the signals
that actually mark a boundary in the material this reads.

Run from c:\\terraform\\arqedia.
"""

import io
import re
import sys

P = "lambda/normalizer/segment.py"


def once(text, pattern, replacement, label, flags=0):
    found = re.findall(pattern, text, flags)
    if len(found) != 1:
        sys.exit("ANCHOR %s matched %d times, expected 1" % (label, len(found)))
    return re.sub(pattern, lambda _m: replacement, text, count=1, flags=flags)


with io.open(P, encoding="utf-8") as fh:
    s = fh.read()

s = once(
    s,
    r'        "Rules:\\n"\n'
    r'        "- The parts must cover every " \+ word \+ " exactly once\. The first "\n'
    r'        "starts at 1, the last ends at " \+ str\(page_count\) \+ ", and each begins "\n'
    r'        "immediately after the previous one ends\. No gaps, no overlaps\.\\n"\n'
    r'        "- Most files hold ONE document\. Return a single part covering "\n'
    r'        "1 to " \+ str\(page_count\) \+ " unless a boundary is clear from the text "\n'
    r'        "itself - a new title page, a new letterhead, a restarting page number, "\n'
    r'        "an unmistakable change of subject\. Splitting a single document in two "\n'
    r'        "is as damaging as missing a boundary\.\\n"\n'
    r'        "- Return null for document_type if a part matches nothing on the list\. "\n'
    r'        "A wrong type causes the wrong facts to be extracted, so null is the "\n'
    r'        "right answer when uncertain\.\\n"',
    '''        "Rules:\\n"
        "- The parts must cover every " + word + " exactly once. The first "
        "starts at 1, the last ends at " + str(page_count) + ", and each begins "
        "immediately after the previous one ends. No gaps, no overlaps.\\n"
        "- A boundary is a change of ARTEFACT, not a change of subject. Two "
        "documents about the same matter, filed together, are still two "
        "documents. Continuity of topic is not evidence against a boundary.\\n"
        "- Signals that mark one, strongest first: a " + word + " number that "
        "restarts (a footer reading 1 of 20 through 20 of 20, then 1 of 10); a "
        "repeated masthead, letterhead, cover sheet or title page; a new "
        "signature block or addressee; a run of " + word + "s in a different "
        "format from what precedes them - prose after a table, a statement "
        "after correspondence.\\n"
        "- Sections that would carry DIFFERENT types from the list are almost "
        "always different documents. If one range reads as correspondence and "
        "another as a financial statement, split them.\\n"
        "- Do not split on a heading, a section number or a new topic inside "
        "one continuous document. Filing one document as two extracts it twice "
        "and charges twice, so a boundary needs a reason you could point at.\\n"
        "- Return null for document_type if a part matches nothing on the list. "
        "A wrong type causes the wrong facts to be extracted, so null is the "
        "right answer when uncertain. Null is about the TYPE only - it is never "
        "a reason to merge parts.\\n"''',
    "segmentation rules",
)

s = once(
    s,
    r'        "Below is an excerpt from each " \+ word \+ " of a file with "\n'
    r'        \+ str\(page_count\) \+ " " \+ word \+ "s, numbered 1 to " \+ str\(page_count\)\n'
    r'        \+ "\. Decide how many documents it holds, where each begins and ends, "\n'
    r'        "and what each one is\.\\n\\n"',
    '''        "Below is an excerpt from each " + word + " of a file with "
        + str(page_count) + " " + word + "s, numbered 1 to " + str(page_count)
        + ". Read every excerpt before answering. Decide how many documents it "
        "holds, where each begins and ends, and what each one is.\\n\\n"''',
    "read-every-page instruction",
)

with io.open(P, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(s)

print("patched " + P)
