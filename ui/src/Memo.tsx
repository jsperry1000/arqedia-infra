import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, type Memo, type Passage, type Rewrite } from "./api";

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
 *
 * Rewriting is the other way to revise. A person writes a prompt under any
 * section and presses Go; the model rewrites each such section and the answer
 * is shown beside what it replaces, to accept or discard. Nothing changes
 * until the accepted sections are saved as a revision, and that revision
 * records which sections the model wrote and at whose prompt.
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


/** A section as the rewrite screen holds it. */
type Section = {
  heading: string;
  // As the memo has it, and as it stands now: the original, or the last
  // rewrite accepted. A second prompt rewrites what is there now.
  original: string;
  text: string;
  prompt: string;
  // A rewrite in flight, and one finished and waiting to be accepted.
  running: number | null;
  result: Pick<Rewrite, "rewrite_id" | "status" | "error" | "output_text"
                       | "citations_dropped"> | null;
  // The rewrites that produced `text`. Saved with the revision, so its record
  // names every prompt that shaped the section.
  accepted: number[];
};

// A section heading as composition writes it: "## II. Business". Level two
// only - composition's own rule, so the two cannot disagree about where a
// section starts.
const SECTION_HEADING = /^##(?!#)\s+\S/;

/**
 * The memo as a head and its sections, losslessly: joining them back gives
 * the markdown exactly as it was, so a memo saved with nothing accepted is the
 * memo it started as.
 */
function splitSections(markdown: string): { head: string; sections: Section[] } {
  const lines = markdown.split("\n");
  const starts: number[] = [];
  lines.forEach((line, i) => { if (SECTION_HEADING.test(line)) starts.push(i); });
  if (starts.length === 0) return { head: markdown, sections: [] };

  const sections = starts.map((start, k) => {
    const end = k + 1 < starts.length ? starts[k + 1] : lines.length;
    const text = lines.slice(start, end).join("\n");
    return { heading: lines[start].trim(), original: text, text, prompt: "",
             running: null, result: null, accepted: [] };
  });
  return { head: lines.slice(0, starts[0]).join("\n"), sections };
}

function joinSections(head: string, sections: Section[], headLines: boolean): string {
  return (headLines ? [head] : []).concat(sections.map((s) => s.text)).join("\n");
}

// What composition calls a citation - the same pattern it masks with.
const CITATION = /\*[^*\n]+?\.(?:pdf|docx|xlsx|txt|json|xml)[^*\n]*?\*/g;

/** Citations present before a rewrite and absent after it. Counted by the
 *  server; named here, because a count does not tell a person what went. */
function lostCitations(before: string, after: string): string[] {
  const had = Array.from(new Set(before.match(CITATION) ?? []));
  return had.filter((c) => !after.includes(c));
}

function errorText(err: unknown): string {
  let message = String((err as Error)?.message ?? err);
  try {
    message = JSON.parse(message).error ?? message;
  } catch { /* not JSON; show it as it came */ }
  return message;
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

  const [rewriting, setRewriting] = useState(false);
  const [head, setHead] = useState("");
  const [hasHead, setHasHead] = useState(true);
  const [sections, setSections] = useState<Section[]>([]);
  const [starting, setStarting] = useState(false);
  // Rewrites carried into the editor by "Edit before saving", so a revision
  // finished by hand still records the sections the model wrote.
  const [carried, setCarried] = useState<number[]>([]);

  const editorRef = useRef<HTMLTextAreaElement | null>(null);
  const previewRef = useRef<HTMLElement | null>(null);
  // Which pane the pointer last touched. Without this, one pane scrolling the
  // other would scroll it back, and the two would fight.
  const driver = useRef<"editor" | "preview" | null>(null);

  useEffect(() => {
    setEditing(false);
    setRewriting(false);
    setSections([]);
    setCarried([]);
    setSaveError("");
    api.memo(memoId).then(setMemo);
  }, [memoId]);

  // Poll while anything is running. Keyed on the ids in flight, so the timer
  // restarts only when that set changes.
  const runningKey = sections
    .filter((s) => s.running !== null).map((s) => s.running).join(",");

  useEffect(() => {
    if (!runningKey) return;
    const ids = runningKey.split(",").map(Number);
    const began = Date.now();

    const timer = setInterval(async () => {
      // A single section takes seconds. Five minutes without an answer is a
      // function that died, and a spinner would say otherwise for ever.
      if (Date.now() - began > 5 * 60 * 1000) {
        setSections((prev) => prev.map((s) =>
          s.running !== null && ids.includes(s.running)
            ? { ...s, running: null,
                result: { rewrite_id: s.running, status: "failed",
                          output_text: null, citations_dropped: null,
                          error: "No answer after five minutes. Press Go again." } }
            : s));
        return;
      }
      try {
        const { rewrites } = await api.rewrites(memoId, ids);
        setSections((prev) => prev.map((s) => {
          const r = rewrites.find((x) => x.rewrite_id === s.running);
          if (!r || r.status === "running") return s;
          return { ...s, running: null, result: r };
        }));
      } catch (err) {
        setSaveError(errorText(err));
      }
    }, 3000);

    return () => clearInterval(timer);
  }, [runningKey, memoId]);

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

  // What composition calls a citation. It masks citations before consolidation
  // with a regex requiring one of these extensions, so an italic run without
  // one was never a citation on the way in and must not become one here.
  const CITATION_FILE = /\.(?:pdf|docx|xlsx|txt|json|xml)\b/i;

  /** A citation renders in the brand mid blue, small and italic. Each
   *  filename that is one of this memo's sources is separately clickable. */
  function Citation({ children }: { children?: React.ReactNode }) {
    const text = textOf(children);

    // Emphasis, not a citation. An extracted value carrying its own italics -
    // a French term from a trade register, a document title - arrives here
    // looking exactly like a citation, and bracketing it takes the word out of
    // the sentence: "The entity is Manty SA, a [Société anonyme]."
    if (!CITATION_FILE.test(text)) {
      return <em>{children}</em>;
    }

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
    setCarried([]);
    setSaveError("");
    setEditing(true);
  }

  function startRewriting() {
    if (!memo) return;
    const split = splitSections(memo.markdown);
    setHead(split.head);
    setHasHead(!SECTION_HEADING.test(memo.markdown.split("\n")[0] ?? ""));
    setSections(split.sections);
    setSaveError("");
    setRewriting(true);
  }

  const update = (i: number, change: Partial<Section>) =>
    setSections((prev) => prev.map((s, k) => (k === i ? { ...s, ...change } : s)));

  // Sections with a prompt and nothing already in flight or awaiting a
  // decision. A section with an answer waiting is decided first.
  const ready = sections
    .map((s, i) => ({ s, i }))
    .filter(({ s }) => s.prompt.trim() && s.running === null && !s.result);
  const inFlight = sections.filter((s) => s.running !== null).length;
  const undecided = sections.filter((s) => s.result !== null).length;
  const acceptedIds = sections.flatMap((s) => s.accepted);

  async function go() {
    if (ready.length === 0) return;
    setStarting(true);
    setSaveError("");
    try {
      const { rewrites } = await api.startRewrites(memoId, ready.map(({ s }) => (
        { heading: s.heading, text: s.text, prompt: s.prompt.trim() })));
      setSections((prev) => prev.map((s, i) => {
        const k = ready.findIndex((r) => r.i === i);
        if (k < 0) return s;
        const r = rewrites[k];
        return r.status === "failed"
          ? { ...s, result: { rewrite_id: r.rewrite_id, status: "failed",
                              output_text: null, citations_dropped: null,
                              error: "The rewrite could not be started." } }
          : { ...s, running: r.rewrite_id };
      }));
    } catch (err) {
      setSaveError(errorText(err));
    } finally {
      setStarting(false);
    }
  }

  function accept(i: number) {
    const s = sections[i];
    if (!s.result?.output_text) return;
    update(i, { text: s.result.output_text.replace(/\s+$/, "") + "\n",
                accepted: [...s.accepted, s.result.rewrite_id],
                result: null, prompt: "" });
  }

  function leaveRewriting() {
    if ((acceptedIds.length || inFlight || undecided) && !window.confirm(
      "Leave without saving? The rewrites stay on record, but nothing is "
      + "saved into the memo.")) return;
    setRewriting(false);
    setSections([]);
  }

  function editBeforeSaving() {
    setDraft(joinSections(head, sections, hasHead));
    setCarried(acceptedIds);
    setRewriting(false);
    setSections([]);
    setSaveError("");
    setEditing(true);
  }

  async function saveRewrites() {
    setSaving(true);
    setSaveError("");
    try {
      const revised = await api.revise(
        memoId, joinSections(head, sections, hasHead), acceptedIds);
      setRewriting(false);
      setSections([]);
      onOpen(revised.memo_id);
    } catch (err) {
      setSaveError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  async function save() {
    setSaving(true);
    setSaveError("");
    try {
      const revised = await api.revise(memoId, draft, carried);
      setEditing(false);
      setCarried([]);
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

  const markdownOf = (text: string) => (
    <ReactMarkdown components={{ em: Citation }}>
      {protectFilenames(unwrapTables(text))}
    </ReactMarkdown>
  );

  const rendered = markdownOf(editing ? draft : memo.markdown);

  // Which sections of this memo the model wrote, grouped by who prompted.
  const rewrittenBy = (memo.rewrites ?? []).reduce<Record<string, string[]>>(
    (acc, w) => {
      (acc[w.prompted_by] ||= []).push(w.section_heading.replace(/^#+\s*/, ""));
      return acc;
    }, {});

  return (
    <div className={editing || rewriting ? "wide" : ""}>
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
            <a className="secondary" onClick={() => {
              setEditing(false);
              setCarried([]);
            }}>Cancel</a>
          </>
        ) : rewriting ? (
          <>
            <button onClick={saveRewrites}
                    disabled={saving || acceptedIds.length === 0
                              || inFlight > 0 || undecided > 0}
                    title={undecided > 0 || inFlight > 0
                      ? "Accept or discard every rewrite first."
                      : acceptedIds.length === 0
                        ? "Nothing has been accepted yet." : undefined}>
              {saving ? "Saving\u2026" : "Save as a new revision"}
            </button>
            <a className="secondary"
               onClick={inFlight || undecided ? undefined : editBeforeSaving}
               aria-disabled={inFlight > 0 || undecided > 0}>
              Edit before saving
            </a>
            <a className="secondary" onClick={leaveRewriting}>Cancel</a>
          </>
        ) : (
          <>
            <a className="secondary" onClick={startRewriting}>Rewrite</a>
            <a className="secondary" onClick={startEditing}>Edit</a>
            <a className="pdf" onClick={rendering ? undefined : downloadPdf}
               aria-disabled={rendering}>
              {rendering ? "Rendering\u2026" : "Download PDF"}
            </a>
          </>
        )}
      </div>

      {isRevision && !editing && !rewriting && (
        <p className="revision-note">
          This is a revision. It was edited by a person, so the citations are
          their responsibility rather than the system's.
          {Object.entries(rewrittenBy).map(([who, headings]) => (
            <span key={who}>
              {" "}{headings.join(", ")}{" "}
              {headings.length === 1 ? "was" : "were"} rewritten by the model
              at {who}&rsquo;s prompt.
            </span>
          ))}{" "}
          Memo{" "}
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

      {rewriting && (
        <p className="muted small edit-note">
          Write a prompt under any section and press Go. Each rewrite appears
          beside what it would replace; nothing changes until you accept it and
          save. Saving creates a new memo. This one stays as it is.
        </p>
      )}

      {rewriting ? (
        <div className="rewrite">
          {head.trim() && (
            <>
              <article className="memo rewrite-body">{markdownOf(head)}</article>
              <p className="muted small rewrite-note">
                The title and header are not rewritten.
              </p>
            </>
          )}
          {sections.length === 0 && (
            <p className="warn">
              This memo has no numbered sections to rewrite.
            </p>
          )}

          {sections.map((s, i) => {
            const lost = s.result?.output_text
              ? lostCitations(s.text, s.result.output_text) : [];
            return (
              <section className="rewrite-section" key={i}>
                {s.result?.status === "done" && s.result.output_text ? (
                  <div className="rewrite-compare">
                    <div>
                      <h4>Now</h4>
                      <article className="memo rewrite-body">
                        {markdownOf(s.text)}
                      </article>
                    </div>
                    <div>
                      <h4>Rewritten</h4>
                      <article className="memo rewrite-body">
                        {markdownOf(s.result.output_text)}
                      </article>
                    </div>
                  </div>
                ) : (
                  <article className="memo rewrite-body">
                    {markdownOf(s.text)}
                  </article>
                )}

                {lost.length > 0 && (
                  <p className="warn">
                    This rewrite leaves out {lost.length === 1
                      ? "a citation" : lost.length + " citations"}:{" "}
                    {lost.map((c) => c.replace(/^\*|\*$/g, "")).join("; ")}
                  </p>
                )}

                {s.result?.status === "failed" && (
                  <p className="error">{s.result.error}</p>
                )}

                <div className="rewrite-actions">
                  {s.running !== null && (
                    <span className="busy">Rewriting&hellip;</span>
                  )}
                  {s.result?.status === "done" && (
                    <>
                      <a onClick={() => accept(i)}>Accept</a>
                      <a onClick={() => update(i, { result: null })}>Discard</a>
                    </>
                  )}
                  {s.result?.status === "failed" && (
                    <a onClick={() => update(i, { result: null })}>Dismiss</a>
                  )}
                  {s.accepted.length > 0 && s.running === null && !s.result && (
                    <>
                      <span className="muted">
                        Rewritten{s.accepted.length > 1
                          ? " " + s.accepted.length + " times" : ""}
                      </span>
                      <a onClick={() => update(i, { text: s.original,
                                                    accepted: [] })}>
                        Put back the original
                      </a>
                    </>
                  )}
                </div>

                {s.running === null && !s.result && (
                  <textarea className="rewrite-prompt" rows={2}
                    placeholder={"How " + s.heading.replace(/^#+\s*/, "")
                                 + " should be rewritten"}
                    value={s.prompt}
                    onChange={(e) => update(i, { prompt: e.target.value })} />
                )}
              </section>
            );
          })}

          <div className="rewrite-go">
            <button onClick={go} disabled={starting || ready.length === 0}>
              {starting
                ? "Starting\u2026"
                : ready.length === 0
                  ? "Go"
                  : `Go \u2014 rewrite ${ready.length} ${
                      ready.length === 1 ? "section" : "sections"}`}
            </button>
            {inFlight > 0 && (
              <span className="busy">
                {inFlight} {inFlight === 1 ? "section" : "sections"} rewriting
              </span>
            )}
          </div>
        </div>
      ) : editing ? (
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
