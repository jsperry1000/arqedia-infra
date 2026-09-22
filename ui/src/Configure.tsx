import { Fragment, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useBackAction, usePinTop, Working } from "./shell";
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
import { StageStrip, StageIcon } from "./StageStrip";
import type { Stage } from "./flock";
import type { Report as StartReport } from "./Welcome";
import {
  slugKey, KeyLine, ColumnEditor, columnsReady, ReadModeControls, useGrows,
} from "./config-parts";

// --- what Get started brought -----------------------------------------------

/** "A", "A and B", "A, B and C". Written out because these are memoranda by
 *  name and a person reads them as a sentence. */
function list(names: string[]) {
  if (names.length <= 1) return names[0] ?? "";
  return names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
}

/** Six names, then a count. The long one here is facts, which can run to
 *  thirty - all thirty would push the editor off the screen, and the editor is
 *  where they can be looked at properly. */
function some(names: string[]) {
  if (names.length <= 6) return list(names);
  return names.slice(0, 6).join(", ") + ` and ${names.length - 6} more`;
}

/** The kinds that brought something, in the order a person meets them. A
 *  schema is the one word the configuration screen never uses, so it is not
 *  reported either - it is machinery, and every fact it carries is listed. */
function added(report: StartReport): [string, string[]][] {
  return ([
    ["facts", report.added.facts],
    ["document types", report.added.document_types],
    ["categories", report.added.categories],
  ] as [string, string[]][]).filter(([, names]) => names.length > 0);
}

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

function FieldForm({ initial, onSave, onCancel, onDelete, onShowDocuments,
                    error }: {
  initial?: ConfigField;
  onSave: (f: FieldDraft) => void;
  onCancel: () => void;
  onDelete?: () => void;
  onShowDocuments?: () => void;
  /** A refusal from the save, shown HERE (17.1). The screen's own error line
   *  sits behind this drawer's backdrop, so a fact refused for holding a name
   *  already taken looked like a Save that did nothing at all. */
  error?: string;
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

  // What the fact is grows with what is written, to 25 lines, then scrolls
  // (UX-09). The same box as "How it should read" on a section, and the same
  // measuring: this description is what the system reads when deciding
  // whether it has found the fact, so it is often several sentences and was
  // being written into two visible rows.
  const describe = useGrows(f.description);

  return (
    <div className="form">
      <h4>{existing ? "Edit field" : "New field"}</h4>

      {/* OUTSIDE THE LABEL. A label hands every click to its input, so the
          link inside one only focused the Name box - it flickered and did
          nothing. Where this fact is looked for still reads beside the name;
          it is simply no longer part of the label. */}
      <div className="row">
        <span>
          <label htmlFor={"name-" + key}>Name</label>
          {existing && onShowDocuments && (
            <span className="muted small">
              {" \u00b7 "}found in{" "}
              <a onClick={onShowDocuments}>
                {(initial?.found_in ?? []).length === 0
                  ? <span className="warn">no document</span>
                  : (initial?.found_in ?? []).length
                    + ((initial?.found_in ?? []).length === 1
                       ? " document" : " documents")}
              </a>
            </span>
          )}
        </span>
        <input id={"name-" + key} value={f.label} autoFocus
               onChange={(e) => setF({ ...f, label: e.target.value })} />
      </div>

      <label className="row">
        <span>What it is</span>
        <textarea rows={2} value={f.description} ref={describe} className="grows"
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

      {/* Kept above the buttons, where the press was. Nothing typed is
          cleared: the card stays open on a refusal, holding its own state,
          and a person fixes the name and presses Save again. */}
      {error && <p className="error">{error}</p>}

      <div className="form-actions">
        {/* THE KEY IS SENT ONLY WHEN EDITING (17.1). A key in the body means
            "this fact exists, change it"; without one the server mints the
            key and refuses if it is taken. The key is still SHOWN above -
            somebody naming a fact should see the identity it will carry -
            but showing it and claiming it are different things. */}
        <button disabled={!f.label.trim()
                  || (isTable && !columnsReady(f.columns as never))}
                onClick={() => onSave(existing ? { ...f, key }
                                               : { ...f, key: undefined })}>Save</button>
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

  // How it should read grows with what is written, to a ceiling of 25 lines,
  // and then scrolls inside itself (UX-09). The field card's description box
  // does the same, through the same hook.
  const prompt = useGrows(s.prompt);

  const dirty = s.numeral !== (initial?.numeral ?? "")
    || s.title !== (initial?.title ?? "")
    || s.kind !== (initial?.kind ?? "extract")
    || s.prompt !== (initial?.prompt ?? "");

  const leave = () => {
    if (dirty && !window.confirm(
      "Leave this section? What you changed is not saved.")) return;
    onCancel();
  };

  // A drawer, and it renders its own backdrop so a click outside asks the
  // same question Cancel does. Inline it sat wherever the sections part was
  // scrolled to, and there was no way to dismiss it but Cancel.
  return (
    <div className="panel-backdrop" onClick={leave}>
      <div className="panel narrow" onClick={(e) => e.stopPropagation()}
           onKeyDown={(e) => { if (e.key === "Escape") leave(); }}>
        <a className="panel-close" onClick={leave}>Close</a>
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
        <textarea rows={4} value={s.prompt} ref={prompt} className="grows"
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
        <a className="secondary" onClick={leave}>Cancel</a>
        {existing && onDelete && (
          <a className="danger small" onClick={onDelete}>
            Delete this section
          </a>
        )}
      </div>
        </div>
      </div>
    </div>
  );
}


/**
 * Every delete asks first (UX-10), in a drawer rather than a browser dialog,
 * and says what the deletion reaches.
 *
 * Nothing in the API computes what else refers to a thing - each delete
 * returns only the key it removed - so the drawer carries no count of
 * references. It says what the editor does on delete, and that the draft is
 * all it touches.
 */
const DRAFT_ONLY = "This changes the draft only. Nothing changes until you "
  + "publish, and no document already filed is touched.";

/** A deletion waiting to be confirmed. A name is typed only for a whole
 *  memorandum. */
type Deleting = {
  title: string;
  reaches: string;
  action: string;
  name?: string;
  run: () => Promise<unknown>;
};

// The parts of the configuration screen, in the order the band offers them.
// How documents group sits on the documents tab rather than a tab of its own.
//
// IN THE STRIP'S ORDER (18.3). The band ran Report sections, Facts, Document
// types while the strip above it ran Documents, Facts, Filed, Report - so the
// two read in opposite directions and the lit miniature travelled backwards
// against the tab beneath it. The band now follows the strip: documents
// arrive, facts are made of them, a report is written from them.
//
// Each carries the line it needs (3.1, 18.4) and the stage of the home page's
// sequence it stands for (3.2). Stage 1 - the swarm, which is the work the
// model does between a document arriving and a fact being filed - belongs to
// no part of the configuration and is never lit.
const PARTS = [
  ["documents", "Document types",
   "Which documents are expected to contain required facts", 0],
  ["facts", "Facts",
   "The extracted facts which all memos draw upon", 2],
  ["sections", "Report sections",
   "What the memorandum says, and in what order", 3],
] as const;

export function ConfigureView({ onBack }: { onBack: () => void }) {
  // Which memorandum, which part and which section is open live in the
  // address, so a refresh returns a person to where they were (UX-13).
  const [params, setParams] = useSearchParams();

  /** Change part of the address. Replaced rather than pushed, so Back leaves
   *  the screen instead of stepping through every tab looked at on the way.
   *  Read from the address itself rather than from this render: two changes
   *  in one handler, or one after an await, would otherwise both start from
   *  the same stale copy and the second would undo the first. */
  const place = (next: Record<string, string | null>) => {
    const merged = new URLSearchParams(window.location.search);
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value); else merged.delete(key);
    }
    setParams(merged, { replace: true });
  };

  const openSection = params.get("section");
  const setOpenSection = (key: string | null) => place({ section: key });

  const [state, setState] = useState<ConfigState | null>(null);
  const [packs, setPacks] = useState<Pack[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [validation, setValidation] = useState<Validation | null>(null);

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

  // Reading a report of the client's own. Begun from the rail's chooser as
  // well as from inside the editor; the chooser says so in the location's
  // state, so the screen opens straight onto the proposer's upload.
  const location = useLocation();
  const navigate = useNavigate();
  const arrived = location.state as
    { propose?: boolean; report?: StartReport } | null;
  const [proposing, setProposing] = useState(Boolean(arrived?.propose));
  // What Get started just did, reported here rather than on the screen that
  // did it: the person is sent straight on, and the account of what arrived
  // belongs where they can see the things themselves. Held in state so it can
  // be dismissed, and read once - a refresh is not a fresh arrival.
  const [started, setStarted] = useState<StartReport | null>(
    arrived?.report ?? null);
  // Leaving clears that state too, so a refresh does not reopen it.
  const leaveProposer = () => { setProposing(false); place({}); };

  // Back leaves the proposer for the editor; otherwise it leaves the screen.
  useBackAction(proposing ? leaveProposer : onBack);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  // Publishing is asked from the bar and confirmed in a drawer.
  const [publishing, setPublishing] = useState(false);

  // Searching a section's field list. Its own box, cleared when the section
  // closes: a filter shared with the fact table once emptied controls
  // elsewhere on the page, which nobody could connect to what they typed.
  const [sectionSearch, setSectionSearch] = useState("");

  // Which group is open in a list. One at a time, because ninety facts under
  // five headings is not a list a person reads.
  const [openFactGroup, setOpenFactGroup] = useState<string | null>(null);
  const [openDocGroup, setOpenDocGroup] = useState<string | null>(null);
  const [typeSearch, setTypeSearch] = useState("");

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
  // In the address, beside the part and the open section. A different
  // memorandum closes whichever section was open.
  const template = params.get("report") ?? "";
  const setTemplate = (key: string) =>
    place({ report: key || null, section: null });
  const [newTemplate, setNewTemplate] = useState("");
  // Renaming a memorandum. Held apart from the label being shown so an
  // abandoned edit leaves the name alone.
  const [renaming, setRenaming] = useState<string | null>(null);
  // A deletion waiting to be confirmed, and the name typed for a memorandum.
  const [deleting, setDeleting] = useState<Deleting | null>(null);
  const [typedName, setTypedName] = useState("");
  const [openField, setOpenField] = useState<string | null>(null);
  const [fieldFilter, setFieldFilter] = useState("");
  // A fact being added from a section's own list, and the section to bind it
  // to when it saves. Null when the card was opened from the Facts tab, where
  // a new fact belongs to the vocabulary and to no section in particular.
  const [bindNewTo, setBindNewTo] =
    useState<{ template_key: string; key: string } | null>(null);
  // Searching the fields a document is looked at for (2.6). Its own box, like
  // the section list's: a filter shared between two lists empties controls
  // nobody can connect to what they typed.
  const [typeFieldSearch, setTypeFieldSearch] = useState("");

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

  // The page is three parts, one on screen at a time, chosen in the bar. It
  // was five long collapsible parts, and a person twenty rows into one had to
  // scroll back up to reach another. Changing part closes the open section.
  const wantedPart = params.get("part");
  // DOCUMENTS BY DEFAULT (18.3). It opened on Report sections, which is
  // where the work ends; the band now reads in the order the business runs
  // and the screen opens at its start. An address carrying a part still
  // wins, so a link into a tab lands in that tab.
  const part = PARTS.some(([key]) => key === wantedPart)
    ? wantedPart as string : "documents";
  const setPart = (key: string) => place({ part: key, section: null });

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

  /** Bind or unbind facts on one section, WITHOUT reloading the screen.
   *
   *  A tick used to run act(), which is three calls in series: the save, then
   *  GET /config - which revalidates the whole draft server-side - and GET
   *  /config/draft. Both reads replace `draft` wholesale, so every list on the
   *  page re-rendered before the tick appeared to take. Measured on dev over
   *  the last three days: GET /config a median of 487 ms, GET /config/draft
   *  328 ms, before the save itself.
   *
   *  So the draft is changed here first and the tick lands at once; the save
   *  follows; a failure puts back exactly what was there and says so.
   *  Validation is read afterwards on its own - binding changes what
   *  publishing would refuse - and it is the cheap call rather than the whole
   *  state. Publish is still refused server-side whatever this holds. */
  const setFields = async (s: ConfigSection, next: string[]) => {
    const before = draft;
    setDraft((d) => d && ({
      ...d,
      sections: d.sections.map((x) =>
        x.template_key === s.template_key && x.key === s.key
          ? { ...x, fields: next } : x),
    }));
    setError("");
    try {
      await api.setSectionFields(s.template_key, s.key, next);
      setValidation(await api.validateDraft());
    } catch (e) {
      setDraft(before);
      setError(message(e));
    }
  };

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

  /** How much each part holds, from the draft, so the band says what is in
   *  there rather than only what it is called (3.1). Sections are the ones
   *  belonging to the memorandum on screen; facts and document types belong
   *  to the whole configuration, as the screen says throughout. */
  const partCount = (key: string) =>
    key === "sections" ? sections.length
      : key === "facts" ? (draft?.fields.length ?? 0)
        : (draft?.document_types.length ?? 0);

  /** Which stage of the home page's sequence the part on screen stands for
   *  (3.2). Stage 1 is not among them. */
  const litStage = (PARTS.find(([key]) => key === part)?.[3] ?? null) as
    Stage | null;

  // The bar and the band are held beneath the site header and the Back strip,
  // and an open section's row beneath both. Every offset is measured rather
  // than assumed: they change with the width of the window.
  const pinTop = usePinTop();

  const bar = useRef<HTMLDivElement | null>(null);
  const [barHeight, setBarHeight] = useState(0);
  const editing = Boolean(state?.draft) && !proposing;
  useLayoutEffect(() => {
    const el = bar.current;
    if (!el) return;
    const measure = () => setBarHeight(el.getBoundingClientRect().height);
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    return () => watch.disconnect();
  }, [editing]);

  // The bar's shadow passes to the open section's row while that row is held
  // beneath it, so the shadow always marks the foot of what stays put.
  const openHead = useRef<HTMLDivElement | null>(null);
  const [stuck, setStuck] = useState(false);
  useEffect(() => {
    if (!openSection) { setStuck(false); return; }
    const check = () => {
      const row = openHead.current;
      setStuck(!!row && Math.abs(
        row.getBoundingClientRect().top - (pinTop + barHeight)) < 1);
    };
    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => {
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, [openSection, part, pinTop, barHeight]);

  // The open section's row, measured, so what it already renders can be held
  // directly beneath it (UX-20).
  const [rowHeight, setRowHeight] = useState(0);
  useLayoutEffect(() => {
    const el = openHead.current;
    if (!el) { setRowHeight(0); return; }
    const measure = () => setRowHeight(el.getBoundingClientRect().height);
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    return () => watch.disconnect();
  }, [openSection, part]);

  if (!state) return <p className="muted">Loading&hellip;</p>;

  // Reading a report of the client's own. Held above every other screen: it
  // is a conversation with its own shape, and nothing it proposes reaches the
  // draft until it is accepted.
  if (proposing) {
    return (
      <ProposeView
        onCancel={leaveProposer}
        onDone={(templateKey) => {
          // Straight into the editor on the new memorandum, with no screen
          // in between (UX-21).
          setProposing(false);
          place({ report: templateKey || null, part: "sections",
                  section: null });
          refresh().catch((e) => setError(message(e)));
        }}
      />
    );
  }

  // --- nothing configured yet: choose a starting point --------------------

  if (!state.draft && state.revisions.length === 0) {
    const base = packs[0];

    // TPL-03. This screen used to list the bases in a dropdown labelled
    // "Memorandum" and fork one whole. A base is not a memorandum: it is the
    // facts, the document types and the routing between them, and it carries
    // no sections at all. So the base is no longer something to choose - it
    // comes with all three routes, silently, because all three need it - and
    // the choice on offer is what is written OVER it.
    //
    // The memoranda themselves are not listed here either. The Get started
    // chooser already lists them with their sections and an "already yours"
    // marker, and a second list would drift from it.

    // No fork here: Get started forks the base itself where the tenant has no
    // published revision, and forking it twice is what fork_base refuses. One
    // path, and it is the chooser's.
    const ours = () => navigate("/welcome", { state: { stopAtDraft: true } });

    const scratch = () => act("Setting up", async () => {
      await api.forkBase();
      await api.openDraft();
    });

    const fromReport = () => act("Setting up", async () => {
      await api.forkBase();
      await api.openDraft();
      setProposing(true);
    });

    return (
      <div>
        <h2>Configure a Report</h2>
        <p className="muted">
          You start with our list of facts and the documents they are found
          in. What you choose here is what is written over them. Everything is
          copied into your own configuration, so later changes we make to it
          will not reach you.
        </p>
        {error && <p className="error">{error}</p>}

        {base && (
          <p className="muted small">
            {base.document_types} document types &middot; {base.fields} facts,
            whichever you choose.
          </p>
        )}

        {packs.length === 0 && (
          <p className="muted">No starting points are available yet.</p>
        )}

        <p>
          <a onClick={busy || !base ? undefined : ours}>
            Select an ARQEDIA Template
          </a>
        </p>
        <p className="muted small">
          One of the memoranda we write, laid out over those facts. Take as
          many as you want, now or later.
        </p>

        <p>
          <a onClick={busy || !base ? undefined : scratch}>
            Draft your own from scratch
          </a>
        </p>
        <p className="muted small">
          An empty memorandum. You write the sections and say what each one
          renders.
        </p>

        <p>
          <a onClick={busy || !base ? undefined : fromReport}>
            Create your own from a report (.pdf, .docx)
          </a>
        </p>
        <p className="muted small">
          Give us a report you already write. We read its shape and put a
          configuration to you to correct &mdash; the file itself is read
          once and deleted.
        </p>

        {busy && <Working what={busy} />}
      </div>
    );
  }

  // --- published, no draft open -------------------------------------------

  if (!state.draft) {
    return (
      <div>
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
        <p className="muted small">
          Every revision that has been published. The one in use is what new
          memoranda are written against; putting an earlier one back is how a
          change is undone. Nothing already filed or generated moves &mdash;
          each names the revision it was read or written under.
        </p>
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
                  {r.revision === state.active_revision ? (
                    <span className="in-use">in use</span>
                  ) : (
                    <a className="small" onClick={() => {
                      if (!window.confirm(
                        `Use revision ${r.revision}? Memoranda generated from `
                        + `now on are written against it, and documents filed `
                        + `from now on are read against it. Nothing already `
                        + `filed or generated changes — each keeps the `
                        + `revision it names, so every memorandum still `
                        + `reproduces. Revision ${state.active_revision} `
                        + `stays, and can be put back the same way.`)) return;
                      act("Selecting", () => api.selectRevision(r.revision));
                    }}>
                      Use this revision
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  /** One fact on a section's list, ticked to bind it. The tick and the name
   *  do different things: wrapping both in one label meant clicking a name to
   *  read what the fact is silently bound it. */
  const bindRow = (s: ConfigSection, f: ConfigField) => {
    const on = s.fields.includes(f.key);
    return (
      <div className="bind" key={f.key}>
        <input type="checkbox" checked={on}
          onChange={() => setFields(s, on
            ? s.fields.filter((x) => x !== f.key)
            : [...s.fields, f.key])} />{" "}
        {/* The whole name on hover: a column holds a fixed width now, so a
            long label is cut rather than pushing its column wider than the
            one beside it. */}
        <a title={f.label} onClick={() => setEditField(f.key)}>{f.label}</a>
        {f.is_group && (
          <span className="muted small"> (table)</span>
        )}
      </div>
    );
  };

  /** The bound facts, column by column.
   *
   *  LEFTMOST WINS, here only. A fact found in documents from two groups
   *  belongs to both, and the lower list says so - that is the truth about it
   *  and it is how a person finds it under either heading. Repeated in the
   *  upper list it reads as two facts bound twice, so above the rule each one
   *  appears in its leftmost column and nowhere to the right of it.
   *
   *  Every group is returned, empty ones included, so the columns above the
   *  rule and the columns below it are the same groups in the same order. */
  const boundColumns = (s: ConfigSection) => {
    const shown = new Set<string>();
    return byGroup.map((g) => {
      const fields = g.fields.filter(
        (f) => s.fields.includes(f.key) && !shown.has(f.key));
      fields.forEach((f) => shown.add(f.key));
      return { key: g.key, label: g.label, fields };
    });
  };

  /** Tick or untick a whole column. Checked when every fact of the group is
   *  bound, part-way when some are; clicking binds all of them, or takes all
   *  of them off. One save, not one per fact. */
  const groupBox = (s: ConfigSection, g: { key: string; fields: ConfigField[] },
                    shownHere: ConfigField[]) => {
    const keys = g.fields.map((f) => f.key);
    const boundHere = keys.filter((k) => s.fields.includes(k));
    const all = keys.length > 0 && boundHere.length === keys.length;
    return (
      <input type="checkbox" className="group-box"
        checked={all}
        ref={(el) => {
          if (el) el.indeterminate = !all && boundHere.length > 0;
        }}
        title={all ? "Take all of these off the section"
                   : "Render all of these in this section"}
        onChange={() => setFields(s, all
          ? s.fields.filter((k) => !keys.includes(k))
          : [...s.fields, ...keys.filter((k) => !s.fields.includes(k))])}
        // Nothing to tick where the group is empty above the rule and below
        // it alike.
        disabled={keys.length === 0 && shownHere.length === 0} />
    );
  };

  // --- editing --------------------------------------------------------------

  return (
    // Asks the page for room: this screen carries lists grouped into a column
    // per document group, and four groups do not fit the width that suits
    // prose. See main:has(.wide-page).
    <div className="wide-page">
      {/* Where the part on screen sits in the whole business: the same four
          stages the home page runs through, still and in miniature, with the
          one this part stands for brought forward (3.2). */}
      <StageStrip />

      {/* The working controls and the band of parts beneath them, held at the
          top together while the page scrolls (UX-02). Measured as ONE block,
          because what an open section's row has to clear is both of them -
          which is what keeps --fields-top honest without a second measure. */}
      <div className={"config-top" + (stuck ? " covered" : "")}
           ref={bar} style={{ top: pinTop }}>
      <div className="config-bar">
        <select aria-label="Memorandum" value={current?.key ?? ""}
                onChange={(e) => {
                  setTemplate(e.target.value);
                  setEditSection(null);
                }}>
          {templates.map((t) => (
            <option key={t.key} value={t.key}>{t.label || t.key}</option>
          ))}
        </select>

        {/* What acts on the memorandum in the dropdown, beside the dropdown.
            These sat in a row of their own under the band, on the sections
            part only, where they read as acting on the sections below them
            rather than on the memorandum named above them. They act on the
            template in every part, so they are here in every part. */}
        <span className="muted small">
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
        {/* A memorandum built from another rather than from nothing. A credit
            pack and a KYC pack share most of their sections, and rebuilding
            the second by hand is where they drift apart. */}
        {current && (
          <a className="small" onClick={() => act("Duplicating", async () => {
            const made = await api.duplicateTemplate(current.key);
            setTemplate(made.key);
          })}>
            Duplicate
          </a>
        )}
        {/* Asked, with the name typed (UX-10). The last memorandum cannot go
            - the API refuses it - so the control says so rather than offering
            a delete that fails. */}
        {current && (templates.length > 1 ? (
          <a className="danger small" onClick={() => {
            const name = current.label || current.key;
            const count = sections.length;
            setTypedName("");
            setDeleting({
              title: `Delete ${name}`,
              reaches: `${count} ${count === 1 ? "section goes" : "sections go"}`
                + " with it, and which facts each renders. The facts"
                + " themselves stay: they belong to you, not to one"
                + " memorandum.",
              action: "Delete this template",
              name,
              run: async () => {
                await api.deleteTemplate(current.key);
                setTemplate("");
              },
            });
          }}>
            Delete this template
          </a>
        ) : (
          <span className="muted small">
            The only memorandum &mdash; it cannot be deleted
          </span>
        ))}

        {/* What Publish covers, beside it (UX-05). The whole configuration,
            not the report on screen. */}
        <span className="live muted small">
          Live: revision {state.active_revision} &middot; Publish applies to
          all memoranda
        </span>
        {/* Asked every time. Nothing here can tell whether the draft differs
            from the live revision, so it cannot say more than this. */}
        <a className="secondary" onClick={() => {
          if (!window.confirm(
            `Discard this draft? Every change made since revision `
            + `${state.active_revision} is lost, in every memorandum. `
            + `Revision ${state.active_revision} stays in use.`)) return;
          act("Discarding", api.discardDraft);
        }}>Discard</a>
        <button
          disabled={!!busy || (validation ? !validation.may_publish : false)}
          onClick={() => setPublishing(true)}>
          Publish
        </button>
      </div>

      {/* The three things this screen is about, at the size that says so
          (3.1). They were three 13px links in the bar, the same weight as
          Discard. The tab pattern is Account management's, widened to carry a
          line about each part and how much of it there is. */}
      {/* The part in use, drawn large in the margin beside the band (18.3).
          It sat in a box inside the band, which made a fourth column out of
          a bearing. It is now in the empty canvas to the left of the
          content column, level with the band and changing with the part -
          and it shows only where that canvas is wide enough to hold it
          without touching either the content or the rail. Positioned
          against .config-top, which is the sticky block, so it travels with
          the band rather than scrolling away from it. */}
      <StageIcon stage={litStage} />

      <nav className="tabs parts-band">
        {PARTS.map(([key, label, note]) => (
          <button key={key} className={part === key ? "on" : undefined}
                  onClick={() => setPart(key)}>
            <b>{label}</b>
            <span className="count">{partCount(key)}</span>
            <i>{note}</i>
          </button>
        ))}
      </nav>
      </div>

      {/* Renaming, under the band rather than inside the sections part: the
          control that opens it is in the bar now, and the bar is on every
          part. Left where it was, pressing Rename anywhere but Report
          sections would have set a name nobody could see or save. */}
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

      <div className="memo-head">
        <div>
          <h2>Configure a Report</h2>
          <p className="muted">
            Editing a draft. Revision {state.active_revision} stays in use
            until you publish.
          </p>
        </div>
      </div>

      {started && (
        <div className="revision-note started">
          <strong>
            {list(started.templates)} {started.templates.length === 1
              ? "is yours" : "are yours"}
            {started.revision !== null
              ? `, published as revision ${started.revision}.` : "."}
          </strong>
          {started.draft_was_open && started.revision !== null && (
            <p>
              It went into the draft you already had open, beside your own
              changes, and publishing shipped both.
            </p>
          )}
          {/* Nothing was published: say where it is and what is left to do,
              rather than leaving somebody to assume it is in use. */}
          {started.revision === null && (
            <p>
              {started.draft_was_open
                ? "It is in the draft you already had open, beside your own changes. "
                : "It is in your draft. "}
              Publishing is a separate step: press Publish when the draft says
              what you want it to say.
            </p>
          )}
          {/* Named, not counted. Somebody who deleted a fact in March and
              finds it back today needs to see which one. */}
          {added(started).length > 0 ? (
            <ul>
              {added(started).map(([what, names]) => (
                <li key={what}>
                  <strong>{names.length} {what}:</strong> {some(names)}
                </li>
              ))}
            </ul>
          ) : (
            <p>Nothing else was added: you already held everything it needs.</p>
          )}
          <a className="secondary" onClick={() => setStarted(null)}>Dismiss</a>
        </div>
      )}

      {error && <p className="error">{error}</p>}
      {busy && <Working what={busy} />}

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
      {/* 1 --- what the report says ---------------------------------------- */}
      {part === "sections" && (<>
      <p className="muted small">
        Each section of the memorandum, in order. A section renders the fields
        bound to it and nothing else.
      </p>

      {/* The memorandum is chosen in the bar, and what acts on it now sits
          beside the dropdown there - including Rename, whose box opens
          directly under the band rather than here. */}

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
          onDelete={editSection ? () => {
            const doomed = sections.find((x) => x.key === editSection);
            setDeleting({
              title: "Delete the section "
                + (doomed ? `${doomed.numeral}. ${doomed.title}` : editSection),
              reaches: `It comes out of ${current?.label || current?.key},`
                + " and which facts it renders goes with it. The facts"
                + " themselves stay.",
              action: "Delete this section",
              run: async () => {
                await api.deleteSection(current?.key ?? "", editSection);
                setEditSection(null);
              },
            });
          } : undefined}
        />
      )}

      {sections.map((s, i) => (
        <div className="review section-row" key={s.key}>
          {/* Open, its heading and Close are held beneath the bar while its
              field list scrolls, so closing is always one click. */}
          <div className={"review-head" + (openSection === s.key
                 ? " pinned" + (stuck ? " stuck" : "") : "")}
               ref={openSection === s.key ? openHead : undefined}
               style={openSection === s.key
                 ? { top: pinTop + barHeight } : undefined}>
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
            </span>
            {/* Pills (UX-06). The count lives on Fields itself. */}
            <a className="pill" onClick={() => {
              // The search and the open group belong to whichever section is
              // open, so both are cleared as it changes.
              setSectionSearch("");
              setOpenFactGroup(null);
              setOpenSection(openSection === s.key ? null : s.key);
            }}>
              {openSection === s.key ? "Close" : `Fields · ${s.fields.length}`}
            </a>
            <a className="pill" onClick={() => {
              // One thing open at a time. Editing a section with
              // another section's field list open left both on screen
              // and it was not obvious which the buttons belonged to.
              setOpenSection(null);
              setEditSection(s.key);
            }}>Edit</a>
          </div>

          {openSection === s.key && (
            // The open section's facts. What it already renders, the rule and
            // the search are held beneath its heading while the facts it
            // could render scroll past (UX-20).
            <div className="binder section-fields" ref={openList}
                 style={{ "--fields-top": `${pinTop + barHeight + rowHeight}px` } as React.CSSProperties}>
              <p className="muted small">
                Which facts this section renders. A section binding a field
                that no longer exists would report it absent whether or not it
                was found, so that is refused here rather than at publish.
              </p>

              <div className="fields-head">
                {/* What this section already renders, at the top and grouped
                    as the list below is, then a rule, then everything it
                    could (UX-08). Unticking one moves it down. */}
                {s.fields.length > 0 && (
                  <>
                    <div className="bound-facts">
                      <div className="binder-groups">
                        {boundColumns(s).map((g) => (
                          <div key={g.key}>
                            {/* Every group, empty ones included, so a column
                                here stands over the same group below the
                                rule. */}
                            <h5>
                              {groupBox(s, byGroup.find((x) => x.key === g.key)
                                ?? { key: g.key, fields: [] }, g.fields)}
                              {" "}{g.label}{" "}
                              <span className="muted">{g.fields.length}</span>
                            </h5>
                            {g.fields.map((f) => bindRow(s, f))}
                          </div>
                        ))}
                      </div>
                    </div>
                    <hr className="bound-rule" />
                  </>
                )}

                <div className="filters">
                  <input placeholder="Search facts" value={sectionSearch}
                         onChange={(e) => setSectionSearch(e.target.value)} />
                  {sectionSearch && (
                    <a className="small"
                       onClick={() => setSectionSearch("")}>Clear</a>
                  )}
                  {/* A fact the vocabulary does not hold yet, from where a
                      person discovers it is missing. It is created in the
                      draft and bound to this section in one act; before this
                      they had to leave for the Facts tab, add it, come back
                      and find the section again. */}
                  <a className="small" onClick={() => {
                    setBindNewTo({ template_key: s.template_key, key: s.key });
                    setEditField("");
                  }}>
                    Add a fact
                  </a>
                </div>
              </div>

              {/* The list scrolls inside itself, as the bound block above it
                  does, so its headings can be held at the top of it while the
                  facts run past (2.5). A sticky child cannot hold against the
                  window from inside a box that scrolls sideways, which this
                  one does - so the box it holds against is this one. */}
              <div className="unbound-facts">
              <div className="binder-groups">
                {byGroup.map((g) => {
                  // Searching narrows what is shown and never what is bound.
                  const needle = sectionSearch.trim().toLowerCase();
                  const fields = g.fields.filter((f) =>
                    !s.fields.includes(f.key)
                    && (!needle || f.label.toLowerCase().includes(needle)));

                  // EVERYTHING OPEN. This is where facts are bound to a
                  // section, and a person doing that needs to see the whole
                  // vocabulary at once. Collapsing it here was a mistake -
                  // the browsing lists collapse, the working list does not.
                  //
                  // An empty column is kept rather than dropped, so the
                  // columns line up with the bound ones above the rule. A
                  // group emptied by the search says so.
                  return (
                  <div key={g.key}>
                    <h5>
                      {g.label}{" "}
                      <span className="muted">{fields.length}</span>
                    </h5>
                    {fields.length === 0 && (
                      <div className="muted small none">
                        {needle ? "none matching" : "all bound"}
                      </div>
                    )}
                    {fields.map((f) => bindRow(s, f))}
                  </div>
                  );
                })}
              </div>
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

      {part === "facts" && (<>
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

            // Collapsible, like the document types below: a browsing list,
            // one group at a time, and a filter opens whatever it matched.
            const open = fieldFilter.trim() !== "" || openFactGroup === g.key;

            return (
              <Fragment key={g.key}>
                <tr className="group-head">
                  <td colSpan={3}>
                    <a onClick={() => setOpenFactGroup(
                      openFactGroup === g.key ? null : g.key)}>
                      {open ? "\u25be" : "\u25b8"} {g.label}
                    </a>
                    <span className="muted small">
                      {" \u00b7 "}{shown.length}
                    </span>
                  </td>
                </tr>
                {open && shown.map((f) => (
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
      {/* 4 --- the documents ------------------------------------------------ */}
      </>)}

      {part === "documents" && (<>
      <p className="muted small">
        Types of documents a client may provide. The description is what the
        system reads to tell one document from another, so it is worth
        writing well.
      </p>

      <div className="filters">
        <input placeholder="Search document types" value={typeSearch}
               onChange={(e) => setTypeSearch(e.target.value)} />
        {typeSearch && (
          <a className="small" onClick={() => setTypeSearch("")}>Clear</a>
        )}
      </div>

      {editType !== null && draft && (
        <TypeForm
          initial={draft.document_types.find((x) => x.key === editType)}
          categories={draft.categories}
          onCancel={() => setEditType(null)}
          onSave={(body) => act("Saving", async () => {
            await api.saveDocumentType(body);
            setEditType(null);
          })}
          onDelete={editType ? () => {
            const doomed = draft.document_types.find((x) => x.key === editType);
            setDeleting({
              title: `Delete the document type ${doomed?.label ?? editType}`,
              reaches: "Facts looked for in it are no longer looked for"
                + " there.",
              action: "Delete this document type",
              run: async () => {
                await api.deleteDocumentType(editType);
                setEditType(null);
              },
            });
          } : undefined}
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
          {documentGroups.map((group) => {
            const needle = typeSearch.trim().toLowerCase();
            const types = needle
              ? group.types.filter((t) =>
                  t.label.toLowerCase().includes(needle)
                  || (t.description ?? "").toLowerCase().includes(needle))
              : group.types;
            if (types.length === 0) return null;

            // A search opens whatever it matched; otherwise one group at a
            // time, and a shut one says how much is inside it.
            const open = needle !== "" || openDocGroup === group.key;

            return (
            <Fragment key={group.key}>
              <tr className="group-head">
                <td colSpan={4}>
                  <a onClick={() => setOpenDocGroup(
                    openDocGroup === group.key ? null : group.key)}>
                    {open ? "\u25be" : "\u25b8"} {group.label}
                  </a>
                  <span className="muted small">
                    {" \u00b7 "}{types.length}
                  </span>
                </td>
              </tr>
              {open && types.map((t) => (
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
                      // The search belongs to whichever document is open, so
                      // it is cleared as that changes.
                      setTypeFieldSearch("");
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
            );
          })}
        </tbody>
      </table>

      <a className="small add" onClick={() => setEditType("")}>
        Add a document
      </a>


      {openType && draft && (
        <div className="panel-backdrop" onClick={() => setOpenType(null)}>
          <aside className="panel" onClick={(e) => e.stopPropagation()}>
            {/* The name, the note, the search and Save are held at the top
                of the drawer while the facts scroll under them (2.6). The
                drawer is the scrolling box, so a sticky child holds against
                it - flush with its top edge since 18.2, which is why Close
                is inside the head rather than above it: the head now covers
                the band Close used to sit in. */}
            <div className="panel-head">
              <a onClick={() => setOpenType(null)} className="panel-close">
                Close
              </a>
              <h3>
                {draft.document_types.find((t) => t.key === openType)?.label}
              </h3>
              <p className="muted small">
                What is looked for in this document. The same relationship as
                &ldquo;where is this field found&rdquo;, read from the other
                end &mdash; changing it here changes it there.
              </p>
              <div className="filters">
                <input placeholder="Search facts" value={typeFieldSearch}
                       onChange={(e) => setTypeFieldSearch(e.target.value)} />
                {typeFieldSearch && (
                  <a className="small"
                     onClick={() => setTypeFieldSearch("")}>Clear</a>
                )}
                <span className="muted small">
                  {typeFields.length} ticked
                </span>
              </div>
              {/* SAVE IN THE PINNED HEAD (18.2). It sat under the list, and
                  the list is every fact this tenant has grouped into columns
                  - so committing a tick made half a minute of scrolling back
                  to a button that had left the screen. The head is already
                  held against the drawer while the facts pass under it. */}
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
            </div>

            <div className="binder-groups">
              {byGroup.map((g) => (
                <div key={g.key}>
                  <h5>{g.label}</h5>
                  {g.fields
                    .filter((f) => {
                      // Searching narrows what is shown and never what is
                      // ticked - a fact already looked for stays looked for
                      // whether or not it matches what was typed.
                      const needle = typeFieldSearch.trim().toLowerCase();
                      return !needle || f.label.toLowerCase().includes(needle);
                    })
                    .map((f) => {
                    const on = typeFields.includes(f.key);
                    return (
                      <div className="bind" key={f.key}>
                        {/* The tick and the name do different things, as on a
                            section's list. The fact opens over this drawer;
                            closing it comes back here. */}
                        <input type="checkbox" checked={on}
                          onChange={() => setTypeFields(on
                            ? typeFields.filter((x) => x !== f.key)
                            : [...typeFields, f.key])} />{" "}
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

          </aside>
        </div>
      )}

      {/* 4b --- how documents group, on the documents tab ------------------- */}
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
          onDelete={editCategory ? () => {
            const doomed = draft?.categories.find((x) => x.key === editCategory);
            setDeleting({
              title: `Delete the group ${doomed?.label ?? editCategory}`,
              reaches: "Its document types stay, without a group.",
              action: "Delete this group",
              run: async () => {
                await api.deleteCategory(editCategory);
                setEditCategory(null);
              },
            });
          } : undefined}
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

      </>)}

      {/* 5 --- publish ------------------------------------------------------ */}
      {/* Asked from the bar, so it is reachable from anywhere on the page, and
          confirmed here with the note and what is worth knowing. */}
      {publishing && (
        <div className="panel-backdrop" onClick={() => setPublishing(false)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}
               onKeyDown={(e) => { if (e.key === "Escape") setPublishing(false); }}>
            <a className="panel-close" onClick={() => setPublishing(false)}>
              Close
            </a>
            <h3>Publish</h3>
            {error && <p className="error">{error}</p>}
            {busy && <Working what={busy} />}

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
              Revision {state.active_revision} is live. Publishing makes this
              draft the configuration new work is filed against, and applies
              every change in it across all memoranda at once &mdash; not just
              the report on screen. Everything already filed keeps resolving
              against the revision it was filed under, so memos already written
              still reproduce.
            </p>

            <div className="inline">
              <input placeholder="What changed?" value={note} autoFocus
                     onChange={(e) => setNote(e.target.value)} />
              <button
                disabled={!!busy || (validation ? !validation.may_publish : false)}
                onClick={() => act("Publishing", async () => {
                  await api.publish(note);
                  setNote("");
                  setPublishing(false);
                })}>
                {busy ? busy + "\u2026" : "Publish"}
              </button>
            </div>

            <div className="form-actions">
              <a className="secondary" onClick={() => setPublishing(false)}>
                Cancel
              </a>
            </div>
          </div>
        </div>
      )}

      {/* LAST, so it sits above every other drawer. A fact opened from a
          document's list must be on top of that list, and stacking follows
          document order where nothing sets a z-index. */}
      {editField !== null && (
        <div className="panel-backdrop" onClick={() => setEditField(null)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}>
            <a className="panel-close"
               onClick={() => setEditField(null)}>Close</a>
            {/* The card closes as the documents open. Both are drawers, and
                the field card is rendered last so it stacks above everything
                - leaving it open put the documents behind it and the click
                looked like it had done nothing. */}
            <FieldForm
              error={error}
              onShowDocuments={() => {
                if (!editField) return;
                setOpenField(editField);
                setEditField(null);
              }}
              initial={draft?.fields.find((x) => x.key === editField)}
              onCancel={() => { setBindNewTo(null); setEditField(null); }}
              onSave={(body) => act("Saving", async () => {
                // THE KEY COMES BACK FROM THE SERVER, because a new fact no
                // longer sends one (17.1) and the binding below needs the key
                // the server minted. Reading it off the body would bind
                // nothing, silently.
                const saved = await api.saveField(body as never) as
                  { key?: string } | undefined;
                // Added from a section's list: bind it there too, so the act
                // a person started - "this section needs a fact we do not
                // hold" - finishes where it began (2.1). A fact added from
                // the Facts tab binds to nothing, as before.
                const target = bindNewTo;
                const added = saved?.key ?? (body as { key?: string }).key;
                if (target && added) {
                  const s = (draft?.sections ?? []).find(
                    (x) => x.template_key === target.template_key
                      && x.key === target.key);
                  if (s && !s.fields.includes(added)) {
                    await api.setSectionFields(
                      target.template_key, target.key, [...s.fields, added]);
                  }
                }
                setBindNewTo(null);
                setEditField(null);
              })}
              onDelete={editField ? () => {
                setDeleting({
                  title: `Delete the fact ${fieldsByKey[editField] ?? editField}`,
                  reaches: "It is taken out of every section that renders"
                    + " it, in every memorandum.",
                  action: "Delete this fact",
                  run: async () => {
                    await api.deleteField(editField);
                    setEditField(null);
                  },
                });
              } : undefined}
            />
          </div>
        </div>
      )}

      {/* LAST, therefore above the field card. Drawer stacking here follows
          document order, so the drill-in has to render after the thing it is
          opened from. It also lived inside "Facts included in sections",
          which is collapsed on arrival - so opened from a section's field
          list it rendered nothing at all. */}
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

      {/* A deletion, asked in a drawer (UX-10). LAST, so it stacks above the
          drawer the delete was chosen from. The name is typed only for a
          whole memorandum. */}
      {deleting && (
        <div className="panel-backdrop" onClick={() => setDeleting(null)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}
               onKeyDown={(e) => { if (e.key === "Escape") setDeleting(null); }}>
            <a className="panel-close" onClick={() => setDeleting(null)}>
              Close
            </a>
            <div className="form">
              <h4>{deleting.title}</h4>
              {error && <p className="error">{error}</p>}
              <p className="muted small">
                {deleting.reaches} {DRAFT_ONLY}
              </p>
              {deleting.name !== undefined && (
                <label className="row">
                  <span>Type {deleting.name} to confirm</span>
                  <input value={typedName} autoFocus
                         onChange={(e) => setTypedName(e.target.value)} />
                </label>
              )}
              <div className="form-actions">
                <button autoFocus={deleting.name === undefined}
                  disabled={!!busy || (deleting.name !== undefined
                    && typedName.trim() !== deleting.name)}
                  onClick={() => act("Deleting", async () => {
                    await deleting.run();
                    setDeleting(null);
                  })}>
                  {deleting.action}
                </button>
                <a className="secondary" onClick={() => setDeleting(null)}>
                  Cancel
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
