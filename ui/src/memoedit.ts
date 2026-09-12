/**
 * Editing a block of the memo where it sits.
 *
 * The person edits the document, not its storage. So a block being edited
 * looks exactly as it reads - same type, same table, same spacing - and what
 * comes back out is markdown of the narrow shape the renderer expects.
 *
 * Citations do not survive being typed around by accident. Each run is one
 * locked mark the editor cannot put a caret inside, carrying its references
 * on the element. Deleting the mark deletes the run, deliberately: that is
 * how a person removes a reference. What the mark must never do is come back
 * as text, half a filename, or a reference to a document that was never a
 * source of this memo, because the save refuses that and the person would be
 * left holding an edit they cannot save.
 */

import type { Inline } from "./memodoc";

// Tags that end a line when pasted in. Their text is kept; their shape is
// not, because a memorandum is not a place for a clipboard to bring its own
// headings and tables.
const BLOCK_TAG = /^(?:p|div|li|ul|ol|h[1-6]|blockquote|tr|table|section|article|br)$/;

const ESCAPE: Record<string, string> = {
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;",
};

function escapeHtml(text: string): string {
  return text.replace(/[&<>"]/g, (c) => ESCAPE[c]);
}

/** What a run of citations looks like while the block is being edited: the
 *  same small mark it wears when it is put away in the reader. */
export function citeChipHtml(refs: string[]): string {
  return '<span class="cite-chip" contenteditable="false" data-refs="'
    + escapeHtml(JSON.stringify(refs)) + '" title="'
    + escapeHtml(refs.join("; ")) + '">' + refs.length + "</span>";
}

/** Inline content as editable HTML. */
export function inlinesToHtml(inlines: Inline[]): string {
  if (inlines.length === 0) return "";
  return inlines.map((n) => {
    if (n.kind === "text") return escapeHtml(n.text);
    if (n.kind === "bold") return "<strong>" + escapeHtml(n.text) + "</strong>";
    if (n.kind === "em") return "<em>" + escapeHtml(n.text) + "</em>";
    return citeChipHtml(n.refs);
  }).join("");
}

/** Runs of the same kind, joined; empty runs dropped. Typing inside a bold
 *  word produces three bold nodes, and writing them back as three would put
 *  "**a****b**" into the markdown. */
function tidy(nodes: Inline[]): Inline[] {
  const out: Inline[] = [];
  for (const n of nodes) {
    if (n.kind !== "cites" && n.text === "") continue;
    const last = out[out.length - 1];
    if (last && last.kind === n.kind && n.kind !== "cites" && last.kind !== "cites") {
      last.text += n.text;
      continue;
    }
    out.push(n.kind === "cites" ? { kind: "cites", refs: [...n.refs] } : { ...n });
  }
  // Emphasis cannot begin or end on a space in markdown: "* text *" is not
  // italic. The space belongs outside the run.
  const spaced: Inline[] = [];
  for (const n of out) {
    if (n.kind === "bold" || n.kind === "em") {
      const lead = /^\s*/.exec(n.text)![0];
      const tail = /\s*$/.exec(n.text)![0];
      const body = n.text.slice(lead.length, n.text.length - tail.length);
      if (!body) { if (n.text) spaced.push({ kind: "text", text: n.text }); continue; }
      if (lead) spaced.push({ kind: "text", text: lead });
      spaced.push({ ...n, text: body });
      if (tail) spaced.push({ kind: "text", text: tail });
      continue;
    }
    spaced.push(n);
  }
  return tidy2(spaced);
}

function tidy2(nodes: Inline[]): Inline[] {
  const out: Inline[] = [];
  for (const n of nodes) {
    if (n.kind !== "cites" && n.text === "") continue;
    const last = out[out.length - 1];
    if (last && last.kind === n.kind && n.kind === "text" && last.kind === "text") {
      last.text += n.text;
      continue;
    }
    out.push(n);
  }
  return out;
}

/**
 * What the editor now holds, as inline content.
 *
 * Only the marks the memo uses are read back: bold, emphasis and citation
 * marks. A browser that pastes a font tag, a colour or a heading contributes
 * its text and nothing else - a memo is not a place for a reader's
 * clipboard formatting to arrive unannounced.
 */
export function nodesToInlines(root: Node): Inline[] {
  const out: Inline[] = [];

  const walk = (node: Node, bold: boolean, em: boolean) => {
    if (node.nodeType === 3) {
      // A contenteditable ends lines with a non-breaking space; it is a space.
      const text = (node.nodeValue ?? "").replace(/\u00a0/g, " ");
      if (!text) return;
      out.push(bold ? { kind: "bold", text }
             : em ? { kind: "em", text }
             : { kind: "text", text });
      return;
    }
    if (node.nodeType !== 1) return;
    const el = node as HTMLElement;

    const refs = el.getAttribute("data-refs");
    if (refs !== null) {
      try {
        const parsed = JSON.parse(refs);
        if (Array.isArray(parsed) && parsed.every((r) => typeof r === "string")) {
          out.push({ kind: "cites", refs: parsed });
        }
      } catch { /* a mark we cannot read is dropped rather than guessed at */ }
      return;
    }

    const tag = el.tagName.toLowerCase();
    if (tag === "br") { out.push({ kind: "text", text: " " }); return; }

    const weight = el.style?.fontWeight ?? "";
    const style = el.style?.fontStyle ?? "";
    const nowBold = bold || tag === "strong" || tag === "b"
      || weight === "bold" || weight === "700";
    const nowEm = em || tag === "em" || tag === "i" || style === "italic";

    // A block inside a block - a pasted paragraph or heading - separates
    // rather than running two sentences together.
    const breaks = BLOCK_TAG.test(tag);
    if (breaks && out.length) out.push({ kind: "text", text: " " });
    el.childNodes.forEach((c) => walk(c, nowBold, nowEm));
    if (breaks) out.push({ kind: "text", text: " " });
  };

  root.childNodes.forEach((c) => walk(c, false, false));
  return tidy(out);
}

/** Text content only, for a heading or a table cell where markup would be
 *  noise. Citations are kept. */
export function plainInlines(root: Node): Inline[] {
  return nodesToInlines(root);
}
