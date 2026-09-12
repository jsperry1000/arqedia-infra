import { useState } from "react";
import { parseBlocks, citationsIn, type Block, type Inline } from "./memodoc";

/**
 * The memo as it reads.
 *
 * A memorandum is prose and tables, and that is what this draws: real tables,
 * headings, gap callouts. What it does NOT draw is the markdown underneath -
 * the pipes, the asterisks, the filenames - which is storage, not something a
 * person should have to read past.
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

export function MemoDocument({ markdown, byFilename, onOpen }: {
  markdown: string;
  byFilename: Record<string, number>;
  onOpen: (ref: Ref) => void;
}) {
  // Which runs are out, by block and position. Put away by default: a memo is
  // read far more often than it is checked.
  const [shown, setShown] = useState<Record<string, boolean>>({});
  const toggle = (key: string) =>
    setShown((prev) => ({ ...prev, [key]: !prev[key] }));

  const blocks = parseBlocks(markdown);

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

  /** The per-block control. Always there, so a reader never hunts for it. */
  function Sources({ block }: { block: Block }) {
    const refs = "inlines" in block ? citationsIn(block.inlines) : [];
    if (!refs.length) return null;
    const inlines = "inlines" in block ? block.inlines : [];
    const out = inlines.some((n, i) => n.kind === "cites" && shown[block.id + ":" + i]);
    return (
      <span className="block-tools">
        <button type="button" className={out ? "tool on" : "tool"}
                onClick={() => toggleBlock(block)}
                title={out ? "Put the sources away"
                           : `Show all ${refs.length} sources`}>
          {out ? "Hide sources" : "Sources"}
        </button>
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
                {inlinesOf(block, block.inlines)}
              </H>
            );
          }

          case "quote":
            return (
              <div key={block.id} className={"callout " + calloutKind(block.inlines)}>
                <p>{inlinesOf(block, block.inlines)}<Sources block={block} /></p>
              </div>
            );

          case "list":
            return block.ordered ? (
              <ol key={block.id}>
                {block.items.map((it, k) => (
                  <li key={k}>{inlinesOf(block, it.inlines)}</li>
                ))}
                <Sources block={block} />
              </ol>
            ) : (
              <ul key={block.id}>
                {block.items.map((it, k) => (
                  <li key={k}>{inlinesOf(block, it.inlines)}</li>
                ))}
              </ul>
            );

          case "table":
            return (
              <div className="table-wrap" key={block.id}>
                <table>
                  <thead>
                    <tr>
                      {block.head.map((c, k) => (
                        <th key={k} className={"al-" + (block.align[k] ?? "left")}>
                          {inlinesOf(block, c)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r}>
                        {row.map((c, k) => (
                          <td key={k} className={"al-" + (block.align[k] ?? "left")}>
                            {inlinesOf(block, c)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );

          default:
            return (
              <p key={block.id}>
                {inlinesOf(block, block.inlines)}
                <Sources block={block} />
              </p>
            );
        }
      })}
    </article>
  );
}
