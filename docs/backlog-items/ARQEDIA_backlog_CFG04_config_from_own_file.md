# CFG-04 · Build a configuration from the client's own memorandum

| | |
|---|---|
| Status | Not built. Decisions taken, open points listed at the end |
| Priority | High. It is the first thing a new client does |
| Depends on | CFG-02 for anything the model writes. Not blocking for the rest |

---

## 1. What it is

A client arrives with his own memorandum format. He drops the file on the
Configure page. We read it, work out its headings, the facts each heading
reports, and the documents those facts come from, and put the whole thing to
him as a proposal. He corrects it, acknowledges each new thing, and accepts.
Only then does any of it reach his draft.

---

## 2. Where it lives

On the Configure page, as one of three ways to start:

1. **Use one of ours and edit it.** Not built — the section lists are the
   starter-pack work, set aside.
2. **Build your own from scratch.** Already built. This is the current editor.
3. **Use your own, from a file.** This item.

The screen ships with route 1 hidden or stubbed until the packs exist.

Existing controls — dropdowns and tick lists. No new way of working the page.

---

## 3. What we propose from his file

The file is form, not substance. We take its shape and nothing else.

It is not filed, not classified, not extracted from, not cited, and not counted
among documents reviewed. Nothing about the borrower is read out of it. It does
not enter his corpus and it is discarded once the proposal is built. No charge
arises from it.

Four guesses, all of them corrigible:

- **His sections**, in his order, with his headings.
- **The facts each section reports.** Ticked where we already hold the fact,
  marked as new where we do not.
- **The document types** his memorandum names or implies.
- **The group each new type belongs in** — Corporate, KYC, Financial, Business,
  or one he makes himself.

And within that, **which document types each fact should be looked for in**.

---

## 4. What he has to acknowledge

Two things carry wording that cannot be corrected afterwards for documents
already filed. Both get a deliberate two-step: he acknowledges, then he
accepts. The friction is the point — it is where he stops and thinks.

**Every new field.** He must acknowledge:

- its name
- what it is
- its shape — a single value or a table

We write the description. He reads it and confirms it says what he means.

**Every new document type.** Same treatment, for the same reason: the
description decides how every future upload is classified, and a bad one sends
documents to the wrong place quietly.

**Nothing lands in his draft until he has accepted it.**

---

## 4a. When his wording matches a field he already holds

One engagement holds one vocabulary, however many memoranda are configured over
it. So a memorandum that says *Turnover* where he already holds *Gross Revenue*
must not silently become a second field meaning the same thing.

**We suggest. He decides.** The field is shown as new, and beside it: we think
you already have this — it is called Gross Revenue, and this is how it is
described. He picks one.

We never make the match ourselves. A wrong match renders a number that is not
the one he meant and looks entirely correct, which is the worst failure
available here.

This sits inside the acknowledgement step and costs no extra screen.

---

## 5. What is one-way and what is not

The distinction that drives the whole design.

**One-way — wrong here costs a re-upload at $0.25 a document:**

- A field's description. It decides what extraction looks for.
- A document type's description. It decides how uploads are classified.
- The list of fields itself. A field added later is empty on every document
  already filed.

**Free, and changeable at any time:**

- The group a document type sits in. Presentation only. Changing it disrupts no
  extraction and no composition.
- Sections, their order, their headings, and which facts they render.

So the group is a guess he can shrug at. The two descriptions are not.

---

## 6. Where it sits in his sequence

This belongs **before he uploads anything**. A field created after a document
is filed is empty on that document, and the only remedy is filing it again and
paying again.

The screen should say so.

---

## 7. Open points — not yet put to the client

**a. One memorandum or several.** Does dropping a file create a new memorandum
alongside what he has, or replace the sections of the one he is editing? A
client with a credit memorandum who later drops his KYC memorandum wants the
first.

**b. Sections his memorandum composes rather than reports.** The sample
memorandum has both kinds — Borrower Overview reports facts, Executive Summary
and Principal Risks draw other sections together. Do we guess which is which,
or propose everything as fact-rendering and let him change it? Guessing needs
CFG-02, which does not exist.

**c. What formats he can drop.** The sample is a PDF with selectable text. A
Word file, or a scan with no text layer, is a different job.

---

## 8. Not in scope

- Drag and drop. Raised and set aside; the existing dropdowns and ticks stand.
- The starter packs and their section lists.
