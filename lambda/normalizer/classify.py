"""
classify.py - decide what a document is.

Returns a proposed document type, never a settled one. eBL has an operator
pick from a list at upload; we have no operator, so the model reads the text
and proposes. The envelope records it as a proposal so a review screen can
confirm it later.

Returns None when the model cannot tell. An unclassified document extracts
nothing, which is correct: extracting the wrong fields is worse than
extracting none.
"""

import json
import os
import re

import boto3

import pack

_bedrock = boto3.client("bedrock-runtime")

MODEL_ID = os.environ.get("CLASSIFIER_MODEL_ID")

# Enough text to recognise a document. Titles and headers sit at the front.
_SAMPLE_CHARS = 4000


def classify(raw_text):
    """Returns (document_type_key or None, confidence or None)."""
    if not MODEL_ID or not (raw_text or "").strip():
        return None, None

    catalogue = []
    for t in pack.document_type_list():
        catalogue.append("  " + t["key"] + "  (" + t["category"] + ")")
        catalogue.append("      " + t["label"] + ". " + t.get("description", ""))

    prompt = (
        "Identify which type of document this is, from the list below.\n\n"
        + "\n".join(catalogue)
        + "\n\nReturn JSON: "
        '{ "document_type": "<key from the list>" | null, '
        '"confidence": "high" | "medium" | "low" }\n\n'
        "Return null if the document does not clearly match any type on the "
        "list. A wrong classification causes the wrong facts to be extracted, "
        "so null is the right answer when uncertain.\n"
        "Return only the JSON object.\n\n"
        "--- DOCUMENT START ---\n"
        + raw_text[:_SAMPLE_CHARS]
        + "\n--- DOCUMENT END ---"
    )

    response = _bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    payload = json.loads(response["body"].read())
    text = "".join(
        b.get("text", "") for b in payload.get("content", [])
        if b.get("type") == "text"
    )
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        return None, None

    proposed = result.get("document_type")

    # Validate against the real list. The model can invent a key; it cannot
    # get an invented key past this.
    if proposed not in pack.DOCUMENT_TYPES:
        return None, None

    return proposed, result.get("confidence")

