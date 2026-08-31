import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, type Memo, type Passage } from "./api";

/**
 * Reading and revising a memo.
 *
 * Every citation names a file and a page. Clicking one opens the passage the
 * system actually read - not the original page image, which is a later piece
 * of work, but what was extracted from it. For checking an extraction that is
 * arguably the more useful thing: a wrong value is usually a misreading rather
 * than a misprint. The original document is one click further, downloadable.
 *
 * Editing produces a NEW memo, numbered 11.2, not an overwrite. The generated
 * memo keeps its machine evidence record; a revision is explicitly a human
 * document, signed by whoever edited it. Which of the two you are reading is
 * never ambiguous.
 */

type Ref = {
  documentId: number;
  filename: string;
  unit: number | null;
  text: string;
};

/**
 * Split a table emitted on one line back into rows.
 *
 * The consolidation sometimes returns a whole table as a single line -
 * "| Item | Status | |---|---| | ... |" - which renders as a run of pipes
 * rather than a table. Telling it not to did not hold, so it is repaired
 * here: the divider is an unambiguous anchor, since "|---|---|" cannot occur
 * in prose, and its column count gives the width of a row.
 *
 * Deterministic, and it repairs memos already written rather than only the
 * next one.
 */
function unwrapTables(markdown: string): string {
  const divider = /\|(?:\s*:?-{2,}:?\s*\|)+/;
  const out: string[] = [];

  for (const line of markdown.split("\n")) {
    const trimmed = line.trim();
    const m = trimmed.match(divider);

    if (!m || !trimmed.startsWith("|") ||
        !trimmed.slice(m.index! + m[0].length).trim()) {
      out.push(line);
      continue;
    }

    const width = (m[0].match(/\|/g) || []).length - 1;
    if (width < 1) { out.push(line); continue; }

    out.push(trimmed.slice(0, m.index!).trim());
    out.push(m[0]);

    const cells = trimmed.slice(m.index! + m[0].length).trim()
      .split(/\s*\|\s*/).filter((c) => c !== "");
    for (let i = 0; i < cells.length; i += width) {
      out.push("| " + cells.slice(i, i + width).join(" | ") + " |");
    }
  }

  return out.join("\n");
}


/**
 * The text inside a node, however deeply nested.
 *
 * String() on React children gives "[object Object]" the moment they are
 * anything but a plain string - which happens whenever a filename contains
 * characters CommonMark reads as markup.
 */
function textOf(node: React.ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  const element = node as { props?: { children?: React.ReactNode } };
  return element.props ? textOf(element.props.children) : "";
}

/**
 * Escape the underscores inside a filename before the markdown is parsed.
 *
 * "CE-_-Corporate-Legal-Deck.pdf" contains -_-, which CommonMark reads as
 * emphasis: the citation came apart into nested elements, the underscores
 * were consumed as markup, and the filename rendered as
 * "CE-,[object Object],-Corporate-Legal-Deck.pdf".
 *
 * Only filenames are touched, so ordinary emphasis elsewhere is unaffected -
 * including in memos written before citations moved to asterisks.
 */
function protectFilenames(markdown: string): string {
  return markdown.replace(
    /[A-Za-z0-9._()\-]+\.(?:pdf|docx|xlsx|txt|json|xml)/gi,
    (name) => name.replace(/_/g, "\\_"));
}


export function MemoView({ memoId, onBack, onOpen }: {
  memoId: number;
  onBack: () => void;
  onOpen: (memoId: number) => void;
}) {
  const [memo, setMemo] = useState<Memo | null>(null);
  const [passage, setPassage] = useState<Passage | null>(null);
  const [loadingRef, setLoadingRef] = useState(false);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [saveError, setSaveError] = useState("");

  const editorRef = useRef<HTMLTextAreaElement | null>(null);
  const previewRef = useRef<HTMLElement | null>(null);
  // Which pane the pointer last touched. Without this, one pane scrolling the
  // other would scroll it back, and the two would fight.
  const driver = useRef<"editor" | "preview" | null>(null);

  useEffect(() => {
    setEditing(false);
    setSaveError("");
    api.memo(memoId).then(setMemo);
  }, [memoId]);

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
   */
  function parseRefs(raw: string): (string | Ref)[] {
    // The backslashes added to protect a filename from the parser are not
    // part of its name.
    const text = raw.replace(/\\_/g, "_");
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
    const text = textOf(children);
    const parts = parseRefs(text);

    // Bracketed, because colour and size alone were not carrying the
    // boundary: "page 1 Its registered office" read as continuous prose, and
    // two consecutive citations read as one long reference.
    if (parts.every((p) => typeof p === "string")) {
      return <em className="ref">[{children}]</em>;
    }

    return (
      <em className="ref">
        [
        {parts.map((p, i) =>
          typeof p === "string" ? (
            <span key={i}>{p}</span>
          ) : (
            <span key={i} className="cite" onClick={() => openRef(p)}
                  title={"Open " + p.filename}>
              {p.text}
            </span>
          ))}
        ]
      </em>
    );
  }

  /**
   * Proportional scroll sync. The two panes have different heights for the
   * same content, so anything better than proportional would mean mapping
   * source lines to rendered elements - real work for a small gain. Either
   * pane can be scrolled alone; only the one under the pointer drives.
   */
  const syncFrom = useCallback((from: "editor" | "preview") => {
    if (driver.current !== from) return;
    const a = from === "editor" ? editorRef.current : previewRef.current;
    const b = from === "editor" ? previewRef.current : editorRef.current;
    if (!a || !b) return;

    const travel = a.scrollHeight - a.clientHeight;
    if (travel <= 0) return;
    const ratio = a.scrollTop / travel;
    b.scrollTop = ratio * (b.scrollHeight - b.clientHeight);
  }, []);

  async function downloadPdf() {
    // Rendered on demand, so it takes a couple of seconds on a long memo.
    // Saying so beats a button that appears to do nothing.
    setRendering(true);
    setSaveError("");
    try {
      const { url } = await api.memoPdf(memoId);
      window.open(url, "_blank", "noopener");
    } catch (err) {
      setSaveError(String((err as Error)?.message ?? err));
    } finally {
      setRendering(false);
    }
  }

  function startEditing() {
    if (!memo) return;
    setDraft(memo.markdown);
    setSaveError("");
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    setSaveError("");
    try {
      const revised = await api.revise(memoId, draft);
      setEditing(false);
      onOpen(revised.memo_id);
    } catch (err: any) {
      // A citation naming a document that is not a source of this memo is
      // refused rather than saved. The message names which.
      let message = String(err?.message ?? err);
      try {
        message = JSON.parse(message).error ?? message;
      } catch { /* not JSON; show it as it came */ }
      setSaveError(message);
    } finally {
      setSaving(false);
    }
  }

  if (!memo) return <p className="muted">Loading&hellip;</p>;

  const isRevision = memo.revision > 1;

  const rendered = (
    <ReactMarkdown components={{ em: Citation }}>
      {protectFilenames(unwrapTables(editing ? draft : memo.markdown))}
    </ReactMarkdown>
  );

  return (
    <div className={editing ? "wide" : ""}>
      <a onClick={onBack} className="back">Back</a>

      <div className="memo-head">
        <div>
          <h2>Memo {memo.label}</h2>
          <p className="muted">
            Generated {(memo.generated_at ?? "").slice(0, 16)}
            {memo.generated_by ? " by " + memo.generated_by : ""}
            {memo.modified_by
              ? ` \u00b7 revised ${(memo.modified_at ?? "").slice(0, 16)} by ${memo.modified_by}`
              : ""}
          </p>
        </div>

        {editing ? (
          <>
            <button onClick={save} disabled={saving || !draft.trim()}>
              {saving ? "Saving\u2026" : "Save as a new revision"}
            </button>
            <a className="secondary" onClick={() => setEditing(false)}>Cancel</a>
          </>
        ) : (
          <>
            <a className="secondary" onClick={startEditing}>Edit</a>
            <a className="pdf" onClick={rendering ? undefined : downloadPdf}
               aria-disabled={rendering}>
              {rendering ? "Rendering\u2026" : "Download PDF"}
            </a>
          </>
        )}
      </div>

      {isRevision && !editing && (
        <p className="revision-note">
          This is a revision. It was edited by a person, so the citations are
          their responsibility rather than the system's. Memo{" "}
          <a onClick={() => onOpen(memo.parent_memo_id!)}>
            {memo.parent_memo_id}.1
          </a>{" "}
          is the generated original and is unchanged.
        </p>
      )}

      {editing && (
        <p className="muted small edit-note">
          Saving creates a new memo. This one stays as it is. The panes scroll
          together; scroll either one on its own to move it alone.
        </p>
      )}

      {saveError && <p className="error">{saveError}</p>}
      {loadingRef && <p className="busy">Opening source&hellip;</p>}

      {editing ? (
        <div className="split">
          <textarea
            ref={editorRef}
            className="editor"
            value={draft}
            spellCheck={false}
            onMouseEnter={() => (driver.current = "editor")}
            onScroll={() => syncFrom("editor")}
            onChange={(e) => setDraft(e.target.value)}
          />
          <article
            ref={previewRef as React.RefObject<HTMLElement>}
            className="memo preview"
            onMouseEnter={() => (driver.current = "preview")}
            onScroll={() => syncFrom("preview")}
          >
            {rendered}
          </article>
        </div>
      ) : (
        <article className="memo">{rendered}</article>
      )}

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
