import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type Draft,
  type Proposal,
  type ProposedFact,
  type ConfigColumn,
} from "./api";

/**
 * Create your own memorandum from a report you already write.
 *
 * The client gives us a copy of his own report. We read its shape - its
 * sections, the facts each one reports, the documents those facts come from -
 * and put a configuration to him. He corrects it and accepts. Nothing reaches
 * his draft until he does.
 *
 * THE FILE IS FORM, NOT SUBSTANCE. It is read once for its layout and deleted.
 * It is never filed, classified, extracted from, cited or charged for.
 *
 * TWO STEPS ON PURPOSE. A field's description is what extraction reads, and a
 * document type's description is what the classifier reads. Neither can be
 * corrected afterwards for documents already filed - the only remedy is filing
 * them again and paying again. So every new one has to be acknowledged before
 * it can be accepted. The friction is the point.
 *
 * WE SUGGEST A MATCH, HE DECIDES. Where a fact looks like a field he already
 * holds, both are shown and he picks. Deciding for him binds a section to a
 * field that means something else, which renders a number that is wrong and
 * looks right.
 */


/** Mirrors slugKey in Configure and _slug in the editor. A key is permanent
 *  identity; it is derived from the label once and never follows it. */
function slugKey(label: string, prefix = ""): string {
  const body = label.toLowerCase().replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return (prefix + (body || "item")).slice(0, 64);
}

function fieldKey(label: string): string {
  return slugKey(label, "f_").replace(/-/g, "_");
}

/** What the person has decided about one fact. */
type FactChoice = {
  use: "existing" | "new" | "skip";
  label: string;
  description: string;
  shape: string;
  existing: string | null;
  why: string | null;
  columns: string[];
  // Document type LABELS, as the reader names them. Resolved to keys only
  // when the proposal is accepted, because a type may not exist yet.
  documents: string[];
  // For a matched fact, the document type KEYS the tenant already looks in.
  // Kept so accepting can add to that set without ever taking from it.
  held: string[];
  // Which of the report's sections name this fact. Empty for one the person
  // added themselves, until they say where it belongs.
  sections: number[];
  // Added from a document card rather than found in the report. It has no
  // section of its own until one is chosen, so it cannot be placed by the
  // ordinary rule.
  added: boolean;
  // Deliberately reported by no section here. The fact is still created and
  // still extracted - it belongs to the tenant, and another memorandum may
  // report it. This only records that the person has seen it and decided.
  unused: boolean;
  acknowledged: boolean;
};

type TypeChoice = {
  use: "existing" | "new" | "skip";
  label: string;
  description: string;
  // The KEY of the group this document sits in. The reader answers with a
  // label, and a label is not a key: creating the group under a slug while
  // pointing the document at the label left the group empty and the document
  // ungrouped. Both are resolved once, here, and never again.
  group: string;
  // Set only where the group does not exist yet, and then it is what the
  // group will be called.
  groupLabel: string;
  existing: string | null;
  acknowledged: boolean;
};

export function ProposeView({ onDone, onCancel }: {
  onDone: (templateKey: string) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const [memoLabel, setMemoLabel] = useState("");
  // Document cards carry a form each. One open at a time, or the page is
  // metres long before the person has read the first one.
  const [openDoc, setOpenDoc] = useState<string | null>(null);
  // The four parts of the page. All open to begin with - a person who has
  // just had a report read wants to see what came back, not four headings.
  const [shut, setShut] = useState<Set<string>>(new Set());
  const part = (key: string, label: string, count: string, wants: number) => (
    <h3>
      <a onClick={() => {
        const next = new Set(shut);
        if (next.has(key)) next.delete(key); else next.add(key);
        setShut(next);
      }}>
        {shut.has(key) ? "\u25b8" : "\u25be"} {label}
      </a>{" "}
      <span className="muted small">{count}</span>
      {shut.has(key) && wants > 0 && (
        <span className="warn small">{" \u00b7 "}{wants} needing you</span>
      )}
    </h3>
  );
  // Accepting is a sequence of writes, not one. Whatever it managed before
  // it stopped is IN the draft, so the person is told what landed rather than
  // left to find out by reading their configuration.
  // Naming a document from a fact card, where the person has found that none
  // of the documents on offer is where this fact actually lives.
  const [addingDoc, setAddingDoc] = useState<string | null>(null);
  const [newDocName, setNewDocName] = useState("");
  // And the reverse: naming a fact from a document card.
  const [addingFact, setAddingFact] = useState<string | null>(null);
  // Groups the person makes here, and held documents they move between
  // groups. Grouping is presentation and nothing else reads it, so moving one
  // disturbs no extraction and no memorandum.
  const [newGroups, setNewGroups] = useState<{ key: string; label: string }[]>(
    []);
  const [heldGroup, setHeldGroup] = useState<Record<string, string>>({});
  const [newGroupName, setNewGroupName] = useState("");
  // Sections the report never had, and facts named onto a section.
  const [newSectionTitle, setNewSectionTitle] = useState("");
  const [newSectionNumeral, setNewSectionNumeral] = useState("");
  const [addingSection, setAddingSection] = useState<number | null>(null);
  const [newInSection, setNewInSection] = useState("");
  // Which section's facts are on show. One at a time, on purpose.
  const [shownSection, setShownSection] = useState<number | null>(null);
  // Which fact is open over the page.
  const [openFact, setOpenFact] = useState<string | null>(null);
  // Amending a field the tenant already holds - its wording, or the columns
  // of a table. Held here and written at Accept with everything else, so the
  // screen keeps its promise that nothing is saved until then.
  const [editField, setEditField] = useState<string | null>(null);
  const [heldEdits, setHeldEdits] = useState<Record<string, {
    label: string; description: string | null; cardinality: string;
    columns: ConfigColumn[];
  }>>({});
  const [newFactName, setNewFactName] = useState("");
  const [written, setWritten] = useState<string[]>([]);
  const [result, setResult] = useState<
    { ok: boolean; error?: string; templateKey?: string } | null>(null);
  const [skipped, setSkipped] = useState<Set<number>>(new Set());
  const [facts, setFacts] = useState<Record<string, FactChoice>>({});
  const [types, setTypes] = useState<Record<string, TypeChoice>>({});

  const polling = useRef<number | null>(null);
  // A reader that dies mid-read would otherwise leave "section 4 of 13" on
  // screen for ever, which reads as working.
  const polls = useRef(0);
  const stalled = useRef(0);
  const seen = useRef(-1);

  function message(err: unknown) {
    let text = String((err as Error)?.message ?? err);
    try { text = JSON.parse(text).error ?? text; } catch { /* as it came */ }
    return text;
  }

  useEffect(() => {
    api.draft().then(setDraft).catch((e) => setError(message(e)));
    return () => {
      if (polling.current) window.clearInterval(polling.current);
    };
  }, []);

  // --- reading ------------------------------------------------------------

  async function send(file: File) {
    setError("");
    setBusy("Uploading");
    try {
      const { key } = await api.proposeFromFile(file);
      setBusy("Reading");
      setProposal({
        status: "starting", key, sections_done: 0, sections_total: null,
        memorandum_label: null, document_types: [], sections: [],
      });

      polls.current = 0;
      stalled.current = 0;
      seen.current = -1;

      const stop = () => {
        if (polling.current) window.clearInterval(polling.current);
        polling.current = null;
        setBusy("");
      };

      polling.current = window.setInterval(async () => {
        try {
          const p = await api.proposal(key);
          setProposal(p);

          if (p.status === "ready" || p.status === "unreadable"
              || p.status === "nothing-found" || p.status === "failed"
              || p.status === "model-unavailable") {
            stop();
            if (p.status === "ready") prepare(p);
            return;
          }

          // Progress is a section arriving. Nothing else counts, because the
          // object is rewritten whether or not anything moved.
          polls.current += 1;
          if (p.sections_done === seen.current) stalled.current += 1;
          else { seen.current = p.sections_done; stalled.current = 0; }

          // Three minutes without a section, or sixteen altogether - the
          // reader itself is stopped at fifteen, so past that there is
          // nothing left to wait for.
          if (stalled.current >= 45 || polls.current >= 240) {
            stop();
            setError("Reading stopped before it finished. Nothing was"
                     + " saved.");
          }
        } catch (e) {
          setError(message(e));
        }
      }, 4000);
    } catch (e) {
      setError(message(e));
      setBusy("");
    }
  }

  /**
   * Turn what the reader found into what the person will decide on.
   *
   * Facts are collapsed by name across sections. A memorandum naming Total
   * Assets in three sections is naming one fact three times, and creating
   * three fields would leave two of them empty for ever.
   */
  function prepare(p: Proposal) {
    setMemoLabel(p.memorandum_label || "My memorandum");

    const known = new Set((draft?.fields ?? []).map((f) => f.key));
    const collected: Record<string, FactChoice> = {};

    const labelOfKey: Record<string, string> = {};
    for (const t of draft?.document_types ?? []) labelOfKey[t.key] = t.label;

    p.sections.forEach((section, index) => {
      (section.facts ?? []).forEach((f: ProposedFact) => {
        const id = (f.label || "").trim().toLowerCase();
        if (!id) return;

        const existing = f.matches_existing && known.has(f.matches_existing)
          ? f.matches_existing : null;

        if (collected[id]) {
          collected[id].sections.push(index);
          return;
        }

        const foundIn = f.found_in ?? [];
        // A matched fact inherits where the tenant already looks for it, so
        // it is grouped where they would expect to find it rather than where
        // this one report happened to mention it.
        const inherited = existing
          ? (draft?.fields ?? []).find((x) => x.key === existing)?.found_in
          : null;

        collected[id] = {
          // A suggested match is taken as the starting position because it is
          // the cheaper mistake: declining it costs a click, while missing it
          // costs a duplicate field nobody notices is empty.
          use: existing ? "existing" : "new",
          label: f.label,
          description: f.description || "",
          shape: f.shape === "table" ? "group" : "one",
          existing,
          why: f.why_match ?? null,
          columns: f.columns ?? [],
          // A matched fact shows where the tenant ALREADY looks, not where
          // this report guessed. Otherwise every match would arrive with our
          // guesses tacked onto routing they settled long ago.
          documents: existing
            ? (inherited ?? []).map((k) => labelOfKey[k]).filter(Boolean)
            : foundIn,
          held: existing ? (inherited ?? []) : [],
          sections: [index],
          added: false,
          unused: false,
          acknowledged: false,
        };
      });
    });
    setFacts(collected);

    const knownTypes = new Set((draft?.document_types ?? []).map((t) => t.key));
    const gathered: Record<string, TypeChoice> = {};
    for (const t of p.document_types ?? []) {
      const id = (t.label || "").trim().toLowerCase();
      if (!id || gathered[id]) continue;
      const existing = t.existing_key && knownTypes.has(t.existing_key)
        ? t.existing_key : null;
      // The reader answers with a group by name. Match it to one the tenant
      // already holds, by key or by label; only where neither matches is a
      // new group proposed.
      const named = (t.group || "").trim();
      const match = (draft?.categories ?? []).find(
        (c) => c.key === named
          || c.label.toLowerCase() === named.toLowerCase());
      const fallback = draft?.categories[0];

      gathered[id] = {
        use: existing ? "existing" : "new",
        label: t.label,
        description: t.description || "",
        group: match ? match.key
          : (named ? slugKey(named) : (fallback?.key ?? "")),
        groupLabel: match || !named ? "" : named,
        existing,
        acknowledged: false,
      };
    }
    setTypes(gathered);
  }

  // --- accepting ----------------------------------------------------------

  /** Every document type the person will hold once this is accepted, by the
   *  label the reader used for it. found_in names labels, not keys. */
  const typeKeyByLabel = useMemo(() => {
    const map: Record<string, string> = {};
    for (const t of draft?.document_types ?? []) {
      map[t.label.trim().toLowerCase()] = t.key;
    }
    for (const t of Object.values(types)) {
      if (t.use === "skip") continue;
      map[t.label.trim().toLowerCase()] =
        t.use === "existing" && t.existing ? t.existing : slugKey(t.label);
    }
    return map;
  }, [draft, types]);

  /** A fact still wanted: not set aside, and named by a section still kept.
   *  A fact named only in sections he unticked would otherwise be created and
   *  bound to nothing - clutter he did not ask for, and one more thing to
   *  acknowledge before he can get on. */
  // Created and extracted unless it is not wanted at all. Being reported by
  // no section is a legitimate state - one vocabulary, several memoranda -
  // and is shown rather than allowed to drop the fact silently.
  const live = (f: FactChoice) => f.use !== "skip";

  /** One key per section, unique within the memorandum. Two sections titled
   *  the same slug to the same key, and the second would silently overwrite
   *  the first. Derived from the proposal alone so a key never moves when he
   *  unticks something. */
  const sectionKeys = useMemo(() => {
    const taken = new Set<string>();
    return (proposal?.sections ?? []).map((s) => {
      const base = slugKey(s.title);
      let key = base;
      let n = 2;
      while (taken.has(key)) key = `${base}-${n++}`.slice(0, 64);
      taken.add(key);
      return key;
    });
  }, [proposal]);

  // A fact the person has set aside is not waiting on them. It is still
  // created and still extracted; they have said this memorandum does not
  // report it, and certifying wording for a fact just set aside is the same
  // trap in a different place.
  const wanting = (f: FactChoice) =>
    f.use === "new" && live(f) && !f.unused && !f.acknowledged;

  const outstanding = useMemo(() => {
    const n = Object.values(facts).filter(wanting).length
      + Object.values(types)
        .filter((t) => t.use === "new" && !t.acknowledged).length;
    return n;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facts, types, skipped]);

  /**
   * Write the accepted proposal into the draft, through the same calls a
   * person authoring by hand would make.
   *
   * The order is not a preference. Binding a section to a field that does not
   * exist yet is refused - deliberately, because a section bound to a missing
   * field reports facts as absent when they were extracted. So: groups,
   * documents, fields, where each is found, the memorandum, its sections, and
   * only then what each section renders.
   */
  async function accept() {
    if (!proposal) return;
    setError("");

    const done: string[] = [];
    let made_key = "";
    setWritten(done);

    try {
      const groups = new Set((draft?.categories ?? []).map((c) => c.key));

      for (const g of newGroups) {
        if (groups.has(g.key)) continue;
        setBusy("Adding a group");
        await api.saveCategory({ key: g.key, label: g.label });
        groups.add(g.key);
        done.push("group " + g.label);
      }

      for (const t of Object.values(types)) {
        if (t.use !== "new" || !t.groupLabel || groups.has(t.group)) continue;
        setBusy("Adding a group");
        await api.saveCategory({ key: t.group, label: t.groupLabel });
        done.push("group " + t.groupLabel);
        groups.add(t.group);
      }

      for (const t of Object.values(types)) {
        if (t.use !== "new") continue;
        setBusy("Adding " + t.label);
        await api.saveDocumentType({
          key: slugKey(t.label),
          label: t.label,
          description: t.description,
          category: t.group,
          read_mode: "text",
          always_ocr: false,
        });
        done.push("document " + t.label);
      }

      // Fields the person amended while deciding a match. Sent whole, with
      // every existing column's key intact, because save_field rewrites a
      // table's columns rather than merging them - a column sent without its
      // key would be created afresh and everything extracted under the old
      // one would stop resolving.
      for (const [key, edit] of Object.entries(heldEdits)) {
        const base = fieldsByKey[key];
        if (!base) continue;
        setBusy("Amending " + base.label);
        await api.saveField({
          key,
          label: edit.label,
          type: base.type,
          cardinality: edit.cardinality,
          description: edit.description,
          columns: edit.cardinality === "group"
            ? edit.columns.filter((c) => c.label.trim()).map((c) => ({
                key: c.key || undefined,
                label: c.label.trim(),
                type: c.type || "text",
                description: c.description ?? "",
              }))
            : [],
        } as never);
        done.push("amended " + edit.label);
      }

      // A held document moved to another group. Its name, description and
      // reading are sent back exactly as they were - the group is the only
      // thing this screen may change about a document already held.
      for (const t of (draft?.document_types ?? [])) {
        const moved = heldGroup[t.key];
        if (!moved || moved === t.category) continue;
        setBusy("Moving " + t.label);
        await api.saveDocumentType({
          key: t.key,
          label: t.label,
          description: t.description,
          category: moved,
          read_mode: t.read_mode,
          always_ocr: t.always_ocr,
        });
        done.push("moved " + t.label);
      }

      for (const f of Object.values(facts)) {
        if (f.use !== "new" || !live(f)) continue;
        setBusy("Adding " + f.label);
        await api.saveField({
          key: fieldKey(f.label),
          label: f.label,
          type: "text",
          cardinality: f.shape,
          description: f.description,
          columns: f.shape === "group"
            ? f.columns.filter((c) => c.trim()).map((c) => ({
                key: slugKey(c), label: c.trim(), type: "text",
                description: "",
              }))
            : [],
        } as never);
        done.push("fact " + f.label);
      }

      for (const f of Object.values(facts)) {
        if (!live(f)) continue;
        const documents = f.documents
          .map((label) => typeKeyByLabel[label.trim().toLowerCase()])
          .filter((k): k is string => Boolean(k));

        if (f.use === "new") {
          if (documents.length === 0) continue;
          setBusy("Where to find " + f.label);
          await api.setFieldDocuments(fieldKey(f.label), documents);
          continue;
        }

        // A fact the tenant already holds. Only ever ADD a document to where
        // it is looked for: they settled that routing, and a screen about a
        // new report is not the place to quietly undo it. Unticking here
        // therefore does nothing, and the note beside it says so.
        if (!f.existing) continue;
        const added = documents.filter((k) => !f.held.includes(k));
        if (added.length === 0) continue;
        setBusy("Where to find " + f.label);
        await api.setFieldDocuments(f.existing, [...f.held, ...added]);
      }

      setBusy("Adding the memorandum");
      const made = await api.saveTemplate({ label: memoLabel.trim() });
      done.push("memorandum " + memoLabel.trim());
      const templateKey = made.key as string;
      // Held so the result screen can hand it back, whatever happens after.
      made_key = templateKey;

      const included = proposal.sections
        .map((s, i) => ({ s, i }))
        .filter(({ i }) => !skipped.has(i));

      for (const { s, i } of included) {
        setBusy("Adding " + s.title);
        await api.saveSection({
          key: sectionKeys[i],
          numeral: s.numeral || "",
          title: s.title,
          kind: "extract",
          template_key: templateKey,
        });
        done.push("section " + s.title);
      }

      for (const { s, i } of included) {
        // Deduplicated, because two facts can land on one field: two of the
        // report's names matched to the same field the tenant holds, or two
        // labels that slug to the same key. A section binding the same field
        // twice is a duplicate primary key and the whole accept stops on its
        // last step, after everything else has been written.
        const keys = Array.from(new Set(Object.values(facts)
          .filter((f) => live(f) && f.sections.includes(i))
          .map((f) => f.use === "existing" && f.existing
            ? f.existing : fieldKey(f.label))));
        if (keys.length === 0) continue;
        setBusy("Binding " + s.title);
        await api.setSectionFields(templateKey, sectionKeys[i], keys);
      }

      setBusy("");
      setWritten(done);
      setResult({ ok: true, templateKey: made_key });
    } catch (e) {
      setBusy("");
      setWritten(done);
      setResult({ ok: false, error: message(e), templateKey: made_key });
    }
  }

  // --- the screen ---------------------------------------------------------

  const fieldsByKey = useMemo(() => {
    const map: Record<string, {
      label: string; description: string | null; found_in: string[];
      type: string; cardinality: string; columns: ConfigColumn[];
    }> = {};
    for (const f of draft?.fields ?? []) {
      map[f.key] = { label: f.label, description: f.description,
                     found_in: f.found_in ?? [],
                     type: f.type, cardinality: f.cardinality,
                     columns: f.columns ?? [] };
    }
    return map;
  }, [draft]);

  /** A held field as it stands, amendments included. The fact card reads
   *  this rather than the draft, so a description edited here is the one the
   *  person then decides the match on. */
  const heldField = (key: string) => {
    const base = fieldsByKey[key];
    if (!base) return null;
    const edit = heldEdits[key];
    return edit ? { ...base, ...edit } : base;
  };


  if (!proposal) {
    return (
      <div>
        <a onClick={onCancel} className="back">Back</a>
        <h2>Create your own from a report</h2>
        <p className="muted">
          Give us a report you already write. We read its shape &mdash; its
          sections, and the facts each one reports &mdash; and put a
          configuration to you to correct. Nothing is saved until you accept
          it.
        </p>
        <p className="muted small">
          The file is read for its layout and then deleted. Nothing in it is
          filed, extracted from, or charged for. A short report is read in
          under a minute; a long one takes a few.
        </p>
        {error && <p className="error">{error}</p>}

        {/* Held until the draft has loaded. Without it we do not know what
            fields the tenant holds, and every fact would be offered as new
            with no match suggested - silently, and wrongly. */}
        <label className="row">
          <span>Your report</span>
          <input type="file" accept=".pdf,.docx" disabled={!!busy || !draft}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) send(file);
            }} />
        </label>
        <p className="muted small">
          {draft ? "PDF or Word." : "Loading your configuration\u2026"}
        </p>
        {busy && <p className="busy">{busy}&hellip;</p>}
      </div>
    );
  }

  /**
   * What is read from one document.
   *
   * The same relationship as "where to look for it" on a fact card, from the
   * other end - one list of facts underneath, so ticking here and ticking
   * there are the same act and the two cannot disagree.
   *
   * Written once and used for both kinds of document, the ones the tenant
   * holds and the ones this report would add. Two copies of a form this
   * particular would drift within a week.
   */
  const readFrom = (label: string, cardId: string) => (
    <>
                {/* The same relationship as "where to look for it", from
                    the other end. One list of facts underneath, so ticking
                    here and ticking there are the same act - a document
                    that reads nothing is a document filed for no reason. */}
                <div className="columns">
                  <h4>What to read from it</h4>
                  <p className="muted small">
                    The facts you already hold. Ticking one adds this
                    document to where it is looked for; unticking leaves
                    what you had alone. Anything this document holds that
                    you do not have a fact for yet, name it below.
                  </p>
                  <p className="muted small">
                    Documents and facts belong to you, not to one memorandum.
                    What is read from this document is read for every
                    memorandum, not only this one.
                  </p>

                  <div className="binder">
                    {/* Facts the tenant already holds, and nothing else.
                        Offering every fact the report proposed made a list
                        of a hundred boxes on each document, most of them
                        repeats of what the fact cards above already ask.
                        Anything genuinely missing is named below. */}
                    {factList
                      .filter(([, f]) => live(f) && f.use === "existing")
                      .sort((a, b) => a[1].label.localeCompare(b[1].label))
                      .map(([fid, f]) => (
                        <label className="bind" key={fid}>
                          <input type="checkbox"
                            checked={f.documents.some(
                              (x) => x.trim().toLowerCase()
                                === label.trim().toLowerCase())}
                            onChange={(e) => {
                              const kept = f.documents.filter(
                                (x) => x.trim().toLowerCase()
                                  !== label.trim().toLowerCase());
                              setFacts({
                                ...facts,
                                [fid]: { ...f,
                                  documents: e.target.checked
                                    ? [...kept, label] : kept,
                                  acknowledged: f.use === "new"
                                    ? false : f.acknowledged } });
                            }} />
                          {f.label}
                        </label>
                      ))}
                  </div>

                  {factList.filter(([, f]) => live(f)
                    && f.documents.some((x) => x.trim().toLowerCase()
                      === label.trim().toLowerCase())).length === 0 && (
                    <p className="warn small">
                      Nothing is read from this document, so filing one
                      would extract nothing. Tick a fact above, or name a
                      new one below.
                    </p>
                  )}

                  {/* The other direction. A document may hold a fact the
                      report never mentioned, and naming it here beats
                      remembering to add it afterwards. */}
                  {addingFact !== cardId ? (
                    <a className="small"
                       onClick={() => {
                         setAddingFact(cardId); setNewFactName("");
                       }}>
                      None of these? Add a fact
                    </a>
                  ) : (
                    <div className="filters">
                      <input placeholder="What the fact is called"
                             value={newFactName} autoFocus
                             onChange={(e) =>
                               setNewFactName(e.target.value)} />
                      <button disabled={!newFactName.trim()}
                        onClick={() => {
                          const label = newFactName.trim();
                          const fid = label.toLowerCase();
                          const already = facts[fid];

                          // Known already. Tick this document onto it
                          // rather than make a second fact meaning the
                          // same thing.
                          if (already) {
                            const kept = already.documents.filter(
                              (x) => x.trim().toLowerCase()
                                !== label.trim().toLowerCase());
                            setFacts({
                              ...facts,
                              [fid]: { ...already,
                                documents: [...kept, label],
                                acknowledged: false } });
                          } else {
                            setFacts({
                              ...facts,
                              [fid]: {
                                use: "new", label, description: "",
                                shape: "one", existing: null, why: null,
                                columns: [], documents: [label],
                                held: [], sections: [],
                                added: true, unused: false,
                                acknowledged: false,
                              } });
                          }
                          // Straight to its card. Left at the foot of the
                          // page it is one more thing to find later, and it
                          // has no description yet.
                          setOpenFact(fid);
                          setAddingFact(null);
                          setNewFactName("");
                        }}>
                        Add
                      </button>
                      <a className="small"
                         onClick={() => setAddingFact(null)}>Cancel</a>
                      <span className="muted small">
                        It appears among the facts above, where it needs a
                        description and a section before you can accept.
                      </span>
                    </div>
                  )}
                </div>
    </>
  );

  /**
   * One fact, opened over the page from wherever it is named.
   *
   * The same card whether it was found in the report, picked from a
   * section, or created from a document - a fact is a fact, and a
   * second form for the same thing is a second set of rules.
   */
  const factCard = (id: string, f: FactChoice) => {
        const match = f.existing ? heldField(f.existing) : null;
        return (
          <div className="review" key={id}>
            <div className="review-head">
              <label><strong>{f.label}</strong></label>
              <span className="muted small">
                {f.shape === "group" ? "a table" : "a single fact"}
                {f.sections.length > 1
                  ? ` \u00b7 named in ${f.sections.length} sections` : ""}
              </span>
            </div>

            {/* Deliberately not the binder/bind pair the field list uses:
                that is a multi-column grid, and it flowed the reason for the
                match into the column beside the choice it explains. A
                decision and its grounds have to read in that order. */}
            {match && (
              <div className="form">
                <label className="inline-check">
                  <input type="radio" name={"m-" + id}
                    checked={f.use === "existing"}
                    onChange={() => setFacts({
                      ...facts, [id]: { ...f, use: "existing" } })} />
                  Use <strong>{match.label}</strong>, which you already hold
                </label>
                {/* The better answer to a fact that nearly fits is often to
                    amend the one you have - a residency column on Ownership
                    and Control rather than a Residency field nobody asked
                    for. */}
                <p className="muted small">
                  <a onClick={() => setEditField(f.existing)}>
                    Open {match.label} and amend it
                  </a>
                  {heldEdits[f.existing ?? ""] ? " \u00b7 amended" : ""}
                </p>
                <p className="muted small">
                  {match.description}
                  {f.why ? " \u2014 " + f.why : ""}
                </p>
                <label className="inline-check">
                  <input type="radio" name={"m-" + id}
                    checked={f.use === "new"}
                    onChange={() => setFacts({
                      ...facts, [id]: { ...f, use: "new" } })} />
                  No, this is a different fact &mdash; add it
                </label>
              </div>
            )}

            {f.use === "new" && (
              <div className="form">
                <label className="row">
                  <span>Name</span>
                  <input value={f.label}
                    onChange={(e) => setFacts({
                      ...facts,
                      [id]: { ...f, label: e.target.value,
                              acknowledged: false } })} />
                </label>

                <label className="row">
                  <span>What it is</span>
                  <textarea rows={2} value={f.description}
                    onChange={(e) => setFacts({
                      ...facts,
                      [id]: { ...f, description: e.target.value,
                              acknowledged: false } })} />
                </label>
                <p className="muted small">
                  This is what the system reads when deciding whether it has
                  found this fact. It cannot be corrected later for documents
                  already filed.
                </p>

                <label className="row">
                  <span>Shape</span>
                  <select value={f.shape}
                    onChange={(e) => setFacts({
                      ...facts,
                      [id]: { ...f, shape: e.target.value,
                              acknowledged: false } })}>
                    <option value="one">A single fact</option>
                    <option value="group">
                      A table &mdash; several rows with columns
                    </option>
                  </select>
                </label>

                {/* A table with no columns holds nothing, and there is no
                    other screen to add them on. So they are named here, and
                    a table cannot be acknowledged without at least one. */}
                {f.shape === "group" && (
                  <div className="columns">
                    <h4>Columns</h4>
                    <p className="muted small">
                      What each row holds. A name means nothing without the
                      things beside it &mdash; a buyer without its country, a
                      figure without its period.
                    </p>

                    {f.columns.map((c, i) => (
                      <div className="column-row" key={i}>
                        <input placeholder="Column" value={c}
                          onChange={(e) => {
                            const next = [...f.columns];
                            next[i] = e.target.value;
                            setFacts({ ...facts,
                              [id]: { ...f, columns: next,
                                      acknowledged: false } });
                          }} />
                        <a className="small" onClick={() => setFacts({
                          ...facts,
                          [id]: { ...f,
                            columns: f.columns.filter((_, j) => j !== i),
                            acknowledged: false } })}>
                          Remove
                        </a>
                      </div>
                    ))}

                    <a className="small" onClick={() => setFacts({
                      ...facts,
                      [id]: { ...f, columns: [...f.columns, ""],
                              acknowledged: false } })}>
                      Add a column
                    </a>

                    {f.columns.filter((c) => c.trim()).length === 0 && (
                      <p className="warn small">
                        A table needs at least one column, or it holds
                        nothing.
                      </p>
                    )}
                  </div>
                )}

                <label className="inline-check">
                  <input type="checkbox" checked={f.acknowledged}
                    disabled={!f.label.trim() || !f.description.trim()
                      || f.documents.length === 0
                      || (f.shape === "group"
                          && f.columns.filter((c) => c.trim()).length === 0)}
                    onChange={(e) => setFacts({
                      ...facts,
                      [id]: { ...f, acknowledged: e.target.checked } })} />
                  I have read this and it says what I mean
                </label>
              </div>
            )}

            {/* Where a fact is read from, shown on every card. It sat inside
                the new-fact form, so the sources of a fact the tenant already
                holds could only be seen by declining the match - the one
                moment nobody is looking for them.

                Guessed from the report and shown rather than applied quietly:
                a fact looked for in the wrong document is never found, and a
                fact looked for in none is never extracted at all. Neither
                says so. */}
              <div className="columns">
                <h4>Where to look for it</h4>
                <p className="muted small">
                  Only the documents ticked here are read for this fact.
                  Tick widely and the wrong answer creeps in; tick nothing
                  and it is never looked for.
                </p>
                {f.use === "existing" && (
                  <p className="muted small">
                    Where you already look for it. Ticking another document
                    adds to that; unticking here leaves what you had alone.
                  </p>
                )}

                <div className="binder">
                  {docOptions.map((label) => (
                    <label className="bind" key={label}>
                      <input type="checkbox"
                        checked={f.documents.some(
                          (x) => x.trim().toLowerCase()
                            === label.toLowerCase())}
                        onChange={(e) => {
                          const kept = f.documents.filter(
                            (x) => x.trim().toLowerCase()
                              !== label.toLowerCase());
                          setFacts({
                            ...facts,
                            [id]: { ...f,
                              documents: e.target.checked
                                ? [...kept, label] : kept,
                              acknowledged: false } });
                        }} />
                      {label}
                    </label>
                  ))}
                </div>

                {f.documents.length === 0 && (
                  <p className="warn small">
                    Nothing is ticked, so this fact would never be looked
                    for.
                  </p>
                )}

                {/* A fact whose document is not on the list. Named here
                    and described below, rather than authored twice: the
                    description is what the classifier reads, and it earns
                    its own acknowledgement wherever it is written. */}
                {addingDoc !== id ? (
                  <a className="small"
                     onClick={() => { setAddingDoc(id); setNewDocName(""); }}>
                    None of these? Add a document
                  </a>
                ) : (
                  <div className="filters">
                    <input placeholder="What the document is called"
                           value={newDocName} autoFocus
                           onChange={(e) => setNewDocName(e.target.value)} />
                    <button disabled={!newDocName.trim()}
                      onClick={() => {
                        const label = newDocName.trim();
                        const tid = label.toLowerCase();
                        const held = (draft?.document_types ?? []).find(
                          (t) => t.label.trim().toLowerCase() === tid);

                        // Already known, under either name. Tick it rather
                        // than make a second document meaning the same.
                        if (!held && !types[tid]) {
                          setTypes({
                            ...types,
                            [tid]: {
                              use: "new", label, description: "",
                              group: draft?.categories[0]?.key ?? "",
                              groupLabel: "", existing: null,
                              acknowledged: false,
                            },
                          });
                        }
                        const name = held ? held.label : label;
                        if (!f.documents.some(
                          (x) => x.trim().toLowerCase()
                            === name.toLowerCase())) {
                          setFacts({
                            ...facts,
                            [id]: { ...f,
                              documents: [...f.documents, name],
                              acknowledged: false } });
                        }
                        setAddingDoc(null);
                        setNewDocName("");
                      }}>
                      Add
                    </button>
                    <a className="small"
                       onClick={() => setAddingDoc(null)}>Cancel</a>
                    <span className="muted small">
                      It appears under Documents below, where it needs a
                      description before you can accept.
                    </span>
                  </div>
                )}
              </div>

            {/* Where this fact is reported. A fact in no section is extracted
                on every filing and reaches no reader, so it is named here
                rather than left to be noticed at publish. */}
            <div className="muted small">
              <strong>Reported in:</strong>{" "}
              {f.sections.length === 0 && "no section yet"}
              {f.sections.map((i) => {
                const s = proposal.sections[i];
                if (!s) return null;
                return (
                  <span key={i} style={{ marginRight: "0.75em" }}>
                    {s.numeral} {s.title}
                    {skipped.has(i) ? " (not wanted)" : ""}{" "}
                    <a onClick={() => setFacts({
                      ...facts,
                      [id]: { ...f,
                        sections: f.sections.filter((x) => x !== i),
                        acknowledged: false } })}>&times;</a>
                  </span>
                );
              })}
            </div>

            <label className="row">
              <span>Add to a section</span>
              <select value=""
                onChange={(e) => {
                  if (e.target.value === "") return;
                  setFacts({
                    ...facts,
                    [id]: { ...f,
                      sections: [...f.sections, Number(e.target.value)],
                      acknowledged: false } });
                }}>
                <option value="">Choose&hellip;</option>
                {proposal.sections.map((s, i) => (
                  skipped.has(i) || f.sections.includes(i) ? null : (
                    <option key={i} value={String(i)}>
                      {s.numeral} {s.title}
                    </option>
                  )
                ))}
              </select>
            </label>

            <div className="muted small">
              <a onClick={() => setFacts({
                ...facts,
                [id]: { ...f, use: f.use === "skip"
                  ? (f.existing ? "existing" : "new") : "skip" } })}>
                {f.use === "skip" ? "Put it back" : "I do not need this fact"}
              </a>
            </div>
          </div>
        );
  };

  /**
   * A field the tenant already holds, opened to be amended.
   *
   * Nothing is written here. The amendment is held and applied at Accept
   * with everything else, because the screen tells the person all the way
   * down that nothing is saved until then.
   */
  const fieldEditor = (key: string) => {
    const base = fieldsByKey[key];
    if (!base) return null;
    const cur = heldEdits[key] ?? {
      label: base.label, description: base.description,
      cardinality: base.cardinality, columns: base.columns,
    };
    const set = (next: Partial<typeof cur>) =>
      setHeldEdits({ ...heldEdits, [key]: { ...cur, ...next } });
    const isTable = cur.cardinality === "group";
    const becameTable = isTable && base.cardinality !== "group";
    const added = cur.columns.filter((c) => !c.key).length;

    return (
      <div className="form">
        <h4>{base.label}</h4>
        <p className="muted small">
          A fact you already hold. Amending it here changes it for every
          memorandum that reports it, not only this one.
        </p>

        <label className="row">
          <span>Name</span>
          <input value={cur.label}
                 onChange={(e) => set({ label: e.target.value })} />
        </label>
        <p className="muted small">
          Renaming is free and reaches memoranda already written: the identity
          never follows the label.
        </p>

        <label className="row">
          <span>What it is</span>
          <textarea rows={3} value={cur.description ?? ""}
                    onChange={(e) => set({ description: e.target.value })} />
        </label>
        <p className="muted small">
          This is what the system reads when deciding whether it has found
          this fact. Changing it applies to documents filed from now on, not
          to those already filed.
        </p>

        {/* A single value that turns out to want columns. The alternative was
            to decline the match and make a second fact meaning the same
            thing, with the first left behind to be remembered and deleted -
            which is the duplicate this whole screen exists to prevent.

            Extraction is pinned, so this reaches documents filed from now on
            and not those already filed: a memorandum written before it still
            reproduces against the revision it was written under. */}
        <label className="row">
          <span>Shape</span>
          <select value={cur.cardinality}
            onChange={(e) => set({ cardinality: e.target.value })}>
            <option value="one">A single fact</option>
            <option value="many">Several values</option>
            <option value="group">
              A table &mdash; several rows with columns
            </option>
          </select>
        </label>

        {cur.cardinality !== base.cardinality && (
          <p className="warn small">
            Changing the shape applies to documents filed from now on. What
            was already read from documents you have filed stays as it was,
            and memoranda already written still reproduce.
          </p>
        )}

        {isTable && (
          <div className="columns">
            <h4>Columns</h4>
            {becameTable && cur.columns.length === 0 && (
              <p className="muted small">
                It has none yet. A table with no columns holds nothing, so
                name what each row should carry.
              </p>
            )}
            {cur.columns.map((c, i) => (
              <div className="column-row" key={c.key ?? "new-" + i}>
                <input placeholder="Column" value={c.label}
                  onChange={(e) => {
                    const next = [...cur.columns];
                    next[i] = { ...c, label: e.target.value };
                    set({ columns: next });
                  }} />
                <input placeholder="What it holds"
                       value={c.description ?? ""}
                  onChange={(e) => {
                    const next = [...cur.columns];
                    next[i] = { ...c, description: e.target.value };
                    set({ columns: next });
                  }} />
                <a className="small" onClick={() => set({
                  columns: cur.columns.filter((_, j) => j !== i) })}>
                  Remove
                </a>
              </div>
            ))}
            <a className="small" onClick={() => set({
              columns: [...cur.columns,
                { key: "", label: "", type: "text", description: "" }] })}>
              Add a column
            </a>

            {added > 0 && (
              <p className="warn small">
                A new column is a new fact. It will be empty on every document
                already filed, and the only way to fill it is to file those
                documents again.
              </p>
            )}
          </div>
        )}

        {isTable && cur.columns.filter((c) => c.label.trim()).length === 0 && (
          <p className="warn small">
            A table needs at least one column.
          </p>
        )}

        <div className="form-actions">
          <button
            disabled={isTable
              && cur.columns.filter((c) => c.label.trim()).length === 0}
            onClick={() => setEditField(null)}>Done</button>
          <a className="secondary" onClick={() => {
            const next = { ...heldEdits };
            delete next[key];
            setHeldEdits(next);
            setEditField(null);
          }}>Leave it as it was</a>
        </div>
      </div>
    );
  };

  // Accepting has run. Said plainly, either way: it wrote to the draft, and a
  // screen that goes quiet afterwards leaves a person unsure whether it did.
  if (result) {
    return (
      <div>
        <h2>{result.ok ? "Added to your draft" : "It stopped part way"}</h2>

        {result.ok ? (
          <p className="muted">
            Your draft now holds this memorandum and everything below.
            Nothing reaches a report until you publish.
          </p>
        ) : (
          <>
            <p className="error">{result.error}</p>
            <p className="muted">
              What is listed below was written before it stopped and is in
              your draft. The rest was not. Nothing has been published.
            </p>
          </>
        )}

        {written.length === 0 && (
          <p className="muted small">Nothing was written.</p>
        )}

        <ul className="muted small">
          {written.map((w, i) => <li key={i}>{w}</li>)}
        </ul>

        <div className="form-actions">
          <button onClick={() => onDone(result.templateKey || "")}>
            Back to the configuration
          </button>
        </div>
      </div>
    );
  }

  // Every ending that is not a proposal. One shape, so none of them can be
  // the one that forgets to offer a way out - the first version told a person
  // to try a shorter report and gave them nothing to click.
  const stopped: Record<string, { title: string; body: string }> = {
    "unreadable": {
      title: "That file could not be read",
      body: "It carries no text we can read \u2014 a scan, most likely."
        + " Send the Word original, or a PDF exported rather than scanned.",
    },
    "nothing-found": {
      title: "No sections found",
      body: "We read the file but could not make out headings in it. A report"
        + " with numbered or titled sections is what this works from.",
    },
    "model-unavailable": {
      title: "It could not be read just now",
      body: "The service that reads reports would not take the request. This"
        + " is nothing to do with your file \u2014 try again in a few"
        + " minutes.",
    },
    "failed": {
      title: "It stopped before finishing",
      body: "Something went wrong while reading it. Nothing was saved.",
    },
  };

  const ending = stopped[proposal.status];
  if (ending) {
    return (
      <div>
        <a onClick={onCancel} className="back">Back</a>
        <h2>{ending.title}</h2>
        <p className="muted">{ending.body}</p>
        {proposal.reason && (
          <p className="muted small">Recorded: {proposal.reason}</p>
        )}
        <div className="form-actions">
          <button onClick={() => { setProposal(null); setError(""); }}>
            Try another report
          </button>
          <a className="secondary" onClick={onCancel}>Back</a>
        </div>
      </div>
    );
  }

  if (proposal.status !== "ready") {
    const done = proposal.sections_done;
    const total = proposal.sections_total;
    return (
      <div>
        <h2>Reading your report</h2>
        <p className="muted">
          {total
            ? `Section ${done} of ${total}.`
            : "Finding the sections\u2026"}
        </p>
        {proposal.memorandum_label && (
          <p className="muted small">
            It reads as a {proposal.memorandum_label}.
          </p>
        )}
        <ul className="muted small">
          {proposal.sections.map((s, i) => (
            <li key={i}>
              {s.numeral} {s.title}
              {" \u00b7 "}{s.facts.length}{" "}
              {s.facts.length === 1 ? "fact" : "facts"}
            </li>
          ))}
        </ul>
        {error && (
          <>
            <p className="error">{error}</p>
            <div className="form-actions">
              <button onClick={() => { setProposal(null); setError(""); }}>
                Try another report
              </button>
              <a className="secondary" onClick={onCancel}>Back</a>
            </div>
          </>
        )}
      </div>
    );
  }

  // Every group a document could sit in: the tenant's, plus any made here.
  // Declared before anything that reads it: groupsOf runs during render, and
  // a const referenced above its own declaration is a blank screen with no
  // message anywhere on the page.
  const allGroups = [...(draft?.categories ?? []), ...newGroups];

  const factList = Object.entries(facts);

  /** What a section may still be given, in the order that tells the person
   *  something: what they already hold, what this report proposed, and what
   *  nothing reports yet - which is where an orphan is most likely to be
   *  picked up. */
  const offerFor = (i: number) => {
    const free = Object.entries(facts).filter(
      ([, f]) => live(f) && !f.sections.includes(i));
    const by = (test: (f: FactChoice) => boolean) => free
      .filter(([, f]) => test(f))
      .sort((a, b) => a[1].label.localeCompare(b[1].label));

    const nowhere = ([, f]: [string, FactChoice]) =>
      !f.sections.some((x) => !skipped.has(x));

    const out = [
      { label: "Not reported anywhere yet",
        entries: free.filter(nowhere)
          .sort((a, b) => a[1].label.localeCompare(b[1].label)) },
      { label: "You already hold these",
        entries: by((f) => f.use === "existing").filter(
          (e) => !nowhere(e)) },
      { label: "New in this report",
        entries: by((f) => f.use === "new").filter((e) => !nowhere(e)) },
    ];
    return out.filter((g) => g.entries.length > 0);
  };

  // Facts no kept section reports. Marked ones stay in the list, marked.
  const stranded = factList
    .filter(([, f]) => live(f)
      && !f.sections.some((i) => !skipped.has(i)))
    .sort((a, b) => a[1].label.localeCompare(b[1].label));

  const typeList = Object.entries(types).filter(([, t]) => t.use !== "existing"
    || t.existing === null);

  // Documents the tenant already holds, less any this report would add under
  // the same name - one document should not appear in both lists.
  const proposedLabels = new Set(
    Object.values(types).filter((t) => t.use === "new")
      .map((t) => t.label.trim().toLowerCase()));
  const heldTypes = (draft?.document_types ?? [])
    .filter((t) => !proposedLabels.has(t.label.trim().toLowerCase()))
    .slice()
    .sort((a, b) => a.label.localeCompare(b.label));

  // Every document a fact could be looked for in once this is accepted: the
  // ones the tenant holds, and the ones this proposal would add. Named by
  // label, because a proposed type has no key until it is created.
  const docOptions: string[] = (() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const t of draft?.document_types ?? []) {
      const l = t.label.trim();
      if (l && !seen.has(l.toLowerCase())) { seen.add(l.toLowerCase()); out.push(l); }
    }
    for (const t of Object.values(types)) {
      if (t.use === "skip") continue;
      const l = t.label.trim();
      if (l && !seen.has(l.toLowerCase())) { seen.add(l.toLowerCase()); out.push(l); }
    }
    return out.sort((a, b) => a.localeCompare(b));
  })();

  return (
    <div>
      <a onClick={onCancel} className="back">Back</a>
      <h2>What we found in your report</h2>
      <p className="muted">
        Correct anything that is wrong. Nothing here has been saved.
      </p>
      {error && <p className="error">{error}</p>}
      {busy && <p className="busy">{busy}&hellip;</p>}

      {/* 1 --- the memorandum ------------------------------------------- */}
      <h3>The memorandum</h3>
      <label className="row">
        <span>Name</span>
        <input value={memoLabel}
               onChange={(e) => setMemoLabel(e.target.value)} />
      </label>

      {/* 2 --- its sections --------------------------------------------- */}
      {part("sections", "Memo sections",
            `${proposal.sections.length} in the report`,
            factList.filter(([, f]) => wanting(f)
              && f.sections.length > 0).length)}

      {!shut.has("sections") && (<>
      <p className="muted small">
        In the order they appear in your report. Untick anything you do not
        want.
      </p>

      <table className="docs">
        <tbody>
          {proposal.sections.map((s, i) => {
            const carries = factList.filter(
              ([, f]) => f.use !== "skip" && f.sections.includes(i));
            const wants = carries.filter(([, f]) => wanting(f)).length;
            return (
            <tr key={i} className={skipped.has(i) ? "aside" : ""}>
              <td>
                <input type="checkbox" checked={!skipped.has(i)}
                  onChange={() => {
                    const next = new Set(skipped);
                    if (next.has(i)) next.delete(i); else next.add(i);
                    setSkipped(next);
                  }} />
              </td>
              <td>
                <input value={s.numeral}
                  style={{ width: "4em", marginRight: "0.5em" }}
                  onChange={(e) => {
                    const next = [...proposal.sections];
                    next[i] = { ...s, numeral: e.target.value };
                    setProposal({ ...proposal, sections: next });
                  }} />
                <input value={s.title}
                  onChange={(e) => {
                    const next = [...proposal.sections];
                    next[i] = { ...s, title: e.target.value };
                    setProposal({ ...proposal, sections: next });
                  }} />
                <div className="muted small">{s.purpose}</div>
                {!s.located && (
                  <div className="warn small">
                    We could not find this heading again in the text, so it was
                    read against the whole report. Worth checking.
                  </div>
                )}

                {/* This section's facts, opened one section at a time. A
                    fact is read where it belongs - inside the section that
                    reports it - rather than in a list of every fact the
                    report named. */}
                <a className="small"
                   onClick={() => setShownSection(
                     shownSection === i ? null : i)}>
                  {shownSection === i ? "\u25be" : "\u25b8"} {carries.length}
                  {carries.length === 1 ? " fact" : " facts"}
                </a>
                {wants > 0 && (
                  <span className="warn small">
                    {" \u00b7 "}{wants} needing you
                  </span>
                )}

                {shownSection === i && (
                  <ul className="muted small">
                    {carries
                      .sort((a, b) => a[1].label.localeCompare(b[1].label))
                      .map(([fid, f]) => (
                      <li key={fid}>
                        <a onClick={() => setOpenFact(fid)}>{f.label}</a>
                        {f.use === "existing"
                          ? " \u00b7 you already hold this"
                          : " \u00b7 new"}
                        {wanting(f) && (
                          <span className="warn"> needs you</span>
                        )}{" "}
                        <a onClick={() => setFacts({
                          ...facts,
                          [fid]: { ...f,
                            sections: f.sections
                              .filter((x) => x !== i) } })}>
                          &times;
                        </a>
                      </li>
                    ))}
                    {carries.length === 0 && <li>Nothing in it yet.</li>}
                  </ul>
                )}

                {/* Pick from what is already on the table before naming
                    anything: typing a name that already exists was the
                    ordinary way to end up with two facts meaning one thing.
                    Sorted by what the person needs to know about each -
                    whether they hold it, whether the report proposed it, and
                    whether anything reports it yet. */}
                <label className="row">
                  <span>Add a fact</span>
                  <select value=""
                    onChange={(e) => {
                      const v = e.target.value;
                      if (v === "") return;
                      if (v === "\u0000new") {
                        setAddingSection(i);
                        setNewInSection("");
                        return;
                      }
                      const f2 = facts[v];
                      if (f2 && !f2.sections.includes(i)) {
                        setFacts({ ...facts,
                          [v]: { ...f2, unused: false,
                            sections: [...f2.sections, i] } });
                      }
                    }}>
                    <option value="">Choose&hellip;</option>
                    {offerFor(i).map((g) => (
                      <optgroup key={g.label} label={g.label}>
                        {g.entries.map(([fid, f]) => (
                          <option key={fid} value={fid}>{f.label}</option>
                        ))}
                      </optgroup>
                    ))}
                    <option value={"\u0000new"}>
                      Create a new fact
                    </option>
                  </select>
                </label>

                {addingSection === i && (
                  <div className="filters">
                    <input placeholder="What the fact is called" autoFocus
                           value={newInSection}
                           onChange={(e) => setNewInSection(e.target.value)} />
                    <button disabled={!newInSection.trim()}
                      onClick={() => {
                        const label = newInSection.trim();
                        const fid = label.toLowerCase();
                        const already = facts[fid];
                        if (already) {
                          if (!already.sections.includes(i)) {
                            setFacts({ ...facts,
                              [fid]: { ...already,
                                sections: [...already.sections, i] } });
                          }
                        } else {
                          setFacts({ ...facts,
                            [fid]: {
                              use: "new", label, description: "",
                              shape: "one", existing: null, why: null,
                              columns: [], documents: [], held: [],
                              sections: [i],
                              added: false, unused: false,
                              acknowledged: false,
                            } });
                        }
                        setAddingSection(null);
                        setNewInSection("");
                      }}>
                      Add
                    </button>
                    <a className="small"
                       onClick={() => setAddingSection(null)}>Cancel</a>
                  </div>
                )}
              </td>
              <td className="muted small">
                {carries.length} {carries.length === 1 ? "fact" : "facts"}
              </td>
            </tr>
            );
          })}
        </tbody>
      </table>

      {/* A section the report never had. Its facts are named on it, the same
          way as any other. */}
      <div className="filters">
        <input placeholder="Numeral" value={newSectionNumeral}
               style={{ width: "5em" }}
               onChange={(e) => setNewSectionNumeral(e.target.value)} />
        <input placeholder="Add a section" value={newSectionTitle}
               onChange={(e) => setNewSectionTitle(e.target.value)} />
        <button disabled={!newSectionTitle.trim()}
          onClick={() => {
            setProposal({
              ...proposal,
              sections: [...proposal.sections, {
                heading: newSectionTitle.trim(),
                title: newSectionTitle.trim(),
                numeral: newSectionNumeral.trim(),
                purpose: "Added by you.",
                located: true,
                facts: [],
              }],
            });
            setNewSectionTitle("");
            setNewSectionNumeral("");
          }}>
          Add
        </button>
      </div>

      {/* 3 --- the facts ------------------------------------------------- */}
      </>)}
      {/* The fact card, opened over the page. The stylesheet already has a
          drawer - panel-backdrop and panel - so this uses it rather than
          introducing a second thing that means the same. */}
      {openFact && facts[openFact] && (
        <div className="panel-backdrop" onClick={() => {
          setEditField(null); setOpenFact(null);
        }}>
          <div className="panel" onClick={(e) => e.stopPropagation()}>
            <a className="panel-close" onClick={() => {
              setEditField(null); setOpenFact(null);
            }}>Close</a>

            {/* One drawer, two things in it. Amending a held field is a step
                inside deciding a match, not a second window over it. */}
            {editField ? (
              <>
                <p className="muted small">
                  <a onClick={() => setEditField(null)}>
                    &lsaquo; Back to {facts[openFact].label}
                  </a>
                </p>
                {fieldEditor(editField)}
              </>
            ) : (
              <>
                {factCard(openFact, facts[openFact])}
                <div className="form-actions">
                  <button onClick={() => setOpenFact(null)}>Done</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* 3 --- facts nothing reports ------------------------------------ */}
      {/* A fact belongs to the tenant, not to one memorandum, so it is
          expected that a memorandum reports only some of them. What is not
          expected is losing track of which - so they are listed rather than
          dropped, and stay listed once marked. */}
      {stranded.length > 0 && (
        <>
          {part("stranded", "Not reported by this memorandum",
                `${stranded.length}`,
                stranded.filter(([, f]) => wanting(f)).length)}

      {!shut.has("stranded") && (<>
          <p className="muted small">
            These will be read from your documents, but no section here
            reports them. Put each in a section, or mark it as not used by
            this memorandum. Another memorandum may still report it.
          </p>

          <table className="docs">
            <tbody>
              {stranded.map(([id, f]) => (
                <tr key={id} className={f.unused ? "aside" : ""}>
                  <td>
                    <a onClick={() => setOpenFact(id)}>{f.label}</a>
                    {wanting(f) && (
                      <span className="warn small"> needs you</span>
                    )}
                  </td>
                  <td>
                    <select value=""
                      onChange={(e) => {
                        if (e.target.value === "") return;
                        const at = Number(e.target.value);
                        setFacts({ ...facts,
                          [id]: { ...f, unused: false,
                            sections: f.sections.includes(at)
                              ? f.sections : [...f.sections, at] } });
                      }}>
                      <option value="">Add to a section&hellip;</option>
                      {proposal.sections.map((s, i) => (
                        skipped.has(i) ? null : (
                          <option key={i} value={String(i)}>
                            {s.numeral} {s.title}
                          </option>
                        )
                      ))}
                    </select>
                  </td>
                  <td className="muted small">
                    <a onClick={() => setFacts({
                      ...facts, [id]: { ...f, unused: !f.unused } })}>
                      {f.unused
                        ? "Marked not used \u2014 undo"
                        : "Not used in this memorandum"}
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
      </>)}
        </>
      )}

      {/* 4 --- the documents --------------------------------------------- */}
      {typeList.length > 0 && (
        <>
          {/* Grouping is for the eye. Nothing reads it, so a group made here
              and a document moved between groups disturb no extraction and no
              memorandum - which is why this is the one thing on the screen
              that may be changed for documents already held. */}
          <div className="filters">
            <input placeholder="Add a group" value={newGroupName}
                   onChange={(e) => setNewGroupName(e.target.value)} />
            <button disabled={!newGroupName.trim()}
              onClick={() => {
                const label = newGroupName.trim();
                const key = slugKey(label);
                if (!allGroups.some((c) => c.key === key)) {
                  setNewGroups([...newGroups, { key, label }]);
                }
                setNewGroupName("");
              }}>
              Add
            </button>
            <span className="muted small">
              Groups order the documents on screen and nothing else.
            </span>
          </div>

          {part("newdocs", "Documents not yet referenced",
                `${typeList.length}`,
                typeList.filter(([, t]) => t.use === "new"
                  && !t.acknowledged).length)}

          {!shut.has("newdocs") && (<>
          <p className="muted small">
            Kinds of document your report appears to rest on, that are not in
            your configuration.
          </p>

          {typeList.map(([id, t]) => (
            <div className="review" key={id}>
              <div className="review-head">
                <a onClick={() => setOpenDoc(openDoc === id ? null : id)}>
                  <strong>
                    {openDoc === id ? "\u25be" : "\u25b8"} {t.label}
                  </strong>
                </a>
                <span className="muted small">
                  {t.use === "skip" ? "not wanted" : "new"}
                </span>
                {openDoc !== id && t.use === "new"
                  && !t.acknowledged && (
                  <span className="warn small">needs you</span>
                )}
              </div>

              {openDoc === id && t.use === "new" && (
                <div className="form">
                  <label className="row">
                    <span>Name</span>
                    <input value={t.label}
                      onChange={(e) => setTypes({
                        ...types,
                        [id]: { ...t, label: e.target.value,
                                acknowledged: false } })} />
                  </label>

                  <label className="row">
                    <span>How to recognise it</span>
                    <textarea rows={3} value={t.description}
                      onChange={(e) => setTypes({
                        ...types,
                        [id]: { ...t, description: e.target.value,
                                acknowledged: false } })} />
                  </label>
                  <p className="muted small">
                    This is what the system reads to tell this document from
                    every other kind. Getting it wrong sends future uploads to
                    the wrong place quietly.
                  </p>

                  <label className="row">
                    <span>Group</span>
                    <select value={t.group}
                      onChange={(e) => {
                        const key = e.target.value;
                        const known = allGroups.some((c) => c.key === key);
                        setTypes({ ...types, [id]: { ...t, group: key,
                          groupLabel: known ? "" : t.groupLabel } });
                      }}>
                      {allGroups.map((c) => (
                        <option key={c.key} value={c.key}>{c.label}</option>
                      ))}
                      {t.groupLabel && (
                        <option value={t.group}>
                          {t.groupLabel} (new group)
                        </option>
                      )}
                    </select>
                  </label>
                  <p className="muted small">
                    Grouping is for the eye alone and can be changed at any
                    time without disturbing anything.
                  </p>

                  {readFrom(t.label, id)}

                  <label className="inline-check">
                    <input type="checkbox" checked={t.acknowledged}
                      disabled={!t.label.trim() || !t.description.trim()
                        || factList.filter(([, f]) => live(f)
                          && f.documents.some((x) => x.trim().toLowerCase()
                            === t.label.trim().toLowerCase())).length === 0}
                      onChange={(e) => setTypes({
                        ...types,
                        [id]: { ...t, acknowledged: e.target.checked } })} />
                    I have read this and it says what I mean
                  </label>
                </div>
              )}

              <div className="muted small">
                <a onClick={() => setTypes({
                  ...types,
                  [id]: { ...t, use: t.use === "skip" ? "new" : "skip" } })}>
                  {t.use === "skip"
                    ? "Put it back" : "I do not need this document"}
                </a>
              </div>
            </div>
          ))}
          </>)}
        </>
      )}

      {/* 4b --- documents the tenant already holds ----------------------- */}
      {heldTypes.length > 0 && (
        <>
          {part("helddocs", "Documents you already hold",
                `${heldTypes.length}`, 0)}

          {!shut.has("helddocs") && (<>
          <p className="muted small">
            Say what each of these is read for, and the whole configuration is
            done here rather than half here and half in the editor afterwards.
            Their names and descriptions are settled and are not changed on
            this screen.
          </p>

          {heldTypes.map((t) => {
            const id = "held:" + t.key;
            const reads = factList.filter(([, f]) => live(f)
              && f.documents.some((x) => x.trim().toLowerCase()
                === t.label.trim().toLowerCase())).length;
            return (
              <div className="review" key={id}>
                <div className="review-head">
                  <a onClick={() => setOpenDoc(openDoc === id ? null : id)}>
                    <strong>
                      {openDoc === id ? "\u25be" : "\u25b8"} {t.label}
                    </strong>
                  </a>
                  <span className="muted small">
                    {reads} {reads === 1 ? "fact" : "facts"}
                  </span>
                </div>

                {openDoc === id && (
                  <div className="form">
                    <label className="row">
                      <span>Group</span>
                      <select value={heldGroup[t.key] ?? t.category}
                        onChange={(e) => setHeldGroup({
                          ...heldGroup, [t.key]: e.target.value })}>
                        {allGroups.map((c) => (
                          <option key={c.key} value={c.key}>{c.label}</option>
                        ))}
                      </select>
                    </label>
                    {readFrom(t.label, id)}
                  </div>
                )}
              </div>
            );
          })}
          </>)}
        </>
      )}

      {/* 5 --- accept ------------------------------------------------------ */}
      <h3>Accept</h3>
      <p className="muted small">
        This writes the memorandum, its sections and anything new into your
        draft. Nothing reaches a report until you publish.
      </p>
      <p className="muted small">
        Worth doing before you upload any documents. A fact added afterwards is
        empty on everything already filed, and the only remedy is filing those
        documents again.
      </p>

      {Object.keys(heldEdits).length > 0 && (
        <p className="muted small">
          {Object.keys(heldEdits).length} fact
          {Object.keys(heldEdits).length === 1 ? "" : "s"} you already hold
          will be amended. That reaches every memorandum reporting them.
        </p>
      )}

      {/* A number is not much use at the foot of a long page. Each of these
          opens the thing that is waiting. */}
      {outstanding > 0 && (
        <div className="warn">
          <p>
            {outstanding} {outstanding === 1 ? "thing has" : "things have"}
            {" "}still to be acknowledged.
          </p>
          <ul className="small">
            {factList.filter(([, f]) => wanting(f)).map(([fid, f]) => (
              <li key={fid}>
                <a onClick={() => setOpenFact(fid)}>{f.label}</a>
              </li>
            ))}
            {Object.entries(types)
              .filter(([, t]) => t.use === "new" && !t.acknowledged)
              .map(([tid, t]) => (
                <li key={tid}>
                  <a onClick={() => setOpenDoc(tid)}>{t.label}</a>
                  {" \u00b7 a document"}
                </li>
              ))}
          </ul>
        </div>
      )}

      <div className="form-actions">
        <button disabled={!!busy || outstanding > 0 || !memoLabel.trim()}
                onClick={accept}>
          {busy ? busy + "\u2026" : "Accept and add to my draft"}
        </button>
        <a className="secondary" onClick={onCancel}>Cancel</a>
      </div>
    </div>
  );
}
