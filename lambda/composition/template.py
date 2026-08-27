"""
template.py - Stage 1 memo template, hard-coded.

Stands in for the tenant template designer, which arrives in Stage 2.

Every field named here MUST exist in pack.py. A template naming a field the
pack does not define produces a memo that reports a fact as absent when it was
extracted under a different name - the most dangerous failure this product has,
because it states a false negative confidently. validate() runs at import and
raises rather than shipping that.

Section kinds:
  extract  - assembled from values, deterministic, no model call
  composed - drafted by the model from the assembled extract sections
"""

import pack

MEMO_SECTIONS = [
    {
        "key": "identity",
        "num": "I",
        "title": "Entity Identification",
        "kind": "extract",
        "fields": [
            "f_legal_name",
            "f_entity_type",
            "f_jurisdiction",
            "f_incorporation_details",
            "f_directors_officers",
            "f_authorized_signatories",
            "f_filings_status",
        ],
    },
    {
        "key": "ownership",
        "num": "II",
        "title": "Ownership and Control",
        "kind": "extract",
        "fields": [
            "f_ownership_as_stated",
            "f_ownership_and_control",
            "f_affiliates_subsidiaries_parents",
            "f_group_relationships",
            "f_source_of_funds",
            "f_authorized_issued_capital",
            "f_shareholder_register",
            "f_equity_instruments",
            "f_encumbrances",
        ],
    },
    {
        "key": "people",
        "num": "III",
        "title": "Individuals and Related Parties",
        "kind": "extract",
        "fields": [
            "f_persons",
            "f_financial_counterparties",
            "f_associated_entities",
        ],
    },
    {
        "key": "business",
        "num": "IV",
        "title": "Business and Trade Activity",
        "kind": "extract",
        "fields": [
            "f_company_summary",
            "f_business_model",
            "f_products_commodities",
            "f_geographies",
            "f_industry_context",
            "f_trade_flows",
            "f_origins",
            "f_destinations",
            "f_turnover_stated",
            "f_margins_stated",
            "f_headquarters",
            "f_financing_requested",
            "f_suppliers",
            "f_buyers",
            "f_key_suppliers",
            "f_key_buyers",
            "f_existing_bank_lines",
            "f_other_debt",
        ],
    },
    {
        "key": "screening",
        "num": "V",
        "title": "Screening and Compliance",
        "kind": "extract",
        "fields": [
            "f_screening_result",
            "f_sanctions_matches",
            "f_pep_matches",
            "f_screening_provider",
            "f_screening_date",
            "f_id_verified",
            "f_risk_notes",
            "f_policy_provided",
            "f_compliance_officer",
            "f_policy_summary",
            "f_licence_or_certificate",
            "f_held_by",
            "f_issuing_body",
            "f_validity",
        ],
    },
    {
        "key": "financial",
        "num": "VI",
        "title": "Financial Position",
        "kind": "extract",
        "fields": [
            "f_turnover",
            "f_gross_revenue",
            "f_gross_profit",
            "f_operating_profit",
            "f_total_equity",
            "f_total_assets",
            "f_total_trade_receivables",
            "f_total_trade_payables",
            "f_short_term_bank_debt",
            "f_long_term_debt",
            "f_liens_on_assets",
            "f_trade_history_notes",
        ],
    },
    {
        "key": "summary",
        "num": "VII",
        "title": "Summary",
        "kind": "composed",
        "context_sections": ["identity", "ownership", "people",
                             "business", "screening", "financial"],
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
            "Three or four paragraphs of measured professional prose. No "
            "headings, no bullet lists."
        ),
    },
    {
        "key": "open_items",
        "num": "VIII",
        "title": "Open Items",
        "kind": "composed",
        "context_sections": ["identity", "ownership", "people",
                             "business", "screening", "financial"],
        "prompt": (
            "Draft the OPEN ITEMS section. List every fact a due diligence "
            "file on this entity would normally contain that the context does "
            "NOT establish.\n"
            "Rules:\n"
            "1. Use ONLY the provided context to determine what is present. "
            "Read the whole context before deciding a fact is absent: a value "
            "stated in one section is present even if another section is "
            "silent on it. Reporting something as missing when it appears "
            "above is the worst error you can make here.\n"
            "2. Frame each item as a documentation gap in our file, never as "
            "a finding about the entity. 'No ownership information has been "
            "provided' is correct; 'the entity has no disclosed owners' is "
            "not.\n"
            "3. Do not state how many items there are, in any form.\n"
            "A list, one line each."
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


def _known_field_ids():
    known = set()
    for schema in pack.SCHEMAS.values():
        for f in schema["fields"]:
            known.add(f[0])
    return known


def validate():
    """Every named field must exist in the pack. Raises on the first mismatch.

    This is the check that was missing when the template still named fields
    from before the pack was ported: the memo reported facts as absent that
    had in fact been extracted under different names."""
    known = _known_field_ids()
    unknown = []
    for s in MEMO_SECTIONS:
        for field_id in s.get("fields", []):
            if field_id not in known:
                unknown.append((s["key"], field_id))
    if unknown:
        raise ValueError(
            "template names fields absent from the pack: "
            + ", ".join("%s/%s" % u for u in unknown)
        )
    return True


validate()
