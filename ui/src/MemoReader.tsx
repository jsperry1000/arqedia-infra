import { useEffect, useMemo, useRef, useState } from "react";
import { parseBlocks, serializeBlocks, blockToMarkdown, trailingOf, citationsIn,
         type Block, type Inline } from "./memodoc";
import { inlinesToHtml, nodesToInlines } from "./memoedit";

/**
 * The memo as it reads.
 *
 * A memorandum is prose and tables, and that is what this draws: real tables,
 * headings, gap callouts. What it does NOT draw is the markdown underneath -
 * the pipes, the asterisks, the filenames - which is storage, not something a
 * person should have to read past.
 *
 * Editing happens here too, in the document rather than beside it. An edit
 * icon on a block opens that block where it sits: same type, same table, same
 * spacing, so nothing moves when a person starts typing. What comes out is
 * markdown of the shape the renderer expects, and every other block is
 * written back exactly as it came.
 *
 * Citations are the other half of that. A finished sentence carrying seven
 * references ended in a paragraph of filenames longer than the sentence. Each
 * run of references is one small mark instead, and the marks stay out of the
 * way until somebody wants them - which is what checking a memo means, and is
 * a thing done a paragraph at a time rather than all at once.
 */

export type Ref = {
  documentId: number;
  filename: string;
  unit: number | null;
  text: string;
};

/**
 * Split a citation run into the documents it names.
 *
 * "Sources: a.pdf, page 1; b.docx, section 2" is eight citations on some
 * sections, not one - matching only the first meant every click opened the
 * same document.
 */
export function parseRefs(raw: string, byFilename: Record<string, number>):
    (string | Ref)[] {
  const pattern =
    /([A-Za-z0-9._()\-]+\.(?:pdf|docx|xlsx|txt|json|xml))(\s*,\s*(?:page|section|sheet)\s*(\d+))?/gi;
  const out: (string | Ref)[] = [];
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = pattern.exec(raw)) !== null) {
    const documentId = byFilename[m[1]];
    if (!documentId) continue;
    if (m.index > last) out.push(raw.slice(last, m.index));
    out.push({ documentId, filename: m[1], unit: m[3] ? Number(m[3]) : null,
               text: m[0] });
    last = m.index + m[0].length;
  }
  if (last < raw.length) out.push(raw.slice(last));
  return out;
}

/** The mark a run of citations leaves in the text when they are put away, and
 *  the references themselves when they are out. */
function Citations({ refs, shown, onToggle, byFilename, onOpen }: {
  refs: string[];
  shown: boolean;
  onToggle: () => void;
  byFilename: Record<string, number>;
  onOpen: (ref: Ref) => void;
}) {
  if (!shown) {
    return (
      <button type="button" className="cite-mark" onClick={onToggle}
              title={refs.length === 1 ? "Show the source"
                                       : `Show ${refs.length} sources`}>
        {refs.length}
      </button>
    );
  }
  return (
    <span className="cite-run">
      {refs.map((raw, i) => (
        <em className="ref" key={i}>
          [
          {parseRefs(raw, byFilename).map((p, k) =>
            typeof p === "string" ? (
              <span key={k}>{p}</span>
            ) : (
              <span key={k} className="cite" onClick={() => onOpen(p)}
                    title={"Open " + p.filename}>{p.text}</span>
            ))}
          ]
        </em>
      ))}
      <button type="button" className="cite-mark shown" onClick={onToggle}
              title="Put the sources away">&times;</button>
    </span>
  );
}

function Inlines({ nodes, blockId, shown, onToggle, byFilename, onOpen }: {
  nodes: Inline[];
  blockId: string;
  shown: Record<string, boolean>;
  onToggle: (key: string) => void;
  byFilename: Record<string, number>;
  onOpen: (ref: Ref) => void;
}) {
  return (
    <>
      {nodes.map((n, i) => {
        if (n.kind === "text") return <span key={i}>{n.text}</span>;
        if (n.kind === "bold") return <strong key={i}>{n.text}</strong>;
        if (n.kind === "em") return <em key={i}>{n.text}</em>;
        const key = blockId + ":" + i;
        return (
          <Citations key={i} refs={n.refs} shown={!!shown[key]}
                     onToggle={() => onToggle(key)}
                     byFilename={byFilename} onOpen={onOpen} />
        );
      })}
    </>
  );
}

/** A gap, a coverage note or a caveat: quoted in the markdown, a callout on
 *  the page. The renderer draws these on a tinted panel; so does this. */
function calloutKind(inlines: Inline[]): string {
  const first = inlines.find((n) => n.kind === "bold");
  const word = (first && first.kind === "bold" ? first.text : "").toLowerCase();
  if (word.startsWith("gap")) return "gap";
  if (word.startsWith("coverage")) return "coverage";
  return "note";
}

/**
 * A block being edited.
 *
 * The content is written into the element ONCE, when it opens, and read out
 * as it changes. React must not re-render it in between: setting the HTML on
 * every keystroke puts the caret back to the start, which is the classic way
 * this goes wrong.
 *
 * Reading it out is the part that has to be reliable. Reading only when the
 * block closed meant relying on an unmount, which React runs after the
 * element has already left the page and which does not run at all if the tab
 * goes first - so an edit took most of the time and occasionally did not,
 * which is worse than no editing. The content is read out on every change, a
 * short pause after typing stops, and again the moment focus leaves. By the
 * time anything else happens the edit is already in.
 */
function Editable({ html, onEdit, multiline, className }: {
  html: string;
  onEdit: (root: HTMLElement) => void;
  multiline?: boolean;
  className?: string;
}) {
  // A span, not a div: a paragraph is a <p>, and a block element inside one
  // is invalid HTML the browser silently closes the paragraph to escape.
  const box = useRef<HTMLSpanElement | null>(null);
  // The current reader, so a commit never writes through a stale copy of the
  // document it was mounted with.
  const read = useRef(onEdit);
  read.current = onEdit;
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);

  const commit = () => {
    if (pending.current) { clearTimeout(pending.current); pending.current = null; }
    if (box.current) read.current(box.current);
  };

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.innerHTML = html;
    el.focus();
    // The caret at the end of what is there, not the start: a person clicking
    // into a paragraph is usually adding to it.
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    // And once more on the way out, for a change that arrived between the
    // last commit and the block closing.
    return () => {
      if (pending.current) clearTimeout(pending.current);
      read.current(el);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <span
      ref={box}
      className={"editable" + (className ? " " + className : "")}
      contentEditable
      suppressContentEditableWarning
      spellCheck
      onInput={() => {
        if (pending.current) clearTimeout(pending.current);
        pending.current = setTimeout(commit, 400);
      }}
      onBlur={commit}
      onKeyDown={(e) => {
        // Bold and italic are the only marks a memo uses.
        const meta = e.metaKey || e.ctrlKey;
        if (meta && (e.key === "b" || e.key === "i")) {
          e.preventDefault();
          document.execCommand(e.key === "b" ? "bold" : "italic");
          return;
        }
        if (e.key === "Enter" && !multiline) { e.preventDefault(); commit(); }
        // A paste of formatted text arrives as text; see nodesToInlines.
      }}
      onPaste={(e) => {
        e.preventDefault();
        const text = e.clipboardData.getData("text/plain");
        document.execCommand("insertText", false, text);
      }}
    />
  );
}

export function MemoDocument({ markdown, byFilename, onOpen, onChange }: {
  markdown: string;
  byFilename: Record<string, number>;
  onOpen: (ref: Ref) => void;
  // Absent, the memo is read-only. Present, every block carries an edit
  // control and this is called with the whole memo after each change.
  onChange?: (markdown: string) => void;
}) {
  // Which runs are out, by block and position. Put away by default: a memo is
  // read far more often than it is checked.
  const [shown, setShown] = useState<Record<string, boolean>>({});
  const toggle = (key: string) =>
    setShown((prev) => ({ ...prev, [key]: !prev[key] }));

  // Which block is open. One at a time: two carets in one document is a way
  // to lose track of which change went where.
  const [editing, setEditing] = useState<string | null>(null);
  // A block just closed, waiting to be judged empty or not.
  const [closed, setClosed] = useState<string | null>(null);

  // A memorandum is a hundred thousand characters. Parsed on every keystroke
  // it would be, and the whole document laid out again with it.
  const blocks = useMemo(() => parseBlocks(markdown), [markdown]);
  const editable = !!onChange;

  /** Write one block back into the memo, leaving every other character of it
   *  alone. */
  function replace(id: string, change: (b: Block) => Block) {
    if (!onChange) return;
    const next = blocks.map((b) => {
      if (b.id !== id) return b;
      const edited = change(b);
      return { ...edited, source: blockToMarkdown(edited, trailingOf(b.source)) };
    });
    const after = serializeBlocks(next);
    if (after !== markdown) onChange(after);
  }

  /** Take a block out of the memo altogether, with the blank lines that
   *  followed it, so the document closes up rather than keeping a hole.
   *
   *  Emptying a block is not the same as removing it: a paragraph typed down
   *  to nothing is still a paragraph, and left there it is an empty box on
   *  the page and a stray blank line in the document. */
  function removeBlock(id: string) {
    if (!onChange) return;
    const block = blocks.find((b) => b.id === id);
    const what = block && "inlines" in block
      ? citationsIn(block.inlines).length : 0;
    if (!window.confirm(
      what > 0
        ? "Delete this, and the " + what
          + (what === 1 ? " reference" : " references") + " in it?"
        : "Delete this?")) return;
    setEditing(null);
    onChange(serializeBlocks(blocks.filter((b) => b.id !== id)));
  }

  /** True when a block has been typed down to nothing. */
  function isEmpty(block: Block): boolean {
    const words = (nodes: Inline[]) =>
      nodes.some((n) => n.kind === "cites" || n.text.trim() !== "");
    if (block.kind === "table") {
      return ![...block.head, ...block.rows.flat()].some(words);
    }
    if (block.kind === "list") return !block.items.some((i) => words(i.inlines));
    if ("inlines" in block) return !words(block.inlines);
    return false;
  }

  /** Close a block, and drop it if there is nothing left in it.
   *
   *  The check waits for the next render rather than happening here: closing
   *  a block takes focus out of it, and the edit that empties it is still on
   *  its way in when the button is pressed. Judging it now would be judging
   *  the block as it stood a moment ago.  */
  function finish(id: string) {
    setEditing(null);
    setClosed(id);
  }

  useEffect(() => {
    if (!closed) return;
    const block = blocks.find((b) => b.id === closed);
    setClosed(null);
    if (!onChange || !block || !isEmpty(block)) return;
    onChange(serializeBlocks(blocks.filter((b) => b.id !== closed)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closed, markdown]);

  /** Inline content out of an edited element, written back to its block.
   *  Called on every change, so it must be cheap and must write nothing when
   *  nothing differs - which replace() checks. */
  const commitInlines = (id: string, set: (b: Block, nodes: Inline[]) => Block) =>
    (root: HTMLElement) => replace(id, (b) => set(b, nodesToInlines(root)));


  /** Show or put away every run in one block at once. */
  function toggleBlock(block: Block) {
    const inlines = "inlines" in block ? block.inlines : [];
    const keys = inlines.map((n, i) => (n.kind === "cites" ? block.id + ":" + i : ""))
                        .filter(Boolean);
    if (!keys.length) return;
    const anyHidden = keys.some((k) => !shown[k]);
    setShown((prev) => {
      const next = { ...prev };
      keys.forEach((k) => { next[k] = anyHidden; });
      return next;
    });
  }

  const inlinesOf = (block: Block, nodes: Inline[]) => (
    <Inlines nodes={nodes} blockId={block.id} shown={shown} onToggle={toggle}
             byFilename={byFilename} onOpen={onOpen} />
  );

  /** The per-block controls. Always there, so they are never hunted for. */
  function Tools({ block }: { block: Block }) {
    const inlines = "inlines" in block ? block.inlines : [];
    const refs = citationsIn(inlines);
    const out = inlines.some((n, i) => n.kind === "cites" && shown[block.id + ":" + i]);
    const open = editing === block.id;
    if (!refs.length && !editable) return null;
    return (
      <span className="block-tools">
        {refs.length > 0 && !open && (
          <button type="button" className={out ? "tool on" : "tool"}
                  onClick={() => toggleBlock(block)}
                  title={out ? "Put the sources away"
                             : `Show all ${refs.length} sources`}>
            {out ? "Hide sources" : "Sources"}
          </button>
        )}
        {editable && (
          <button type="button" className={open ? "tool on" : "tool"}
                  onClick={() => (open ? finish(block.id) : setEditing(block.id))}
                  title={open ? "Finish editing" : "Edit this"}>
            {open ? "Done" : block.kind === "table" ? "Edit table" : "Edit"}
          </button>
        )}
        {editable && open && (
          <button type="button" className="tool danger"
                  onClick={() => removeBlock(block.id)}
                  title="Take this out of the memo">
            Delete
          </button>
        )}
      </span>
    );
  }

  return (
    <article className="memo doc">
      {blocks.map((block) => {
        switch (block.kind) {
          case "raw":
            return null;

          case "rule":
            return <hr key={block.id} />;

          case "heading": {
            const H = ("h" + Math.min(block.level + 1, 6)) as "h2";
            return (
              <H key={block.id} className={"doc-h" + block.level}>
                {editing === block.id ? (
                  <Editable html={inlinesToHtml(block.inlines)}
                            onEdit={commitInlines(block.id, (b, nodes) =>
                              ({ ...b, inlines: nodes } as Block))} />
                ) : inlinesOf(block, block.inlines)}
                <Tools block={block} />
              </H>
            );
          }

          case "quote":
            return (
              <div key={block.id} className={"callout " + calloutKind(block.inlines)}>
                <p>
                  {editing === block.id ? (
                    <Editable html={inlinesToHtml(block.inlines)}
                              onEdit={commitInlines(block.id, (b, nodes) =>
                                ({ ...b, inlines: nodes } as Block))} />
                  ) : inlinesOf(block, block.inlines)}
                  <Tools block={block} />
                </p>
              </div>
            );

          case "list":
            const items = block.items.map((it, k) => (
              <li key={k}>
                {editing === block.id ? (
                  <Editable html={inlinesToHtml(it.inlines)}
                            onEdit={(root) => replace(block.id, (b) => {
                              if (b.kind !== "list") return b;
                              const next = b.items.slice();
                              next[k] = { ...next[k], inlines: nodesToInlines(root) };
                              return { ...b, items: next };
                            })} />
                ) : inlinesOf(block, it.inlines)}
              </li>
            ));
            return (
              <div className="list-wrap" key={block.id}>
                {block.ordered ? <ol>{items}</ol> : <ul>{items}</ul>}
                <Tools block={block} />
              </div>
            );

          case "table":
            return (
              <div className="table-wrap" key={block.id}>
                <div className="table-tools"><Tools block={block} /></div>
                <table className={editing === block.id ? "editing" : undefined}>
                  <thead className={block.head.every((c) => c.length === 0)
                                    ? "empty" : undefined}>
                    <tr>
                      {block.head.map((c, k) => (
                        <th key={k} className={"al-" + (block.align[k] ?? "left")}>
                          {editing === block.id ? (
                            <Editable html={inlinesToHtml(c)}
                                      onEdit={(root) => replace(block.id, (b) => {
                                        if (b.kind !== "table") return b;
                                        const head = b.head.slice();
                                        head[k] = nodesToInlines(root);
                                        return { ...b, head };
                                      })} />
                          ) : inlinesOf(block, c)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r}>
                        {row.map((c, k) => (
                          <td key={k} className={"al-" + (block.align[k] ?? "left")}>
                            {editing === block.id ? (
                              <Editable html={inlinesToHtml(c)}
                                        onEdit={(root) => replace(block.id, (b) => {
                                          if (b.kind !== "table") return b;
                                          const rows = b.rows.map((x) => x.slice());
                                          rows[r][k] = nodesToInlines(root);
                                          return { ...b, rows };
                                        })} />
                            ) : inlinesOf(block, c)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {editing === block.id && (
                  <div className="row-tools">
                    <button type="button" className="tool"
                            onClick={() => replace(block.id, (b) => b.kind === "table"
                              ? { ...b, rows: [...b.rows, b.head.map(() => [])] } : b)}>
                      Add a row
                    </button>
                    {block.rows.length > 0 && (
                      <button type="button" className="tool"
                              onClick={() => replace(block.id, (b) => b.kind === "table"
                                ? { ...b, rows: b.rows.slice(0, -1) } : b)}>
                        Remove the last row
                      </button>
                    )}
                  </div>
                )}
              </div>
            );

          default:
            return (
              <p key={block.id}>
                {editing === block.id ? (
                  <Editable html={inlinesToHtml(block.inlines)} multiline
                            onEdit={commitInlines(block.id, (b, nodes) =>
                              ({ ...b, inlines: nodes } as Block))} />
                ) : inlinesOf(block, block.inlines)}
                <Tools block={block} />
              </p>
            );
        }
      })}
    </article>
  );
}
