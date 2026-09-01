# ARQEDIA — Backlog Item

## UI-03 · Nothing tells a user which template, at which revision, produced a memo

| | |
|---|---|
| Status | Not built |
| Priority | Medium. Low effort; it is a correctness problem disguised as a display problem |
| Type | Front end, and a field on two existing API responses. No schema change |
| Raised | 1 September 2026 |

---

### Observation

A memo's front matter shows subject, engagement, generation time and a count of
documents reviewed. It does not say which configuration wrote it.

Two memos generated a fortnight apart, under revisions 3 and 7, are
indistinguishable on the page. The second may carry a section the first did not
have, a field renamed, a document type retired. Nothing on either says so, and
the only way to tell them apart is to remember.

The Configure screen has the same silence at the other end. It opens on the
draft without saying which revision the draft descends from, whether it has
been published, or what has changed since it was.

### Why it matters more than it looks

The registry's central promise is that an old memo still reproduces because it
names a revision and a revision cannot change. That promise is real in the
data and invisible in the product. A reader cannot invoke a guarantee they
cannot see.

**And the configuration is no longer the pack.** The loader wrote `pack.py`
into revision 1; tenants have since edited and published. Any reasoning that
starts from the starter pack is now reasoning about history. That divergence is
correct and expected — it is the point of the registry — but it means "which
revision" has stopped being a formality and become the only way to know what a
memo was built to say.

The same applies to the fork. A tenant's revision 1 is a deep copy of a pack
revision, and later edits to the pack never reach them. A tenant should be able
to see which pack they forked and at which version, or they will assume they
are current when they are years behind.

### Where the data already is

Nothing needs to be stored that is not stored.

- Every document carries `config_revision`.
- Every extracted value carries `config_revision`.
- A revision is an integer on an append-only series, with a publish time.

What is missing is a name and a lineage: a revision has a number but no label,
and a forked revision 1 does not record which pack revision it came from.
Those two are additive columns, not a redesign.

### What to show, and where

- **Memo front matter.** The template name and revision number alongside the
  generation time. One line, in the existing band.
- **Memo footer or source section.** The same, in the block that already
  lists source documents, so it survives print and share.
- **Configure screen header.** Which revision is published, whether the draft
  differs from it, and when it was last published.
- **Fork provenance.** On the Configure screen: which starter pack this
  tenant's revision 1 was copied from, and at which pack revision.
- **Engagement or document list.** Only if it earns its space. A document
  filed under a retired type is the case that justifies it.

### Notes

- **A revision needs a human name.** "Revision 7" is precise and tells a person
  nothing. A short label set at publish — the same discipline as a commit
  message — makes the history readable. Optional, and empty is acceptable.
- **Do not offer a diff yet.** Comparing two revisions across four object kinds
  is a screen of its own and should not be smuggled in behind a version label.
- **Do not let this become an edit surface.** This item is display only.
  Publishing, forking and validation already have theirs.

### Acceptance

A reader of any memo can see which template and which revision produced it,
without leaving the memo. A tenant on the Configure screen can see which
revision is live, whether their draft has diverged from it, and which starter
pack their configuration was forked from.
