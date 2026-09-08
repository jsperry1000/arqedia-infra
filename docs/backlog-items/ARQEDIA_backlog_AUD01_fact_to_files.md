# AUD-01 · Walk from a fact to the files it was read from

| | |
|---|---|
| Status | Not built. Design question open |
| Priority | Medium. It turns Configure into an audit tool as well as an editor |
| Type | API route, then front end |

---

## What is wanted

A chain that can be walked from the configuration into the evidence:

    section → fact → which documents → which files → the passage

The first two links exist. The last two exist on the **Review** screen, where a
file can be opened and the passage a value came from can be read.

What is missing is the middle: from a fact's card, a button — *Extracted from
which documents?* — and from a document's name, a way through to the files
themselves, with the name clickable independently of the tick beside it.

---

## The design question, unresolved

**Configure is not in an engagement.** A configuration belongs to the tenant and
every engagement uses it. So "which files did this fact come from" has no single
answer on that screen.

**A.** Configure shows document *types* only, and drilling into files stays on
Review where an engagement has been chosen. Honest to how the product is built,
and needs no new route.

**B.** Configure asks across every engagement — "this fact was extracted from
fourteen files in three engagements" — and lets any of them be opened. This is
what was described, and it needs a route that does not exist: values by field
across engagements, with the document and engagement on each.

**B is the more useful tool** and the more work. The choice should be made
before either is started.

---

## What not to do meanwhile

Do not make a document's name a link before there is somewhere for it to go. A
link that does nothing is worse than a plain label, and the fact lists on the
same screen have taught people that a name is clickable.

---

## Why it is worth doing

A configuration screen that can be walked into the evidence answers the question
a reviewer actually asks: *not what did we ask for, but what did that produce.*
Today those are two screens with no path between them.
