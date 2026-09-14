# ARQEDIA — Backlog Item

## RW-01 · Section rewrite: what was left

| | |
|---|---|
| Status | Feature built and verified. Follow-ups open |
| Priority | Low to medium, per item |
| Type | Front end, API, pricing |
| Raised | 11 September 2026 |

---

### What was built

A person writes a prompt under any `##` section of a memo and presses Go. The
model rewrites each prompted section; the result appears beside the current
text to accept or discard; accepted sections are saved as a new revision that
records which sections the model wrote and at whose prompt.

| PR | |
|---|---|
| #118 | `012_memo_rewrite.sql`; composition's rewrite entry point |
| #119 | API routes `POST` and `GET /memos/{memo_id}/rewrites`; `revise` records accepted rewrites; `GET /memos/{id}` returns them |
| #120 | Rewrite mode on the memo screen |

Verified live on 11 September: memo 95 is revision 2 of memo 94, saved by
joeschmoe1000@gmail.com, carrying rewrites 3 and 4 (sections I and III), both
done with no citations dropped.

Rules the build holds to, for whoever changes it:

- The model sees only the section's current text and the prompt. It cannot
  add a fact.
- Citations are masked and restored with composition's own functions.
- The heading is removed before the call and restored after; the model never
  writes it.
- A section over 40,000 characters, or a reply that used all 4,096 output
  tokens, is refused rather than saved incomplete.
- A failure is written to the row and never retried by Lambda, so no model
  call is spent twice.
- Nothing about a memo changes until `revise` is called with the accepted
  rewrite ids. A rewrite already accepted into one revision is never moved.

---

### 1 · Price

Free by decision on 11 September. Every row carries `tokens_in`, `tokens_out`
and `model_id`, including discarded and failed rewrites, so the cost per
tenant is already recorded. Neither `pipeline_spec_v1` nor
`wallet_entitlement_spec_v1` mentions a rewrite. When it is priced,
the charge follows the click on Go, as every other charge does.

### 2 · Resume after a reload

The screen holds a Go in memory. Refresh the page mid-rewrite and the work is
not lost - the rows complete and stay on record - but the screen no longer
shows it. `GET /memos/{memo_id}/rewrites` with no ids already returns the
latest ten for the memo; the screen does not use it.

### 3 · The screen gives up before the function does

The screen marks a section failed after five minutes without an answer.
Composition's timeout is 600 seconds. A rewrite finishing between the two
completes on the row while the screen says it failed. Rare - a section takes
seconds - but the two numbers should agree, or the screen should look once
more before saying so.

### 4 · Test rows

`memo_rewrite` rows 1 and 2 on tenant 2 are test data from the build, marked
`prompted_by` = `stage-2-test` and `stage-3-test`. Row 1 names memo 0, which
does not exist. Both are unaccepted and harmless. Left on record rather than
deleted.

### 5 · Sections without a `##` heading

The title, the header table and any text before the first `##` heading cannot
be rewritten, by design. A memo with no `##` headings says so and offers
nothing. A memorandum configured with a different heading level would offer
nothing either; composition writes `##` today.

### 6 · UI-08 shows through

The rewrite screen renders through the same function as the reader, so its
tables show as pipes until UI-08 is fixed.

### 7 · Work in progress is lost on leaving

Raised by the user on 11 September. Everything short of a saved revision is
held in the page, and every way out of the rewrite screen throws it away:

- **Cancel** asks, then discards prompts, results and accepted sections.
- **Edit before saving** carries the text into the editor, but **Cancel** there
  discards all of it, carried rewrites included. There is no way back from Edit
  to Rewrite.
- **Back**, a reload, or opening another memo discards it without asking.

The rewrite rows themselves stay on record. What is lost is the person's work:
prompts typed and not yet sent, which rewrites were accepted, and hand edits.

Wanted: leaving and coming back returns the person to where they were. A
prompt still does nothing until Go is pressed.

Precedent: `PUT /config/draft/working` exists because a proposal's decisions,
held only in the browser, were lost to a closed tab. Proposal and decisions
are in the 11 September session; not built.
