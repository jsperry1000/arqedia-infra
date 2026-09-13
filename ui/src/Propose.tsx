import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Draft, type Proposal, type ProposedFact } from "./api";
import { slugKey, fieldKey } from "./config-parts";
import { Working } from "./shell";

/**
 * Create your own memorandum from a report you already write - a first cut.
 *
 * The client gives us a copy of a report they already write. We read its
 * shape - its sections, and the facts each one reports - and put that to them
 * as a first cut: which sections to keep, and which facts each should carry.
 * Accept writes it into the draft and opens the configuration editor on the
 * new memorandum. The editor is where it is corrected; this screen does not
 * reproduce it (UX-21).
 *
 * THE FILE IS FORM, NOT SUBSTANCE. It is read once for its layout and deleted.
 * It is never filed, classified, extracted from, cited or charged for.
 *
 * NOTHING IS TAKEN UNLESS TICKED. A report names far more facts than anyone
 * wants configured. Every fact starts unticked, and nothing unticked is
 * written - no field, no binding, no document brought in for it.
 *
 * A fact the reader matched to one the tenant already holds uses that one.
 * New facts and document types are written in the reader's own words. Nothing
 * has been filed against them yet, so every one can still be corrected in the
 * editor before a document is read.
 */

/** One fact the report names, and whether the person has ticked it. */
type FactChoice = {
  label: string;
  description: string;
  shape: string;
  columns: string[];
  // A field the tenant already holds that the reader matched this to.
  existing: string | null;
  // Document type LABELS the reader named. Resolved to keys only at Accept,
  // because a type may not exist until then.
  documents: string[];
  // Positions in the proposal's section list that name this fact.
  sections: number[];
  chosen: boolean;
};

/** A document type the reader named. */
type TypeChoice = {
  label: string;
  description: string;
  // The KEY of the group it sits in. The reader answers with a label, and a
  // label is not a key: both are resolved once, here, and never again.
  group: string;
  // Set only where the group does not exist yet: what it will be called.
  groupLabel: string;
  // A type the tenant already holds under this name, which is used as it is.
  existing: string | null;
};

// Every ending that is not a proposal. One shape, so none of them can be the
// one that forgets to offer a way out.
const STOPPED: Record<string, { title: string; body: string }> = {
  "unreadable": {
    title: "That file could not be read",
    body: "It carries no text we can read — a scan, most likely."
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
      + " is nothing to do with your file — try again in a few"
      + " minutes.",
  },
  "failed": {
    title: "It stopped before finishing",
    body: "Something went wrong while reading it. Nothing was saved.",
  },
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
  const [skipped, setSkipped] = useState<Set<number>>(new Set());
  const [facts, setFacts] = useState<Record<string, FactChoice>>({});
  const [types, setTypes] = useState<Record<string, TypeChoice>>({});
  // Accepting is a sequence of writes. Whatever it managed before it stopped
  // is IN the draft, so the person is told what landed.
  const [written, setWritten] = useState<string[]>([]);

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
    setBusy("Uploading your report");
    try {
      const { key } = await api.proposeFromFile(file);
      setBusy("");
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
      };

      polling.current = window.setInterval(async () => {
        try {
          const p = await api.proposal(key);
          setProposal(p);

          if (p.status === "ready" || STOPPED[p.status]) {
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
   * Turn what the reader found into what the person ticks.
   *
   * Facts are collapsed by name across sections. A memorandum naming Total
   * Assets in three sections is naming one fact three times, and creating
   * three fields would leave two of them empty for ever.
   */
  function prepare(p: Proposal) {
    setMemoLabel(p.memorandum_label || "My memorandum");
    setSkipped(new Set());

    const known = new Set((draft?.fields ?? []).map((f) => f.key));
    const collected: Record<string, FactChoice> = {};

    p.sections.forEach((section, index) => {
      (section.facts ?? []).forEach((f: ProposedFact) => {
        const id = (f.label || "").trim().toLowerCase();
        if (!id) return;

        if (collected[id]) {
          if (!collected[id].sections.includes(index)) {
            collected[id].sections.push(index);
          }
          return;
        }

        collected[id] = {
          label: f.label,
          description: f.description || "",
          shape: f.shape === "table" ? "group" : "one",
          columns: f.columns ?? [],
          existing: f.matches_existing && known.has(f.matches_existing)
            ? f.matches_existing : null,
          documents: f.found_in ?? [],
          sections: [index],
          chosen: false,
        };
      });
    });
    setFacts(collected);

    const heldTypes = draft?.document_types ?? [];
    const gathered: Record<string, TypeChoice> = {};
    for (const t of p.document_types ?? []) {
      const id = (t.label || "").trim().toLowerCase();
      if (!id || gathered[id]) continue;
      const existing = (t.existing_key
          && heldTypes.some((h) => h.key === t.existing_key)
          ? t.existing_key : null)
        ?? heldTypes.find((h) => h.label.trim().toLowerCase() === id)?.key
        ?? null;
      // The reader answers with a group by name. Match it to one the tenant
      // already holds, by key or by label; only where neither matches is a
      // new group made.
      const named = (t.group || "").trim();
      const match = (draft?.categories ?? []).find(
        (c) => c.key === named
          || c.label.toLowerCase() === named.toLowerCase());
      const fallback = draft?.categories[0];

      gathered[id] = {
        label: t.label,
        description: t.description || "",
        group: match ? match.key
          : (named ? slugKey(named) : (fallback?.key ?? "")),
        groupLabel: match || !named ? "" : named,
        existing,
      };
    }
    setTypes(gathered);
  }

  // --- accepting ----------------------------------------------------------

  /** Taken: ticked, and named by at least one section that is kept. A fact
   *  bound to nothing would be extracted on every filing and read by no
   *  one. */
  const live = (f: FactChoice) =>
    f.chosen && f.sections.some((i) => !skipped.has(i));

  /** A document type is wanted only where a taken new fact is looked for in
   *  it. */
  const needed = (label: string) => {
    const l = label.trim().toLowerCase();
    return Object.values(facts).some((f) => live(f) && !f.existing
      && f.documents.some((x) => x.trim().toLowerCase() === l));
  };

  /** Every document type the person will hold once this is accepted, by the
   *  label the reader used. found_in names labels, not keys. */
  const typeKeyByLabel = useMemo(() => {
    const map: Record<string, string> = {};
    for (const t of draft?.document_types ?? []) {
      map[t.label.trim().toLowerCase()] = t.key;
    }
    for (const t of Object.values(types)) {
      map[t.label.trim().toLowerCase()] = t.existing ?? slugKey(t.label);
    }
    return map;
  }, [draft, types]);

  /** One key per section, unique within the memorandum. Two sections titled
   *  the same slug to the same key, and the second would silently overwrite
   *  the first. */
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

  /**
   * Write the first cut into the draft, through the same calls a person
   * authoring by hand would make, and open the editor on it.
   *
   * The order is not a preference. Binding a section to a field that does not
   * exist yet is refused - deliberately, because a section bound to a missing
   * field reports facts as absent when they were extracted. So: groups,
   * document types, facts, where each is found, the memorandum, its sections,
   * and only then what each section renders.
   */
  async function accept() {
    if (!proposal) return;
    setError("");
    setWritten([]);
    const done: string[] = [];

    try {
      const groups = new Set((draft?.categories ?? []).map((c) => c.key));
      const wantedTypes = Object.values(types)
        .filter((t) => !t.existing && needed(t.label));

      for (const t of wantedTypes) {
        if (!t.groupLabel || groups.has(t.group)) continue;
        setBusy("Adding the group " + t.groupLabel);
        await api.saveCategory({ key: t.group, label: t.groupLabel });
        groups.add(t.group);
        done.push("group " + t.groupLabel);
      }

      for (const t of wantedTypes) {
        setBusy("Adding the document type " + t.label);
        await api.saveDocumentType({
          key: slugKey(t.label),
          label: t.label,
          description: t.description,
          category: t.group,
          read_mode: "text",
          always_ocr: false,
        });
        done.push("document type " + t.label);
      }

      const newFacts = Object.values(facts)
        .filter((f) => live(f) && !f.existing);

      for (const f of newFacts) {
        // A table with no columns holds nothing; written as a single fact
        // instead, and made a table in the editor if it should be one.
        const columns = f.columns.filter((c) => c.trim());
        const table = f.shape === "group" && columns.length > 0;
        setBusy("Adding the fact " + f.label);
        await api.saveField({
          key: fieldKey(f.label),
          label: f.label,
          type: "text",
          cardinality: table ? "group" : "one",
          description: f.description,
          // No column key. A column's identity is the group's key and a
          // suffix, and the editor mints it that way when none is given.
          columns: table
            ? columns.map((c) => ({ label: c.trim(), type: "text",
                                    description: "" }))
            : [],
        } as never);
        done.push("fact " + f.label);
      }

      for (const f of newFacts) {
        const documents = Array.from(new Set(f.documents
          .map((label) => typeKeyByLabel[label.trim().toLowerCase()])
          .filter((k): k is string => Boolean(k))));
        if (documents.length === 0) continue;
        setBusy("Where to find " + f.label);
        await api.setFieldDocuments(fieldKey(f.label), documents);
      }

      setBusy("Adding the memorandum");
      const made = await api.saveTemplate({ label: memoLabel.trim() });
      const templateKey = made.key as string;
      done.push("memorandum " + memoLabel.trim());

      const included = proposal.sections
        .map((s, i) => ({ s, i }))
        .filter(({ i }) => !skipped.has(i));

      let order = 0;
      for (const { s, i } of included) {
        order += 1;
        setBusy("Adding the section " + s.title);
        await api.saveSection({
          key: sectionKeys[i],
          numeral: s.numeral || "",
          title: s.title,
          kind: "extract",
          template_key: templateKey,
          // Sent, not left to default: sections left at zero tie, and the
          // memorandum comes out in whatever order the database returns.
          sort_order: order,
        } as never);
        done.push("section " + s.title);
      }

      for (const { s, i } of included) {
        // Deduplicated: two of the report's names can land on one field, and
        // a section binding the same field twice is refused.
        const keys = Array.from(new Set(Object.values(facts)
          .filter((f) => live(f) && f.sections.includes(i))
          .map((f) => f.existing ?? fieldKey(f.label))));
        if (keys.length === 0) continue;
        setBusy("Binding " + s.title);
        await api.setSectionFields(templateKey, sectionKeys[i], keys);
      }

      setBusy("");
      onDone(templateKey);
    } catch (e) {
      // Stay on the screen, with what was written named: it is in the draft.
      setBusy("");
      setWritten(done);
      setError(message(e));
    }
  }

  // --- the screen ---------------------------------------------------------

  if (!proposal) {
    return (
      <div>
        <h2>Create your own from a report</h2>
        <p className="muted">
          Give us a report you already write. We read its shape &mdash; its
          sections, and the facts each one reports &mdash; and put a first cut
          to you. Accept it and it opens in the editor, where you correct it.
        </p>
        <p className="muted small">
          The file is read for its layout and then deleted. Nothing in it is
          filed, extracted from, or charged for. A short report is read in
          under a minute; a long one takes a few.
        </p>
        {error && <p className="error">{error}</p>}

        {/* Held until the draft has loaded. Without it we do not know what
            facts the tenant holds, and nothing the reader proposes could be
            matched to one. */}
        <label className="row">
          <span>Your report</span>
          <input type="file" accept=".pdf,.docx" disabled={!!busy || !draft}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) send(file);
            }} />
        </label>
        <p className="muted small">
          {draft ? "PDF or Word." : "Loading your configuration…"}
        </p>
        {busy && <Working what={busy} />}
      </div>
    );
  }

  const ending = STOPPED[proposal.status];
  if (ending) {
    return (
      <div>
        <h2>{ending.title}</h2>
        <p className="muted">{ending.body}</p>
        {proposal.reason && (
          <p className="muted small">Recorded: {proposal.reason}</p>
        )}
        <div className="form-actions">
          <button onClick={() => { setProposal(null); setError(""); }}>
            Try another report
          </button>
        </div>
      </div>
    );
  }

  if (proposal.status !== "ready") {
    const total = proposal.sections_total;
    return (
      <div>
        <h2>Reading your report</h2>
        {!error && (
          <Working what={total
            ? `Reading your report — section ${proposal.sections_done} of ${total}`
            : "Reading your report — finding the sections"} />
        )}
        {proposal.memorandum_label && (
          <p className="muted small">
            It reads as a {proposal.memorandum_label}.
          </p>
        )}
        <ul className="muted small">
          {proposal.sections.map((s, i) => (
            <li key={i}>
              {s.title}
              {" · "}{s.facts.length}{" "}
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
            </div>
          </>
        )}
      </div>
    );
  }

  const factList = Object.entries(facts);
  const keptCount = proposal.sections.length - skipped.size;
  const taken = factList.filter(([, f]) => live(f));
  const newCount = taken.filter(([, f]) => !f.existing).length;
  const heldCount = taken.length - newCount;
  const typeCount = Object.values(types)
    .filter((t) => !t.existing && needed(t.label)).length;

  return (
    <div>
      <h2>A first cut from your report</h2>
      <p className="muted">
        Keep the sections you want and tick the facts each should carry.
        Accept writes this into your draft and opens it in the editor, where
        everything can be corrected. Nothing reaches a report until you
        publish.
      </p>
      {error && <p className="error">{error}</p>}
      {written.length > 0 && (
        <div className="revision-note">
          <strong>It stopped part way.</strong>
          <p className="muted small">
            What is listed below is already in your draft. Accepting again
            writes the same things under the same names and finishes the rest.
          </p>
          <ul className="muted small">
            {written.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}
      {busy && <Working what={busy} />}

      <h3>The memorandum</h3>
      <label className="row">
        <span>Name</span>
        <input value={memoLabel}
               onChange={(e) => setMemoLabel(e.target.value)} />
      </label>

      <h3>Sections</h3>
      <p className="muted small">
        In the order they appear in your report. Untick a section to leave it
        out. A fact named in two sections is the same tick in both.
      </p>

      {proposal.sections.map((s, i) => {
        const kept = !skipped.has(i);
        const here = factList
          .filter(([, f]) => f.sections.includes(i))
          .sort((a, b) => a[1].label.localeCompare(b[1].label));
        const ticked = here.filter(([, f]) => f.chosen).length;
        return (
          <div className="review" key={i}>
            <div className="review-head">
              <label>
                <input type="checkbox" checked={kept}
                  onChange={() => {
                    const next = new Set(skipped);
                    if (next.has(i)) next.delete(i); else next.add(i);
                    setSkipped(next);
                  }} />
                <strong>{s.title}</strong>
              </label>
              <span className="muted small">
                {ticked} of {here.length} {here.length === 1 ? "fact" : "facts"}
              </span>
            </div>
            {s.purpose && <p className="why">{s.purpose}</p>}
            {!s.located && (
              <p className="why warn">
                We could not find this heading again in the text, so it was
                read against the whole report. Worth checking.
              </p>
            )}
            {kept && here.map(([fid, f]) => (
              <label className="bind" key={fid}>
                <input type="checkbox" checked={f.chosen}
                  onChange={(e) => setFacts({
                    ...facts, [fid]: { ...f, chosen: e.target.checked } })} />
                {f.label}
                {f.existing && (
                  <span className="muted small">&middot; you hold this</span>
                )}
              </label>
            ))}
          </div>
        );
      })}

      <h3>Accept</h3>
      <p className="muted small">
        Writes a memorandum with {keptCount}{" "}
        {keptCount === 1 ? "section" : "sections"}, {newCount} new{" "}
        {newCount === 1 ? "fact" : "facts"} and {typeCount} new document{" "}
        {typeCount === 1 ? "type" : "types"}, using {heldCount}{" "}
        {heldCount === 1 ? "fact" : "facts"} you already hold, and opens it in
        the editor.
      </p>
      <p className="muted small">
        Worth doing before you upload any documents. A fact added afterwards is
        empty on everything already filed.
      </p>

      <div className="form-actions">
        <button disabled={!!busy || !memoLabel.trim() || keptCount === 0}
                onClick={accept}>
          Accept and open in the editor
        </button>
        <a className="secondary" onClick={onCancel}>Cancel</a>
      </div>
    </div>
  );
}
