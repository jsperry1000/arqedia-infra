# ARQEDIA — Backlog Item

## HONE-01 · Keep a rewrite prompt, so the next memo starts where this one ended

| | |
|---|---|
| Status | Proposed. Decisions pending |
| Priority | Medium. Nothing is broken; this compounds |
| Type | Front end, one API route, no schema change |
| Raised | 12 September 2026 |
| Depends on | Section rewrite (#118–#120), the config draft editor |

---

### The need

A person generates a memorandum, reads a section, and finds it reads badly -
a list where a table belongs, four paragraphs where one would do, the wrong
thing first. They write a prompt, press Go, and the section comes back the way
they wanted it.

Then they generate the next memorandum and it comes back exactly as the first
one did, because the prompt applied to one memo and nothing was learned. The
same instruction is typed again, and again, once per memo, for ever.

The instruction already has a home. Every section in the configuration carries
a narrative prompt - `config_section.prompt` - which is what composition writes
the section from. A rewrite prompt and a section prompt are the same kind of
thing said at different moments: one about this memo, one about every memo.
There is currently no way to move the first into the second except to open the
configuration editor and type it again from memory.

### What this is, and what it is not

**It is a honing loop for how a memorandum reads.** Generate, see it read
badly, prompt a rewrite, see it read better, keep the prompt, publish. The
next memo starts from the improved instruction. The rewrite screen becomes
where an instruction is tried on real content before it is committed to -
which is a better place to test one than the configuration editor, where a
person is imagining the result rather than looking at it.

**It is not a honing loop for what is extracted.** Nothing here reaches the
values. A field's description decides what is read out of a document, that
decision is pinned at filing, and a prompt about how a section should read
says nothing about what to look for in a PDF. Feeding presentation prompts
into extraction would make extraction worse: its prompt is deliberately
narrow, and sentences about tables and paragraphs in it are noise.

**It does not apply to edits.** An edited sentence is a wording, not an
instruction, and there is no sound way to turn "you changed these words" into
something to tell the model next time. If the same edit recurs across memos
that is a signal the section prompt should change - but the person has to
decide what it should say.

### Shape, proposed

1. **A control beside a rewrite prompt**, offered once the rewrite has been
   accepted rather than before: keeping an instruction that produced something
   you rejected is not a thing anyone wants.
2. **It writes into the open configuration draft**, never into a published
   revision. Published revisions are immutable by standing decision, and the
   draft is where every other configuration edit lands.
3. **Admin only**, as every configuration edit is, and refused with a plain
   sentence when no draft is open or the person is not an administrator.
4. **It shows the section's current prompt** and lets the person edit the
   combination before it is kept - see the risk below.
5. **It changes nothing until the draft is published**, which the person does
   through the ordinary configuration screen, with the ordinary validation.
6. **It names the memorandum and the section** it will change, because a
   tenant may hold several memoranda and a section called "summary" may exist
   in more than one.

### Severity of the change

**Front end: small.** One control on the rewrite screen, and a panel showing
the current prompt beside the new instruction. The rewrite screen already
holds the prompt, the section heading and the memo, so nothing has to be
fetched that is not already there except the section's current prompt.

**API: one route, or none.** `POST /config/draft/sections` already saves a
section into the draft, admin-gated. If it accepts a partial update, this is a
front-end change only. If it expects a whole section, either it is extended or
the screen reads the section first and writes it back whole. Which of the two
is a five-minute question against `editor.py`, which has not been read for
this item.

**Database: nothing.** The prompt is a column that already exists on a table
that already exists, written through a path that already exists.

**Extraction, composition, the pipeline: untouched.** No document is re-read,
no memo already written changes, nothing is charged. A published section
prompt reaches every memo generated afterwards, which is the existing
behaviour of every composition-side edit and is what makes the loop cheap.

### Risks

**The prompt accreting into a pile.** This is the real one. Ten rounds of
honing appends ten sentences, some contradicting earlier ones, and nobody
remembers why any given clause is there. A section prompt that has grown this
way produces worse output than a short one, and the person cannot tell which
sentence is doing the damage. The mitigation is point 4: never append
silently. Show the current prompt, show the new instruction, and make the
person produce the prompt they want - which is usually a rewrite of the whole
thing, not the two joined with a newline.

**A casual instruction becoming a standing rule.** A rewrite prompt is typed
in seconds against one memo; a section prompt governs every memorandum the
tenant writes. Writing straight into a published revision would let a
throwaway phrase silently change everything. Landing in the draft, and
requiring a publish, is what stops that - and it is also why this must not
grow a "publish immediately" shortcut, however convenient that looks.

**A prompt that only made sense for one memo.** "Lead with the Congolese
sourcing risk" is right for this subject and wrong for the next one. Nothing
can detect that. What the screen can do is show the instruction in the context
of the section's existing prompt, where a subject-specific sentence looks
obviously out of place among general ones.

**Draft contention.** There is one mutable draft per tenant. Two people
honing prompts from two memos are editing the same draft, and one may publish
what the other was still working on. That is an existing property of the
configuration model rather than something this introduces, but this makes it
easier to hit, because it puts configuration editing in front of people who
were not in the configuration screen.

**Nothing to undo it with.** A kept prompt is a configuration edit and shares
the configuration model's answer to mistakes: edit it again, or discard the
draft. There is no undo in the memo screen either (UNDO-01). Since nothing
takes effect before a publish, the window in which a mistake is invisible is
small, but it is not zero.

### What would not change

- Memos already generated. A section prompt is read at generation.
- Anything extracted. Field descriptions and document-type bindings are
  untouched, and no document is re-read.
- The rewrite record. `memo_rewrite` already holds every prompt, who wrote it
  and which model ran it, whether or not it is kept.

### Needed before code

- Confirm the six points above.
- Decide whether keeping a prompt is offered only after a rewrite is accepted,
  or also on a prompt that was discarded.
- `lambda/api/editor.py`, to see whether a section can be saved partially.
