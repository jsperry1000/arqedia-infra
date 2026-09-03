import { Fragment, useEffect, useMemo, useState } from "react";
import {
  api,
  type ConfigCategory,
  type ConfigDocumentType,
  type ConfigField,
  type ConfigSection,
  type ConfigState,
  type Draft,
  type Pack,
  type Validation,
} from "./api";
import { ProposeView } from "./Propose";

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

/**
 * A key is a field's permanent identity. Every extracted value points at it,
 * which is why renaming a label is free and deleting a field is not. It is
 * derived from the label so nobody has to invent an identifier, editable
 * until first saved, and fixed thereafter.
 */
function slugKey(label: string, prefix = ""): string {
  const body = label.toLowerCase().replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return (prefix + (body || "item")).slice(0, 64);
}

function KeyLine({ value }: { value: string }) {
  return (
    <div className="keyline">
      <span className="muted small">Identity</span> <code>{value}</code>
      <div className="muted small">
        Fixed once saved. Renaming the label afterwards changes nothing that
        was already extracted.
      </div>
    </div>
  );
}

type FieldDraft = {
  key?: string;
  label: string;
  type: string;
  cardinality: string;
  description: string;
  columns: { key?: string; label: string; type: string;
             description: string }[];
};

function FieldForm({ initial, onSave, onCancel, onDelete }: {
  initial?: ConfigField;
  onSave: (f: FieldDraft) => void;
  onCancel: () => void;
  onDelete?: () => void;
}) {
  const existing = Boolean(initial);
  const [f, setF] = useState<FieldDraft>({
    key: initial?.key,
    label: initial?.label ?? "",
    type: initial?.type ?? "text",
    cardinality: initial?.cardinality ?? "one",
    description: initial?.description ?? "",
    columns: (initial?.columns ?? []).map((c) => ({
      key: c.key, label: c.label, type: c.type,
      description: c.description ?? "",
    })),
  });

  const key = f.key ?? slugKey(f.label, "f_").replace(/-/g, "_");
  const isTable = f.cardinality === "group";

  return (
    <div className="form">
      <h4>{existing ? "Edit field" : "New field"}</h4>

      <label className="row">
        <span>Name</span>
        <input value={f.label} autoFocus
               onChange={(e) => setF({ ...f, label: e.target.value })} />
      </label>

      <label className="row">
        <span>What it is</span>
        <textarea rows={2} value={f.description}
          placeholder="What this fact is, in a sentence. This is what the system reads when deciding whether it has found it."
          onChange={(e) => setF({ ...f, description: e.target.value })} />
      </label>

      <label className="row">
        <span>Shape</span>
        <select value={f.cardinality}
                disabled={existing}
                onChange={(e) => setF({ ...f, cardinality: e.target.value })}>
          <option value="one">A single fact</option>
          <option value="many">Several values</option>
          <option value="group">A table &mdash; several rows with columns</option>
        </select>
      </label>
      {existing && (
        <p className="muted small">
          The shape cannot change once values have been extracted under it.
        </p>
      )}

      {isTable && (
        <div className="columns">
          <h4>Columns</h4>
          <p className="muted small">
            What each row holds. A name means nothing without the things
            beside it &mdash; a bank without its role, a shipper without its
            route.
          </p>

          {f.columns.map((c, i) => (
            <div className="column-row" key={i}>
              <input placeholder="Column" value={c.label}
                onChange={(e) => {
                  const next = [...f.columns];
                  next[i] = { ...c, label: e.target.value };
                  setF({ ...f, columns: next });
                }} />
              <input placeholder="What it holds" value={c.description}
                onChange={(e) => {
                  const next = [...f.columns];
                  next[i] = { ...c, description: e.target.value };
                  setF({ ...f, columns: next });
                }} />
              <a className="small" onClick={() =>
                setF({ ...f,
                       columns: f.columns.filter((_, j) => j !== i) })}>
                Remove
              </a>
            </div>
          ))}

          <a className="small" onClick={() => setF({ ...f, columns: [
            ...f.columns, { label: "", type: "text", description: "" }] })}>
            Add a column
          </a>
        </div>
      )}

      <KeyLine value={key} />

      <div className="form-actions">
        <button disabled={!f.label.trim()}
                onClick={() => onSave({ ...f, key })}>Save</button>
        <a className="secondary" onClick={onCancel}>Cancel</a>
        {existing && onDelete && (
          <a className="danger small" onClick={onDelete}>Delete this field</a>
        )}
      </div>
    </div>
  );
}

function TypeForm({ initial, categories, onSave, onCancel, onDelete }: {
  initial?: ConfigDocumentType;
  categories: ConfigCategory[];
  onSave: (t: Partial<ConfigDocumentType>) => void;
  onCancel: () => void;
  onDelete?: () => void;
}) {
  const existing = Boolean(initial);
  const [t, setT] = useState({
    key: initial?.key,
    label: initial?.label ?? "",
    category: initial?.category ?? (categories[0]?.key ?? ""),
    description: initial?.description ?? "",
    read_mode: initial?.read_mode ?? "text",
    always_ocr: initial?.always_ocr ?? false,
  });

  const key = t.key ?? slugKey(t.label);

  return (
    <div className="form">
      <h4>{existing ? "Edit document" : "New document"}</h4>

      <label className="row">
        <span>Name</span>
        <input value={t.label} autoFocus
               onChange={(e) => setT({ ...t, label: e.target.value })} />
      </label>

      <label className="row">
        <span>How to recognise it</span>
        <textarea rows={3} value={t.description}
          placeholder="A sentence describing this document. This is what the system reads to tell it from every other kind, so it is worth writing well."
          onChange={(e) => setT({ ...t, description: e.target.value })} />
      </label>

      <label className="row">
        <span>Group</span>
        <select value={t.category}
                onChange={(e) => setT({ ...t, category: e.target.value })}>
          {categories.map((c) => (
            <option key={c.key} value={c.key}>{c.label}</option>
          ))}
        </select>
      </label>

      <label className="row">
        <span>Read as</span>
        <select value={t.read_mode}
                onChange={(e) => setT({ ...t, read_mode: e.target.value })}>
          <option value="text">Prose</option>
          <option value="forms">Forms and tables</option>
          <option value="expense">Invoices</option>
        </select>
      </label>

      <label className="inline-check">
        <input type="checkbox" checked={t.always_ocr}
               onChange={(e) => setT({ ...t, always_ocr: e.target.checked })} />
        Always read by OCR, even where the file carries text
      </label>
      <p className="muted small">
        Worth setting where a garbled text layer would corrupt figures &mdash;
        statements and ledgers, chiefly.
      </p>

      <KeyLine value={key} />

      <div className="form-actions">
        <button disabled={!t.label.trim() || !t.description.trim()}
                onClick={() => onSave({ ...t, key })}>Save</button>
        <a className="secondary" onClick={onCancel}>Cancel</a>
        {existing && onDelete && (
          <a className="danger small" onClick={onDelete}>
            Delete this document
          </a>
        )}
      </div>
    </div>
  );
}

function CategoryForm({ initial, onSave, onCancel, onDelete }: {
  initial?: ConfigCategory;
  onSave: (c: Partial<ConfigCategory>) => void;
  onCancel: () => void;
  onDelete?: () => void;
}) {
  const existing = Boolean(initial);
  const [c, setC] = useState({
    key: initial?.key, label: initial?.label ?? "",
  });
  const key = c.key ?? slugKey(c.label);

  return (
    <div className="form">
      <h4>{existing ? "Edit group" : "New group"}</h4>
      <label className="row">
        <span>Name</span>
        <input value={c.label} autoFocus
               onChange={(e) => setC({ ...c, label: e.target.value })} />
      </label>
      <KeyLine value={key} />
      <div className="form-actions">
        <button disabled={!c.label.trim()}
                onClick={() => onSave({ ...c, key })}>Save</button>
        <a className="secondary" onClick={onCancel}>Cancel</a>
        {existing && onDelete && (
          <a className="danger small" onClick={onDelete}>Delete this group</a>
        )}
      </div>
    </div>
  );
}

function SectionForm({ initial, onSave, onCancel, onDelete }: {
  initial?: ConfigSection;
  onSave: (s: Partial<ConfigSection>) => void;
  onCancel: () => void;
  onDelete?: () => void;
}) {
  const existing = Boolean(initial);
  const [s, setS] = useState({
    key: initial?.key,
    numeral: initial?.numeral ?? "",
    title: initial?.title ?? "",
    kind: initial?.kind ?? "extract",
    prompt: initial?.prompt ?? "",
  });
  const key = s.key ?? slugKey(s.title);

  return (
    <div className="form">
      <h4>{existing ? "Edit section" : "New section"}</h4>

      <label className="row">
        <span>Number</span>
        <input value={s.numeral} placeholder="IX"
               onChange={(e) => setS({ ...s, numeral: e.target.value })} />
      </label>

      <label className="row">
        <span>Title</span>
        <input value={s.title} autoFocus
               onChange={(e) => setS({ ...s, title: e.target.value })} />
      </label>

      <label className="row">
        <span>How it is written</span>
        <select value={s.kind}
                onChange={(e) => setS({ ...s, kind: e.target.value })}>
          <option value="extract">
            Assembled from what was found
          </option>
          <option value="composed">Written by the model</option>
        </select>
      </label>

      {s.kind === "composed" && (
        <label className="row">
          <span>Instruction</span>
          <textarea rows={4} value={s.prompt}
            placeholder="What this section should say, and what it must not."
            onChange={(e) => setS({ ...s, prompt: e.target.value })} />
        </label>
      )}

      <KeyLine value={key} />

      <div className="form-actions">
        <button disabled={!s.title.trim()}
                onClick={() => onSave({ ...s, key })}>Save</button>
        <a className="secondary" onClick={onCancel}>Cancel</a>
        {existing && onDelete && (
          <a className="danger small" onClick={onDelete}>
            Delete this section
          </a>
        )}
      </div>
    </div>
  );
}


export function ConfigureView({ onBack }: { onBack: () => void }) {
  const [state, setState] = useState<ConfigState | null>(null);
  const [packs, setPacks] = useState<Pack[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);

  // How the person is starting. One of our memoranda, an empty one of their
  // own, or one read from a report they already write.
  const [start, setStart] = useState("");
  const [proposing, setProposing] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [openSection, setOpenSection] = useState<string | null>(null);
  // Which memorandum is being edited. A tenant may hold a credit, a KYC and a
  // lender memorandum over the same documents.
  const [template, setTemplate] = useState("");
  const [newTemplate, setNewTemplate] = useState("");
  const [openField, setOpenField] = useState<string | null>(null);
  const [fieldFilter, setFieldFilter] = useState("");

  // What is being added or amended. Null is nothing open; a key is that item;
  // the empty string is a new one.
  const [editField, setEditField] = useState<string | null>(null);
  const [editType, setEditType] = useState<string | null>(null);
  const [editCategory, setEditCategory] = useState<string | null>(null);
  const [editSection, setEditSection] = useState<string | null>(null);
  const [openType, setOpenType] = useState<string | null>(null);
  // Held while a document's fields are being ticked, so a dozen changes are
  // one save rather than a dozen.
  const [typeFields, setTypeFields] = useState<string[]>([]);

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

  const sortedFields = useMemo(() => {
    const needle = fieldFilter.trim().toLowerCase();
    return [...(draft?.fields ?? [])]
      .filter((f) => !needle ||
        f.label.toLowerCase().includes(needle) ||
        (f.description ?? "").toLowerCase().includes(needle))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [draft, fieldFilter]);

  // Documents as they are grouped for the person who has to say what one is,
  // and alphabetical within each group. Categories keep the order the
  // configuration gives them, because a tenant who has ordered their groups
  // deliberately meant it; only the documents are sorted.
  //
  // The count of fields sought is computed here rather than in the table, so
  // the rendering does not have to reach back into the draft.
  const documentGroups = useMemo(() => {
    if (!draft) return [];

    const sought = (key: string) =>
      draft.fields.filter((f) => f.found_in.includes(key)).length;

    const withCounts = (list: ConfigDocumentType[]) =>
      list.map((t) => ({ ...t, sought: sought(t.key) }))
          .sort((a, b) => a.label.localeCompare(b.label));

    const groups = draft.categories
      .map((c) => ({
        key: c.key,
        label: c.label,
        types: withCounts(
          draft.document_types.filter((t) => t.category === c.key)),
      }))
      .filter((g) => g.types.length > 0);

    // A document whose group has been deleted still exists and is still
    // extracted against. Dropping it because its heading is gone would hide a
    // live document behind a configuration mistake.
    const known = new Set(draft.categories.map((c) => c.key));
    const orphans = withCounts(
      draft.document_types.filter((t) => !known.has(t.category)));
    if (orphans.length > 0) {
      groups.push({ key: "ungrouped", label: "Ungrouped", types: orphans });
    }

    return groups;
  }, [draft]);

  // The memorandum on screen, and its sections. Nothing is inferred from the
  // order rows came back: an unset choice takes the first by key, and a
  // template deleted under the selection falls back to that.
  const templates = draft?.templates ?? [];
  const current = templates.find((t) => t.key === template)
    ?? templates[0];
  const sections = (draft?.sections ?? [])
    .filter((s) => s.template_key === current?.key);

  const bound = useMemo(() => {
    const set = new Set<string>();
    // Across EVERY memorandum. A field bound in the credit memo is used, even
    // while the KYC memo is on screen; showing it as unused would invite
    // deleting a field another memorandum renders.
    for (const s of draft?.sections ?? []) s.fields.forEach((f) => set.add(f));
    return set;
  }, [draft]);

  if (!state) return <p className="muted">Loading&hellip;</p>;

  // Reading a report of the client's own. Held above every other screen: it
  // is a conversation with its own shape, and nothing it proposes reaches the
  // draft until it is accepted.
  if (proposing) {
    return (
      <ProposeView
        onCancel={() => setProposing(false)}
        onDone={(templateKey) => {
          setProposing(false);
          setTemplate(templateKey);
          refresh().catch((e) => setError(message(e)));
        }}
      />
    );
  }

  // --- nothing configured yet: choose a starting point --------------------

  if (!state.draft && state.revisions.length === 0) {
    const pack = packs[0];

    return (
      <div>
        <a onClick={onBack} className="back">Back</a>
        <h2>Configure a Report</h2>
        <p className="muted">
          You start with our list of facts and the documents they are found
          in. What you choose here is the memorandum written from them.
          Everything is copied into your own configuration, so later changes
          we make to it will not reach you.
        </p>
        {error && <p className="error">{error}</p>}

        <label className="row">
          <span>Memorandum</span>
          <select value={start} onChange={(e) => setStart(e.target.value)}>
            <option value="">Choose&hellip;</option>
            {packs.map((p) => (
              <option key={p.revision} value={"pack:" + p.revision}>
                {p.note || "ARQEDIA memorandum"}
              </option>
            ))}
            <option value="scratch">Draft your own from scratch</option>
            <option value="report">
              Create your own from a report (.pdf, .docx)
            </option>
          </select>
        </label>

        {pack && (
          <p className="muted small">
            {pack.document_types} document types &middot; {pack.fields} facts,
            whichever you choose.
          </p>
        )}

        {start === "report" && (
          <p className="muted small">
            Give us a report you already write. We read its shape and put a
            configuration to you to correct &mdash; the file itself is read
            once and deleted.
          </p>
        )}

        {packs.length === 0 && (
          <p className="muted">No starting points are available yet.</p>
        )}

        {/* Both of the build-your-own routes still need the facts and the
            documents, so they take the pack too. Our memorandum comes with
            it and can be deleted; removing it unasked would be the one
            destructive thing on this screen. */}
        <button disabled={!start || !!busy || !pack}
                onClick={() => act("Setting up", async () => {
                  const revision = start.startsWith("pack:")
                    ? Number(start.slice(5)) : pack.revision;
                  await api.forkPack(revision);
                  if (start === "report") {
                    const now = await api.configState();
                    if (!now.draft) await api.openDraft();
                    setProposing(true);
                  }
                })}>
          {busy ? busy + "\u2026" : "Get to work"}
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

      <div className="filters">
        <label className="inline-check">
          Memorandum
          <select value={current?.key ?? ""}
                  onChange={(e) => {
                    setTemplate(e.target.value);
                    setOpenSection(null);
                    setEditSection(null);
                  }}>
            {templates.map((t) => (
              <option key={t.key} value={t.key}>{t.label || t.key}</option>
            ))}
          </select>
        </label>
        <span className="muted">
          {sections.length} {sections.length === 1 ? "section" : "sections"}
        </span>
        {templates.length > 1 && current && (
          <a className="danger small" onClick={() =>
            act("Deleting", async () => {
              await api.deleteTemplate(current.key);
              setTemplate("");
            })}>
            Delete this memorandum
          </a>
        )}
      </div>

      <p className="muted small">
        Every memorandum draws on the same facts and the same documents. What
        differs is which sections it has, what each renders, and how each is
        written. A document is read once whichever memoranda you write from it.
      </p>

      {editSection !== null && (
        <SectionForm
          initial={sections.find((x) => x.key === editSection)}
          onCancel={() => setEditSection(null)}
          onSave={(body) => act("Saving", async () => {
            await api.saveSection({ ...body,
                                    template_key: current?.key });
            setEditSection(null);
          })}
          onDelete={editSection ? () => act("Deleting", async () => {
            await api.deleteSection(current?.key ?? "", editSection);
            setEditSection(null);
          }) : undefined}
        />
      )}

      {sections.map((s) => (
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
            <a className="small" onClick={() => setEditSection(s.key)}>Edit</a>
          </div>

          {openSection === s.key && (
            <div className="binder">
              <p className="muted small">
                Which facts this section renders. A section binding a field
                that no longer exists would report it absent whether or not it
                was found, so that is refused here rather than at publish.
              </p>
              {sortedFields.map((f) => {
                const on = s.fields.includes(f.key);
                return (
                  <label className="bind" key={f.key}>
                    <input type="checkbox" checked={on}
                      onChange={() => {
                        const next = on
                          ? s.fields.filter((x) => x !== f.key)
                          : [...s.fields, f.key];
                        act("Saving",
                            () => api.setSectionFields(
                              s.template_key, s.key, next));
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

      <a className="small add" onClick={() => setEditSection("")}>
        Add a section
      </a>

      <div className="inline">
        <input placeholder="Add a memorandum" value={newTemplate}
               onChange={(e) => setNewTemplate(e.target.value)} />
        <button disabled={!!busy || !newTemplate.trim()}
                onClick={() => act("Adding", async () => {
                  const made = await api.saveTemplate(
                    { label: newTemplate.trim() });
                  setNewTemplate("");
                  setTemplate(made.key);
                })}>
          Add
        </button>
      </div>

      <p className="muted small">
        Or <a onClick={() => setProposing(true)}>
          create one from a report you already write
        </a>. We read its shape and put a configuration to you to correct.
      </p>

      {/* 2 --- what it needs ----------------------------------------------- */}
      <h3>What it needs</h3>
      <p className="muted small">
        Every fact the report can draw on. A field bound to no section is
        extracted and never read; one found in no document is never extracted.
      </p>

      {editField !== null && (
        <FieldForm
          initial={draft?.fields.find((x) => x.key === editField)}
          onCancel={() => setEditField(null)}
          onSave={(body) => act("Saving", async () => {
            await api.saveField(body as never);
            setEditField(null);
          })}
          onDelete={editField ? () => act("Deleting", async () => {
            await api.deleteField(editField);
            setEditField(null);
          }) : undefined}
        />
      )}

      <div className="filters">
        <input placeholder="Filter fields" value={fieldFilter}
               onChange={(e) => setFieldFilter(e.target.value)} />
        <span className="muted">
          {sortedFields.length} of {draft?.fields.length ?? 0}
        </span>
      </div>

      <table className="docs">
        <thead>
          <tr>
            <th>Field</th>
            <th>Found in</th>
            <th>Used by</th>
          </tr>
        </thead>
        <tbody>
          {sortedFields.map((f) => (
            <tr key={f.key} className={bound.has(f.key) ? "" : "aside"}>
              <td>
                <a onClick={() => setEditField(f.key)}>{f.label}</a>
                {f.is_group && (
                  <span className="muted small">
                    {" "}table of {f.columns.length}
                  </span>
                )}
              </td>
              <td className="muted small">
                <a onClick={() =>
                  setOpenField(openField === f.key ? null : f.key)}>
                  {f.found_in.length === 0
                    ? <span className="warn">no document</span>
                    : f.found_in.length + (f.found_in.length === 1
                        ? " document" : " documents")}
                </a>
              </td>
              <td className="muted small">
                {bound.has(f.key)
                  ? ((draft?.sections ?? [])
                      .filter((s) => s.fields.includes(f.key))
                      .map((s) => s.template_key === current?.key
                        ? s.numeral
                        : `${s.template_key} ${s.numeral}`)
                      .join(", "))
                  : <span className="warn">nothing</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <a className="small add" onClick={() => setEditField("")}>
        Add a field
      </a>

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

      {editType !== null && draft && (
        <TypeForm
          initial={draft.document_types.find((x) => x.key === editType)}
          categories={draft.categories}
          onCancel={() => setEditType(null)}
          onSave={(body) => act("Saving", async () => {
            await api.saveDocumentType(body);
            setEditType(null);
          })}
          onDelete={editType ? () => act("Deleting", async () => {
            await api.deleteDocumentType(editType);
            setEditType(null);
          }) : undefined}
        />
      )}

      <table className="docs">
        <thead>
          <tr>
            <th>Document</th>
            <th>Read as</th>
            <th>Fields sought</th>
          </tr>
        </thead>
        <tbody>
          {documentGroups.map((group) => (
            <Fragment key={group.key}>
              <tr className="group-head">
                <td colSpan={4}>
                  {group.label}
                  <span className="muted small">
                    {" \u00b7 "}{group.types.length}
                  </span>
                </td>
              </tr>
              {group.types.map((t) => (
                <tr key={t.key} className={t.sought ? "" : "aside"}>
                  <td>
                    <a onClick={() => setEditType(t.key)}>
                      <strong>{t.label}</strong>
                    </a>
                    <div className="muted small">{t.description}</div>
                  </td>
                  <td className="muted small">
                    {t.read_mode}{t.always_ocr ? " \u00b7 always OCR" : ""}
                  </td>
                  <td className="muted small">
                    <a onClick={() => {
                      setOpenType(t.key);
                      setTypeFields((draft?.fields ?? [])
                        .filter((f) => f.found_in.includes(t.key))
                        .map((f) => f.key));
                    }}>
                      {t.sought || <span className="warn">none</span>}
                    </a>
                  </td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>

      <a className="small add" onClick={() => setEditType("")}>
        Add a document
      </a>


      {openType && draft && (
        <div className="panel-backdrop" onClick={() => setOpenType(null)}>
          <aside className="panel" onClick={(e) => e.stopPropagation()}>
            <a onClick={() => setOpenType(null)} className="panel-close">
              Close
            </a>
            <h3>
              {draft.document_types.find((t) => t.key === openType)?.label}
            </h3>
            <p className="muted small">
              What is looked for in this document. The same relationship as
              &ldquo;where is this field found&rdquo;, read from the other end
              &mdash; changing it here changes it there.
            </p>

            <div className="binder">
              {sortedFields.map((f) => {
                const on = typeFields.includes(f.key);
                return (
                  <label className="bind" key={f.key}>
                    <input type="checkbox" checked={on}
                      onChange={() => setTypeFields(on
                        ? typeFields.filter((x) => x !== f.key)
                        : [...typeFields, f.key])} />
                    {f.label}
                    {f.is_group && <span className="muted small"> (table)</span>}
                  </label>
                );
              })}
            </div>

            <div className="form-actions">
              <button disabled={!!busy} onClick={() =>
                act("Saving", async () => {
                  await api.setDocumentFields(openType, typeFields);
                  setOpenType(null);
                })}>
                Save {typeFields.length}{" "}
                {typeFields.length === 1 ? "field" : "fields"}
              </button>
              <a className="secondary" onClick={() => setOpenType(null)}>
                Cancel
              </a>
            </div>
          </aside>
        </div>
      )}

      {/* 4b --- how documents group ----------------------------------------- */}
      <h3>How documents group</h3>
      <p className="muted small">
        Grouping is for the eye alone &mdash; it decides how documents are
        listed when somebody confirms what one is. It has no effect on what is
        extracted.
      </p>

      {editCategory !== null && (
        <CategoryForm
          initial={draft?.categories.find((x) => x.key === editCategory)}
          onCancel={() => setEditCategory(null)}
          onSave={(body) => act("Saving", async () => {
            await api.saveCategory(body);
            setEditCategory(null);
          })}
          onDelete={editCategory ? () => act("Deleting", async () => {
            await api.deleteCategory(editCategory);
            setEditCategory(null);
          }) : undefined}
        />
      )}

      <table className="docs">
        <tbody>
          {draft?.categories.map((c) => {
            const count = draft.document_types.filter(
              (t) => t.category === c.key).length;
            return (
              <tr key={c.key}>
                <td><a onClick={() => setEditCategory(c.key)}>{c.label}</a></td>
                <td className="muted small">
                  {count} {count === 1 ? "document" : "documents"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <a className="small add" onClick={() => setEditCategory("")}>
        Add a group
      </a>

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
