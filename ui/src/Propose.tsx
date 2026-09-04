import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type Draft,
  type Proposal,
  type ProposedFact,
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
  documents: string[];
  sections: number[];
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
  // A hundred cards, most of them already answered. Without this the few
  // that need a person are found by scrolling for them.
  const [onlyOutstanding, setOnlyOutstanding] = useState(false);
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
              || p.status === "nothing-found") {
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
            setError("Reading stopped before it finished. Nothing was saved."
                     + " Try a shorter report.");
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
          documents: f.found_in ?? [],
          sections: [index],
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
  const live = (f: FactChoice) =>
    f.use !== "skip" && f.sections.some((i) => !skipped.has(i));

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

  const outstanding = useMemo(() => {
    const n = Object.values(facts)
      .filter((f) => f.use === "new" && live(f) && !f.acknowledged).length
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

    try {
      const groups = new Set((draft?.categories ?? []).map((c) => c.key));
      for (const t of Object.values(types)) {
        if (t.use !== "new" || !t.groupLabel || groups.has(t.group)) continue;
        setBusy("Adding a group");
        await api.saveCategory({ key: t.group, label: t.groupLabel });
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
      }

      for (const f of Object.values(facts)) {
        if (f.use !== "new" || !live(f)) continue;
        const documents = f.documents
          .map((label) => typeKeyByLabel[label.trim().toLowerCase()])
          .filter((k): k is string => Boolean(k));
        if (documents.length === 0) continue;
        setBusy("Where to find " + f.label);
        await api.setFieldDocuments(fieldKey(f.label), documents);
      }

      setBusy("Adding the memorandum");
      const made = await api.saveTemplate({ label: memoLabel.trim() });
      const templateKey = made.key as string;

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
      }

      for (const { s, i } of included) {
        const keys = Object.values(facts)
          .filter((f) => live(f) && f.sections.includes(i))
          .map((f) => f.use === "existing" && f.existing
            ? f.existing : fieldKey(f.label));
        if (keys.length === 0) continue;
        setBusy("Binding " + s.title);
        await api.setSectionFields(templateKey, sectionKeys[i], keys);
      }

      setBusy("");
      onDone(templateKey);
    } catch (e) {
      setError(message(e));
      setBusy("");
    }
  }

  // --- the screen ---------------------------------------------------------

  const fieldsByKey = useMemo(() => {
    const map: Record<string, { label: string; description: string | null }> =
      {};
    for (const f of draft?.fields ?? []) {
      map[f.key] = { label: f.label, description: f.description };
    }
    return map;
  }, [draft]);

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

  if (proposal.status === "unreadable") {
    return (
      <div>
        <a onClick={onCancel} className="back">Back</a>
        <h2>That file could not be read</h2>
        <p className="muted">
          It carries no text we can read &mdash; a scan, most likely. Send the
          Word original, or a PDF exported rather than scanned.
        </p>
        <p className="muted small">Reason recorded: {proposal.reason}</p>
      </div>
    );
  }

  if (proposal.status === "nothing-found") {
    return (
      <div>
        <a onClick={onCancel} className="back">Back</a>
        <h2>No sections found</h2>
        <p className="muted">
          We read the file but could not make out headings in it. A report with
          numbered or titled sections is what this works from.
        </p>
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
        {error && <p className="error">{error}</p>}
      </div>
    );
  }

  const factList = Object.entries(facts);
  const factsOutstanding = factList
    .filter(([, f]) => f.use === "new" && live(f) && !f.acknowledged).length;
  const shown = onlyOutstanding
    ? factList.filter(([, f]) => f.use === "new" && live(f)
        && !f.acknowledged)
    : factList;
  const typeList = Object.entries(types).filter(([, t]) => t.use !== "existing"
    || t.existing === null);

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
      <h3>Its sections</h3>
      <p className="muted small">
        In the order they appear in your report. Untick anything you do not
        want.
      </p>

      <table className="docs">
        <tbody>
          {proposal.sections.map((s, i) => (
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
                <strong>{s.numeral} {s.title}</strong>
                <div className="muted small">{s.purpose}</div>
                {!s.located && (
                  <div className="warn small">
                    We could not find this heading again in the text, so it was
                    read against the whole report. Worth checking.
                  </div>
                )}
              </td>
              <td className="muted small">
                {s.facts.length} {s.facts.length === 1 ? "fact" : "facts"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* 3 --- the facts ------------------------------------------------- */}
      <h3>The facts it reports</h3>
      <p className="muted small">
        {factList.length} in all, counted once however many sections name them.
        Where one looks like a fact you already hold, we say so &mdash; you
        decide whether it is the same thing.
      </p>

      <div className="filters">
        <label className="inline-check">
          <input type="checkbox" checked={onlyOutstanding}
            onChange={(e) => setOnlyOutstanding(e.target.checked)} />
          Show only the ones still needing me
        </label>
        <span className="muted small">
          {shown.length} of {factList.length}
          {factsOutstanding > 0
            ? ` \u00b7 ${factsOutstanding} to acknowledge` : ""}
        </span>
      </div>

      {shown.length === 0 && (
        <p className="muted small">Nothing left here.</p>
      )}

      {shown.map(([id, f]) => {
        const match = f.existing ? fieldsByKey[f.existing] : null;
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
                      || (f.shape === "group"
                          && f.columns.filter((c) => c.trim()).length === 0)}
                    onChange={(e) => setFacts({
                      ...facts,
                      [id]: { ...f, acknowledged: e.target.checked } })} />
                  I have read this and it says what I mean
                </label>
              </div>
            )}

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
      })}

      {/* 4 --- the documents --------------------------------------------- */}
      {typeList.length > 0 && (
        <>
          <h3>Documents it draws on</h3>
          <p className="muted small">
            Kinds of document your report appears to rest on, that you do not
            hold yet.
          </p>

          {typeList.map(([id, t]) => (
            <div className="review" key={id}>
              <div className="review-head">
                <label><strong>{t.label}</strong></label>
                <span className="muted small">
                  {t.use === "skip" ? "not wanted" : "new"}
                </span>
              </div>

              {t.use === "new" && (
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
                        const known = (draft?.categories ?? [])
                          .some((c) => c.key === key);
                        setTypes({ ...types, [id]: { ...t, group: key,
                          groupLabel: known ? "" : t.groupLabel } });
                      }}>
                      {(draft?.categories ?? []).map((c) => (
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

                  <label className="inline-check">
                    <input type="checkbox" checked={t.acknowledged}
                      disabled={!t.label.trim() || !t.description.trim()}
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

      {outstanding > 0 && (
        <p className="warn">
          {outstanding} {outstanding === 1 ? "thing has" : "things have"} still
          to be acknowledged.
        </p>
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
