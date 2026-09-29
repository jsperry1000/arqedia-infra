# ARQEDIA — Getting started

**Living draft. 3 September 2026.**

Written from the project documents and from screens observed on the Manty
tenant. Steps marked **[not built]** describe something the product needs and
the editor does not yet offer; they are proposed, not described. Steps marked
**[unpriced]** name a charge whose amount is not recorded anywhere I have read.

**Corrected 28 September 2026.** Steps 2 to 7 and 12 are administrator only.
`_require_admin` guards every draft, editor, publish, fork and active-revision
route in `lambda/api/app.py` (`POST /config/draft` onward); a Member is
refused with "only an administrator may change the configuration". CLAUDE.md
records this as the 17.7 correction to its "Two roles" decision. Neither
**[not built]** mark in this guide still stands (Steps 6 and 12, below), and
generating is priced (Step 9, below).

---

## Before you start

**Get your configuration right before you upload anything.**

ARQEDIA reads each document once, at the moment you file it, against the
configuration that is live at that moment. It never reads it again.

Everything you do *afterwards* with the facts it found — how they are grouped,
which memorandum they appear in, what order the sections run in, what each
section is asked to say — you can change freely, at any time, at no cost.

But the list of facts it looks for, and the wording that tells it what to look
for, are fixed for a document at the moment you file it. Change them later and
the change applies to the next document you file, not to the ones already in.

So the order below is not a suggestion. It is the order that keeps you from
paying twice.

---

## Step 1 · Review your existing process first

Before you open the product, take the reports you write today and mark them up.

You are looking for three things:

- **The facts you rely on.** Every figure, name, date and finding your current
  memoranda quote. That becomes your field vocabulary.
- **Where each fact comes from.** Which document in a file you would turn to.
  That becomes the document types each fact is sought in.
- **The shape of each report.** The headings, in order, and what each has to
  establish. That becomes your sections.

This is the work that decides whether the product is useful to you, and it is
credit judgement rather than software. Do it on paper.

**One rule to carry into it:** be generous with the fact list and precise with
the wording. A fact you defined and never used costs you nothing. A fact you
did not define costs you a re-upload.

---

## Step 2 · Open a draft

Go to **Configure a Report**.

The screen tells you which revision is live and that you are editing a draft:
*Editing a draft. Revision 26 stays in use until you publish.*

Nothing you do here affects anything until you publish. The live revision keeps
running, and memoranda already written keep saying what they said.

**Discard** throws the draft away and leaves the live revision alone.

**Corrected 28 September 2026.** Only an administrator can open a draft:
`POST /config/draft` calls `_require_admin` (`lambda/api/app.py`). A draft
opens from the revision selected for use, not the newest published one
(`docs/specs/revision_selection_decisions_2026-09-17.md` §2 item 9).

---

## Step 3 · Author the facts

Define each fact from your Step 1 list. For each one you give:

- **A name.** What it is called on the page. You can change this later, freely,
  and it will change on memoranda already written.
- **A description.** What the product should look for. This is the wording that
  does the work, and it is the thing you cannot change retrospectively. Write
  it as you would brief an analyst who has never seen the file.
- **Whether it is a single value or a table.** A table fact carries several
  columns and several rows — buyers, suppliers, insurance policies, service
  counterparties. Table facts are marked *(table)* wherever they appear.

**Your facts are shared across every memorandum you write.** A document is read
once, and the same facts are then read three ways by a credit memorandum, a
KYC memorandum and a lender memorandum. You are not defining them three times
and you are not paying for them three times.

---

## Step 4 · Say where each fact is looked for

Open a fact and tick the document types it should be sought in. They are
grouped: Corporate, KYC AML and Screening, Financial, Business.

Ticking widely is not free — it costs reading time and it invites the wrong
answer. A fact about the business model belongs in the operations memorandum,
the market analysis and the trade summary. It does not belong in a certificate
of incorporation.

**Be careful with correspondence.** Facts that assert something was *done* — a
screening was run, a check was performed — should only be sought in documents
that record it being done. An email that names an inspector is not evidence
that an inspection took place, and a memorandum that says otherwise is worse
than one that says nothing.

---

## Step 5 · Lay out each memorandum

Use the **Memorandum** selector at the top of the pane. Everything below it is
scoped to the memorandum you have chosen.

**Add a section** for each heading from your Step 1 markup. For each section
you set:

- **A numeral and a title.** These are what the reader sees.
- **How it is written.** Either it renders the facts you bind to it, or it is
  written by the model from other sections.
- **Its order.**

You can add, retitle, reorder and delete sections whenever you like, before or
after you have uploaded anything, and the change reaches memoranda you generate
from documents filed months ago.

**Delete this memorandum** removes the whole memorandum. The last one cannot be
deleted.

---

## Step 6 · Bind facts to sections

Open a section and tick the facts it should render. A section renders the facts
bound to it and nothing else.

Bindings are per memorandum. The same fact can sit in section II of your credit
memorandum and section V of your KYC memorandum, and improving its description
improves both.

**[not built]** A section written by the model does not render bound facts at
all — it reads the other sections you name as its context. The editor currently
offers the fact list on such a section and accepts the ticks, and they do
nothing. There is no control yet for naming the context sections. Until both
are fixed, author your sections to render facts.

**Corrected 28 September 2026.** Built, as CFG-02: `05ce073` (#238),
`0eac323` (#239). A composed section now shows a tick list of the sections it
reads and hides the fact list; publish refuses a composed section that reads
nothing, or reads a composed section placed after it.

---

## Step 7 · Publish

A draft reaches nothing. Publish it and it becomes the live revision, and the
revision number goes up.

A published revision is never edited again. That is what lets a memorandum
written in March reproduce exactly in September.

**Corrected 28 September 2026.** Publishing is administrator only
(`POST /config/publish` calls `_require_admin`). And "publish it and it
becomes the live revision" is not what the decision record says:
`docs/specs/revision_selection_decisions_2026-09-17.md` §2 items 1 and 2 read
"Publishing makes a revision available, and nothing more" and "A separate tick
selects which published revision is in use" — `tenant.active_revision`. The
code does both: `registry.publish` still sets `tenant.active_revision` to the
revision it has just written (`lambda/shared/registry.py`, after `_copy` in
`publish`), and `PUT /config/active` (`registry.select_revision`) selects any
published revision, refused while a draft is open. So, as built today,
publishing also puts the new revision in use, and an administrator can then
select an earlier one. Which of the two is intended is not settled here.

---

## Step 8 · Upload your documents

Now, and not before.

Each document is classified, read once, and the facts you defined are extracted
from it. The document is stamped with the revision that was live when you filed
it.

**A filing is charged at $0.25 per document.**

**Corrected 28 September 2026.** What the data says: migration
`db/migrations/015_wallet.sql` seeds the standard price (`meter_price`,
`tenant_id IS NULL`) as `document_filed` 25 cents and `memo_generated` 100
cents; no later migration adds or changes a `meter_price` row. The unit is a
`document` row: the filing charge's quantity is the number of documents
included in the click (`lambda/api/app.py`, `chargeable` in
`file_documents`). Where one uploaded file is split into parts, each part is
its own `document` row (`011_document_parts.sql`), so the charge is $0.25 per
part, not per uploaded file. A tenant may carry a negotiated override row; the
live table was not queried.

**Decided 29 September 2026.** $0.25 per split part is the decision, not only
what the data does. Live `meter_price` on dev, 29 September: `document_filed`
25 cents, standard (`tenant_id IS NULL`), no tenant override.

---

## Step 9 · Generate a memorandum

Go to **Review**. Where you hold more than one memorandum, a **Write** selector
appears; where you hold one, it does not.

Generating composes the memorandum fresh, against the live revision, from the
facts already held. It does not re-read your documents.

You can generate as often as you like as you refine the layout.

**[unpriced]** Generating spends inference. The charge is not recorded in the
material I have read.

**Corrected 28 September 2026.** Priced. `meter_price` seeds `memo_generated`
at 100 cents, $1.00 a generation, standard (`db/migrations/015_wallet.sql`),
charged once per generation (`wallet.charge(..., "memo_generated", 1, ...)` in
`lambda/api/app.py`). "The live revision" here is the revision selected for
use, `tenant.active_revision`, which composition reads
(`docs/specs/revision_selection_decisions_2026-09-17.md` §2 item 2).

---

## Step 10 · Read what came back

Two things to look for.

**The coverage note at the top** names any section the product had no material
for. A section with nothing behind it says so rather than inventing something.

**Gaps inside a section** are the same thing at section level: *No material
addressing this section was provided.* A gap means one of four things, and they
are worth telling apart:

1. Nothing you filed contains the fact.
2. The fact was never defined.
3. The fact was defined after those documents were filed — see Step 11.
4. The fact is defined and found, but not bound to any section.

Only the fourth is fixed by editing bindings.

---

## Step 11 · Changing your mind later

This is the part worth understanding before you have to.

**Free, and applies to everything already filed:**

- Binding or unbinding a fact
- Adding, retitling, reordering or deleting a section
- Changing how a section is written, or what it is asked to say
- Adding a whole new memorandum
- Renaming a fact

**Applies only to documents you file from now on:**

- Adding a new fact
- Changing a fact's description
- Changing which document types a fact is sought in
- Adding or editing a document type's description

**A new fact is empty on every document already filed.** A table fact shows as
a row of dashes; a single fact shows as an absent line. Neither announces
itself, and the memorandum will not tell you the difference between "we looked
and found nothing" and "we were not looking for this yet".

**The only way to fill a new fact on an old document is to upload that document
again.** It is filed afresh, read against the current configuration, and
charged again at $0.25. Set the old copy aside rather than deleting it —
memoranda already written cited what was current when they were written.

There is no re-read that fills a new fact. This is deliberate: if editing a
fact re-read your whole file, a memorandum you had already sent to a reader
could change under them.

---

## Step 12 · Adding a memorandum later

Adding a memorandum of your own is free and immediate — it is layout over facts
you already hold, and it reaches every document you have filed.

**[not built]** Taking a memorandum we ship later and importing it into a
configuration you have already customised is designed and not built.

**Corrected 28 September 2026.** Built, as TPL-02: `0cb620d` (#142).
`registry.fork_template` adds a memorandum on offer to the tenant's draft,
additively, brings back any fact it needs, and says what it added; routes
`GET /config/templates/available` and `POST /config/templates/fork`,
administrator only. It lands in the draft and reaches nothing until published.

---

## The short version

| | |
|---|---|
| Get right before uploading | The fact list, and the wording of each description |
| Change freely afterwards | Sections, order, bindings, whole memoranda, fact names |
| Costs a re-upload | Any new fact, on documents already filed |
| Costs nothing | Everything else |

---

## Open for review

- Wording throughout is a first pass and has had no product review.
- Screen names are taken from the current build and will move.
- The charge for generating is unpriced here.
- Steps 6 and 12 describe behaviour that is not built. They are written as the
  product should read, not as it reads today.
- **Corrected 28 September 2026.** Steps 6 and 12 are built (#238/#239,
  #142); generating is priced at $1.00 (Step 9); Step 7's account of
  publishing differs from the revision-selection decision record (Step 7).
