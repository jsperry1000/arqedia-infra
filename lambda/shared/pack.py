"""
pack.py - ARQEDIA Stage 1 configuration, hard-coded.

Field definitions ported from the eBL Finance schemas, which have been run
against real counterparty documents. Descriptions are kept verbatim: they are
the part that was earned through use.

Field IDs are stable and must never change. Extracted values reference them,
and renaming one orphans everything already extracted.

Field shape: (field_id, label, data_type, cardinality, description)
  cardinality 'one'   - a single value
  cardinality 'many'  - a list of values
  cardinality 'group' - a repeating row. A sixth element holds the columns:
                        (sub_id, label, data_type, description). Each row is
                        stored under one row number so a person's nationality
                        stays attached to that person's name. One level deep
                        only: a row cannot contain its own table.

Sub-field IDs are scoped to their group - f_persons.full_name - so the group
is the unit a template binds to, not a floating column.
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
             "Directors, officers and company secretary OF THE ENTITY, with their roles, exactly as stated. Statutory and governance roles only. Do NOT include operational or management staff (country manager, logistics manager, sourcing manager) - those are business information, not corporate governance. Do NOT include a person who certified, witnessed, stamped or filed the document."),
            ("f_ownership_as_stated", "Ownership As Stated", "entity_name", "many",
             "Owners and their holdings exactly as the source states them, including percentages or share counts where given. Registered holders and beneficial owners both, each attributed to the source's own wording."),
            ("f_authorized_signatories", "Authorized Signatories", "entity_name", "many",
             "Who can bind the entity, as stated in a board resolution, bylaws or mandate. Do NOT include a person who signed only as witness, certifier, notary or registry official."),
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
            ("f_persons", "Persons", "group", "group",
             "One record per natural person (UBO, director, officer or authorised signatory) OF THE ENTITY named in the document. Include only persons actually named; do not invent. Do NOT include a person who merely certified, witnessed, stamped, notarised or filed the document, or a registry official processing it - they are not parties to the entity.",
             [
                 ("f_persons.full_name", "Full Name", "entity_name",
                  "full legal name as stated"),
                 ("f_persons.role", "Role", "text",
                  "role/capacity: UBO, director, signatory, or as stated"),
                 ("f_persons.ownership_pct", "Ownership Pct", "number",
                  "percentage owned, if stated for this person"),
                 ("f_persons.date_of_birth", "Date Of Birth", "date",
                  "date of birth, if stated"),
                 ("f_persons.nationality", "Nationality", "text",
                  "nationality/nationalities, if stated"),
                 ("f_persons.residential_address", "Residential Address", "address",
                  "residential address, if stated"),
                 ("f_persons.id_document", "Id Document", "identifier",
                  "ID document type and number, if stated"),
                 ("f_persons.pep_status", "Pep Status", "text",
                  "PEP status/flag for this person, if stated"),
             ]),
            ("f_financial_counterparties", "Financial Counterparties", "group", "group",
             "One record per BANK, INSURER, INSURANCE BROKER or WAREHOUSE/COLLATERAL OPERATOR the source connects to the entity. These are the counterparties a lender must see: who holds the cash, who carries the cargo and credit risk, and who holds the goods. Capture each one the source identifies, including those also named elsewhere in the document. Do not include buyers, suppliers, parents, subsidiaries, inspection or certification bodies, or regulators - those belong to other fields.",
             [
                 ("f_financial_counterparties.name", "Name", "entity_name",
                  "institution name exactly as the source gives it; transcribe, never expand an abbreviation or correct a spelling"),
                 ("f_financial_counterparties.type", "Type", "text",
                  "one of: bank, insurer, insurance-broker, warehouse. Use the term the source supports; if the source does not make the type clear, leave null rather than guessing"),
                 ("f_financial_counterparties.role", "Role", "text",
                  "what it does for the entity as stated (e.g. operating account, collections, stock throughput cover, credit insurance, storage), if stated"),
                 ("f_financial_counterparties.jurisdiction", "Jurisdiction", "text",
                  "country or location of the institution, if stated"),
             ]),
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
            ("f_suppliers", "Suppliers", "group", "group",
             "One record per supplier the source identifies, whether the source lists them in a table or describes them in prose. Capture every supplier it identifies, in the order given. Where a supplier is identified only by a positional or placeholder label rather than a company name (e.g. 'Supplier 1' in an anonymised schedule), still capture the record and put that label in `name` exactly as written: whether such a label counts as a name is not a judgement to make here, and the remaining details are needed either way. Never substitute or infer a name. Do not add suppliers the source does not identify.",
             [
                 ("f_suppliers.name", "Name", "entity_name",
                  "supplier identifier exactly as the source gives it: the company name where named, or the row label verbatim (e.g. 'Supplier 1') where the source uses positional labels. Transcribe; never substitute, infer or blank it."),
                 ("f_suppliers.location", "Location", "text",
                  "country, region, or city of the supplier, if stated"),
                 ("f_suppliers.commodity", "Commodity", "text",
                  "what is bought from this supplier, if stated"),
                 ("f_suppliers.payment_terms", "Payment Terms", "text",
                  "payment terms expected or in place with this supplier (e.g. CAD, prepayment, 30 days, LC), if stated"),
                 ("f_suppliers.relationship_length", "Relationship Length", "text",
                  "how long the entity has traded with them, if stated"),
             ]),
            ("f_buyers", "Buyers", "group", "group",
             "One record per buyer or customer the source identifies, whether the source lists them in a table or describes them in prose. Capture every buyer it identifies, in the order given. Where a buyer is identified only by a positional or placeholder label rather than a company name (e.g. 'Buyer 1' in an anonymised schedule), still capture the record and put that label in `name` exactly as written: whether such a label counts as a name is not a judgement to make here, and the remaining details are needed either way. Never substitute or infer a name. Do not add buyers the source does not identify.",
             [
                 ("f_buyers.name", "Name", "entity_name",
                  "buyer identifier exactly as the source gives it: the company name where named, or the row label verbatim (e.g. 'Buyer 1') where the source uses positional labels. Transcribe; never substitute, infer or blank it."),
                 ("f_buyers.location", "Location", "text",
                  "country, region, or city of the buyer, if stated"),
                 ("f_buyers.commodity", "Commodity", "text",
                  "what is sold to this buyer, if stated"),
                 ("f_buyers.payment_terms", "Payment Terms", "text",
                  "payment terms sought or in place with this buyer (e.g. CAD, LC, open account, days credit), if stated"),
                 ("f_buyers.relationship_length", "Relationship Length", "text",
                  "how long the entity has traded with them, if stated"),
             ]),
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
                                "description": "The entity's articles of association or constitutional document, setting out share classes, director powers and internal rules.",
                                "schemas": ["corporate-structure"]},
    "bylaws":                  {"category": "corp", "label": "Bylaws",
                                "description": "Internal governance rules or bylaws adopted by the entity.",
                                "schemas": ["corporate-structure"]},
    "good-standing":           {"category": "corp", "label": "Certificate of Good Standing",
                                "description": "A certificate issued by a registry confirming the entity exists and is in good standing at a stated date.",
                                "schemas": ["corporate-structure"]},
    "certificate-of-incorporation": {"category": "corp", "label": "Certificate of Incorporation",
                                "description": "The registry certificate recording that the entity was incorporated: legal name, registration number and date.",
                                "schemas": ["corporate-structure"]},
    "board-resolution":        {"category": "corp", "label": "Board Resolution",
                                "description": "A minuted resolution of the board or members, typically authorising an act or appointing signatories.",
                                "schemas": ["corporate-structure"]},
    "beneficial-ownership":    {"category": "corp", "label": "Beneficial Ownership Declaration",
                                "description": "A declaration naming the ultimate beneficial owners and their percentage holdings.",
                                "schemas": ["KYC", "corporate-structure"]},
    "regulatory-filings":      {"category": "corp", "label": "Regulatory Filings",
                                "description": "An extract or filing made to a company registry or regulator: annual return, register extract, officer or shareholder filing. Records what the registry holds, not what the entity says about itself.",
                                "schemas": ["corporate-structure"]},
    "cap-table":               {"category": "corp", "label": "Cap Table or Share Instrument",
                                "description": "A share register, cap table, or an instrument affecting share ownership: share purchase agreement, option, warrant or pledge.",
                                "schemas": ["capital-structure"]},

    # KYC, AML and screening
    "aml-policy":              {"category": "kyc-aml-pep", "label": "AML Policy",
                                "description": "The entity's own anti-money-laundering or counter-terrorist-financing policy document.",
                                "schemas": ["aml-policies-summary"]},
    "cdd-questionnaire":       {"category": "kyc-aml-pep", "label": "CDD Questionnaire",
                                "description": "A completed questionnaire or information request in which the entity answers questions about ITSELF: legal name, ownership, directors, business activity, banking, trade flows, financing sought. Question-and-answer or form format, completed by or on behalf of the entity being reviewed.",
                                "schemas": ["KYC", "business-overview",
                                            "corporate-structure", "trade-flow-profile"]},
    "id-verification":         {"category": "kyc-aml-pep", "label": "Identity Verification",
                                "description": "Identity documents or verification evidence for a named individual: passport, national identity card, proof of address.",
                                "schemas": ["KYC"]},
    "pep-screen":              {"category": "kyc-aml-pep", "label": "PEP Screening",
                                "description": "The output of a politically-exposed-person screening run against named individuals.",
                                "schemas": ["KYC"]},
    "sanctions-screen":        {"category": "kyc-aml-pep", "label": "Sanctions Screening",
                                "description": "The output of a sanctions list screening run against the entity or named individuals.",
                                "schemas": ["KYC"]},
    "source-of-funds":         {"category": "kyc-aml-pep", "label": "Source of Funds",
                                "description": "A statement or evidence of where the entity's funds or a person's wealth originated.",
                                "schemas": ["KYC"]},

    # Financial
    "audited-statements":      {"category": "financial", "label": "Audited Financial Statements",
                                "description": "Financial statements bearing an auditor's report.",
                                "schemas": ["financial-output"]},
    "interim-statements":      {"category": "financial", "label": "Interim Financial Statements",
                                "description": "Management-prepared or unaudited financial statements for a period.",
                                "schemas": ["financial-output"]},
    "tax-returns":             {"category": "financial", "label": "Tax Returns",
                                "description": "A filed tax return or tax assessment.",
                                "schemas": ["financial-output"]},
    "bank-statements":         {"category": "financial", "label": "Bank Statements",
                                "description": "Statements of account issued by a bank showing transactions over a period.",
                                "schemas": ["financial-output"]},
    "aging-reports":           {"category": "financial", "label": "Aged Debtors or Creditors",
                                "description": "An aged debtors or aged creditors schedule showing amounts outstanding by age.",
                                "schemas": ["financial-output"]},

    # Business
    "counterparty-list":       {"category": "business", "label": "Customer or Supplier List",
                                "description": "A schedule or list OF the entity's customers, buyers or suppliers - names, locations, volumes or terms, usually tabular. A list of third parties, not a questionnaire about the entity itself.",
                                "schemas": ["business-overview", "trade-flow-profile"]},
    "market-analysis":         {"category": "business", "label": "Market Analysis",
                                "description": "Analysis or commentary on the market, sector or commodity the entity trades in.",
                                "schemas": ["business-overview", "trade-flow-profile"]},
    "operations-memo":         {"category": "business", "label": "Operations Memorandum",
                                "description": "A description of how the entity operates: sourcing, logistics, processing, warehousing, settlement.",
                                "schemas": ["business-overview", "trade-flow-profile"]},
    "trade-references":        {"category": "business", "label": "Trade References",
                                "description": "A reference given by a trading partner, bank or customer about dealings with the entity.",
                                "schemas": ["business-overview", "trade-flow-profile"]},
    "trade-summary":           {"category": "business", "label": "Trade Summary",
                                "description": "A summary of completed or planned trades, typically tabular: counterparties, commodities, volumes, values.",
                                "schemas": ["business-overview"]},
    "licenses-certificates":   {"category": "business", "label": "Licences and Certificates",
                                "description": "A licence, permit, registration or certification held by a named party: regulatory licence, import permit, quality or scheme certification.",
                                "schemas": ["licenses-certifications"]},
    "insurance-coverage":      {"category": "business", "label": "Insurance Policy",
                                "description": "An insurance policy, certificate or schedule: cargo, stock throughput, credit or liability cover.",
                                "schemas": ["KYC", "business-overview"]},
    "banking-relationships":   {"category": "business", "label": "Bank Reference",
                                "description": "A bank reference letter or confirmation of the entity's banking relationships.",
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
        {"key": k, "label": v["label"], "category": CATEGORIES[v["category"]],
         "description": v.get("description", "")}
        for k, v in DOCUMENT_TYPES.items()
    ]


def label_for(field_id):
    for schema in SCHEMAS.values():
        for f in schema["fields"]:
            if f[0] == field_id:
                return f[1]
    return field_id


def group_columns(field_id):
    """Column definitions for a repeating-row field, or None."""
    for schema in SCHEMAS.values():
        for f in schema["fields"]:
            if f[0] == field_id and f[3] == "group":
                return f[5]
    return None
