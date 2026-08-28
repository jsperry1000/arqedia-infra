import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, type Memo, type Passage } from "./api";

/**
 * Reading a memo.
 *
 * Every citation names a file and a page. Clicking one opens the passage the
 * system actually read - not the original page image, which is a later piece
 * of work, but what was extracted from it. For checking an extraction that is
 * arguably the more useful thing: a wrong value is usually a misreading rather
 * than a misprint. The original document is one click further, downloadable.
 */

type Ref = {
  documentId: number;
  filename: string;
  unit: number | null;
  text: string;
};

export function MemoView({ memoId, onBack }: {
  memoId: number;
  onBack: () => void;
}) {
  const [memo, setMemo] = useState<Memo | null>(null);
  const [passage, setPassage] = useState<Passage | null>(null);
  const [loadingRef, setLoadingRef] = useState(false);

  useEffect(() => { api.memo(memoId).then(setMemo); }, [memoId]);

  // filename -> document_id, so a citation naming a file can be opened. The
  // memo text carries no identifiers; this is the map.
  const byFilename = useMemo(() => {
    const map: Record<string, number> = {};
    for (const s of memo?.sources ?? []) map[s.filename] = s.document_id;
    return map;
  }, [memo]);

  /**
   * Split a citation line into its parts. "Sources: a.pdf, page 1;
   * b.docx, section 2." is EIGHT citations on some sections, not one - and
   * matching only the first meant every click opened the same document.
   *
   * Returns the line as alternating text and openable references, so the
   * unmatched parts still read as ordinary citation text.
   */
  function parseRefs(text: string): (string | Ref)[] {
    const pattern =
      /([A-Za-z0-9._()\-]+\.(?:pdf|docx|xlsx|txt|json|xml))(\s*,\s*(?:page|section|sheet)\s*(\d+))?/gi;

    const out: (string | Ref)[] = [];
    let last = 0;
    let m: RegExpExecArray | null;

    while ((m = pattern.exec(text)) !== null) {
      const documentId = byFilename[m[1]];
      if (!documentId) continue;
      if (m.index > last) out.push(text.slice(last, m.index));
      out.push({
        documentId,
        filename: m[1],
        unit: m[3] ? Number(m[3]) : null,
        text: m[0],
      });
      last = m.index + m[0].length;
    }
    if (last < text.length) out.push(text.slice(last));
    return out;
  }

  async function openRef(ref: Ref) {
    setLoadingRef(true);
    try {
      setPassage(await api.passage(ref.documentId, ref.unit));
    } finally {
      setLoadingRef(false);
    }
  }

  /** A citation renders in the brand mid blue, small and italic. Each
   *  filename that is one of this memo's sources is separately clickable. */
  function Citation({ children }: { children?: React.ReactNode }) {
    const text = String(children ?? "");
    const parts = parseRefs(text);

    if (parts.every((p) => typeof p === "string")) {
      return <em className="ref">{children}</em>;
    }

    return (
      <em className="ref">
        {parts.map((p, i) =>
          typeof p === "string" ? (
            <span key={i}>{p}</span>
          ) : (
            <span key={i} className="cite" onClick={() => openRef(p)}
                  title={"Open " + p.filename}>
              {p.text}
            </span>
          ))}
      </em>
    );
  }

  if (!memo) return <p className="muted">Loading&hellip;</p>;

  return (
    <div>
      <a onClick={onBack} className="back">Back</a>

      <div className="memo-head">
        <div>
          <h2>Memo {memo.label}</h2>
          <p className="muted">
            Generated {(memo.generated_at ?? "").slice(0, 16)}
            {memo.generated_by ? " by " + memo.generated_by : ""}
            {memo.modified_by
              ? ` \u00b7 modified ${(memo.modified_at ?? "").slice(0, 16)} by ${memo.modified_by}`
              : ""}
          </p>
        </div>
        {memo.pdf_url && (
          <a className="pdf" href={memo.pdf_url} target="_blank"
             rel="noreferrer">Download PDF</a>
        )}
      </div>

      {loadingRef && <p className="busy">Opening source&hellip;</p>}

      <article className="memo">
        <ReactMarkdown components={{ em: Citation }}>
          {memo.markdown}
        </ReactMarkdown>
      </article>

      {passage && (
        <PassagePanel passage={passage} onClose={() => setPassage(null)} />
      )}
    </div>
  );
}

/** What the system read at the cited page, and a link to the document. */
function PassagePanel({ passage, onClose }: {
  passage: Passage;
  onClose: () => void;
}) {
  return (
    <div className="panel-backdrop" onClick={onClose}>
      <aside className="panel" onClick={(e) => e.stopPropagation()}>
        <a onClick={onClose} className="panel-close">Close</a>
        <h3>{passage.filename}</h3>
        <p className="muted">
          {passage.unit
            ? `${passage.unit_kind} ${passage.unit}${passage.unit_label ? " \u2014 " + passage.unit_label : ""} of ${passage.pages}`
            : `${passage.pages} pages`}
        </p>

        <p className="muted small">
          This is the text the system read. It is what every value from this
          document was extracted from.
        </p>

        <pre className="passage">{passage.text}</pre>

        <a href={passage.source_url} target="_blank" rel="noreferrer">
          Open the original document
        </a>
      </aside>
    </div>
  );
}
