"""
pack.py - ARQEDIA Stage 1 configuration, hard-coded.

Field definitions ported from the eBL Finance schemas, which have been run
against real counterparty documents. Descriptions are kept verbatim: they
are the part that was earned through use.

Field IDs are stable and must never change. Extracted values reference them,
and renaming one orphans everything already extracted.

cardinality: 'one' or 'many'.
data types are PROPOSED: assigned by field semantics, default 'text'.
"""

SCHEMAS = {
    "business-overview": {
        "label": "Business Overview",
        "handler": "text",
        "fields": [
            ("f_company_summary", "Company Summary", "text", "one",
             "one-paragraph description of the entity"),
            ("f_business_model", "Business Model", "text", "one",
             "how it operates / makes money"),
            ("f_products_commodities", "Products Commodities", "text", "many",
             "goods/commodities it trades or produces"),
            ("f_key_suppliers", "Key Suppliers", "entity_name", "many",
             "named suppliers, if stated"),
            ("f_key_buyers", "Key Buyers", "entity_name", "many",
             "named buyers/customers, if stated"),
            ("f_geographies", "Geographies", "text", "many",
             "countries/regions of operation"),
            ("f_industry_context", "Industry Context", "text", "one",
             "sector / market positioning"),
            ("f_trade_flows", "Trade Flows", "text", "one",
             "how goods/payments move, if described"),
            ("f_existing_bank_lines", "Existing Bank Lines", "text", "many",
             "existing bank lines / facilities, if stated"),
            ("f_other_debt", "Other Debt", "text", "many",
             "other debt obligations, if stated"),
        ],
    },
    "corporate-structure": {
        "label": "Corporate Structure",
        "handler": "text",
        "fields": [
            ("f_legal_name", "Legal Name", "entity_name", "one",
             "full legal entity name"),
            ("f_entity_type", "Entity Type", "text", "one",
             "legal form (SA, GmbH, Ltd, etc.)"),
            ("f_jurisdiction", "Jurisdiction", "text", "one",
             "country/state of incorporation"),
            ("f_incorporation_details", "Incorporation Details", "text", "one",
             "date, registration number, registered office"),
            ("f_directors_officers", "Directors Officers", "entity_name", "many",
             "names + roles as stated"),
            ("f_ownership_as_stated", "Ownership As Stated", "entity_name", "many",
             "shareholders/owners named in the TEXT (not diagrams)"),
            ("f_authorized_signatories", "Authorized Signatories", "entity_name", "many",
             "who can bind the entity (board-resolution/bylaws)"),
            ("f_affiliates_subsidiaries_parents", "Affiliates Subsidiaries Parents", "entity_name", "many",
             "named related entities (parents, subs, affiliates)"),
            ("f_group_relationships", "Group Relationships", "text", "one",
             "nature of group/parent/subsidiary ties, in prose"),
            ("f_filings_status", "Filings Status", "text", "many",
             "statutory filings made, pending or in remediation, as stated: register extracts, officer or UBO filings, corrective filings, tax-record amendments"),
        ],
    },
    "capital-structure": {
        "label": "Capital Structure",
        "handler": "text",
        "fields": [
            ("f_authorized_issued_capital", "Authorized Issued Capital", "text", "one",
             "authorised and issued share capital, class and nominal value, as stated"),
            ("f_paid_up_status", "Paid Up Status", "text", "one",
             "whether capital is paid up, partly paid or unpaid, and any date given for payment"),
            ("f_shareholder_register", "Shareholder Register", "text", "many",
             "holders and holdings as recorded in the instrument, with share numbers or percentages if stated"),
            ("f_equity_instruments", "Equity Instruments", "text", "many",
             "options, warrants, convertibles, call or put options, subscription rights: holder, quantity or percentage, exercise terms, consideration, expiry"),
            ("f_transfer_restrictions", "Transfer Restrictions", "text", "one",
             "pre-emption rights, board approval, drag or tag, lock-up or other restriction on transfer"),
            ("f_encumbrances", "Encumbrances", "text", "many",
             "pledges, charges, security interests or liens over shares, and in whose favour"),
            ("f_change_of_control_triggers", "Change Of Control Triggers", "text", "many",
             "events or instruments under which control of the entity could pass, as stated"),
            ("f_recent_transfers", "Recent Transfers", "text", "many",
             "share transfers recorded in the instrument, with date, parties and consideration"),
        ],
    },
    "licenses-certifications": {
        "label": "Licences and Certifications",
        "handler": "text",
        "fields": [
            ("f_licence_or_certificate", "Licence Or Certificate", "text", "one",
             "what the document is, as titled"),
            ("f_held_by", "Held By", "text", "one",
             "the named holder. State plainly whether this is the counterparty itself or another party"),
            ("f_issuing_body", "Issuing Body", "text", "one",
             "issuing authority, certification body or regulator, with any scheme name"),
            ("f_identifier", "Identifier", "identifier", "one",
             "licence, registration, operator or scheme number as stated"),
            ("f_scope", "Scope", "text", "one",
             "activities, products, sites or geographies the document covers"),
            ("f_validity", "Validity", "text", "one",
             "issue date, expiry date and current status as stated"),
            ("f_conditions_restrictions", "Conditions Restrictions", "text", "many",
             "conditions, limitations or suspensions recorded on the document"),
        ],
    },
    "KYC": {
        "label": "KYC and Screening",
        "handler": "text",
        "fields": [
            ("f_screening_result", "Screening Result", "text", "one",
             "Overall screening outcome as stated (clear / match / potential match)."),
            ("f_pep_matches", "Pep Matches", "entity_name", "many",
             "Named individuals flagged as PEPs, with role/position if stated."),
            ("f_sanctions_matches", "Sanctions Matches", "entity_name", "many",
             "Named individuals and entities flagged as sanctioned."),
            ("f_product_and_port", "Product And Port", "text", "many",
             "Screening of products and ports."),
            ("f_source_of_funds", "Source Of Funds", "text", "one",
             "Description of source of wealth and of equity in the company."),
            ("f_associated_entities", "Associated Entities", "entity_name", "many",
             "Entities or organizations connected to any flagged person."),
            ("f_id_verified", "Id Verified", "text", "one",
             "Method and confirmation of identity verification of all persons and entities."),
            ("f_ownership_and_control", "Ownership And Control", "entity_name", "many",
             "Named individuals and entities which own and/or control the company."),
            ("f_screening_provider", "Screening Provider", "text", "one",
             "The screening tool/vendor or source, if stated."),
            ("f_screening_date", "Screening Date", "date", "one",
             "Date the screening was performed, if stated."),
            ("f_risk_notes", "Risk Notes", "text", "one",
             "Any stated risk commentary, disposition, or analyst note."),
        ],
    },
    "aml-policies-summary": {
        "label": "AML Programme",
        "handler": "text",
        "fields": [
            ("f_policy_provided", "Policy Provided", "text", "one",
             "Whether this document is, or contains, an AML/CTF policy or programme description. Answer 'yes' or 'no' based only on what the document is. Do not comment on whether the counterparty has a programme — only on what this document contains."),
            ("f_policy_document", "Policy Document", "text", "one",
             "Identification of the document as stated: title, issuing entity, version, effective or approval date, and review cycle, to the extent given."),
            ("f_compliance_officer", "Compliance Officer", "text", "one",
             "The named compliance officer, MLRO, or responsible person, with title, if the document states one."),
            ("f_policy_summary", "Policy Summary", "text", "one",
             "A summary, in prose, of the terms the policy actually sets out — the obligations, controls, and procedures it describes. Summarise what is there; do not list what is absent."),
            ("f_policy_scope_notes", "Policy Scope Notes", "text", "one",
             "Stated scope and limits: which entities, jurisdictions, or business lines the policy covers, and any matter it expressly says is out of scope or governed by a separate document."),
        ],
    },
    "financial-output": {
        "label": "Financial Position",
        "handler": "tables",
        "fields": [
            ("f_gross_revenue", "Gross Revenue", "text", "many",
             "3 years (one entry per year, with year and currency)."),
            ("f_cost_of_goods", "Cost Of Goods", "text", "many",
             "3 years."),
            ("f_trade_history_notes", "Trade History Notes", "text", "many",
             "Stated history, volume, length of dealing; commodities, origins/destinations, suppliers/buyers."),
            ("f_commissions", "Commissions", "text", "many",
             "3 years."),
            ("f_gross_profit", "Gross Profit", "text", "many",
             "3 years — total and as percentage of sales."),
            ("f_expenses", "Expenses", "text", "many",
             "3 years — with detail if given."),
            ("f_operating_profit", "Operating Profit", "text", "many",
             "3 years."),
            ("f_taxes", "Taxes", "text", "many",
             "3 years."),
            ("f_turnover", "Turnover", "text", "many",
             "3 years."),
            ("f_total_equity", "Total Equity", "text", "many",
             "3 years."),
            ("f_total_assets", "Total Assets", "text", "many",
             "3 years."),
            ("f_total_trade_receivables", "Total Trade Receivables", "text", "many",
             "3 years."),
            ("f_total_other_receivables", "Total Other Receivables", "text", "many",
             "3 years."),
            ("f_total_trade_payables", "Total Trade Payables", "text", "many",
             "3 years."),
            ("f_total_other_payables_accrued", "Total Other Payables Accrued", "text", "many",
             "3 years — other payables and accrued expenses."),
            ("f_deferred_income", "Deferred Income", "text", "many",
             "3 years."),
            ("f_intercompany_receivables", "Intercompany Receivables", "text", "many",
             "3 years — with whom."),
            ("f_intercompany_payables", "Intercompany Payables", "text", "many",
             "3 years — with whom."),
            ("f_short_term_bank_debt", "Short Term Bank Debt", "text", "many",
             "3 years — with whom."),
            ("f_liens_on_assets", "Liens On Assets", "text", "many",
             "With whom."),
            ("f_long_term_debt", "Long Term Debt", "text", "many",
             "3 years — with whom."),
        ],
    },
    "trade-flow-profile": {
        "label": "Trade Flow Profile",
        "handler": "text",
        "fields": [
            ("f_origins", "Origins", "text", "many",
             "Countries, regions, or ports the goods are sourced or shipped FROM, as stated."),
            ("f_destinations", "Destinations", "text", "many",
             "Countries, regions, or ports the goods are delivered TO, as stated."),
            ("f_flow_stages_sought", "Flow Stages Sought", "text", "many",
             "Which stages of the trade cycle financing is sought for. Use only stages the document actually identifies, from: upstream warehouse, inland transport, seaborne transit, downstream warehouse, receivables. State each with any detail given (duration, value, location)."),
            ("f_turnover_stated", "Turnover Stated", "text", "one",
             "Annual turnover or trading volume as NARRATED in this document (not from financial statements). Include the period and currency stated."),
            ("f_margins_stated", "Margins Stated", "text", "one",
             "Gross or trading margin as NARRATED in this document, per unit or per percentage, with the basis stated."),
            ("f_headquarters", "Headquarters", "address", "one",
             "Where the business is actually headquartered or principally operates from, if stated. This may differ from the registered office."),
            ("f_financing_requested", "Financing Requested", "text", "one",
             "The financing being sought: amount, currency, tenor, facility type, advance rate, and pricing expectation, to the extent stated."),
        ],
    },
}

# ---------------------------------------------------------------------------
# Document type -> the schemas it feeds.
# 26 counterparty diligence types across four categories, from the eBL
# vocabulary. Facility and draw mechanics are deliberately excluded: they are
# trade-finance specific and do not belong in a general diligence pack.
# ---------------------------------------------------------------------------

CATEGORIES = {
    "corp": "Corporate",
    "kyc-aml-pep": "KYC, AML and Screening",
    "financial": "Financial",
    "business": "Business",
}

DOCUMENT_TYPES = {
    # Corporate
    "articles":                {"category": "corp", "label": "Articles of Association",
                                "schemas": ["corporate-structure"]},
    "bylaws":                  {"category": "corp", "label": "Bylaws",
                                "schemas": ["corporate-structure"]},
    "good-standing":           {"category": "corp", "label": "Certificate of Good Standing",
                                "schemas": ["corporate-structure"]},
    "certificate-of-incorporation": {"category": "corp", "label": "Certificate of Incorporation",
                                "schemas": ["corporate-structure"]},
    "board-resolution":        {"category": "corp", "label": "Board Resolution",
                                "schemas": ["corporate-structure"]},
    "beneficial-ownership":    {"category": "corp", "label": "Beneficial Ownership Declaration",
                                "schemas": ["KYC", "corporate-structure"]},
    "regulatory-filings":      {"category": "corp", "label": "Regulatory Filings",
                                "schemas": ["corporate-structure"]},
    "cap-table":               {"category": "corp", "label": "Cap Table or Share Instrument",
                                "schemas": ["capital-structure"]},

    # KYC, AML and screening
    "aml-policy":              {"category": "kyc-aml-pep", "label": "AML Policy",
                                "schemas": ["aml-policies-summary"]},
    "cdd-questionnaire":       {"category": "kyc-aml-pep", "label": "CDD Questionnaire",
                                "schemas": ["KYC", "business-overview",
                                            "corporate-structure", "trade-flow-profile"]},
    "id-verification":         {"category": "kyc-aml-pep", "label": "Identity Verification",
                                "schemas": ["KYC"]},
    "pep-screen":              {"category": "kyc-aml-pep", "label": "PEP Screening",
                                "schemas": ["KYC"]},
    "sanctions-screen":        {"category": "kyc-aml-pep", "label": "Sanctions Screening",
                                "schemas": ["KYC"]},
    "source-of-funds":         {"category": "kyc-aml-pep", "label": "Source of Funds",
                                "schemas": ["KYC"]},

    # Financial
    "audited-statements":      {"category": "financial", "label": "Audited Financial Statements",
                                "schemas": ["financial-output"]},
    "interim-statements":      {"category": "financial", "label": "Interim Financial Statements",
                                "schemas": ["financial-output"]},
    "tax-returns":             {"category": "financial", "label": "Tax Returns",
                                "schemas": ["financial-output"]},
    "bank-statements":         {"category": "financial", "label": "Bank Statements",
                                "schemas": ["financial-output"]},
    "aging-reports":           {"category": "financial", "label": "Aged Debtors or Creditors",
                                "schemas": ["financial-output"]},

    # Business
    "counterparty-list":       {"category": "business", "label": "Customer or Supplier List",
                                "schemas": ["business-overview", "trade-flow-profile"]},
    "market-analysis":         {"category": "business", "label": "Market Analysis",
                                "schemas": ["business-overview", "trade-flow-profile"]},
    "operations-memo":         {"category": "business", "label": "Operations Memorandum",
                                "schemas": ["business-overview", "trade-flow-profile"]},
    "trade-references":        {"category": "business", "label": "Trade References",
                                "schemas": ["business-overview", "trade-flow-profile"]},
    "trade-summary":           {"category": "business", "label": "Trade Summary",
                                "schemas": ["business-overview"]},
    "licenses-certificates":   {"category": "business", "label": "Licences and Certificates",
                                "schemas": ["licenses-certifications"]},
    "insurance-coverage":      {"category": "business", "label": "Insurance Policy",
                                "schemas": ["KYC", "business-overview"]},
    "banking-relationships":   {"category": "business", "label": "Bank Reference",
                                "schemas": ["KYC"]},
}

CONFIG_REVISION = 1


def schemas_for(document_type):
    """Schemas a document type feeds. Unknown or unclassified -> none, so an
    unrecognised document extracts nothing rather than the wrong thing."""
    entry = DOCUMENT_TYPES.get(document_type)
    return entry["schemas"] if entry else []


def get_schema(schema_key):
    return SCHEMAS.get(schema_key)


def document_type_list():
    """For the classifier prompt: key, label and category."""
    return [
        {"key": k, "label": v["label"], "category": CATEGORIES[v["category"]]}
        for k, v in DOCUMENT_TYPES.items()
    ]


def label_for(field_id):
    for schema in SCHEMAS.values():
        for f in schema["fields"]:
            if f[0] == field_id:
                return f[1]
    return field_id
