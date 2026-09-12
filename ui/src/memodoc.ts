/**
 * The memo as a document rather than as text.
 *
 * A memorandum is paragraphs, tables, headings and citations. On screen it was
 * none of those: it was the markdown it happens to be stored as, which is how
 * a header table came to read as a row of pipe characters and how a sentence
 * carrying seven references came to end in a paragraph of filenames.
 *
 * This turns the stored markdown into blocks a screen can lay out, and back
 * again. Two rules hold it together:
 *
 *   1. Every block keeps the source it was parsed from. A block nobody edits
 *      is written back character for character - so saving a memo after
 *      editing one paragraph changes that paragraph and nothing else, and the
 *      PDF, which is rendered from this markdown, is unaffected everywhere
 *      else.
 *   2. Nothing is inferred. A line that is not a heading, a table row, a list
 *      item, a quote or a rule is a paragraph, and its text is kept as it was.
 *
 * The markdown the renderer expects is narrow and specific - each table row on
 * its own line, citations in asterisks, a gap as "> **Gap.**" - so the
 * serializer writes that and only that.
 */

// What composition calls a citation: an italic run naming a source file. It
// masks citations before consolidation with a regex requiring one of these
// extensions, so an italic run without one was never a citation on the way in
// and must not become one here.
const CITATION_FILE = /\.(?:pdf|docx|xlsx|txt|json|xml)\b/i;

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "em"; text: string }
  // A RUN of citations, not one: "…increase. *a.docx, section 1* *a.pdf,
  // page 2* *b.pdf, page 5*" is three references to one statement, and the
  // reader wants them as one mark, not three.
  | { kind: "cites"; refs: string[] };

export type Block =
  | { id: string; source: string; kind: "heading"; level: number; inlines: Inline[] }
  // The indent is kept: a paragraph written under a list item carries two
  // spaces, and writing it back flush against the margin moves it out of the
  // item it belongs to.
  | { id: string; source: string; kind: "para"; indent: string; inlines: Inline[] }
  | { id: string; source: string; kind: "quote"; inlines: Inline[] }
  | { id: string; source: string; kind: "rule" }
  // Each item keeps the exact marker and indent it was written with -
  // "  - ", "* ", "3. " - so a list nobody edited is written back as it was
  // and an edited one keeps the shape of the list it belongs to.
  | { id: string; source: string; kind: "list"; ordered: boolean;
      items: { prefix: string; inlines: Inline[] }[] }
  | { id: string; source: string; kind: "table"; head: Inline[][]; rows: Inline[][][];
      align: ("left" | "right" | "centre")[] }
  // Anything unrecognised. Kept whole and shown as written rather than
  // guessed at, so a memo is never silently altered by being displayed.
  | { id: string; source: string; kind: "raw" };

const HEADING = /^(#{1,6})\s+(.*)$/;
const RULE = /^(?:-{3,}|\*{3,}|_{3,})\s*$/;
const QUOTE = /^>\s?(.*)$/;
const BULLET = /^(\s*[-*+]\s+)(.*)$/;
const NUMBERED = /^(\s*\d+[.)]\s+)(.*)$/;
const DIVIDER = /^\s*\|?[\s:|-]*-[\s:|-]*\|[\s:|-]*$/;
// The divider where it sits mid-line, a table emitted without its breaks.
const ONE_LINE_TABLE = /\|(?:\s*:?-{2,}:?\s*\|)+/;

function isTableRow(line: string): boolean {
  return line.trim().startsWith("|");
}

/** Cells of one row. An escaped pipe is content, not a boundary. */
export function splitRow(line: string): string[] {
  const out: string[] = [];
  let cell = "";
  const text = line.trim().replace(/^\|/, "").replace(/\|\s*$/, "");
  for (let i = 0; i < text.length; i++) {
    if (text[i] === "\\" && text[i + 1] === "|") { cell += "|"; i++; continue; }
    if (text[i] === "|") { out.push(cell.trim()); cell = ""; continue; }
    cell += text[i];
  }
  out.push(cell.trim());
  return out;
}

function alignOf(divider: string): ("left" | "right" | "centre")[] {
  return splitRow(divider).map((c) => {
    const left = c.startsWith(":");
    const right = c.endsWith(":");
    return left && right ? "centre" : right ? "right" : "left";
  });
}

/**
 * Emphasis, bold and citations, in order.
 *
 * Underscores are never emphasis here. Real filenames are full of them -
 * CE_Response_Lender_IM_and_KYC_Clarifications_SIGNED.pdf - and reading them
 * as markup consumed the underscores and produced a citation to a file that
 * does not exist.
 */
export function parseInlines(text: string): Inline[] {
  const out: Inline[] = [];
  let plain = "";
  const flush = () => { if (plain) { out.push({ kind: "text", text: plain }); plain = ""; } };

  let i = 0;
  while (i < text.length) {
    if (text.startsWith("**", i)) {
      const end = text.indexOf("**", i + 2);
      if (end > i + 2) {
        flush();
        out.push({ kind: "bold", text: text.slice(i + 2, end) });
        i = end + 2;
        continue;
      }
    }
    if (text[i] === "*") {
      const end = text.indexOf("*", i + 1);
      if (end > i + 1 && !text.slice(i + 1, end).includes("\n")) {
        const body = text.slice(i + 1, end);
        flush();
        if (CITATION_FILE.test(body)) {
          // Gather the whole run: adjacent citations separated by nothing but
          // spaces belong to one statement.
          const refs = [body];
          let at = end + 1;
          for (;;) {
            const next = /^(\s*)\*([^*\n]+)\*/.exec(text.slice(at));
            if (!next || !CITATION_FILE.test(next[2])) break;
            refs.push(next[2]);
            at += next[0].length;
          }
          out.push({ kind: "cites", refs });
          i = at;
        } else {
          out.push({ kind: "em", text: body });
          i = end + 1;
        }
        continue;
      }
    }
    plain += text[i];
    i++;
  }
  flush();
  return out;
}

export function inlinesToMarkdown(inlines: Inline[]): string {
  return inlines.map((n) => {
    if (n.kind === "text") return n.text;
    if (n.kind === "bold") return "**" + n.text + "**";
    if (n.kind === "em") return "*" + n.text + "*";
    return n.refs.map((r) => "*" + r + "*").join(" ");
  }).join("");
}

/** Every citation in a block, in order. */
export function citationsIn(inlines: Inline[]): string[] {
  return inlines.flatMap((n) => (n.kind === "cites" ? n.refs : []));
}

/**
 * The memo as blocks. Each block carries the exact source it came from,
 * INCLUDING the blank lines that followed it, so joining the sources back
 * together reproduces the document byte for byte.
 */
export function parseBlocks(markdown: string): Block[] {
  const lines = markdown.split("\n");
  const blocks: Block[] = [];
  let n = 0;
  let i = 0;

  // The blank lines after a block belong to it, so nothing falls between two
  // blocks and gets lost.
  const take = (from: number, to: number) => {
    let end = to;
    while (end < lines.length && lines[end].trim() === "") end++;
    return { source: lines.slice(from, end).join("\n"), next: end };
  };
  // Distributive, so each member of the union keeps its own fields.
  type NoId<T> = T extends unknown ? Omit<T, "id"> : never;
  const add = (b: NoId<Block>) => blocks.push({ id: "b" + n++, ...b } as Block);

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      // Leading blank lines, or a run this loop has not claimed.
      const { source, next } = take(i, i);
      add({ source, kind: "raw" });
      i = next;
      continue;
    }

    const heading = HEADING.exec(line);
    if (heading) {
      const { source, next } = take(i, i + 1);
      add({ source, kind: "heading", level: heading[1].length,
            inlines: parseInlines(heading[2].trim()) });
      i = next;
      continue;
    }

    if (RULE.test(line.trim())) {
      const { source, next } = take(i, i + 1);
      add({ source, kind: "rule" });
      i = next;
      continue;
    }

    // A table needs a header row and a divider under it. Without the divider
    // it is not a table, and a paragraph that happens to start with a pipe
    // must not be eaten as one.
    if (isTableRow(line) && i + 1 < lines.length && DIVIDER.test(lines[i + 1])) {
      let end = i + 2;
      while (end < lines.length && isTableRow(lines[end])) end++;
      const head = splitRow(line).map(parseInlines);
      const width = head.length;
      const rows = lines.slice(i + 2, end).map((r) => {
        const cells = splitRow(r).map(parseInlines);
        // Ragged rows are the model's, not the reader's problem: pad or trim
        // to the header so the table is a rectangle.
        while (cells.length < width) cells.push([]);
        return cells.slice(0, width);
      });
      const { source, next } = take(i, end);
      add({ source, kind: "table", head, rows, align: alignOf(lines[i + 1]) });
      i = next;
      continue;
    }

    // A whole table emitted on ONE line - "| Item | Status | |---|---| | ... |".
    // The consolidation does this occasionally and telling it not to did not
    // hold. The divider is an unambiguous anchor, since "|---|---|" cannot
    // occur in prose, and its column count gives the width of a row. The
    // source is kept as it came, so a table nobody edits is written back
    // unchanged; editing one writes it out properly.
    const inline = ONE_LINE_TABLE.exec(line.trim());
    if (isTableRow(line) && inline && inline[0].length < line.trim().length) {
      const before = line.trim().slice(0, inline.index);
      const after = line.trim().slice(inline.index + inline[0].length);
      const head = splitRow(before).map(parseInlines);
      const width = head.length;
      const cells = after.trim().split(/\s*\|\s*/).filter((c) => c !== "");
      const rows: Inline[][][] = [];
      for (let k = 0; k < cells.length; k += width) {
        const row = cells.slice(k, k + width).map(parseInlines);
        while (row.length < width) row.push([]);
        rows.push(row);
      }
      if (width > 0 && rows.length > 0) {
        const { source, next } = take(i, i + 1);
        add({ source, kind: "table", head, rows, align: alignOf(inline[0]) });
        i = next;
        continue;
      }
    }

    if (QUOTE.test(line)) {
      let end = i;
      while (end < lines.length && QUOTE.test(lines[end])) end++;
      const body = lines.slice(i, end)
        .map((l) => (QUOTE.exec(l) as RegExpExecArray)[1]).join(" ").trim();
      const { source, next } = take(i, end);
      add({ source, kind: "quote", inlines: parseInlines(body) });
      i = next;
      continue;
    }

    if (BULLET.test(line) || NUMBERED.test(line)) {
      const ordered = NUMBERED.test(line) && !BULLET.test(line);
      const match = ordered ? NUMBERED : BULLET;
      let end = i;
      const items: { prefix: string; inlines: Inline[] }[] = [];
      while (end < lines.length && match.test(lines[end])) {
        const m = match.exec(lines[end]) as RegExpExecArray;
        items.push({ prefix: m[1], inlines: parseInlines(m[2].trim()) });
        end++;
      }
      const { source, next } = take(i, end);
      add({ source, kind: "list", ordered, items });
      i = next;
      continue;
    }

    // A paragraph runs to the next blank line or the start of another block.
    let end = i;
    while (end < lines.length) {
      const l = lines[end];
      if (l.trim() === "") break;
      if (end > i && (HEADING.test(l) || RULE.test(l.trim()) || QUOTE.test(l)
                      || BULLET.test(l) || NUMBERED.test(l) || isTableRow(l))) break;
      end++;
    }
    const { source, next } = take(i, end);
    const indent = /^\s*/.exec(lines[i])?.[0] ?? "";
    add({ source, kind: "para", indent,
          inlines: parseInlines(lines.slice(i, end).join(" ").trim()) });
    i = next;
  }

  return blocks;
}

/** The document, from its blocks. Untouched blocks are written back as they
 *  came; an edited one carries the markdown the editor produced. */
export function serializeBlocks(blocks: Block[]): string {
  return blocks.map((b) => b.source).join("\n");
}

/** The source for a block that has been edited. What the renderer expects:
 *  one table row per line, citations in asterisks, headings at their level. */
export function blockToMarkdown(block: Block, trailing: string): string {
  const cell = (c: Inline[]) => inlinesToMarkdown(c).replace(/\|/g, "\\|");
  let body: string;

  switch (block.kind) {
    case "heading":
      body = "#".repeat(block.level) + " " + inlinesToMarkdown(block.inlines);
      break;
    case "para":
      body = block.indent + inlinesToMarkdown(block.inlines);
      break;
    case "rule":
      // Written as the source had it: a memo uses --- between sections and a
      // different rule would change the page.
      body = block.source.trim().split("\n")[0];
      break;
    case "quote":
      body = "> " + inlinesToMarkdown(block.inlines);
      break;
    case "list":
      body = block.items.map((it) =>
        it.prefix + inlinesToMarkdown(it.inlines)).join("\n");
      break;
    case "table": {
      const rule = block.align.length === block.head.length
        ? block.align
        : block.head.map(() => "left" as const);
      // "| | |" - the header of the front-matter table - has empty cells. A
      // cell padded on both sides would write "|  |  |" and change a line
      // nobody edited.
      const line = (cells: Inline[][]) =>
        "|" + cells.map((c) => {
          const text = cell(c);
          return text ? " " + text + " " : " ";
        }).join("|") + "|";
      const divider = "|" + rule.map((a) =>
        a === "centre" ? ":---:" : a === "right" ? "---:" : "---").join("|") + "|";
      body = [line(block.head), divider, ...block.rows.map(line)].join("\n");
      break;
    }
    default:
      body = block.source.replace(/\n+$/, "");
  }
  // No trailing spaces. Two of them at the end of a line are a hard break in
  // markdown, and a paragraph broken in two leaves the first half ending in
  // the space that was before the caret.
  return body.replace(/[ \t]+$/gm, "") + trailing;
}

/** The blank space a block's source ends with, so an edit keeps the spacing
 *  around it and the document does not close up.
 *
 *  Whitespace, not newlines: a memo carries lines holding a single space, and
 *  counting only newlines rewrote them away. */
export function trailingOf(source: string): string {
  return source.slice(source.trimEnd().length);
}
