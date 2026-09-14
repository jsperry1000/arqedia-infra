# ARQEDIA — Backlog Item

## UX-01 · The UI work required for a deliverable MVP

| | |
|---|---|
| Status | Not built |
| Type | Front end, one CSS token addition, one registry field (UX-07 only) |
| Raised | 13 September 2026 |
| Decisions | All seven settled, 13 September 2026. See §Decisions |
| Depends on | BR-01 (fourth brand colour), UI-03 (revision provenance) |

---

## Introduction — what stands between here and a deliverable MVP

The configuration screen now holds the right objects. What it does not yet hold
is a shape a person can work in for an hour without losing their place. Every
item below came from working the screen, and they fall into six groups.

- **Nothing stays put.** The Configure header, the part selector, Back, Publish
  and Discard all scroll away. A person deep in a section list has no way out
  and no way to save without scrolling back up. This is the single largest
  complaint and it is one layout change.
- **The entry to a report is buried.** Choosing which report to work on sits
  underneath the report's own sections. It belongs above everything, behind a
  deliberate choice of three: open one, start from nothing, start from a report
  the tenant already writes.
- **Publish is unexplained.** One Publish covers the whole configuration, not
  the report in front of you. Nothing on the screen says so. Discard throws away
  a draft with no guard.
- **Destruction is unguarded.** Sections, facts, documents, groups and whole
  memoranda all delete on one click.
- **Work in progress is invisible.** Uploading a file and generating a memo both
  require leaving the screen and coming back. There is no working indicator, and
  a refresh loses the place.
- **There is no front door.** A tenant logging in for the first time lands in a
  configuration editor with no explanation of what the product is or what it
  costs.

One item is not cosmetic. Section numbering (UX-07) adds a field the registry
does not have and must be agreed against the schema before it is written.
Everything else is front end over interfaces that already exist.

---

## The work list

### Shell and navigation

**UX-02 · Pin the working header.**
- One sticky header across the configuration screen carrying, in order: Back,
  the report selector, the part selector (Report sections · Facts · Document
  types), Discard, Publish.
- Back is a filled pill in `brand_deep` with reversed text, first item, always
  visible.
- Publish sits immediately beside Discard, not at the foot of the page.
- When a subsection is opened, its own heading and close control pin directly
  beneath the header, so closing is always one click.
- The header does not scroll. Nothing below it changes.

**UX-03 · A menu rail.**
- A fixed rail on the **left**, carrying the top-level destinations, freeing the
  header for the working controls in UX-02.
- The rail is a set of routes. It lands after `ux-routing`, not before.

**UX-19 · An account menu on the tenant name.**
- The signed-in line in the header becomes a control. Clicking it opens a small
  menu holding Sign out.
- Sign out leaves the foot of the rail. One place to leave, not two.
- The header already carries the email and tenant. That line is the trigger.
- Closes on a click outside or Escape, like every other panel on the screen.
- Room for Settings and the seat's role later. Sign out is what MVP needs.

### Entering a report

**UX-04 · Configure a report opens a choice, not a screen.**
- Clicking **Configure a report** in the top menu opens a small dropdown panel
  with three options: open an existing report, create from scratch, create from
  a report you already write.
- Open an existing report reveals a list in the same panel, five rows visible
  then scroll, selecting one opens straight into it.
- Create from scratch opens an empty report with one untitled section.
- Create from a report you already write is `derive_template`
  (`config_editors_spec_v1.md` §6A). **In the MVP.** The functions work; the
  screen around them is the work.

**UX-05 · Say what publishing covers.**
- A single line in the pinned header: the live revision number, that the draft
  covers the whole configuration, and that the live revision stays in use until
  Publish.
- Publish opens the existing change summary before committing.
- Discard asks for confirmation whenever the draft differs from the live
  revision, naming what will be lost.
- The line reads that publishing applies every change across all memoranda at
  once.
- Overlaps UI-03, which adds the revision label and fork provenance. Do UI-03
  first and this becomes copy rather than plumbing.

**UX-15 · Switching memorandum must not lose an open edit. CLOSED, verified 13 September 2026.**
- Tested on the live screen: an open, unsaved edit survives switching memorandum
  and switching back. The selector already routes through the drawer guard.
- Saved changes were never at risk: editors write to the one draft, which is
  configuration-wide, and it holds until Publish.
- No work. Recorded so it is not re-tested.

**UX-16 · One Back, the same everywhere.**
- The dark pill built for the configuration bar becomes the only Back in the
  product. Engagements, the engagement, the memo, Settings and the plain
  Configure screens all use it.
- One component, one class. No page carries its own Back styling.
- It sits in the same position on every screen, top left of the working area,
  beside the rail.
- It stays visible while the page scrolls, on every screen and not only on
  Configure.
- Tenant colour: it reads `brand_deep` the way the configuration bar does,
  including the platform fallback where no colour is set.
- The `ux-shell` work left the plain Configure screens and the other views on a
  text link. This closes that.

**UX-17 · The report chooser. CLOSED, verified 13 September 2026.**
- Open an existing report lists the memoranda in the configuration, one row
  each, five visible then scroll.
- Create from a report you already write opens the file picker and nothing
  else.
- Choosing an option replaces the three options, with a link back to them.
- Delivered on `ux-surfaces`.

**UX-18 · Resume a proposal, inside the proposer. CLOSED, verified 13 September 2026.**
- The proposer's own start screen already listed unfinished proposals through
  `api.proposals()` and reopened them by its existing path.
- The resume list came out of the chooser. No endpoint was added.
- Delivered on `ux-surfaces`.

**UX-21 · The proposer is a first cut, not a second editor. Supersedes part of UX-17 and UX-18.**
- **The third option opens the proposer page.** Clicking *create from a report
  you already write* must not fire a file dialog. It lands on the proposer,
  which carries its own upload control. The person chooses the file there.
- **The proposer does one job:** a first cut at the sections, and its guess at
  which facts each section needs. Correcting individual facts line by line is
  not its job.
- **Accept names the memorandum, writes the proposal into the draft, and opens
  the configuration editor on that new memorandum.** No intermediate screen.
  The editor is the better instrument and already exists; the proposer should
  not reproduce it.
- **The review screen stops duplicating the editor.** Numerals, add-a-section,
  add-a-fact, per-fact section pickers and the fact search all belong to the
  configuration editor. The proposer keeps the name, the section list with its
  ticks, and the fact ticks — enough to judge whether the cut is close.
- **The resume list comes out entirely**, including from the proposer. Once a
  proposal is accepted the work continues in the configuration editor, and the
  memorandum appears under *open an existing report*. That is the resume path.
- `GET /config/draft/proposals` stays in the API. Nothing calls it from the
  screen. Recorded rather than removed.

### The editing surfaces

**UX-06 · Pills.**
- Section rows render as pills: sort control, title, a Fields pill, an Edit
  pill, all inline on one row.
- The Fields pill carries its own count, reading `Fields · 8`.
- Subsections render inside a contrasting pill using `brand_light`, which does
  not exist yet — BR-01 must land first or the pill borrows `brand_mid` and
  outweighs the heading above it.
- One radius token for every pill, set once and used everywhere.

**UX-07 · Configurable numbering.**
- The Sort control on the left of a section row opens a menu with two levels,
  setting the numbering style for that level and its children.
- Styles offered: integer, upper Roman, lower Roman, upper alpha, lower alpha.
- **One global scheme, applied to every memorandum.** Expressed level by level,
  so `I · 2 · a` and `1 · a · ii` are both reachable. No per-section override.
- **Proposed, not in the schema.** A section today carries a numeral and a
  title. The scheme is a new field on the configuration, not on a memorandum
  and not on a section. It is the only registry change in this item and is
  agreed against the schema before it is written.

**UX-08 · Fields in use, at the top.**
- Opening a section lists the fields it already binds at the top of the fields
  panel, above the search box.
- A mid-colour rule separates them from the unbound list below.
- The unbound list keeps its search. The bound list does not need one.

**UX-20 · The tint covers the whole panel and is too dark.**
- Observed 13 September, after `ux-surfaces` merged.
- As built, the tenant's light colour fills the entire open-section panel:
  the bound facts, the rule, the search box and the whole unbound list.
- Only the **bound facts** carry a background. Everything below the rule —
  search box and unbound lists — sits on white.
- The bound-facts background is the canvas colour, not the tenant's light.
  It marks which part of the panel is in use; it is not brand.
- The rule beneath the bound facts stays as it is.
- **The bound facts stay put while the unbound list scrolls.** They pin
  beneath the section heading, along with the rule and the search box. The
  point of the panel is to see what is already chosen while looking for what
  to add next, and that fails the moment the chosen list scrolls away.
- The bound block has its own ceiling: past roughly a third of the panel it
  scrolls within itself rather than pushing the unbound list off the screen.
- **CSS to be rendered, not reasoned.** A scroll on an inner element is
  confined to that element — the fault that cost four attempts on the grouped
  layout. Render it and look, or ask.

**UX-09 · The how-it-should-read box grows.**
- The narrative prompt field grows with its content to a ceiling of 25 lines,
  then scrolls internally.
- No manual resize handle.

**UX-10 · Confirm every deletion.**
- Sections, facts, document types and field groups each ask before deleting.
- **Deleting a whole memorandum asks too**, and is the heaviest of them: it
  takes its sections and every binding with it. The confirmation names the
  memorandum and the number of sections that go with it, and requires the
  memorandum's name to be typed.
- The last memorandum cannot be deleted, and the control says so rather than
  failing on click.
- The confirmation names the object and says what still references it, using
  `change_impact`, which already computes this for the publish summary.
- It also says the deletion is draft-only until Publish and reaches no filed
  document, because "delete" reads as destruction and here it is not.

### Work in progress

**UX-11 · The screen updates itself.**
- After files are added, rows appear and advance through their states without
  leaving the screen and returning.
- The same for memo generation: the memo appears when it is ready.
- **Polling.** The browser asks the API while any row is unfinished and stops
  once every row has reached a terminal state. Front end only, no new
  infrastructure, replaceable by a push channel later without touching a screen.

**UX-12 · A working indicator.**
- One indicator used everywhere something is running: uploading, analysing,
  filing, generating, publishing.
- It states what is running, not merely that something is.
- Respects reduced motion, per the quality floor in `frontend_onboarding_spec_v1.md` §6.

**UX-13 · A refresh returns you where you were.**
- Report, part and open section survive a browser refresh.
- Only achievable once D1 is settled.

### First run

**UX-14 · An introduction page.**
- Shown on login before any editor: what the product does, the order of work
  (configure, publish, then upload), and what a filing costs.
- A purchase link and a **Get started** pill.
- Copy drafted from `ARQEDIA_UI_GUIDE_DRAFT.md` and marked draft, but the page
  itself is functional and routed.

---

## Decisions — settled 13 September 2026

| | | |
|---|---|---|
| D1 | Routing | No router today. One is added first, as its own branch. A URL per surface. |
| D2 | Rail side | Left. |
| D3 | Numbering | One global scheme applied to every memorandum. A field on the configuration. |
| D4 | Publish wording | The screen says publishing applies changes across all memoranda at once. |
| D5 | Derive from an existing report | In the MVP. |
| D6 | Brand colours | BR-01 lands before any pill work. |
| D7 | Live updates | Polling. |

---

## Branches, in order

Each is merged to main before the next starts. A short push summary on every
push. Nothing merges until the screen has been rendered and looked at.

| Branch | Carries | State |
|---|---|---|
| `br-01-brand-light` | BR-01, the fourth brand colour | Merged 13 September |
| `ux-routing` | The router. Nothing else. | Merged 13 September |
| `ux-shell` | UX-02, UX-03, UX-13 | Merged 13 September |
| `ux-entry` | UX-04, UX-05, UX-16 | Merged 13 September |
| `ux-surfaces` | UX-17, UX-18, UX-06, UX-08, UX-09, UX-10 | Next |
| `ux-progress` | UX-21, UX-20, UX-11, UX-12, UX-14, UX-19 | Next |
| Held back | UX-07, until its field is agreed against the schema | |

---

## Not in this item

UI-01 (search within a memo), UI-02 (citation spacing) and AUD-01 (fact to
files) are open and unaffected by anything above.
