"""
cleanup.py - the consolidation pass.

Composition assembles one block per source document, so a fact stated by eight
documents appears eight times. That is correct while the memo is being built:
nothing is merged, so nothing is silently lost. It is wrong for a reader.

This pass turns the assembled draft into the version a reader receives. It runs
once per section rather than once per memo - a single prompt over fifty
documents produces mush, and a section-scoped pass lets one section have its own
shape without imposing it on the rest.

Ported from the eBL Finance consolidation pass, including the rules that were
earned through failure. Rule 3 exists because a run once rendered "Money
Laundering Regulations" as "Money Loundering Regulations" in a regulated record.

Two things here are deliberately NOT model work:
  * front_matter()      - the title block is structured data
  * coverage_callout()  - the missing-input banner is generated from a list
Neither can fail the composition: both return an empty string rather than raise.
"""

CLEANUP_PREAMBLE = (
    "You are consolidating a finished internal memorandum into the version a "
    "reader receives. Rules you must follow:\n"
    "1. Use ONLY what the source memo states. Add no fact, figure, name or "
    "inference beyond it. Do not compute ratios, percentages, totals or "
    "period-on-period changes yourself - if a figure is not in the source, it "
    "is not available.\n"
    "2. De-duplicate. The source repeats the same fact from several documents; "
    "state it once. Where two documents give the SAME entity under different "
    "names, merge them and use the fuller name. Where they give DIFFERENT "
    "values for the same fact, do NOT merge or average - present both and say "
    "the sources disagree, naming each.\n"
    "3. Keep every figure exactly as written, including currency and period. "
    "Reproduce proper nouns, statute and regulation titles, certification and "
    "registration identifiers, document codes and entity names EXACTLY as the "
    "source writes them, character for character. Do not correct, modernise, "
    "expand or abbreviate them. If the source is itself inconsistent, keep the "
    "form used in the passage you are consolidating.\n"
    "4. Preserve every open item and missing-material note. Never resolve a "
    "gap by inventing content. Render gaps using the form described below.\n"
    "5. Do not assert creditworthiness, suitability or recommendation the "
    "source does not substantiate, and do not write promotional copy. "
    "Describe what the business does; do not praise it.\n"
    "6. Keep the section numbering and title exactly as given.\n"
    "7. Preserve the source citation for every fact you keep. Where several "
    "documents state the same fact, cite them all after the consolidated "
    "statement.\n"
    "\n"
    "PRESENTATION\n"
    "Open the section with one sentence stating its substance, then give the "
    "detail. A reader who stops after that sentence should still know what the "
    "section says.\n"
    "Write in measured, professional prose. Prefer short paragraphs and tables "
    "to bullet lists of raw field names. Never emit an internal field name "
    "(products_commodities, key_buyers, trade_flows) - write what it means.\n"
    "Render any list of four or more items as a table grouped on a meaningful "
    "axis (region, tier, category), not as a flat bullet list. Put the "
    "grouping label in the left column in bold.\n"
    "Every table row, including the header and the separator, MUST be on its "
    "own line. A table emitted as one long line of pipes does not render as a "
    "table and is unreadable.\n"
    "Cite sources with asterisks, never underscores: *file.pdf, page 3*. "
    "Filenames contain underscores and an underscore-delimited citation "
    "breaks apart mid-name.\n"
    "Where a section carries a caveat or a reconciliation point, write it as a "
    "final paragraph beginning '**Note.**'.\n"
    "\n"
    "GAPS\n"
    "A gap that blocks assessment of the whole section:\n"
    "    > **Gap.** <one or two sentences on what is missing and what it "
    "prevents.>\n"
    "A gap inside a section that otherwise has content:\n"
    "    > **Gap.** <one sentence naming what is absent.>\n"
    "Do not invent the name of a missing document type.\n"
)

CLEANUP_PROMPT = (
    "Consolidate the section below. Merge the repeated extracts into one "
    "account, remove duplication across sources, and present it as part of a "
    "professional memorandum. Keep the same numbering and title. Output "
    "markdown only - no preamble, no commentary on what you changed."
)

# Per-section shape. Keyed by section key. An absent key yields "" and the
# generic presentation rules apply unchanged, so adding a directive is additive
# and affects nothing else.
#
# Keep these SHORT and about SHAPE. Anything about what may be said belongs in
# CLEANUP_PREAMBLE, which governs every section.
SECTION_PRESENTATION = {
    "people": (
        "\nThis section is an inventory of individuals and related parties. "
        "Present EVERY person and institution named in the source as a table "
        "row - never as prose, however few there are. Use one table per group, "
        "in this order:\n"
        "  Individuals   | Name | Role | Holding | Nationality | Date of birth | Identity document |\n"
        "  Banks         | Institution | Role | Jurisdiction |\n"
        "  Insurers      | Insurer | Cover | Jurisdiction |\n"
        "  Related entities | Entity | Jurisdiction | Relationship |\n"
        "Banks and Insurers are two separate tables. An insurer is not a bank. "
        "Where a group has no entities, omit it - except Individuals, which "
        "always renders, with a gap line if empty.\n"
        "Do not omit a row because it would be sparse - write an em dash in "
        "the empty cell. Do not merge two named people into one row.\n"
    ),
    "business": (
        "\nPresent suppliers and buyers as two tables, not as prose:\n"
        "  Suppliers | Entity | Location | Product | Payment terms |\n"
        "  Buyers    | Entity | Location | Product | Payment terms |\n"
        "Merge the same counterparty appearing in several source documents "
        "into one row, using the fuller name. Where sources give different "
        "terms for the same counterparty, keep both and say so in a final "
        "paragraph beginning '**Note.**'.\n"
        "Narrative on the business model goes in prose above the tables, in "
        "no more than two paragraphs.\n"
    ),
    "financial": (
        "\nPresent figures as a table with the period stated in the heading. "
        "Do not compute any figure the source does not state. Where two "
        "sources give different figures for the same line, show both rows and "
        "name each source.\n"
    ),
}


def presentation_for(section_key):
    """Shape directive for a section, or nothing."""
    return SECTION_PRESENTATION.get(section_key, "")


# ---------------------------------------------------------------------------
# Deterministic - never model work
# ---------------------------------------------------------------------------

def front_matter(subject, engagement, generated_at, document_count, source_count,
                 title=None):
    """The title block. Structured data, so it is built rather than written.

    Where no source states a legal name, the engagement name stands in. A
    memorandum titled "Not stated in the sources" is accurate and useless; the
    engagement name is what the person called this piece of work, and the
    absence of a registered name is reported in the body where it belongs.

    The TITLE is the memorandum's own, from the tenant's configuration. It was
    the string "Due Diligence Memorandum" until a tenant held more than one
    memorandum, at which point a credit memorandum came out headed as a due
    diligence one - the same hard-coding as the template module, in the one
    place a reader looks first."""
    try:
        lines = [
            "# " + (title or "Due Diligence Memorandum"),
            "",
            "| | |",
            "|---|---|",
            "| **Subject** | %s |" % (subject or engagement),
            "| **Engagement** | %s |" % engagement,
            "| **Generated** | %s |" % generated_at,
            "| **Documents reviewed** | %d |" % document_count,
            "| **Sources cited** | %d |" % source_count,
            "",
            "---",
            "",
        ]
        return "\n".join(lines)
    except Exception:
        return ""


def coverage_callout(missing_types):
    """Names what was absent at generation, at the top, where it cannot be
    missed. Silent omission is the dangerous failure in a compliance record."""
    try:
        if not missing_types:
            return ""
        return (
            "> **Coverage.** This memorandum was generated without the "
            "following material, and any section depending on it is "
            "incomplete: "
            + "; ".join(sorted(missing_types))
            + ".\n\n"
        )
    except Exception:
        return ""


def subject_from(values):
    """The entity the memo is about: the most frequently stated legal name.

    Determined by counting, not asked of the model - the title of a compliance
    record should not be a generated guess."""
    try:
        names = {}
        for v in values:
            if v.get("field_id") in ("f_legal_name", "f_registered_name"):
                key = (v.get("value") or "").strip()
                if key:
                    names[key] = names.get(key, 0) + 1
        if not names:
            return None
        # Most cited wins; the longer form breaks a tie, being the fuller name.
        return sorted(names.items(), key=lambda kv: (kv[1], len(kv[0])))[-1][0]
    except Exception:
        return None


# Appended to every consolidation prompt. Citations arrive as opaque tokens
# rather than as text, because a model told to write for a reader turns a
# filename into a description - which reads well and proves nothing. A token
# has nothing to paraphrase.
CITATION_TOKENS = (
    "\n\nCITATIONS\n"
    "Passages of the form [[C1]], [[C2]] are citation tokens. They stand for "
    "a source reference and will be replaced afterwards.\n"
    "- Reproduce every token EXACTLY as written. Do not alter, translate, "
    "renumber, merge or describe them, and never write a citation in your own "
    "words in place of one.\n"
    "- Keep each token with the statement it supports. Where you merge two "
    "statements that carry different tokens, keep both tokens on the merged "
    "statement.\n"
    "- Do not invent a token. A token you were not given has no source behind "
    "it and will be discarded.\n"
    "- Do not write the word 'Source' or 'Sources' beside a token, and do not "
    "wrap one in brackets or parentheses. The token IS the citation and is "
    "presented as one; anything added beside it is duplicated in the output.\n"
    "- Do not drop a token. A statement that loses its token becomes an "
    "assertion nobody can check.\n"
)
