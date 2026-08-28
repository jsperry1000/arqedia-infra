import { useEffect, useState } from "react";
import { api, type Pending, type DocType, type Decision, type Doc, type MemoRef } from "./api";

/**
 * The review step. Uploading analyses a document and proposes what it is;
 * a person confirms; filing starts extraction.
 *
 * The proposal is made from whatever text was readable. A certified scan
 * carries only its stamp, so the proposal will sometimes be confidently
 * wrong - which is why this screen exists rather than filing automatically.
 */

type Choice = { type: string | null; include: boolean };

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

  useEffect(() => {
    api.documentTypes().then((r) => setTypes(r.types));
  }, []);

  useEffect(() => { refresh(); }, [id]);

  // Poll only while something is unsettled: uploading, filing, or analysed
  // documents still waiting to be filed. A settled engagement polls not at all.
  const settling = busy !== "" || pending.length > 0 ||
    docs.some((d) => d.values === 0);

  useEffect(() => {
    if (!settling) return;
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [id, settling]);

  async function upload(files: FileList | null) {
    if (!files) return;
    for (const file of Array.from(files)) {
      setBusy("Uploading " + file.name);
      await api.upload(id, file);
    }
    setBusy("");
    refresh();
  }

  async function fileAll() {
    const decisions: Decision[] = pending.map((p) => ({
      document_id: p.document_id,
      document_type: choices[p.document_id]?.type ?? p.proposed_type,
      include: choices[p.document_id]?.include ?? true,
    }));
    setBusy("Filing");
    await api.file(id, decisions);
    setChoices({});
    setBusy("");
    refresh();
  }

  async function generate() {
    setBusy("Generating - this takes a minute or two");
    await api.generate(id);
    setTimeout(() => { setBusy(""); refresh(); }, 120000);
  }

  const byCategory = types.reduce<Record<string, DocType[]>>((acc, t) => {
    (acc[t.category] ||= []).push(t);
    return acc;
  }, {});

  const includedCount = pending.filter(
    (p) => choices[p.document_id]?.include ?? true).length;

  return (
    <div>
      <a onClick={onBack} className="back">Back</a>
      <h2>{id}</h2>

      <input type="file" multiple onChange={(e) => upload(e.target.files)} />
      {busy && <p className="busy">{busy}</p>}

      {pending.length > 0 && (
        <>
          <h3>Ready to file</h3>
          {pending.map((p) => {
            const choice = choices[p.document_id] ?? {
              type: p.proposed_type, include: true };
            return (
              <div className="review" key={p.document_id}>
                <div className="review-head">
                  <label>
                    <input
                      type="checkbox"
                      checked={choice.include}
                      onChange={(e) => setChoices({
                        ...choices,
                        [p.document_id]: { ...choice, include: e.target.checked },
                      })}
                    />
                    <strong>{p.filename}</strong>
                  </label>
                  <span className="muted">{p.pages ?? "?"} pages</span>
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

                  {p.thin_text && (
                    <span className="warn" title="Only a stamp or header was readable. Filing this will run optical character recognition.">
                      scan
                    </span>
                  )}
                </div>

                {p.why && <p className="why">{p.why}</p>}
                {p.thin_text && (
                  <p className="why warn">
                    Little readable text - {p.chars} characters across {p.pages} pages.
                    Confirm the type and file it to read the scan.
                  </p>
                )}
              </div>
            );
          })}

          <button onClick={fileAll} disabled={!!busy || includedCount === 0}>
            File {includedCount} {includedCount === 1 ? "document" : "documents"}
          </button>
        </>
      )}

      <h3>Filed</h3>
      {docs.length === 0 && <p className="muted">Nothing filed yet.</p>}
      <table>
        <tbody>
          {docs.map((d) => (
            <tr key={d.document_id}>
              <td>{d.filename}</td>
              <td className="muted">{d.document_type ?? "unclassified"}</td>
              <td className="muted">{d.pages ?? "-"} pages</td>
              <td className="muted">{d.values} values</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Memos</h3>
      <button onClick={generate} disabled={docs.length === 0 || !!busy}>
        Generate memo
      </button>
      <table>
        <tbody>
          {memos.map((m) => (
            <tr key={m.memo_id} onClick={() => onMemo(m.memo_id)}>
              <td><a>Memo {m.memo_id}</a></td>
              <td className="muted">{m.generated_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

