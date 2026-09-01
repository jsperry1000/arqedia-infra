"""
segment.py - decide what documents a file holds, and what each one is.

Replaces classify.py, which read the first 4000 characters of a file and
returned one type for all of it. A 37-page pack of four emails was classified
from its first page and a half, and the other three documents were extracted
against a schema set chosen for the first.

Pipeline spec v1.0 §4 requires this: detect document boundaries within a
combined file and propose parts, then propose a type per part. One 47 MB PDF
may be 18 documents.

Every page is sampled, because a boundary can only be seen from the page it
falls on. eBL's build settled on 2500 characters per page and recorded that
reverting that constant stopped the split happening.

Returns proposals, never settled facts. A person confirms each part on the
review screen before anything is filed or charged.
"""

import json
import math
import os
import re

import boto3

_bedrock = boto3.client("bedrock-runtime")

MODEL_ID = os.environ.get("CLASSIFIER_MODEL_ID")

# Per page. Enough to see a masthead, a heading and the opening lines, which is
# what a boundary looks like. Reverting this to a whole-file sample is what
# removes the split.
MAX_CHARS_PER_PAGE = 2500

# Total sample across the file. A 400-page file at 2500 each would be a million
# characters, so the per-page allowance shrinks to fit rather than the file
# being truncated - a boundary on the last page matters as much as one on the
# first, and truncation would silently drop it.
MAX_SAMPLE_CHARS = 120000
MIN_CHARS_PER_PAGE = 400

# Parts are small objects. Eighteen of them fit comfortably; a model that needs
# more than this is not proposing a split, it is failing.
MAX_RESPONSE_TOKENS = 2000


def _sample_budget(page_count):
    """Characters per page, shrunk to keep the whole sample bounded."""
    if page_count < 1:
        return MAX_CHARS_PER_PAGE
    fits = int(math.floor(MAX_SAMPLE_CHARS / page_count))
    return max(MIN_CHARS_PER_PAGE, min(MAX_CHARS_PER_PAGE, fits))


def _page_samples(raw_text, units):
    """One labelled excerpt per unit, in order."""
    budget = _sample_budget(len(units))
    out = []
    for u in units:
        start = min(u["char_start"], len(raw_text))
        end = min(u["char_end"], len(raw_text))
        text = raw_text[start:end][:budget].strip()
        label = " (" + u["label"] + ")" if u.get("label") else ""
        head = "--- " + u["kind"].upper() + " " + str(u["index"]) + label + " ---"
        out.append(head + "\n" + (text or "(no extractable text)"))
    return "\n\n".join(out)


def _whole_file(units, document_type=None, confidence=None, why="",
                boundary=""):
    """The one-part answer: this file holds a single document.

    page_from and page_to are None rather than 1 and N. A part covering every
    page IS the file, and recording a range would make an ordinary upload look
    like a fragment of something larger."""
    return [{
        "part_index": 1,
        "page_from": None,
        "page_to": None,
        "document_type": document_type,
        "confidence": confidence,
        "why": why,
        "boundary": boundary,
    }]


def _valid_parts(proposed, page_count, registry):
    """Accept the model's split only if it accounts for the file exactly.

    Four rules: every part is a forward range, the first starts at page 1, the
    last ends at the final page, and each begins where the previous ended. A
    split with a gap loses a document silently; a split with an overlap
    extracts the same pages twice and pays for both. Neither is recoverable
    downstream, so a proposal that breaks any of them is discarded whole rather
    than repaired - a repaired boundary is a guess, and a guess about where one
    document ends is exactly what this function exists to avoid."""
    if not isinstance(proposed, list) or not proposed:
        return None

    cleaned, expected_start = [], 1

    for i, part in enumerate(proposed, start=1):
        if not isinstance(part, dict):
            return None
        try:
            first = int(part.get("page_from"))
            last = int(part.get("page_to"))
        except (TypeError, ValueError):
            return None
        if first != expected_start or last < first or last > page_count:
            return None

        document_type = part.get("document_type")
        # The model can invent a key; it cannot get an invented key past this.
        if document_type not in registry.DOCUMENT_TYPES:
            document_type = None

        cleaned.append({
            "part_index": i,
            "page_from": first,
            "page_to": last,
            "document_type": document_type,
            "confidence": part.get("confidence"),
            "why": (part.get("contents") or part.get("why") or "")[:400],
            "boundary": (part.get("boundary") or "")[:400],
        })
        expected_start = last + 1

    if expected_start != page_count + 1:
        return None

    return cleaned


def segment(raw_text, units, registry):
    """Returns (parts, usage).

    Each part carries part_index, page_from, page_to, document_type,
    confidence and why. A single-document file returns one part with both page
    bounds None, which is what an ordinary upload has always been.

    `registry` is the tenant's configuration at its active revision. The type
    descriptions authored in the editor are what the model reads to tell one
    type from another - they are functional, not decorative, and Stage 1 showed
    the same document classified differently as a PDF and as a Word file until
    every type carried a sentence describing itself."""
    page_count = len(units)

    if not MODEL_ID or not (raw_text or "").strip() or page_count < 1:
        print("[segment] not-attempted model=%s chars=%d pages=%d" % (
            bool(MODEL_ID), len(raw_text or ""), page_count))
        return _whole_file(units), {}

    catalogue = []
    for t in registry.document_type_list():
        catalogue.append("  " + t["key"] + "  (" + t["category"] + ")")
        catalogue.append("      " + t["label"] + ". " + (t.get("description") or ""))

    word = units[0]["kind"]

    prompt = (
        "A file may hold one document or several bound together - a corporate "
        "pack, a mail thread export, a set of statements scanned in one pass.\n\n"
        "Below is an excerpt from each " + word + " of a file with "
        + str(page_count) + " " + word + "s, numbered 1 to " + str(page_count)
        + ". Read every excerpt before answering. Decide how many documents it "
        "holds, where each begins and ends, and what each one is.\n\n"
        "Document types available:\n\n"
        + "\n".join(catalogue)
        + '\n\nReturn JSON: { "parts": [ { "page_from": integer, '
        '"page_to": integer, "document_type": "<key from the list>" | null, '
        '"confidence": "high" | "medium" | "low", '
        '"contents": "<what this part holds>", '
        '"boundary": "<why it starts here>" } ] }\n\n'
        "Rules:\n"
        "- The parts must cover every " + word + " exactly once. The first "
        "starts at 1, the last ends at " + str(page_count) + ", and each begins "
        "immediately after the previous one ends. No gaps, no overlaps.\n"
        "- A boundary is a change of ARTEFACT, not a change of subject. Two "
        "documents about the same matter, filed together, are still two "
        "documents. Continuity of topic is not evidence against a boundary.\n"
        "- Signals that mark one, strongest first: a " + word + " number that "
        "restarts (a footer reading 1 of 20 through 20 of 20, then 1 of 10); a "
        "repeated masthead, letterhead, cover sheet or title page; a new "
        "signature block or addressee; a run of " + word + "s in a different "
        "format from what precedes them - prose after a table, a statement "
        "after correspondence.\n"
        "- Sections that would carry DIFFERENT types from the list are almost "
        "always different documents. If one range reads as correspondence and "
        "another as a financial statement, split them.\n"
        "- Do not split on a heading, a section number or a new topic inside "
        "one continuous document. Filing one document as two extracts it twice "
        "and charges twice, so a boundary needs a reason you could point at.\n"
        "- Return null for document_type if a part matches nothing on the list. "
        "A wrong type causes the wrong facts to be extracted, so null is the "
        "right answer when uncertain. Null is about the TYPE only - it is never "
        "a reason to merge parts.\n"
        "- \"contents\" is read by a person deciding what this part is, often "
        "without opening the file. Say what MATERIAL it holds: the kind of "
        "document, who the parties are, and what it is about - financial "
        "figures and for which periods, operational description, counterparty "
        "or buyer and supplier lists, identity and ownership detail, "
        "correspondence and its subject. Two sentences at most. Never describe "
        "the pagination, the headers, or where the part sits in the file: that "
        "belongs in \"boundary\" and is worthless to a reader choosing a type.\n"
        "- \"boundary\" is one short sentence on what marks the start of this "
        "part. For a single-part answer covering the whole file, say so.\n"
        "Return only the JSON object.\n\n"
        "--- FILE START ---\n"
        + _page_samples(raw_text, units)
        + "\n--- FILE END ---"
    )

    response = _bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": MAX_RESPONSE_TOKENS,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    payload = json.loads(response["body"].read())
    usage = payload.get("usage", {})

    text = "".join(
        b.get("text", "") for b in payload.get("content", [])
        if b.get("type") == "text"
    )
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(),
                     flags=re.MULTILINE).strip()

    # The reply itself, so a rejected split can be read rather than guessed
    # at. Truncated: a long proposal is a symptom, and the first part of it is
    # enough to see the shape.
    print("[segment] reply pages=%d in=%s out=%s body=%s" % (
        page_count, usage.get("input_tokens"), usage.get("output_tokens"),
        cleaned[:600].replace("\n", " ")))

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        print("[segment] not-json")
        return _whole_file(units), usage

    parts = _valid_parts(result.get("parts"), page_count, registry)

    # An unusable split is not a reason to refuse the file. Fall back to what
    # the product did before this existed: one document, type unknown, for a
    # person to name on the review screen.
    if parts is None:
        proposed = result.get("parts")
        print("[segment] rejected count=%s ranges=%s" % (
            len(proposed) if isinstance(proposed, list) else "not-a-list",
            [(p.get("page_from"), p.get("page_to"))
             for p in proposed if isinstance(p, dict)]
            if isinstance(proposed, list) else None))
        return _whole_file(units), usage

    # One part covering the whole file is not a split. Record it as the
    # ordinary upload it is, keeping its type and reason.
    if len(parts) == 1:
        print("[segment] one-document type=%s confidence=%s" % (
            parts[0]["document_type"], parts[0]["confidence"]))
        return _whole_file(units, parts[0]["document_type"],
                           parts[0]["confidence"], parts[0]["why"],
                           parts[0]["boundary"]), usage

    print("[segment] split parts=%d ranges=%s" % (
        len(parts), [(p["page_from"], p["page_to"], p["document_type"])
                     for p in parts]))
    return parts, usage
