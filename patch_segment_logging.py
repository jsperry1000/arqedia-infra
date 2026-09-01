"""Say why a file was not split.

Three fallbacks in segment() currently produce identical output. This makes
each one announce itself, and prints the model's reply so a rejected split can
be read rather than inferred.

Logging only. No behaviour changes.
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
    r"    if not MODEL_ID or not \(raw_text or \"\"\)\.strip\(\) or page_count < 1:\n"
    r"        return _whole_file\(units\), \{\}",
    '''    if not MODEL_ID or not (raw_text or "").strip() or page_count < 1:
        print("[segment] not-attempted model=%s chars=%d pages=%d" % (
            bool(MODEL_ID), len(raw_text or ""), page_count))
        return _whole_file(units), {}''',
    "not-attempted",
)

s = once(
    s,
    r"    try:\n"
    r"        result = json\.loads\(cleaned\)\n"
    r"    except json\.JSONDecodeError:\n"
    r"        return _whole_file\(units\), usage",
    '''    # The reply itself, so a rejected split can be read rather than guessed
    # at. Truncated: a long proposal is a symptom, and the first part of it is
    # enough to see the shape.
    print("[segment] reply pages=%d in=%s out=%s body=%s" % (
        page_count, usage.get("input_tokens"), usage.get("output_tokens"),
        cleaned[:600].replace("\\n", " ")))

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        print("[segment] not-json")
        return _whole_file(units), usage''',
    "reply and not-json",
)

s = once(
    s,
    r"    if parts is None:\n"
    r"        return _whole_file\(units\), usage",
    '''    if parts is None:
        proposed = result.get("parts")
        print("[segment] rejected count=%s ranges=%s" % (
            len(proposed) if isinstance(proposed, list) else "not-a-list",
            [(p.get("page_from"), p.get("page_to"))
             for p in proposed if isinstance(p, dict)]
            if isinstance(proposed, list) else None))
        return _whole_file(units), usage''',
    "rejected",
)

s = once(
    s,
    r"    if len\(parts\) == 1:\n"
    r"        return _whole_file\(units, parts\[0\]\[\"document_type\"\],",
    '''    if len(parts) == 1:
        print("[segment] one-document type=%s confidence=%s" % (
            parts[0]["document_type"], parts[0]["confidence"]))
        return _whole_file(units, parts[0]["document_type"],''',
    "one-document",
)

s = once(
    s,
    r"    return parts, usage\n$",
    '''    print("[segment] split parts=%d ranges=%s" % (
        len(parts), [(p["page_from"], p["page_to"], p["document_type"])
                     for p in parts]))
    return parts, usage
''',
    "split",
)

with io.open(P, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(s)

print("patched " + P)
