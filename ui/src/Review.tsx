import { useEffect, useMemo, useState } from "react";
import {
  api,
  type Pending,
  type DocType,
  type Decision,
  type Doc,
  type MemoRef,
  type DocumentDetail,
} from "./api";

/**
 * The engagement. Three states of a document are visible here:
 *
 *   ready to file   analysed, type proposed, awaiting confirmation
 *   filed           extracted, and either in use or set aside
 *   memos           what has been generated from the documents in use
 *
 * Setting a document aside excludes it from the NEXT memo. It never deletes,
 * and never alters a memo already generated - that memo cited what was
 * current when it was written.
 */

type Choice = { type: string | null; include: boolean };
type SortKey = "filename" | "document_type" | "filed_at" | "values" | "active";

export function EngagementView({ id, onBack, onMemo }: {
  id: string;
  onBack: () => void;
  onMemo: (memoId: number) => void;
}) {
  const [pending, setPending] = useState<Pending[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [memos, setMemos] = useState<MemoRef[]>([]);
  const [types, setTypes] = useState<DocType[]>([]);
  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const [sortKey, setSortKey] = useState<SortKey>("filename");
  const [sortDown, setSortDown] = useState(false);
  const [nameFilter, setNameFilter] = useState("");
  const [showInactive, setShowInactive] = useState(true);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);

  async function refresh() {
    const [p, d, m] = await Promise.all([
      api.pending(id), api.documents(id), api.memos(id),
    ]);
    setPending(p.pending);
    setDocs(d.documents);
    setMemos(m.memos);

    // Seed a choice for anything newly analysed, without disturbing edits.
    setChoices((prev) => {
      const next = { ...prev };
      for (const row of p.pending) {
        if (!(row.document_id in next)) {
          next[row.document_id] = { type: row.proposed_type, include: true };
        }
      }
      return next;
    });
  }

  useEffect(() => { api.documentTypes().then((r) => setTypes(r.types)); }, []);
  useEffect(() => { refresh(); }, [id]);

  // A document being read by OCR is still in flight. Generating now would
  // produce a memo missing whatever it is about to say.
  const reading = docs.filter((d) => d.state === "reading").length;
  const unfiled = pending.length;
  const settling = busy !== "" || reading > 0 || unfiled > 0;

  useEffect(() => {
    if (!settling) return;
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [id, settling]);

  async function upload(files: FileList | null) {
    if (!files) return;
    const list = Array.from(files);
    setError("");

    for (let i = 0; i < list.length; i++) {
      setBusy(`Uploading ${i + 1} of ${list.length} \u2014 ${list[i].name}`);
      try {
        await api.upload(id, list[i]);
      } catch (err) {
        // A failure used to leave "Uploading" on screen indefinitely, which
        // reads as a hang rather than as the refusal it is.
        setError(String((err as Error)?.message ?? err));
        setBusy("");
        refresh();
        return;
      }
      // Refresh as each lands. Waiting for all of them made a twenty-file
      // upload look frozen, and polling could not start because there was
      // nothing pending for it to see yet.
      refresh();
    }

    setBusy("");
    refresh();
  }

  // Picking a file uploads it, so there is no cancelling before it exists.
  // Removing is the cancel, and it is final: nothing has been extracted and
  // nothing has been charged, so there is nothing worth keeping.
  async function remove(p: Pending) {
    if (busy || p.state === "reading") return;
    setError("");
    setBusy(`Removing ${p.filename}`);
    try {
      await api.removeDocument(p.document_id);
    } catch (err) {
      setError(String((err as Error)?.message ?? err));
    }
    setChoices((prev) => {
      const next = { ...prev };
      delete next[p.document_id];
      return next;
    });
    setBusy("");
    refresh();
  }

  async function fileAll() {
    const decisions: Decision[] = pending.map((p) => ({
      document_id: p.document_id,
      document_type: choices[p.document_id]?.type ?? p.proposed_type,
      include: true,
    }));
    setBusy("Filing");
    await api.file(id, decisions);
    setChoices({});
    setBusy("");
    refresh();
  }

  async function toggleActive(d: Doc) {
    // Optimistic: the row flips at once, and refresh confirms it.
    setDocs((prev) => prev.map((x) =>
      x.document_id === d.document_id ? { ...x, active: !x.active } : x));
    await api.setActive(d.document_id, !d.active);
    refresh();
  }

  async function generate() {
    setBusy("Generating - this takes a minute or two");
    await api.generate(id);
    setTimeout(() => { setBusy(""); refresh(); }, 150000);
  }

  function sortBy(key: SortKey) {
    if (key === sortKey) setSortDown(!sortDown);
    else { setSortKey(key); setSortDown(false); }
  }

  const visible = useMemo(() => {
    const needle = nameFilter.trim().toLowerCase();
    let rows = docs.filter((d) =>
      (showInactive || d.active) &&
      (!needle || d.filename.toLowerCase().includes(needle) ||
        (d.document_type ?? "").toLowerCase().includes(needle)));

    rows = [...rows].sort((a, b) => {
      let x: string | number = "";
      let y: string | number = "";
      if (sortKey === "values") { x = a.values; y = b.values; }
      else if (sortKey === "active") { x = a.active ? 1 : 0; y = b.active ? 1 : 0; }
      else { x = (a[sortKey] ?? "") as string; y = (b[sortKey] ?? "") as string; }
      if (x < y) return sortDown ? 1 : -1;
      if (x > y) return sortDown ? -1 : 1;
      return 0;
    });
    return rows;
  }, [docs, nameFilter, showInactive, sortKey, sortDown]);

  const activeCount = docs.filter((d) => d.active && d.state === "filed").length;

  const byCategory = types.reduce<Record<string, DocType[]>>((acc, t) => {
    (acc[t.category] ||= []).push(t);
    return acc;
  }, {});

  function arrow(key: SortKey) {
    if (key !== sortKey) return "";
    return sortDown ? " \u2193" : " \u2191";
  }

  return (
    <div>
      <a onClick={onBack} className="back">Back</a>
      <h2>{id}</h2>

      <input type="file" multiple onChange={(e) => upload(e.target.files)} />
      {busy && <p className="busy">{busy}</p>}
      {error && <p className="error">{error}</p>}

      {pending.length > 0 && (
        <>
          <h3>Ready to file</h3>
          {pending.map((p) => {
            const choice = choices[p.document_id] ??
              { type: p.proposed_type, include: true };
            const chosen = types.find((t) => t.key === choice.type);
            return (
              <div className="review" key={p.document_id}>
                <div className="review-head">
                  <strong>{p.filename}</strong>
                  <span className="muted">{p.pages ?? "?"} pages</span>
                  <button
                    className="secondary"
                    disabled={!!busy || p.state === "reading"}
                    onClick={() => remove(p)}
                    title={p.state === "reading"
                      ? "Being read. It can no longer be removed here."
                      : "Remove. The file and what was read from it both go."}
                  >
                    Remove
                  </button>
                </div>

                <div className="review-body">
                  <select
                    value={choice.type ?? ""}
                    onChange={(e) => setChoices({
                      ...choices,
                      [p.document_id]: { ...choice, type: e.target.value || null },
                    })}
                  >
                    <option value="">Not classified</option>
                    {Object.entries(byCategory).map(([category, list]) => (
                      <optgroup label={category} key={category}>
                        {list.map((t) => (
                          <option value={t.key} key={t.key}>{t.label}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>

                  {p.confidence && (
                    <span className={p.confidence === "low" ? "low" : "muted"}>
                      {p.confidence}
                    </span>
                  )}

                  {(p.thin_text || chosen?.always_ocr) && (
                    <span className="warn">will be read by OCR</span>
                  )}
                </div>

                {p.why && <p className="why">{p.why}</p>}
                {p.thin_text && (
                  <p className="why warn">
                    Little readable text &mdash; {p.chars} characters across{" "}
                    {p.pages} pages. Confirm the type and file it to read the scan.
                  </p>
                )}
              </div>
            );
          })}

          <button onClick={fileAll} disabled={!!busy || pending.length === 0}>
            File {pending.length}{" "}
            {pending.length === 1 ? "document" : "documents"}
          </button>
        </>
      )}

      <h3>Filed</h3>

      {docs.length === 0 && <p className="muted">Nothing filed yet.</p>}

      {docs.length > 0 && (
        <>
          <div className="filters">
            <input
              placeholder="Filter by name or type"
              value={nameFilter}
              onChange={(e) => setNameFilter(e.target.value)}
            />
            <label className="inline-check">
              <input
                type="checkbox"
                checked={showInactive}
                onChange={(e) => setShowInactive(e.target.checked)}
              />
              Show set aside
            </label>
            <span className="muted">{activeCount} of {docs.length} in use</span>
          </div>

          <table className="docs">
            <thead>
              <tr>
                <th onClick={() => sortBy("active")}>Use{arrow("active")}</th>
                <th onClick={() => sortBy("filename")}>Document{arrow("filename")}</th>
                <th onClick={() => sortBy("document_type")}>Type{arrow("document_type")}</th>
                <th onClick={() => sortBy("values")}>Values{arrow("values")}</th>
                <th onClick={() => sortBy("filed_at")}>Uploaded{arrow("filed_at")}</th>
                <th>By</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((d) => (
                <tr key={d.document_id} className={d.active ? "" : "aside"}>
                  <td>
                    <input
                      type="checkbox"
                      checked={d.active}
                      disabled={d.state === "reading"}
                      onChange={() => toggleActive(d)}
                      title={d.active
                        ? "In use. Uncheck to leave it out of the next memo."
                        : "Set aside" + (d.deactivated_by
                          ? " by " + d.deactivated_by : "")}
                    />
                  </td>
                  <td>
                    <a onClick={() =>
                      api.documentValues(d.document_id).then(setDetail)}>
                      {d.filename}
                    </a>
                  </td>
                  <td className="muted">
                    {d.state === "reading"
                      ? <span className="warn">reading&hellip;</span>
                      : (d.document_type ?? "unclassified")}
                  </td>
                  <td className="muted">
                    {d.state === "reading" || !d.extracted_at
                      ? <span className="warn">extracting&hellip;</span>
                      : d.values}
                  </td>
                  <td className="muted">{(d.filed_at ?? "").slice(0, 16)}</td>
                  <td className="muted">{d.uploaded_by ?? "\u2014"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3>Memos</h3>

      <button onClick={generate} disabled={settling || activeCount === 0}>
        {reading > 0
          ? `Wait \u2014 reading ${reading} ${reading === 1 ? "document" : "documents"}`
          : unfiled > 0
            ? `Wait \u2014 ${unfiled} to file`
            : busy
              ? "Wait\u2026"
              : `Generate memo from ${activeCount} ${activeCount === 1 ? "document" : "documents"}`}
      </button>

      <table>
        <tbody>
          {memos.map((m) => (
            <tr key={m.memo_id} onClick={() => onMemo(m.memo_id)}>
              <td><a>Memo {m.label}</a></td>
              <td className="muted">{(m.generated_at ?? "").slice(0, 16)}</td>
              <td className="muted">
                {m.modified_by
                  ? "modified by " + m.modified_by
                  : m.generated_by ?? "\u2014"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {detail && <ValuePanel detail={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

/** What one document yielded, and what its type called for but did not. */
function ValuePanel({ detail, onClose }: {
  detail: DocumentDetail;
  onClose: () => void;
}) {
  return (
    <div className="panel-backdrop" onClick={onClose}>
      <aside className="panel" onClick={(e) => e.stopPropagation()}>
        <a onClick={onClose} className="panel-close">Close</a>
        <h3>{detail.filename}</h3>
        <p className="muted">
          {detail.document_type ?? "unclassified"} &middot; {detail.pages} pages
          &middot; read by {detail.method ?? "unknown"}
        </p>

        <h4>Extracted &mdash; {detail.values.length} of {detail.expected} fields</h4>
        {detail.values.length === 0 && (
          <p className="muted">Nothing was extracted from this document.</p>
        )}
        <table>
          <tbody>
            {detail.values.map((v, i) => (
              <tr key={i}>
                <td className="muted">{v.label}</td>
                <td>{v.value}</td>
                <td className="ref">
                  {v.locator_kind && v.locator_kind !== "none"
                    ? `${v.locator_kind} ${v.locator_index}`
                    : "\u2014"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {detail.missing.length > 0 && (
          <>
            <h4>Looked for, not found</h4>
            <p className="muted">
              {detail.missing.map((m) => m.label).join(", ")}
            </p>
          </>
        )}
      </aside>
    </div>
  );
}
