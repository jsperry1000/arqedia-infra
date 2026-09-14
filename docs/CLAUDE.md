# ARQEDIA

Read this at the start of every session. The Rules of Engagement below apply to
every response and every commit, without being restated.

---

## Rules of Engagement

- Rules of Engagement are printed in full at the head of every response, not
  summarised.
- Schema-faithful. Where something is missing from the schema, flag it as
  proposed rather than inventing it.
- Additive and non-destructive. Nothing already recorded is overwritten or
  discarded.
- Two-LTV discipline: Bill of Exchange value is the invoiced amount, not marked
  to market.
- Confirm before build. Decisions that are hard to reverse are put to me before
  code is written.
- Concise.
- No assumptions about architecture or intent. Ask rather than infer.
- No fabrication.
- No hallucination.
- No rabbit-holing. Surface when a line of work has stopped being productive.
- Simple question, simple answer. Analysis only when asked for it.
- One path. No if-then branching in instructions.
- Read or ask for live state. Never infer it from naming.
- Review prior chat and context before answering.
- Separate branches, commit periodically.
- Working directory `c:\terraform\arqedia`, Terraform and Docker.
- Web-search third-party capabilities rather than assuming them.
- A short push summary on every push.
- Never edit a document, schema or file without first reading it in full.

---

## Working practices earned the hard way

**Never write CSS from reasoning.** Four attempts at one grouped layout, each
worse than the last, until the rule was supplied. What worked was letting the
label set the column — `max-content`, `nowrap` — and having the OUTER box
scroll. Render it and look at it, or ask.

**Drawer stacking follows document order.** There are no z-indexes. A drawer
opened from another must render AFTER it in the component, and must not sit
inside a collapsible part or it renders nothing when that part is shut.

**Keep what the row had.** Every upsert keeps fields the caller did not send.
A caller that omits `sort_order` must not zero it.

---

## The product, in one paragraph

A tenant holds one configuration — document types, facts and their wording, and
memoranda with their sections and bindings. That configuration is uniform across
every engagement. An engagement holds documents. A document is read once, at
filing, against the revision live at that moment, and never read again. A
memorandum is layout over facts already held, composed on demand. One Publish
covers the whole configuration, not a single memorandum.

---

## Current work

`docs/ARQEDIA_backlog_UX01_mvp_ui_worklist.md` is the specification for the UI
work to MVP. Its decisions are settled; its branch order is not to be
rearranged. Work one branch at a time and stop at the end of each for review.

---

## What is not automated

- Merging to main. A human looks at the rendered screen first.
- Anything touching Terraform or the registry schema, including the numbering
  field in UX-07.
- New decisions. Ask; do not choose.
