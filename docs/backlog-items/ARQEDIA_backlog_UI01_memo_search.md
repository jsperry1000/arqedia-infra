# ARQEDIA — Backlog Item

## UI-01 · Search within a memo

| | |
|---|---|
| Status | Not built |
| Priority | Low effort, high daily value |
| Type | Front end only. No API, no schema, no cost |
| Raised | 30 August 2026 |

---

### What

A search bar on the memo, highlighting every match in the rendered memo and,
when editing, in the editor pane at the same time.

### Why

A seventeen-page memo drawn from thirty documents is read by looking for
something: a person, a registration number, a bank. The browser's own search
finds text in the rendered pane but not in the editor, and an editor checking
a name against the source has to find it twice.

### Behaviour

- Match count and position, "3 of 11", with next and previous.
- Every match highlighted; the current one distinguished from the rest.
- While editing, matches highlight in BOTH panes, so the same passage is
  visible in the markdown and in the rendering.
- Selecting a match scrolls both panes to it, overriding the proportional
  sync for that jump.
- Case-insensitive by default. Whole-word and case-sensitive as toggles only
  if they prove necessary.

### The one real difficulty

**Highlighting inside a textarea is not directly possible.** A textarea holds
plain text and cannot carry markup. The usual solution is a highlight layer
positioned behind the textarea, mirroring its content, scroll position and
metrics exactly. It works, and it is fiddly: font, padding, line height and
wrapping have to match to the pixel or the highlights drift from the text.

Two ways round it, both worth weighing before building:

- **Accept a weaker editor behaviour** - scroll the editor to the match and
  select it natively, without highlighting the others. Much simpler, and
  arguably enough.
- **Replace the textarea** with an editor component that supports decorations.
  That is the rich-editor work, and this should not be the reason for doing
  it.

Rendered-pane highlighting is straightforward either way.

### Notes

- **Do not highlight inside a citation.** A search for "page 1" would light up
  every reference on the page and drown the thing being looked for.
- Search state should survive switching into and out of editing.

### Acceptance

Typing in the search bar highlights every match in the rendered memo, reports
how many there are, and moves between them. While editing, a match is locatable
in both panes.
