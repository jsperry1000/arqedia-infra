"""
template.py - Stage 1 memo template, hard-coded.

Stands in for the tenant template designer, which arrives in Stage 2.

Section kinds:
  extract  - assembled from values, deterministic, no model call
  composed - drafted by the model from the assembled extract sections
"""

MEMO_SECTIONS = [
    {
        "key": "identity",
        "num": "I",
        "title": "Entity Identification",
        "kind": "extract",
        "fields": [
            "f_registered_name",
            "f_company_number",
            "f_jurisdiction",
            "f_legal_form",
            "f_incorporation_date",
            "f_registered_office",
        ],
    },
    {
        "key": "summary",
        "num": "II",
        "title": "Summary",
        "kind": "composed",
        "context_sections": ["identity"],
        "prompt": (
            "Draft the SUMMARY section of a due diligence memorandum on the "
            "entity described in the context below.\n"
            "Rules:\n"
            "1. Use ONLY the provided context. Add nothing from outside "
            "knowledge.\n"
            "2. Where the context is silent on something a reader would "
            "expect, say so plainly and mark it as an open item. Do not fill "
            "the gap with inference.\n"
            "3. Where sources disagree, state the disagreement and attribute "
            "each value. Never reconcile silently.\n"
            "4. Do not assert suitability, standing or risk the sources do "
            "not substantiate.\n"
            "Two or three paragraphs of measured professional prose. No "
            "headings, no bullet lists."
        ),
    },
    {
        "key": "open_items",
        "num": "III",
        "title": "Open Items",
        "kind": "composed",
        "context_sections": ["identity"],
        "prompt": (
            "Draft the OPEN ITEMS section. List every fact a due diligence "
            "file on this entity would normally contain that the context does "
            "NOT establish - ownership, directors, financial standing, "
            "screening, and anything else absent.\n"
            "Rules:\n"
            "1. Use ONLY the provided context to determine what is present.\n"
            "2. Frame each item as a documentation gap in our file, never as "
            "a finding about the entity. 'No ownership information has been "
            "provided' is correct; 'the entity has no disclosed owners' is "
            "not.\n"
            "3. Do not state how many items there are, in any form.\n"
            "A short list, one line each."
        ),
    },
]

TEMPLATE_KEY = "stage1-kyc"
CONFIG_REVISION = 1


def section(key):
    for s in MEMO_SECTIONS:
        if s["key"] == key:
            return s
    return None


def sections_of_kind(kind):
    return [s for s in MEMO_SECTIONS if s["kind"] == kind]
