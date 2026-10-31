/**
 * Editing a block of the memo where it sits.
 *
 * The person edits the document, not its storage. So a block being edited
 * looks exactly as it reads - same type, same table, same spacing - and what
 * comes back out is markdown of the narrow shape the renderer expects.
 *
 * Citations do not survive being typed around by accident. Each reference is
 * one locked mark the editor cannot put a caret inside, carrying it on the
 * element. Deleting the mark deletes that reference, deliberately: that is
 * how a person removes one.
 *
 * ONE MARK A REFERENCE, NOT ONE A RUN (26 October 2026). A run was one mark,
 * so taking out one reference took out every other one beside it - and a
 * citation to a deleted document has to come out alone for a revision to
 * save. Marks side by side are read back as one run, as they were written.
 * What the mark must never do is come back
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

/** What one reference reads as on its mark: enough of the file to tell two
 *  apart, and the page. The whole of it is the mark's title.
 *
 *  THE END OF THE NAME, NOT THE START. One deal's files share their start -
 *  "Meridian-Place-Property-Inspection…", "Meridian-Place-Property-Appraisal…"
 *  - so cutting the end off made two of them read the same, and the mark
 *  being deleted could not be told from the one beside it. */
export function chipLabel(ref: string): string {
  const m = /^(.*?)\.(?:pdf|docx|xlsx|txt|json|xml)\b\s*(?:,\s*(?:page|section|sheet)\s*(\d+))?/i
    .exec(ref.trim());
  const name = m ? m[1] : ref.trim();
  const short = name.length > 28 ? "…" + name.slice(-27) : name;
  return m?.[2] ? short + ", p. " + m[2] : short;
}

/** What one reference looks like while the block is being edited. `gone`
 *  marks one whose document has been deleted, in the same black the reader
 *  gives it. */
export function citeChipHtml(ref: string, gone = false): string {
  return '<span class="cite-chip' + (gone ? " gone" : "")
    + '" contenteditable="false" data-refs="'
    + escapeHtml(JSON.stringify([ref])) + '" title="'
    + escapeHtml(ref + (gone ? " (deleted)" : "")) + '">'
    + escapeHtml(chipLabel(ref)) + "</span>";
}

/** Inline content as editable HTML. `gone` says which references name a
 *  deleted document. */
export function inlinesToHtml(inlines: Inline[],
                              gone: (ref: string) => boolean = () => false): string {
  if (inlines.length === 0) return "";
  return inlines.map((n) => {
    if (n.kind === "text") return escapeHtml(n.text);
    if (n.kind === "bold") return "<strong>" + escapeHtml(n.text) + "</strong>";
    if (n.kind === "em") return "<em>" + escapeHtml(n.text) + "</em>";
    if (n.kind === "boldem") {
      return "<strong><em>" + escapeHtml(n.text) + "</em></strong>";
    }
    return n.refs.map((r) => citeChipHtml(r, gone(r))).join("");
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
    if (n.kind === "bold" || n.kind === "em" || n.kind === "boldem") {
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
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (n.kind !== "cites" && n.text === "") continue;
    const last = out[out.length - 1];
    // Marks side by side are one run, as they were written; so are marks
    // with nothing but a space between, which is how a run is written out.
    if (n.kind === "cites" && last?.kind === "cites") {
      last.refs = [...last.refs, ...n.refs];
      continue;
    }
    if (n.kind === "text" && !n.text.trim() && last?.kind === "cites"
        && nodes[i + 1]?.kind === "cites") continue;
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
 * Only the marks the memo uses are read back: bold, emphasis, the two
 * together, and citation marks. A browser that pastes a font tag, a colour or a heading contributes
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
      // Both at once is a mark of its own, not bold with the slant lost.
      out.push(bold && em ? { kind: "boldem", text }
             : bold ? { kind: "bold", text }
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
