import { useEffect, useMemo, useState } from "react";
import {
  api,
  type ConfigState,
  type Draft,
  type Pack,
  type Validation,
} from "./api";

/**
 * Configure a Report.
 *
 * The page reads in the order a person thinks, which is the reverse of the
 * order the machine stores:
 *
 *   1. Sections    what the report says
 *   2. Fields      what each section needs
 *   3. Documents   where those facts are found
 *   4. Categories  how the documents group
 *
 * The schema never appears. In the data model a field belongs to a schema and
 * a schema is fed by document types; here a person answers "where is this
 * found?" and the schema is derived behind them. Nobody outside the pipeline
 * needs the word.
 *
 * Editing writes a draft. Nothing reaches a memo until it is published, and a
 * published revision is never edited - it is what memos were composed against.
 */

export function ConfigureView({ onBack }: { onBack: () => void }) {
  const [state, setState] = useState<ConfigState | null>(null);
  const [packs, setPacks] = useState<Pack[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);

  const [chosen, setChosen] = useState<number | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [openSection, setOpenSection] = useState<string | null>(null);
  const [openField, setOpenField] = useState<string | null>(null);

  function message(err: unknown) {
    let text = String((err as Error)?.message ?? err);
    try { text = JSON.parse(text).error ?? text; } catch { /* as it came */ }
    return text;
  }

  async function refresh() {
    const s = await api.configState();
    setState(s);
    setValidation(s.validation ?? null);
    if (s.draft) setDraft(await api.draft());
    else setDraft(null);
  }

  useEffect(() => {
    api.packs().then((p) => setPacks(p.packs)).catch(() => setPacks([]));
    refresh().catch((e) => setError(message(e)));
  }, []);

  async function act(what: string, fn: () => Promise<unknown>) {
    setBusy(what);
    setError("");
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  }

  const fieldsByKey = useMemo(() => {
    const map: Record<string, string> = {};
    for (const f of draft?.fields ?? []) map[f.key] = f.label;
    return map;
  }, [draft]);

  const bound = useMemo(() => {
    const set = new Set<string>();
    for (const s of draft?.sections ?? []) s.fields.forEach((f) => set.add(f));
    return set;
  }, [draft]);

  if (!state) return <p className="muted">Loading&hellip;</p>;

  // --- nothing configured yet: choose a starting point --------------------

  if (!state.draft && state.revisions.length === 0) {
    return (
      <div>
        <a onClick={onBack} className="back">Back</a>
        <h2>Configure a Report</h2>
        <p className="muted">
          Choose a starting point. It is copied into your own configuration, so
          later changes we make to it will not reach you.
        </p>
        {error && <p className="error">{error}</p>}

        <table className="docs">
          <tbody>
            {packs.map((p) => (
              <tr key={p.revision}
                  className={chosen === p.revision ? "" : ""}>
                <td>
                  <input type="radio" name="pack" checked={chosen === p.revision}
                         onChange={() => setChosen(p.revision)} />
                </td>
                <td>
                  <strong>{p.note || "Starter pack"}</strong>
                  <div className="muted small">
                    {p.document_types} document types &middot; {p.fields} fields
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {packs.length === 0 && (
          <p className="muted">No starting points are available yet.</p>
        )}

        <button disabled={chosen === null || !!busy}
                onClick={() => act("Setting up",
                                   () => api.forkPack(chosen as number))}>
          {busy ? busy + "\u2026" : "Start editing"}
        </button>
      </div>
    );
  }

  // --- published, no draft open -------------------------------------------

  if (!state.draft) {
    return (
      <div>
        <a onClick={onBack} className="back">Back</a>
        <h2>Configure a Report</h2>
        <p className="muted">
          Revision {state.active_revision} is in use. Memos are written against
          it, and it cannot be edited &mdash; editing opens a copy, and nothing
          reaches a memo until you publish.
        </p>
        {error && <p className="error">{error}</p>}

        <button disabled={!!busy} onClick={() => act("Opening", api.openDraft)}>
          {busy ? busy + "\u2026" : "Start editing"}
        </button>

        <h3>History</h3>
        <table className="docs">
          <tbody>
            {state.revisions.map((r) => (
              <tr key={r.revision}>
                <td><strong>Revision {r.revision}</strong></td>
                <td className="muted">{r.note}</td>
                <td className="muted">
                  {(r.published_at ?? "").slice(0, 16)}
                  {r.published_by ? " \u00b7 " + r.published_by : ""}
                </td>
                <td>
                  {r.revision === state.active_revision && (
                    <span className="in-use">in use</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // --- editing --------------------------------------------------------------

  return (
    <div>
      <a onClick={onBack} className="back">Back</a>

      <div className="memo-head">
        <div>
          <h2>Configure a Report</h2>
          <p className="muted">
            Editing a draft. Revision {state.active_revision} stays in use
            until you publish.
          </p>
        </div>
        <a className="secondary" onClick={() =>
          act("Discarding", api.discardDraft)}>Discard</a>
      </div>

      {error && <p className="error">{error}</p>}
      {busy && <p className="busy">{busy}&hellip;</p>}

      {validation && !validation.may_publish && (
        <div className="revision-note fatal">
          <strong>This cannot be published yet.</strong>
          <ul>
            {validation.fatal.map((f, i) => <li key={i}>{f.detail}</li>)}
          </ul>
        </div>
      )}

      {/* 1 --- what the report says ---------------------------------------- */}
      <h3>What the report says</h3>
      <p className="muted small">
        Each section of the memorandum, in order. A section renders the fields
        bound to it and nothing else.
      </p>

      {draft?.sections.map((s) => (
        <div className="review" key={s.key}>
          <div className="review-head">
            <label>
              <strong>{s.numeral}. {s.title}</strong>
            </label>
            <span className="muted small">
              {s.kind === "composed" ? "written by the model" : "assembled"}
              {" \u00b7 "}{s.fields.length} fields
            </span>
            <a className="small" onClick={() =>
              setOpenSection(openSection === s.key ? null : s.key)}>
              {openSection === s.key ? "Close" : "Fields"}
            </a>
          </div>

          {openSection === s.key && (
            <div className="binder">
              <p className="muted small">
                Which facts this section renders. A section binding a field
                that no longer exists would report it absent whether or not it
                was found, so that is refused here rather than at publish.
              </p>
              {draft.fields.map((f) => {
                const on = s.fields.includes(f.key);
                return (
                  <label className="bind" key={f.key}>
                    <input type="checkbox" checked={on}
                      onChange={() => {
                        const next = on
                          ? s.fields.filter((x) => x !== f.key)
                          : [...s.fields, f.key];
                        act("Saving",
                            () => api.setSectionFields(s.key, next));
                      }} />
                    {f.label}
                    {f.is_group && <span className="muted small"> (table)</span>}
                  </label>
                );
              })}
            </div>
          )}
        </div>
      ))}

      {/* 2 --- what it needs ----------------------------------------------- */}
      <h3>What it needs</h3>
      <p className="muted small">
        Every fact the report can draw on. A field bound to no section is
        extracted and never read; one found in no document is never extracted.
      </p>

      <table className="docs">
        <thead>
          <tr>
            <th>Field</th>
            <th>Found in</th>
            <th>Used by</th>
          </tr>
        </thead>
        <tbody>
          {draft?.fields.map((f) => (
            <tr key={f.key} className={bound.has(f.key) ? "" : "aside"}>
              <td>
                <a onClick={() =>
                  setOpenField(openField === f.key ? null : f.key)}>
                  {f.label}
                </a>
                {f.is_group && <span className="muted small"> (table)</span>}
              </td>
              <td className="muted small">
                {f.found_in.length === 0
                  ? <span className="warn">no document</span>
                  : f.found_in.length + (f.found_in.length === 1
                      ? " document" : " documents")}
              </td>
              <td className="muted small">
                {bound.has(f.key)
                  ? (draft.sections.filter((s) => s.fields.includes(f.key))
                      .map((s) => s.numeral).join(", "))
                  : <span className="warn">nothing</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* 3 --- where it is found -------------------------------------------- */}
      {openField && draft && (
        <div className="panel-backdrop" onClick={() => setOpenField(null)}>
          <aside className="panel" onClick={(e) => e.stopPropagation()}>
            <a onClick={() => setOpenField(null)} className="panel-close">
              Close
            </a>
            <h3>{fieldsByKey[openField]}</h3>
            <p className="muted small">
              Which documents this fact is expected to be found in. It is
              looked for in these and nowhere else.
            </p>

            {draft.categories.map((c) => (
              <div key={c.key}>
                <h4>{c.label}</h4>
                {draft.document_types
                  .filter((t) => t.category === c.key)
                  .map((t) => {
                    const field = draft.fields.find((f) => f.key === openField);
                    const on = field?.found_in.includes(t.key) ?? false;
                    return (
                      <label className="bind" key={t.key}>
                        <input type="checkbox" checked={on}
                          onChange={() => {
                            const current = field?.found_in ?? [];
                            const next = on
                              ? current.filter((x) => x !== t.key)
                              : [...current, t.key];
                            act("Saving",
                                () => api.setFieldDocuments(openField, next));
                          }} />
                        {t.label}
                      </label>
                    );
                  })}
              </div>
            ))}
          </aside>
        </div>
      )}

      {/* 4 --- the documents ------------------------------------------------ */}
      <h3>The documents</h3>
      <p className="muted small">
        What a customer might send you. The description is what the system
        reads to tell one document from another, so it is worth writing well.
      </p>

      <table className="docs">
        <thead>
          <tr>
            <th>Document</th>
            <th>Group</th>
            <th>Read as</th>
            <th>Fields sought</th>
          </tr>
        </thead>
        <tbody>
          {draft?.document_types.map((t) => {
            const sought = draft.fields.filter(
              (f) => f.found_in.includes(t.key)).length;
            return (
              <tr key={t.key} className={sought ? "" : "aside"}>
                <td>
                  <strong>{t.label}</strong>
                  <div className="muted small">{t.description}</div>
                </td>
                <td className="muted small">
                  {draft.categories.find((c) => c.key === t.category)?.label
                    ?? t.category}
                </td>
                <td className="muted small">
                  {t.read_mode}{t.always_ocr ? " \u00b7 always OCR" : ""}
                </td>
                <td className="muted small">
                  {sought || <span className="warn">none</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* 5 --- publish ------------------------------------------------------ */}
      <h3>Publish</h3>

      {validation && validation.warnings.length > 0 && (
        <details className="warnings">
          <summary>
            {validation.warnings.length} things worth knowing
          </summary>
          <ul>
            {validation.warnings.map((w, i) => <li key={i}>{w.detail}</li>)}
          </ul>
        </details>
      )}

      <p className="muted small">
        Publishing makes this the configuration new work is filed against.
        Everything already filed keeps resolving against the revision it was
        filed under, so memos already written still reproduce.
      </p>

      <div className="inline">
        <input placeholder="What changed?" value={note}
               onChange={(e) => setNote(e.target.value)} />
        <button
          disabled={!!busy || (validation ? !validation.may_publish : false)}
          onClick={() => act("Publishing", async () => {
            await api.publish(note);
            setNote("");
          })}>
          {busy ? busy + "\u2026" : "Publish"}
        </button>
      </div>
    </div>
  );
}
