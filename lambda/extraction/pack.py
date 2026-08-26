"""
pack.py - Stage 1 configuration, hard-coded.

Stands in for the tenant configuration registry, which arrives in Stage 2.
Field IDs are stable and must never change: extracted values reference them,
and renaming one orphans everything already extracted.
"""

# handler is one of: text, tables, forms, expense
SCHEMAS = {
    "company-identity": {
        "label": "Company Identity",
        "handler": "text",
        "fields": [
            ("f_registered_name", "Registered Name", "entity_name",
             "The full legal registered name of the company"),
            ("f_company_number", "Company Number", "identifier",
             "The registration or company number issued by the registry"),
            ("f_jurisdiction", "Jurisdiction", "text",
             "The country or territory of incorporation"),
            ("f_legal_form", "Legal Form", "text",
             "The legal form, e.g. limited company, LLC, partnership"),
            ("f_incorporation_date", "Incorporation Date", "date",
             "The date of incorporation, as stated"),
            ("f_registered_office", "Registered Office", "address",
             "The registered office address"),
        ],
    },
}

# document type -> the schemas it feeds
MAPPING = {
    "certificate-of-incorporation": ["company-identity"],
    "unclassified": ["company-identity"],
}

CONFIG_REVISION = 1


def schemas_for(document_type):
    return MAPPING.get(document_type or "unclassified", [])


def get_schema(schema_key):
    return SCHEMAS.get(schema_key)
