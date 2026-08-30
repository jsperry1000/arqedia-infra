# ARQEDIA — Backlog Item

## UI-02 · Citations run into the following sentence

| | |
|---|---|
| Status | Not fixed |
| Priority | Readability, both PDF and browser |
| Type | Composition, or renderer, or both |
| Raised | 30 August 2026 |

---

### Observation

In a rendered memo, a citation and the sentence after it have no separation:

> The company was incorporated on 29th May 2026 in Kampala, Uganda.
> *Certificate-of-Incorporation.pdf, page 1 CE_Response_Lender_IM_and_KYC_
> Clarifications_SIGNED.pdf, page 1* Its registered office is Ntinda Village
> 1, Plot 2, Kimera Road, Kampala.

Two faults in one line. Consecutive citations run together with only a space
between them, so it is not obvious that they are two references rather than
one long one. And the next sentence begins immediately after the closing
italic, so "page 1 Its registered office" reads as continuous prose.

The colour and smaller size help, but a paragraph carrying four citations
still reads as one run of text broken by pale patches.

### Where it comes from

The consolidation emits citations inline, as `*file.pdf, page 1*`, directly
adjacent to the surrounding prose. Neither the PDF renderer nor the browser
adds anything around them, because neither knows a citation from any other
italic run - the token masking makes the text faithful, not structured.

### Options, roughly in order of cost

- **Separate at render.** The renderer already treats italic as a citation and
  colours it; it could also add a leading space and a separator between
  consecutive ones. Cheapest, and fixes both surfaces if applied in the PDF
  renderer and in the memo reader.
- **Bracket them.** `[file.pdf, page 1]` reads as a reference at a glance,
  which italic alone does not. Changes what a citation looks like everywhere,
  including in memos already written.
- **Move them.** Superscript markers in the text, references collected at the
  foot of the section. The most readable, and the largest change: it needs a
  numbering scheme that survives editing and revision.

### Notes

- Whatever is chosen must not alter the citation TEXT. Fidelity is
  deterministic by design (see the citation masking in composition) and a
  separator added at render is presentation, not content.
- A reader clicks a citation in the browser. Anything that merges two
  citations into one visual unit breaks that.

### Acceptance

A paragraph carrying several citations reads as prose, with each reference
visibly distinct from the next and from the sentence that follows it.
