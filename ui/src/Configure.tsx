import { Fragment, useEffect, useMemo, useRef, useState } from "react";
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
import {
  slugKey, KeyLine, ColumnEditor, columnsReady, ReadModeControls,
} from "./config-parts";

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

      {/* The shape was locked on an existing field, with a note saying it
          could not change once values had been extracted. That is not true:
          extraction is pinned to the revision a document was filed under, so
          a shape change reaches documents filed from now on and leaves what
          is already read alone. Locking it forced a second field meaning the
          same thing, with the first left behind. */}
      <label className="row">
        <span>Shape</span>
        <select value={f.cardinality}
                onChange={(e) => setF({ ...f, cardinality: e.target.value })}>
          <option value="one">A single fact</option>
          <option value="many">Several values</option>
          <option value="group">A table &mdash; several rows with columns</option>
        </select>
      </label>
      {existing && (
        <p className="muted small">
          Changing the shape applies to documents filed from now on. What was
          already read from documents you have filed stays as it was, and
          memoranda already written still reproduce.
        </p>
      )}

      {isTable && (
        <ColumnEditor
          columns={f.columns as never}
          onChange={(next) => setF({ ...f, columns: next as never })}
          note={"What each row holds. A name means nothing without the things"
            + " beside it \u2014 a bank without its role, a shipper without"
            + " its route."} />
      )}

      <KeyLine value={key} />

      <div className="form-actions">
        <button disabled={!f.label.trim()
                  || (isTable && !columnsReady(f.columns as never))}
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

  // A document card saves on Save, so a half-typed description is a real
  // unsaved change. Asked about rather than discarded.
  const dirty = t.label !== (initial?.label ?? "")
    || t.category !== (initial?.category ?? (categories[0]?.key ?? ""))
    || t.description !== (initial?.description ?? "")
    || t.read_mode !== (initial?.read_mode ?? "text")
    || t.always_ocr !== (initial?.always_ocr ?? false);

  const leave = () => {
    if (dirty && !window.confirm(
      "Leave this document? What you changed is not saved.")) return;
    onCancel();
  };

  // A drawer, and it renders its own backdrop so that a click outside asks
  // the same question Cancel does. Rendered inline before, it sat wherever
  // the documents part happened to be scrolled to, and opening another
  // document silently replaced whatever was half-typed in it.
  return (
    <div className="panel-backdrop" onClick={leave}>
      <div className="panel narrow" onClick={(e) => e.stopPropagation()}
           onKeyDown={(e) => { if (e.key === "Escape") leave(); }}>
        <a className="panel-close" onClick={leave}>Close</a>
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

      <ReadModeControls readMode={t.read_mode} alwaysOcr={t.always_ocr}
                        onChange={(next) => setT({ ...t, ...next })} />

      <KeyLine value={key} />

      <div className="form-actions">
        <button disabled={!t.label.trim() || !t.description.trim()}
                onClick={() => onSave({ ...t, key })}>Save</button>
        <a className="secondary" onClick={leave}>Cancel</a>
        {existing && onDelete && (
          <a className="danger small" onClick={onDelete}>
            Delete this document
          </a>
        )}
      </div>
        </div>
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
    // Carried, not edited. This form does not show the position - the list
    // does - but a value a form holds and does not send is a value the save
    // discards. The editor also leaves it alone now, so this is belt and
    // braces rather than the fix.
    sort_order: initial?.sort_order,
  });
  const key = s.key ?? slugKey(s.title);

  const dirty = s.numeral !== (initial?.numeral ?? "")
    || s.title !== (initial?.title ?? "")
    || s.kind !== (initial?.kind ?? "extract")
    || s.prompt !== (initial?.prompt ?? "");

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

      {/* On both kinds now. An assembled section is written up by a second
          pass, and that pass had no instruction from the tenant at all - its
          only shaping came from a table inside the product, keyed on our own
          section names. A field description asking for three paragraphs
          shaped what was EXTRACTED and never reached the writer. */}
      <label className="row">
        <span>How it should read</span>
        <textarea rows={4} value={s.prompt}
          onChange={(e) => setS({ ...s, prompt: e.target.value })}
          placeholder={s.kind === "composed"
            ? "What this section should say, and what it must not."
            : "How this section should read \u2014 its length, whether it is "
              + "prose or a table, what to leave out."} />
      </label>

      <KeyLine value={key} />

      <div className="form-actions">
        <button disabled={!s.title.trim()}
                onClick={() => onSave({ ...s, key })}>Save</button>
        {/* Asked before an edit is thrown away. Clicking Edit on another
            section closes this one, and without the check a rewritten
            instruction would go with it silently. */}
        <a className="secondary" onClick={() => {
          if (dirty && !window.confirm(
            "Leave this section? What you changed is not saved.")) return;
          onCancel();
        }}>Cancel</a>
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
  // What is being typed into a position box, until it is left. Saving on
  // every keystroke would move the row out from under the cursor as soon as
  // the first digit of "10" was typed.
  const [order, setOrder] = useState<Record<string, string>>({});

  // A click anywhere else closes the open field list. It stayed open until
  // Close was found, and with ten sections that is a page of tick lists.
  const openList = useRef<HTMLDivElement | null>(null);

  /** A memorandum by the name a person gave it. */
  const labelOf = (key: string) =>
    templates.find((t) => t.key === key)?.label ?? key;

  const [proposing, setProposing] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [openSection, setOpenSection] = useState<string | null>(null);

  useEffect(() => {
    if (!openSection) return;
    const away = (e: MouseEvent) => {
      const box = openList.current;
      const at = e.target as Node | null;
      // Inside the list, or on the row that opened it: leave it be. The row
      // carries Close and Edit, and closing before those fire would make
      // them do nothing.
      if (!box || !at) return;
      if (box.contains(at)) return;
      if (box.parentElement && box.parentElement.contains(at)) return;

      // A drawer opened FROM this list is not "elsewhere on the page".
      // Without this, clicking a fact to read it closed the section behind
      // the drawer, so closing the drawer landed the person at the top of
      // the section list and they had to find their section again for every
      // fact they looked at.
      if (at instanceof Element && at.closest(".panel-backdrop")) return;

      setOpenSection(null);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [openSection]);
  // Which memorandum is being edited. A tenant may hold a credit, a KYC and a
  // lender memorandum over the same documents.
  const [template, setTemplate] = useState("");
  const [newTemplate, setNewTemplate] = useState("");
  // Renaming a memorandum. Held apart from the label being shown so an
  // abandoned edit leaves the name alone.
  const [renaming, setRenaming] = useState<string | null>(null);
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

  // The page is five long parts. Closed to begin with, so a person arrives
  // at a list of what is here rather than the middle of the fields table.
  const [shut, setShut] = useState<Set<string>>(new Set(
    ["says", "needs", "documents", "groups"]));

  const part = (key: string, label: string, count: string) => (
    <h3>
      <a onClick={() => {
        const next = new Set(shut);
        if (next.has(key)) next.delete(key); else next.add(key);
        setShut(next);
      }}>
        {shut.has(key) ? "\u25b8" : "\u25be"} {label}
      </a>{" "}
      <span className="muted small">{count}</span>
    </h3>
  );

  /** Put a section at a position and renumber the rest.
   *
   *  Typing the place is one edit where the arrows were nine clicks to move
   *  a section from the bottom to the top. Every section is renumbered from
   *  one afterwards, so two sections cannot share a number and tie - which
   *  is what left a memorandum reading VI, V, III, VIII. */
  const placeAt = (key: string, wanted: number) => {
    const rest = sections.filter((s) => s.key !== key);
    const moved = sections.find((s) => s.key === key);
    if (!moved) return;

    const at = Math.max(1, Math.min(wanted, sections.length)) - 1;
    const ordered = [...rest.slice(0, at), moved, ...rest.slice(at)];

    act("Reordering", async () => {
      for (let i = 0; i < ordered.length; i++) {
        if (ordered[i].sort_order === i + 1) continue;
        await api.saveSection({ ...ordered[i], sort_order: i + 1 });
      }
    });
  };

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

  // Every fact the tenant holds, alphabetical. Used wherever a person is
  // choosing from the whole vocabulary - a section's facts, a document's.
  const allFields = useMemo(
    () => [...(draft?.fields ?? [])]
      .sort((a, b) => a.label.localeCompare(b.label)),
    [draft]);

  /** Facts under the groups whose documents hold them, a column each.
   *
   *  A fact found in documents from two groups appears in BOTH columns. That
   *  is the truth about it, and the version that picked one group and hid
   *  the rest put financial figures under Corporate because Corporate sorted
   *  first. A fact in no document gets a column of its own rather than being
   *  dropped - one found nowhere is the one worth looking at. */
  const byGroup = useMemo(() => {
    const groupOf: Record<string, string> = {};
    for (const t of draft?.document_types ?? []) groupOf[t.key] = t.category;

    const out: { key: string; label: string; fields: ConfigField[] }[] = [];
    for (const c of draft?.categories ?? []) {
      const fields = allFields.filter(
        (f) => f.found_in.some((t) => groupOf[t] === c.key));
      if (fields.length) out.push({ key: c.key, label: c.label, fields });
    }

    const homeless = allFields.filter(
      (f) => !f.found_in.some((t) => groupOf[t]));
    if (homeless.length) {
      out.push({ key: "\u0000none", label: "In no document",
                 fields: homeless });
    }
    return out;
  }, [draft, allFields]);

  // The same list narrowed by the filter box, and used ONLY by the table that
  // box sits above. It was used by the section and document tick lists too,
  // so typing in a filter halfway down the page silently emptied controls
  // elsewhere on it - a section reading "3 fields" and offering one, with
  // nothing on screen to connect the two.
  const sortedFields = useMemo(() => {
    const needle = fieldFilter.trim().toLowerCase();
    return allFields.filter((f) => !needle ||
      f.label.toLowerCase().includes(needle) ||
      (f.description ?? "").toLowerCase().includes(needle));
  }, [allFields, fieldFilter]);

  /** The keys the filter box leaves visible. Kept apart from the grouping so
   *  that narrowing the list never changes where a fact sits. */
  const visible = useMemo(
    () => new Set(sortedFields.map((f) => f.key)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sortedFields]);


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
    // Asks the page for room: this screen carries lists grouped into a column
    // per document group, and four groups do not fit the width that suits
    // prose. See main:has(.wide-page).
    <div className="wide-page">
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

      {/* A fact, opened over the page. It used to sit inside "What it
          needs", so clicking a fact name from a section did nothing at all
          while that part was closed - which it is on arrival - and clicking
          one in the fields table opened a form above the filter box, out of
          sight of the row that was clicked. */}
      {editField !== null && (
        <div className="panel-backdrop" onClick={() => setEditField(null)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}>
            <a className="panel-close"
               onClick={() => setEditField(null)}>Close</a>
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
          </div>
        </div>
      )}

      {/* 1 --- what the report says ---------------------------------------- */}
      {part("says", "What the report says", `${sections.length} ${sections.length === 1 ? "section" : "sections"}`)}

      {!shut.has("says") && (<>
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
        {/* Renaming is free and reaches memoranda already written: the key is
            minted once and never follows the label, so nothing stored has to
            move. */}
        {current && renaming === null && (
          <a className="small"
             onClick={() => setRenaming(current.label || current.key)}>
            Rename
          </a>
        )}
        {/* A memorandum built from another rather than from nothing. A
            credit pack and a KYC pack share most of their sections, and
            rebuilding the second by hand is where they drift apart. */}
        {current && (
          <a className="small" onClick={() => act("Duplicating", async () => {
            const made = await api.duplicateTemplate(current.key);
            setTemplate(made.key);
          })}>
            Duplicate
          </a>
        )}
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

      {current && renaming !== null && (
        <div className="filters">
          <input value={renaming} autoFocus
                 onChange={(e) => setRenaming(e.target.value)} />
          <button disabled={!!busy || !renaming.trim()}
                  onClick={() => act("Renaming", async () => {
                    await api.saveTemplate(
                      { key: current.key, label: renaming.trim() });
                    setRenaming(null);
                  })}>
            Save
          </button>
          <a className="small" onClick={() => setRenaming(null)}>Cancel</a>
          <span className="muted small">
            The name only. Sections, bindings and memoranda already written
            are untouched.
          </span>
        </div>
      )}

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

      {sections.map((s, i) => (
        <div className="review" key={s.key}>
          <div className="review-head">
            {/* The order the memorandum reads in. There was no way to change
                it, so a memorandum whose sections all sat at zero stayed in
                whatever order the database returned. */}
            <input value={order[s.key] ?? String(i + 1)}
              style={{ width: "2.6em", textAlign: "center" }}
              title="Position"
              onChange={(e) => setOrder({ ...order, [s.key]: e.target.value })}
              onBlur={() => {
                const typed = parseInt(order[s.key] ?? "", 10);
                const next = { ...order };
                delete next[s.key];
                setOrder(next);
                if (!isNaN(typed) && typed !== i + 1) placeAt(s.key, typed);
              }} />
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
            <a className="small" onClick={() => {
              // One thing open at a time. Editing a section with
              // another section's field list open left both on screen
              // and it was not obvious which the buttons belonged to.
              setOpenSection(null);
              setEditSection(s.key);
            }}>Edit</a>
          </div>

          {openSection === s.key && (
            <div className="binder" ref={openList}>
              <p className="muted small">
                Which facts this section renders. A section binding a field
                that no longer exists would report it absent whether or not it
                was found, so that is refused here rather than at publish.
              </p>
              <div className="binder-groups">
                {byGroup.map((g) => (
                  <div key={g.key}>
                    <h5>{g.label}</h5>
                    {g.fields.map((f) => {
                      const on = s.fields.includes(f.key);
                      return (
                        <div className="bind" key={f.key}>
                          {/* The tick and the name do different things.
                              Wrapping both in one label meant clicking a name
                              to read what the fact is silently bound it. */}
                          <input type="checkbox" checked={on}
                            onChange={() => {
                              const next = on
                                ? s.fields.filter((x) => x !== f.key)
                                : [...s.fields, f.key];
                              act("Saving",
                                  () => api.setSectionFields(
                                    s.template_key, s.key, next));
                            }} />{" "}
                          <a onClick={() => setEditField(f.key)}>{f.label}</a>
                          {f.is_group && (
                            <span className="muted small"> (table)</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
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
      </>)}

      {part("needs", "What it needs", `${draft?.fields.length ?? 0} facts`)}

      {!shut.has("needs") && (<>
      <p className="muted small">
        Every fact the report can draw on. A field bound to no section is
        extracted and never read; one found in no document is never extracted.
      </p>

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
          {/* Under the group whose documents hold each fact, and a fact held
              by two groups appears under both. The filter still applies; it
              narrows what is shown rather than changing the grouping. */}
          {byGroup.map((g) => {
            const shown = g.fields.filter((x) => visible.has(x.key));
            if (shown.length === 0) return null;
            return (
              <Fragment key={g.key}>
                <tr className="group-head">
                  <td colSpan={3}>{g.label}</td>
                </tr>
                {shown.map((f) => (
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
              {/* The memorandum by its name, not its key. "stage1-kyc V"
                  told a person nothing about which report that was. */}
              <td className="muted small">
                {bound.has(f.key)
                  ? ((draft?.sections ?? [])
                      .filter((s) => s.fields.includes(f.key))
                      .map((s) => s.template_key === current?.key
                        ? `${s.numeral} ${s.title}`
                        : `${labelOf(s.template_key)} \u00b7 `
                          + `${s.numeral} ${s.title}`)
                      .join("; "))
                  : <span className="warn">nothing</span>}
              </td>
            </tr>
                ))}
              </Fragment>
            );
          })}
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
      </>)}

      {part("documents", "The documents", `${draft?.document_types.length ?? 0} kinds`)}

      {!shut.has("documents") && (<>
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

            <div className="binder-groups">
              {byGroup.map((g) => (
                <div key={g.key}>
                  <h5>{g.label}</h5>
                  {g.fields.map((f) => {
                    const on = typeFields.includes(f.key);
                    return (
                      <label className="bind" key={f.key}>
                        <input type="checkbox" checked={on}
                          onChange={() => setTypeFields(on
                            ? typeFields.filter((x) => x !== f.key)
                            : [...typeFields, f.key])} />
                        {f.label}
                        {f.is_group && (
                          <span className="muted small"> (table)</span>
                        )}
                      </label>
                    );
                  })}
                </div>
              ))}
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
      </>)}

      {part("groups", "How documents group", `${draft?.categories.length ?? 0} groups`)}

      {!shut.has("groups") && (<>
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
      </>)}

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
