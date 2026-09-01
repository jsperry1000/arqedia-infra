"""Make a part's description say what is in it.

The prompt asked for one short sentence explaining the part, in the middle of a
task about boundaries, so it explained the boundary: "footer pagination showing
1/20 through 20/20". True, and useless to someone choosing a document type from
a dropdown.

The same model described the unsplit lender memo as a credit memorandum
combining borrower overview, financial analysis, KYC, risk assessment and
facility terms - which is what a person needs - purely because there was no
boundary to discuss.

The boundary reasoning is worth keeping, so it moves into its own field and out
of the way. The description becomes what it always should have been.

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
    r"""        \+ '\\n\\nReturn JSON: \{ "parts": \[ \{ "page_from": integer, '
        '"page_to": integer, "document_type": "<key from the list>" \| null, '
        '"confidence": "high" \| "medium" \| "low", '
        '"why": "<one short sentence>" \} \] \}\\n\\n'""",
    '''        + '\\n\\nReturn JSON: { "parts": [ { "page_from": integer, '
        '"page_to": integer, "document_type": "<key from the list>" | null, '
        '"confidence": "high" | "medium" | "low", '
        '"contents": "<what this part holds>", '
        '"boundary": "<why it starts here>" } ] }\\n\\n\'''',
    "json shape",
)

s = once(
    s,
    r'''        "- Return null for document_type if a part matches nothing on the list\. "
        "A wrong type causes the wrong facts to be extracted, so null is the "
        "right answer when uncertain\. Null is about the TYPE only - it is never "
        "a reason to merge parts\.\\n"''',
    '''        "- Return null for document_type if a part matches nothing on the list. "
        "A wrong type causes the wrong facts to be extracted, so null is the "
        "right answer when uncertain. Null is about the TYPE only - it is never "
        "a reason to merge parts.\\n"
        "- \\"contents\\" is read by a person deciding what this part is, often "
        "without opening the file. Say what MATERIAL it holds: the kind of "
        "document, who the parties are, and what it is about - financial "
        "figures and for which periods, operational description, counterparty "
        "or buyer and supplier lists, identity and ownership detail, "
        "correspondence and its subject. Two sentences at most. Never describe "
        "the pagination, the headers, or where the part sits in the file: that "
        "belongs in \\"boundary\\" and is worthless to a reader choosing a type.\\n"
        "- \\"boundary\\" is one short sentence on what marks the start of this "
        "part. For a single-part answer covering the whole file, say so.\\n"''',
    "contents rule",
)

# _valid_parts reads the old key. Both fields are kept: the description is what
# a person sees, the boundary is what explains a split that looks wrong.
s = once(
    s,
    r'''            "confidence": part\.get\("confidence"\),
            "why": \(part\.get\("why"\) or ""\)\[:400\],''',
    '''            "confidence": part.get("confidence"),
            "why": (part.get("contents") or part.get("why") or "")[:400],
            "boundary": (part.get("boundary") or "")[:400],''',
    "valid_parts fields",
)

s = once(
    s,
    r'''def _whole_file\(units, document_type=None, confidence=None, why=""\):''',
    '''def _whole_file(units, document_type=None, confidence=None, why="",
                boundary=""):''',
    "whole_file signature",
)

s = once(
    s,
    r'''        "confidence": confidence,
        "why": why,
    \}\]''',
    '''        "confidence": confidence,
        "why": why,
        "boundary": boundary,
    }]''',
    "whole_file body",
)

s = once(
    s,
    r'''        return _whole_file\(units, parts\[0\]\["document_type"\],
                           parts\[0\]\["confidence"\], parts\[0\]\["why"\]\), usage''',
    '''        return _whole_file(units, parts[0]["document_type"],
                           parts[0]["confidence"], parts[0]["why"],
                           parts[0]["boundary"]), usage''',
    "one-document return",
)

with io.open(P, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(s)

print("patched " + P)


# The boundary reasoning is worth keeping in the log, where it explains a split
# that looks wrong, rather than on a screen where it explains nothing.
N = "lambda/normalizer/app.py"
with io.open(N, encoding="utf-8") as fh:
    t = fh.read()

t = once(
    t,
    r'''        print\("\[analysed\] doc=%s part=%s of %s pages=%s-%s method=%s "
              "type=%s by=%s key=%s" % \(
                  document_id, part\["part_index"\], len\(parts\),
                  part\["page_from"\] or 1, part\["page_to"\] or len\(units\),
                  method, part\["document_type"\], uploaded_by, src_key\)\)''',
    '''        print("[analysed] doc=%s part=%s of %s pages=%s-%s method=%s "
              "type=%s by=%s key=%s boundary=%s" % (
                  document_id, part["part_index"], len(parts),
                  part["page_from"] or 1, part["page_to"] or len(units),
                  method, part["document_type"], uploaded_by, src_key,
                  (part.get("boundary") or "-")[:120]))''',
    "normalizer analysed log",
)

with io.open(N, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(t)

print("patched " + N)
