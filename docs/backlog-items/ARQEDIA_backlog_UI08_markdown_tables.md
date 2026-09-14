# ARQEDIA — Backlog Item

## UI-08 · Tables render as pipe characters in the browser

| | |
|---|---|
| Status | Diagnosed, not fixed |
| Priority | High for its size. It is the first thing a reader sees |
| Type | Front end |
| Raised | 10 September 2026, proposed. Diagnosed 11 September 2026 |

---

### Observation

The header block of every memo renders as one running line of pipes -
`| | | |---|---| | **Subject** | COCOA EMPIRE UGANDA LIMITED | ...` - rather
than as a table. Subject, Engagement, Generated, Documents reviewed and Sources
cited are all present and correct; only the table is unrendered. Reported on
10 September as affecting every table in a memo, not only the header.

Seen again on 11 September on memo 94.1, in the section rewrite screen. That
screen renders through the same function as the reader, so it shows the same
fault; it did not introduce it.

### Cause

`ui/src/Memo.tsx` renders with `<ReactMarkdown components={{ em: Citation }}>`
and passes no plugins. react-markdown supports CommonMark only; tables are a
GitHub Flavored Markdown extension and need the `remark-gfm` plugin. Without it
the table markdown is ordinary paragraph text, which is exactly what is on
screen.

`unwrapTables` in the same file is not the cause and not the cure. It repairs a
table the model emitted on one line by splitting it back into rows. That makes
the markdown correct; it does not make the renderer understand tables.

Checked against the react-markdown documentation, 11 September.

### Fix

1. Confirm from `ui/package.json` whether `remark-gfm` is already installed.
2. Add it, and pass `remarkPlugins={[remarkGfm]}` in `markdownOf` in
   `Memo.tsx`. Since the section rewrite work, every rendering in that file -
   reader, editor preview, rewrite screen - goes through `markdownOf`, so one
   change reaches all three.
3. Check the rendered tables against the existing `.memo table` styles in
   `index.css`, by looking at them, not by reasoning about them.

### Not in scope

- The PDF. The renderer is a separate path and has not been checked for this.
- `remark-gfm` turns on all of GFM, not only tables: autolink literals,
  footnotes, strikethrough and task lists, per its readme checked on
  11 September. Strikethrough accepts a single tilde by default, so a memo
  writing `~500~` would render struck through. Pass `singleTilde: false`,
  and look for footnote and task-list syntax in real memo text before
  shipping.

### Acceptance

The header block and every section table render as tables in the reader, the
editor preview and the rewrite screen, with no change to the saved markdown.
