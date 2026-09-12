import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api, type Memo, type Passage, type Rewrite } from "./api";
import { MemoDocument, type Ref } from "./MemoReader";

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
 *
 * Editing happens in the document itself - an edit control on each block,
 * and the block opens where it sits. There is no second pane and no markdown
 * on screen: the stored form is storage, and a person revising a memorandum
 * should be looking at a memorandum.
 *
 * Reading, editing and rewriting all work on ONE working copy: the text as it
 * stands, the prompts typed, the rewrites accepted and the ones still out.
 * Leaving - Back, a reload, another memo - keeps it, on the server, and
 * coming back reopens it where it was. Only saving a revision or Discard
 * changes ends it.
 */

// A section heading as composition writes it: "## II. Business". Level two
// only - composition's own rule, so the two cannot disagree about where a
// section starts.
const SECTION_HEADING = /^##(?!#)\s+\S/;

type Part = { key: string; heading: string; text: string };

/**
 * The text as a head and its sections, losslessly: joining them back gives
 * the text exactly as it was, so a section nobody touched is saved unchanged.
 *
 * A section is known by its heading. Where a heading repeats, its occurrence
 * number is part of the key, so two sections never share a prompt.
 */
function splitSections(markdown: string): {
  head: string; hasHead: boolean; sections: Part[];
} {
  const lines = markdown.split("\n");
  const starts: number[] = [];
  lines.forEach((line, i) => { if (SECTION_HEADING.test(line)) starts.push(i); });
  if (starts.length === 0) return { head: markdown, hasHead: true, sections: [] };

  const seen: Record<string, number> = {};
  const sections = starts.map((start, k) => {
    const end = k + 1 < starts.length ? starts[k + 1] : lines.length;
    const heading = lines[start].trim();
    seen[heading] = (seen[heading] ?? 0) + 1;
    return { key: seen[heading] > 1 ? heading + " #" + seen[heading] : heading,
             heading, text: lines.slice(start, end).join("\n") };
  });
  return { head: lines.slice(0, starts[0]).join("\n"), hasHead: starts[0] > 0,
           sections };
}

function joinSections(head: string, hasHead: boolean, sections: Part[]): string {
  return (hasHead ? [head] : []).concat(sections.map((s) => s.text)).join("\n");
}

/** The text with one section replaced. */
function replaceSection(markdown: string, key: string, text: string): string {
  const split = splitSections(markdown);
  return joinSections(split.head, split.hasHead, split.sections.map((s) =>
    s.key === key ? { ...s, text } : s));
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

type Result = Pick<Rewrite, "rewrite_id" | "status" | "error" | "output_text"
                           | "citations_dropped">;

// A rewrite out for one section: in flight, or finished and waiting to be
// accepted or discarded.
type Run = { id: number; result: Result | null };

// Editing is not a mode: every block carries its own control while reading.
// Rewriting is, because the whole document is laid out differently for it.
type Mode = "read" | "rewrite";

// How long typing pauses before the working copy is kept. Short enough that a
// reload loses a sentence at most; long enough not to write on every key.
const KEEP_AFTER_MS = 1500;

export function MemoView({ memoId, onBack, onOpen }: {
  memoId: number;
  onBack: () => void;
  onOpen: (memoId: number) => void;
}) {
  const [memo, setMemo] = useState<Memo | null>(null);
  const [passage, setPassage] = useState<Passage | null>(null);
  const [loadingRef, setLoadingRef] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  // The working copy. Rewrite and Edit both read and write these.
  const [mode, setMode] = useState<Mode>("read");
  const [draft, setDraft] = useState("");
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  // Rewrites accepted, by section. Kept even when a hand edit renames the
  // section, so the revision still records every section the model wrote.
  const [acceptedBy, setAcceptedBy] = useState<Record<string, number[]>>({});
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [starting, setStarting] = useState(false);

  const [loaded, setLoaded] = useState(false);
  const [keeping, setKeeping] = useState<"" | "keeping" | "kept" | "failed">("");

  // The memo's own head - Rewrite, Edit and the PDF while reading; Go, Save,
  // Edit and Close while revising - is held just under the site header, so a
  // person at the foot of a long memo does not scroll back to the top to act. The site header's height is measured,
  // not assumed: it changes with the width of the window and the length of
  // the signed-in address.
  const [pinTop, setPinTop] = useState(0);
  useLayoutEffect(() => {
    const header = document.querySelector(".shell header");
    if (!header) return;
    const measure = () => setPinTop(header.getBoundingClientRect().height);
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const watch = new ResizeObserver(measure);
    watch.observe(header);
    return () => watch.disconnect();
  }, []);

  // What was last written to the server, and what would be written now - so a
  // leave can keep the difference without waiting for the pause.
  const kept = useRef<{ id: number; payload: string }>({ id: 0, payload: "null" });
  const latest = useRef<{ id: number; payload: string }>({ id: 0, payload: "null" });
  const sending = useRef<{ id: number; payload: string } | null>(null);
  // Set when the kept copy could not be read. Keeping anything then would
  // overwrite a copy the person has not seen, so nothing is kept.
  const keepBlocked = useRef(false);

  function keepNow(id: number, payload: string) {
    if (keepBlocked.current) return;
    if (kept.current.id === id && kept.current.payload === payload) return;
    if (sending.current?.id === id && sending.current.payload === payload) return;
    sending.current = { id, payload };
    setKeeping("keeping");
    api.keepMemoWorking(id, JSON.parse(payload))
      .then(() => {
        kept.current = { id, payload };
        if (latest.current.id === id) setKeeping("kept");
      })
      .catch((err) => {
        setKeeping("failed");
        setSaveError("Your changes could not be kept: " + errorText(err));
      })
      .finally(() => {
        if (sending.current?.id === id && sending.current.payload === payload) {
          sending.current = null;
        }
      });
  }

  // Load the memo and any working copy together, and reopen the copy where it
  // was left. Leaving this memo - for another, or for Back - keeps what has
  // not been kept yet.
  useEffect(() => {
    let live = true;
    setLoaded(false);
    setMemo(null);
    setMode("read");
    setSaveError("");
    setKeeping("");

    keepBlocked.current = false;
    const working = api.memoWorking(memoId).catch(() => null);

    Promise.all([api.memo(memoId), working]).then(([m, w]) => {
      if (!live) return;
      if (w === null) {
        keepBlocked.current = true;
        setSaveError("Your kept changes to this memo could not be read, so "
          + "nothing you change now will be kept. Reload to try again.");
      }
      const copy = w?.working ?? null;
      setMemo(m);
      setDraft(copy?.text ?? m.markdown);
      setPrompts(copy?.prompts ?? {});
      setAcceptedBy(copy?.accepted_by ?? {});
      setRuns(Object.fromEntries(Object.entries(copy?.pending ?? {})
        .map(([key, id]) => [key, { id, result: null }])));
      // A copy kept before editing moved into the document names a mode that
      // no longer exists; it opens in the reader, where editing now lives.
      setMode(copy?.mode === "rewrite" ? "rewrite" : "read");
      const payload = copy ? JSON.stringify(copy) : "null";
      kept.current = { id: memoId, payload };
      latest.current = { id: memoId, payload };
      setLoaded(true);
    }).catch((err) => live && setSaveError(errorText(err)));

    return () => {
      live = false;
      const { id, payload } = latest.current;
      if (id === memoId) keepNow(id, payload);
    };
  }, [memoId]);

  const acceptedIds = Array.from(new Set(Object.values(acceptedBy).flat()));
  const inFlight = Object.values(runs).filter((r) => r.result === null).length;
  const undecided = Object.values(runs).filter((r) => r.result !== null).length;
  const typedPrompts = Object.fromEntries(
    Object.entries(prompts).filter(([, p]) => p.trim()));

  const hasChanges = !!memo && (draft !== memo.markdown
    || Object.keys(typedPrompts).length > 0 || acceptedIds.length > 0
    || Object.keys(runs).length > 0);

  const payload = !memo || !hasChanges ? "null" : JSON.stringify({
    version: 1,
    mode,
    text: draft,
    prompts: typedPrompts,
    accepted_by: acceptedBy,
    pending: Object.fromEntries(Object.entries(runs).map(([k, r]) => [k, r.id])),
  });

  // Keep the working copy after a pause in the changes.
  useEffect(() => {
    if (!loaded || keepBlocked.current) return;
    latest.current = { id: memoId, payload };
    if (kept.current.id === memoId && kept.current.payload === payload) return;
    const timer = setTimeout(() => keepNow(memoId, payload), KEEP_AFTER_MS);
    return () => clearTimeout(timer);
  }, [payload, loaded, memoId]);

  // Poll while anything is in flight. Keyed on the ids, so the timer restarts
  // only when that set changes.
  const runningKey = Object.values(runs)
    .filter((r) => r.result === null).map((r) => r.id).sort().join(",");

  useEffect(() => {
    if (!runningKey) return;
    const ids = runningKey.split(",").map(Number);
    const began = Date.now();

    const settle = (id: number, result: Result) =>
      setRuns((prev) => Object.fromEntries(Object.entries(prev).map(([k, r]) =>
        [k, r.id === id && r.result === null ? { ...r, result } : r])));

    const timer = setInterval(async () => {
      // A single section takes seconds. Five minutes without an answer is a
      // function that died, and a spinner would say otherwise for ever.
      if (Date.now() - began > 5 * 60 * 1000) {
        ids.forEach((id) => settle(id, {
          rewrite_id: id, status: "failed", output_text: null,
          citations_dropped: null,
          error: "No answer after five minutes. Press Go again." }));
        return;
      }
      try {
        const { rewrites } = await api.rewrites(memoId, ids);
        rewrites.filter((r) => r.status !== "running")
          .forEach((r) => settle(r.rewrite_id, r));
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

  async function openRef(ref: Ref) {
    setLoadingRef(true);
    try {
      setPassage(await api.passage(ref.documentId, ref.unit));
    } finally {
      setLoadingRef(false);
    }
  }

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

  /** Into the rewrite screen, or back out of it, keeping the copy either
   *  way. */
  function openRewrite() {
    setSaveError("");
    setMode("rewrite");
  }

  function close() {
    setMode("read");
    keepNow(memoId, latest.current.payload);
  }

  function back() {
    keepNow(memoId, latest.current.payload);
    onBack();
  }

  function discard() {
    if (!window.confirm("Discard your changes to this memo? Accepted rewrites "
        + "and typed prompts are thrown away. The rewrites stay on record, but "
        + "nothing is saved into the memo.")) return;
    if (!memo) return;
    setDraft(memo.markdown);
    setPrompts({});
    setAcceptedBy({});
    setRuns({});
    setMode("read");
    setSaveError("");
    keepNow(memoId, "null");
  }

  const split = splitSections(draft);
  const originals = Object.fromEntries(
    splitSections(memo?.markdown ?? "").sections.map((s) => [s.key, s.text]));

  const ready = split.sections.filter((s) =>
    (prompts[s.key] ?? "").trim() && !runs[s.key]);

  async function go() {
    if (ready.length === 0) return;
    const sending = ready;
    setStarting(true);
    setSaveError("");
    try {
      const { rewrites } = await api.startRewrites(memoId, sending.map((s) => (
        { heading: s.heading, text: s.text, prompt: (prompts[s.key] ?? "").trim() })));
      setRuns((prev) => {
        const next = { ...prev };
        sending.forEach((s, k) => {
          const r = rewrites[k];
          next[s.key] = r.status === "failed"
            ? { id: r.rewrite_id, result: { rewrite_id: r.rewrite_id,
                status: "failed", output_text: null, citations_dropped: null,
                error: "The rewrite could not be started." } }
            : { id: r.rewrite_id, result: null };
        });
        return next;
      });
    } catch (err) {
      setSaveError(errorText(err));
    } finally {
      setStarting(false);
    }
  }

  function dropRun(key: string) {
    setRuns((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  function accept(key: string) {
    const run = runs[key];
    if (!run?.result?.output_text) return;
    setDraft((d) => replaceSection(d, key,
      run.result!.output_text!.replace(/\s+$/, "") + "\n"));
    setAcceptedBy((prev) => ({ ...prev,
                               [key]: [...(prev[key] ?? []), run.id] }));
    setPrompts((prev) => ({ ...prev, [key]: "" }));
    dropRun(key);
  }

  function putBack(key: string) {
    if (originals[key] === undefined) return;
    setDraft((d) => replaceSection(d, key, originals[key]));
    setAcceptedBy((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  const blocked = inFlight > 0 || undecided > 0;
  const canSave = !!memo && !saving && !blocked && !!draft.trim()
    && draft !== memo.markdown;

  async function save() {
    setSaving(true);
    setSaveError("");
    try {
      const revised = await api.revise(memoId, draft, acceptedIds);
      // The server clears the working copy with the save. Nothing is left to
      // keep, so leaving must not write the old one back.
      kept.current = { id: memoId, payload: "null" };
      latest.current = { id: memoId, payload: "null" };
      setMode("read");
      onOpen(revised.memo_id);
    } catch (err) {
      // A citation naming a document that is not a source of this memo is
      // refused rather than saved. The message names which.
      setSaveError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  if (!memo) {
    return saveError
      ? <p className="error">{saveError}</p>
      : <p className="muted">Loading&hellip;</p>;
  }

  const isRevision = memo.revision > 1;

  // Every rendering of memo text on this screen - the reader, the editor's
  // preview, both panes of a rewrite - goes through here, so tables are
  // tables and citations behave the same way everywhere.
  const markdownOf = (text: string) => (
    <MemoDocument markdown={text} byFilename={byFilename} onOpen={openRef} />
  );

  // Which sections of this memo the model wrote, grouped by who prompted.
  const rewrittenBy = (memo.rewrites ?? []).reduce<Record<string, string[]>>(
    (acc, w) => {
      (acc[w.prompted_by] ||= []).push(w.section_heading.replace(/^#+\s*/, ""));
      return acc;
    }, {});

  const blockedTitle = blocked ? "Accept or discard every rewrite first." : undefined;

  return (
    <div className={mode !== "read" ? "wide" : ""}>
      <a onClick={back} className="back">Back</a>

      <div className="memo-head pinned" style={{ top: pinTop }}>
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

        {mode === "read" ? (
          <>
            {hasChanges && (
              <button onClick={save} disabled={!canSave} title={blockedTitle}>
                {saving ? "Saving\u2026" : "Save as a new revision"}
              </button>
            )}
            <a className="secondary" onClick={openRewrite}>Rewrite</a>
            <a className="pdf" onClick={rendering ? undefined : downloadPdf}
               aria-disabled={rendering}>
              {rendering ? "Rendering\u2026" : "Download PDF"}
            </a>
          </>
        ) : (
          <>
            {mode === "rewrite" && (
              <>
                <button onClick={go} disabled={starting || ready.length === 0}
                        title={ready.length === 0
                          ? "Write a prompt under a section first." : undefined}>
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
              </>
            )}
            <button onClick={save} disabled={!canSave} title={blockedTitle}>
              {saving ? "Saving\u2026" : "Save as a new revision"}
            </button>
            <a className="secondary" onClick={close}>Close</a>
          </>
        )}
      </div>

      {mode === "read" && hasChanges && (
        <p className="working-note">
          You have unsaved changes to this memo. They are kept if you leave,
          until you save or{" "}
          <a onClick={discard}>discard them</a>.
          {keeping === "keeping" && <span> Keeping&hellip;</span>}
          {keeping === "kept" && <span> Kept.</span>}
        </p>
      )}

      {isRevision && mode === "read" && (
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

      {mode === "rewrite" && (
        <p className="muted small edit-note">
          Write a prompt under any section and press Go. Each rewrite appears
          beside what it would replace; nothing changes until you accept it and
          save. Your changes are kept if you leave, until you save or{" "}
          <a onClick={discard}>discard them</a>. Saving creates a new memo; this
          one stays as it is.
          {keeping === "keeping" && <span> Keeping&hellip;</span>}
          {keeping === "kept" && hasChanges && <span> Kept.</span>}
        </p>
      )}

      {saveError && <p className="error">{saveError}</p>}
      {loadingRef && <p className="busy">Opening source&hellip;</p>}

      {mode === "rewrite" ? (
        <div className="rewrite">
          {split.head.trim() && (
            <>
              <div className="rewrite-body">
                <MemoDocument markdown={split.head} byFilename={byFilename}
                              onOpen={openRef}
                              onChange={(text) => setDraft(
                                joinSections(text, split.hasHead, split.sections))} />
              </div>
              <p className="muted small rewrite-note">
                The title and header are not rewritten.
              </p>
            </>
          )}
          {split.sections.length === 0 && (
            <p className="warn">
              This memo has no numbered sections to rewrite.
            </p>
          )}

          {split.sections.map((s) => {
            const run = runs[s.key];
            const result = run?.result ?? null;
            const accepted = acceptedBy[s.key] ?? [];
            const lost = result?.output_text
              ? lostCitations(s.text, result.output_text) : [];
            return (
              <section className="rewrite-section" key={s.key}>
                {result?.status === "done" && result.output_text ? (
                  <div className="rewrite-compare">
                    <div>
                      <h4>Now</h4>
                      <div className="rewrite-body">
                        {markdownOf(s.text)}
                      </div>
                    </div>
                    <div>
                      <h4>Rewritten</h4>
                      <div className="rewrite-body">
                        {markdownOf(result.output_text)}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rewrite-body">
                    <MemoDocument markdown={s.text} byFilename={byFilename}
                                  onOpen={openRef}
                                  onChange={(text) => setDraft(
                                    replaceSection(draft, s.key, text))} />
                  </div>
                )}

                {lost.length > 0 && (
                  <p className="warn">
                    This rewrite leaves out {lost.length === 1
                      ? "a citation" : lost.length + " citations"}:{" "}
                    {lost.map((c) => c.replace(/^\*|\*$/g, "")).join("; ")}
                  </p>
                )}

                {result?.status === "failed" && (
                  <p className="error">{result.error}</p>
                )}

                <div className="rewrite-actions">
                  {run && !result && (
                    <span className="busy">Rewriting&hellip;</span>
                  )}
                  {result?.status === "done" && (
                    <>
                      <a onClick={() => accept(s.key)}>Accept</a>
                      <a onClick={() => dropRun(s.key)}>Discard</a>
                    </>
                  )}
                  {result?.status === "failed" && (
                    <a onClick={() => dropRun(s.key)}>Dismiss</a>
                  )}
                  {accepted.length > 0 && !run && (
                    <>
                      <span className="muted">
                        Rewritten{accepted.length > 1
                          ? " " + accepted.length + " times" : ""}
                      </span>
                      {originals[s.key] !== undefined && (
                        <a onClick={() => putBack(s.key)}>
                          Put back the original
                        </a>
                      )}
                    </>
                  )}
                </div>

                {!run && (
                  <textarea className="rewrite-prompt" rows={2}
                    placeholder={"How " + s.heading.replace(/^#+\s*/, "")
                                 + " should be rewritten"}
                    value={prompts[s.key] ?? ""}
                    onChange={(e) => {
                      const value = e.target.value;
                      setPrompts((prev) => ({ ...prev, [s.key]: value }));
                    }} />
                )}
              </section>
            );
          })}
        </div>
      ) : (
        <MemoDocument markdown={draft} byFilename={byFilename} onOpen={openRef}
                      onChange={setDraft} />
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
