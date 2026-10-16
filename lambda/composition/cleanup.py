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

# A section with its own instruction. The preamble above governs WHAT MAY BE
# SAID and HOW IT LOOKS together, and it is a system prompt - so a tenant's
# "one short paragraph" arrived as one instruction among a grouped-table rule,
# an opening-sentence rule and a Note rule that outranked it. Memo 191's
# Suppliers came back as three paragraphs, a region table and a Note, none of
# which its instruction asked for.
#
# So the instruction decides the form, and these rules decide what may be
# said, exactly as REWRITE_PREAMBLE already does. They are CLEANUP_PREAMBLE's
# rules restated, with two settled differences: a disagreement is always
# stated but in a form the instruction allows, and a gap or open item is always
# kept even where the instruction does not ask for one (16 October 2026).
#
# The shape rules - opening sentence, grouped tables, the Note paragraph - are
# absent on purpose. What remains under PRESENTATION is mechanics: a table
# that does not render and a citation that breaks apart are not a form anyone
# chose.
INSTRUCTED_PREAMBLE = (
    "You are consolidating one section of an internal memorandum into the "
    "version a reader receives. The section's INSTRUCTION decides its form. "
    "These rules decide what may be said, and the instruction does not "
    "override them:\n"
    "1. Use ONLY what the source section states. Add no fact, figure, name or "
    "inference beyond it. Do not compute ratios, percentages, totals or "
    "period-on-period changes yourself - if a figure is not in the source, it "
    "is not available. If the instruction asks for something the source does "
    "not contain, leave it out rather than supply it.\n"
    "2. De-duplicate. The source repeats the same fact from several documents; "
    "state it once. Where two documents give the SAME entity under different "
    "names, merge them and use the fuller name. Where they give DIFFERENT "
    "values for the same fact, do NOT merge, average or choose one - state "
    "both and say the sources disagree, naming each, in whatever form the "
    "instruction allows.\n"
    "3. Keep every figure exactly as written, including currency and period. "
    "Reproduce proper nouns, statute and regulation titles, certification and "
    "registration identifiers, document codes and entity names EXACTLY as the "
    "source writes them, character for character. Do not correct, modernise, "
    "expand or abbreviate them. If the source is itself inconsistent, keep the "
    "form used in the passage you are consolidating.\n"
    "4. Preserve every open item and missing-material note, even where the "
    "instruction does not ask for one. You may shorten its wording; never "
    "remove it, and never resolve a gap by inventing content.\n"
    "5. Do not assert creditworthiness, suitability or recommendation the "
    "source does not substantiate, and do not write promotional copy. "
    "Describe what the business does; do not praise it.\n"
    "6. Keep the section numbering and title exactly as given.\n"
    "7. Preserve the source citation for every fact you keep. Where several "
    "documents state the same fact, cite them all after the consolidated "
    "statement.\n"
    "8. The instruction governs length, order, emphasis and form - how many "
    "paragraphs, prose or table, what comes first - and which of the material "
    "to include. Leave out material it does not ask for. Where following it "
    "means leaving a statement out, leave it out; do not compress two "
    "statements into one that says something neither said.\n"
    "\n"
    "FIELD KEYS\n"
    "Material in the section is labelled with its field key in brackets, for "
    "example 'Trade Flows (f_trade_flows)'. The instruction may refer to "
    "material by that key. Never write a field key in your output - write "
    "what it means.\n"
    "\n"
    "PRESENTATION\n"
    "Every table row, including the header and the separator, MUST be on its "
    "own line. A table emitted as one long line of pipes does not render as a "
    "table and is unreadable.\n"
    "Cite sources with asterisks, never underscores: *file.pdf, page 3*. "
    "Filenames contain underscores and an underscore-delimited citation "
    "breaks apart mid-name.\n"
    "Write a gap as a line beginning '> **Gap.**'. Do not invent the name of "
    "a missing document type.\n"
)

INSTRUCTED_PROMPT = (
    "Write the section below as the instruction asks, from the material in it "
    "and nothing else. Output markdown only - no preamble, no commentary on "
    "what you changed."
)

# A composed section has already been drafted to its own instruction, from the
# sections before it. Consolidating it under that instruction again, or under
# the built-in shape, would re-form prose that was formed on purpose. It is
# consolidated under the rules alone, and told to keep the form it has.
COMPOSED_INSTRUCTION = (
    "This section was drafted to its own instruction. Keep the form it was "
    "drafted in - its length, order, paragraphs and tables. Change it only "
    "where the rules require: state a repeated fact once, and keep every "
    "citation, disagreement and gap."
)

# Per-section shape. Keyed by section key. An absent key yields "" and the
# generic presentation rules apply unchanged, so adding a directive is additive
# and affects nothing else.
#
# Keep these SHORT and about SHAPE. Anything about what may be said belongs in
# CLEANUP_PREAMBLE, which governs every section without an instruction of its
# own - and in INSTRUCTED_PREAMBLE, which restates it for those with one.
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


# Who the memorandum is about. Appended to the draft prompt and to both
# preambles, because all three write prose about companies and none of them
# was ever told which company the memorandum is for.
#
# ABOUT WHAT MAY BE SAID, not about shape - which is why it joins
# CLEANUP_PREAMBLE and REWRITE_PREAMBLE rather than SECTION_PRESENTATION.
#
# THE NAME IS INDICATIVE. "Cocoa Empire" has to reach "Cocoa Empire Uganda
# Limited" and "CE", and no matching we could write would do that honestly;
# the model is told the name and told what counts as the same company. The
# last sentence is the one this exists for: memo 120 described a BUYER's
# business as the subject's, under a citation that was perfectly correct.
#
# EMPTY WHERE THERE IS NO SUBJECT. An engagement that never named one - which
# is every engagement opened before migration 031 - composes exactly as it
# did before. Silence is the honest answer; a guessed subject in a prompt is
# worse than none, because the model would then attribute facts to it.
def subject_rule(subject_name):
    """The subject block for a prompt, or nothing."""
    name = (subject_name or "").strip()
    if not name:
        return ""
    return (
        "\n\nSUBJECT\n"
        "This memorandum is about " + name + ". Documents may write the "
        "name differently - with or without a legal suffix such as Limited "
        "or Ltd, in another capitalisation, abbreviated, or in full. Treat "
        "any name that refers to the same company as the subject.\n"
        "Every other company - a buyer, supplier, lender, inspector or "
        "other counterparty - is not the subject. Never state a fact about "
        "another company as a fact about the subject.\n"
    )


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


def open_item(text):
    """An Open Item as the memorandum writes it: a callout, as a gap is, so
    the reader and the renderer draw it on the same tinted panel."""
    return "> **Open item.** " + " ".join((text or "").split())


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
    record should not be a generated guess.

    NO LONGER THE FIRST ANSWER (SUBJ-01). The engagement's own subject_name
    is, where it has one: this counts f_legal_name across every document in
    the engagement, and the same counting that can crown a counterparty in
    the body can crown one in the title. It stays as the fallback because
    every engagement opened before migration 031 has no subject_name, and
    the alternative for those is a cleaned folder name."""
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


# Section rewrite. A person has read a finished section and asks for it to be
# written differently: shorter, reordered, as a table, in three paragraphs.
#
# The instruction governs FORM. The rules below govern what may be SAID, and no
# instruction relaxes them. They are consolidation's rules, restated for a pass
# whose input is already a reader's text rather than assembled extracts - so
# there is nothing to de-duplicate and nothing new to merge.
#
# The heading is not the model's to write. It is taken off before the call and
# put back after, so rule 7 is belt and braces rather than the only guard.
REWRITE_PREAMBLE = (
    "You are rewriting one section of an internal memorandum at a reader's "
    "instruction. The instruction decides the form. These rules decide what "
    "may be said, and the instruction does not override them:\n"
    "1. Use ONLY what the section states. Add no fact, figure, name or "
    "inference beyond it. Do not compute ratios, percentages, totals or "
    "period-on-period changes. If the instruction asks for something the "
    "section does not contain, leave it out rather than supply it.\n"
    "2. Keep every figure exactly as written, including currency and period. "
    "Reproduce proper nouns, statute and regulation titles, certification and "
    "registration identifiers, document codes and entity names EXACTLY as the "
    "section writes them, character for character.\n"
    "3. Where the section says sources disagree, keep the disagreement and "
    "keep both values. Never resolve it by choosing one.\n"
    "4. Keep every gap and open-item note. You may shorten its wording; never "
    "remove it and never fill it.\n"
    "5. Do not assert creditworthiness, suitability or recommendation the "
    "section does not substantiate, and do not write promotional copy.\n"
    "6. The instruction governs length, order, emphasis and form - prose or "
    "table, how many paragraphs, what comes first. Where following it means "
    "leaving a statement out, leave it out; do not compress two statements "
    "into one that says something neither said.\n"
    "7. Do not write the section heading. It is added afterwards.\n"
    "\n"
    "PRESENTATION\n"
    "Write in measured, professional prose. Every table row, including the "
    "header and the separator, MUST be on its own line. Write a gap as a line "
    "beginning '> **Gap.**'. Where the section ends with a paragraph beginning "
    "'**Note.**', keep it as the final paragraph.\n"
)

REWRITE_PROMPT = (
    "Rewrite the section below as the instruction asks. Output markdown only "
    "- no heading, no preamble, no commentary on what you changed."
)


# Update. A person has saved their own text of a memorandum, and the
# configuration or the documents have moved on since. The section is written
# again from what is on file now, and this pass compares the two.
#
# THE MODEL NEVER RETURNS THE SAVED TEXT. It returns only what to ADD, and
# where, by block number; the additions are put in by code and every saved
# character stays where it was. "Content already in the saved text stays
# exactly as the user wrote it" is therefore a property of the code, not an
# instruction the model may or may not follow.
#
# What the model does decide - and nothing can check - is whether a fact is
# already covered, new, or a contradiction. That judgement is the weak point
# of Update and was accepted as one (decision of 16 October 2026).
UPDATE_PREAMBLE = (
    "You are comparing two versions of one section of an internal "
    "memorandum. SAVED is the text a person wrote and signed off. It is "
    "final: you cannot change, reword, shorten or remove any of it. FRESH is "
    "the same section written again from the documents now on file.\n"
    "Your only task is to say what FRESH states that SAVED does not.\n"
    "1. An ADDITION is a fact FRESH states that SAVED does not state at all, "
    "in any wording. A fact SAVED already states, however differently "
    "worded, is not an addition. A difference of style, order or emphasis is "
    "not an addition.\n"
    "2. An OPEN ITEM is a fact FRESH states differently from SAVED - a "
    "different figure, date, name, holding or status for the same thing. "
    "Never add it as an addition and never choose between them. Write one "
    "sentence saying what the memorandum states and what the documents now "
    "on file state, naming both.\n"
    "3. Use ONLY what FRESH states. Add no fact, figure, name or inference "
    "beyond it. Do not compute ratios, percentages, totals or changes.\n"
    "4. Keep every figure exactly as FRESH writes it, including currency and "
    "period. Reproduce proper nouns, identifiers and entity names EXACTLY, "
    "character for character.\n"
    "5. Every addition and every open item MUST carry the citation token or "
    "tokens FRESH gives for that fact. One without a token is discarded.\n"
    "6. Write each addition in the register of the saved text, as measured "
    "professional prose or, where it extends a list or table, as a short "
    "sentence. Do not write a heading.\n"
    "7. If FRESH states nothing SAVED does not, return no additions and no "
    "open items. That is the expected answer when nothing has changed.\n"
)

UPDATE_PROMPT = (
    "SAVED is given as numbered blocks. For each addition and open item, say "
    "which block it belongs after - the block whose subject it extends - or "
    "0 to put it before the first block.\n"
    "Answer with JSON only, no preamble and no commentary, in exactly this "
    "shape:\n"
    "{\"additions\": [{\"after\": 2, \"text\": \"...\"}], "
    "\"open_items\": [{\"after\": 1, \"text\": \"...\"}]}"
)

# What an Update row carries in memo_rewrite.prompt, which is NOT NULL. Not an
# instruction anybody typed, and the screen says so from the row's source.
UPDATE_ROW_PROMPT = "Update: regenerated from current template and documents"
