import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  chargeKey,
  type Pending,
  type DocType,
  type Decision,
  type Doc,
  type MemoRef,
  type DocumentDetail,
  type Passage,
  type Template,
  type Quote,
} from "./api";
import { useNavigate } from "react-router-dom";
import { useBackAction, Working } from "./shell";

/** The name a file is stored under: the API's _clean, whitespace to a dash
 *  and anything else unsafe dropped. Compared on both sides, so a row whose
 *  filename was or was not cleaned still matches the file that was sent. */
function stored(name: string) {
  return (name || "").trim()
    .replace(/\s+/g, "-")
    .replace(/[^A-Za-z0-9._-]/g, "")
    .replace(/-{2,}/g, "-")
    .replace(/^[-.]+|[-.]+$/g, "")
    .slice(0, 120);
}

function money(cents: number) {
  return "$" + (cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// How long nothing may change before the screen stops asking. A step that
// died - a read that never came back - would otherwise be polled for ever.
const WAIT_CEILING_MS = 10 * 60 * 1000;

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
  useBackAction(onBack);
  // Where a top-up is offered from, because the way out of "not enough
  // balance" is Account management and nothing else on this screen.
  const navigate = useNavigate();
  const [pending, setPending] = useState<Pending[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [memos, setMemos] = useState<MemoRef[]>([]);
  const [types, setTypes] = useState<DocType[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [template, setTemplate] = useState("");
  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // What filing this proposal would cost, and what the memo would.
  //
  // FETCHED, NOT CALCULATED. Multiplying a count by a price the screen
  // happens to know is how a client and a server come to disagree about a
  // bill. The server prices it; the screen shows what came back.
  const [fileQuote, setFileQuote] = useState<Quote | null>(null);
  const [memoQuote, setMemoQuote] = useState<Quote | null>(null);

  // Files sent and not yet seen as a row. The row exists only once the file
  // has been read, so between an upload finishing and its row appearing the
  // screen had nothing unfinished to watch, and stopped. Known ids are the
  // rows that were there before, so a file sent again under a name already
  // on screen still waits for its own row.
  const [expected, setExpected] = useState<
    { names: string[]; known: Set<number> } | null>(null);
  // A memo asked for and not yet listed: how many memos there were when it
  // was asked for.
  const [generating, setGenerating] = useState<{ before: number } | null>(null);
  // Set once nothing has changed for the ceiling, so polling stops.
  const [gaveUp, setGaveUp] = useState(false);

  const [sortKey, setSortKey] = useState<SortKey>("filename");
  const [sortDown, setSortDown] = useState(false);
  const [nameFilter, setNameFilter] = useState("");
  const [showInactive, setShowInactive] = useState(true);
  // Which group of the filed list is open. One at a time and none on arrival,
  // as on the configuration screens.
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [passage, setPassage] = useState<Passage | null>(null);
  const [bounds, setBounds] = useState<[number, number]>([1, 1]);
  // The confirmation between pressing Generate and spending anything (4.1).
  const [confirming, setConfirming] = useState(false);

  // 8.1 - which of the pre-filing documents are ticked, the confirmation
  // before they go, what the last removal did, and why any of them stayed.
  // Only the two blocks above the filed table carry ticks: the filed table's
  // tick means in use, which is not destructive and must not be confused
  // with this one.
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [removing, setRemoving] = useState(false);
  const [removeSaid, setRemoveSaid] = useState("");
  const [removeWhy, setRemoveWhy] = useState<Record<number, string>>({});

  async function refresh() {
    const [p, d, m] = await Promise.all([
      api.pending(id), api.documents(id), api.memos(id),
    ]);
    setPending(p.pending);
    setDocs(d.documents);
    setMemos(m.memos);

    // A sent file is seen once a row it produced is on screen.
    setExpected((e) => {
      if (!e) return e;
      const rows = [...p.pending, ...d.documents];
      const left = e.names.filter((n) => !rows.some(
        (r) => !e.known.has(r.document_id) && stored(r.filename) === n));
      return left.length ? { ...e, names: left } : null;
    });
    // A memo asked for is ready once the list has grown.
    setGenerating((g) => g && m.memos.length > g.before ? null : g);

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

  // A document nobody could read is not fileable, and this screen must not
  // offer it as though it were. It arrives on the pending list deliberately -
  // the row is what stops the screen waiting for a file it will never see
  // (decision record, 18 September, item 1) - but it belongs in a block of its
  // own, out of the count, out of the quote, and out of what File sends.
  const refused = pending.filter((p) => p.state === "unreadable");
  const toFile = pending.filter((p) => p.state !== "unreadable");

  /** What may be ticked. A document being read has a Textract job in flight
   *  that would write back to a row no longer there, so the server refuses
   *  it - the tick is withheld for the same reason the row's own Remove is
   *  disabled today, rather than offered and then refused. */
  const selectable = (p: Pending) => p.state !== "reading";

  const pickedIn = (list: Pending[]) =>
    list.filter((p) => selectable(p) && picked.has(p.document_id));

  /** Tick or untick a whole block. Checked where every document in it that
   *  CAN go is ticked; part-way where some are. */
  const allBox = (list: Pending[], label: string) => {
    const may = list.filter(selectable);
    const chosen = pickedIn(list);
    const all = may.length > 0 && chosen.length === may.length;
    return (
      <label className="inline-check">
        <input type="checkbox" checked={all} disabled={may.length === 0}
               ref={(el) => {
                 if (el) el.indeterminate = !all && chosen.length > 0;
               }}
               onChange={() => setPicked((prev) => {
                 const next = new Set(prev);
                 may.forEach((p) => {
                   if (all) next.delete(p.document_id);
                   else next.add(p.document_id);
                 });
                 return next;
               })} />
        {all ? `All ${may.length} ${label} selected`
             : `Select all ${may.length} ${label}`}
      </label>
    );
  };

  /** One document's tick. */
  const pickBox = (p: Pending) => (
    <input type="checkbox" checked={picked.has(p.document_id)}
           disabled={!selectable(p) || !!busy}
           title={selectable(p)
             ? "Select for removal"
             : "Being read. It cannot be removed until that finishes."}
           onChange={() => setPicked((prev) => {
             const next = new Set(prev);
             if (next.has(p.document_id)) next.delete(p.document_id);
             else next.add(p.document_id);
             return next;
           })} />
  );

  const pickedAll = [...refused, ...toFile]
    .filter((p) => selectable(p) && picked.has(p.document_id));

  useEffect(() => { api.documentTypes().then((r) => setTypes(r.types)); }, []);

  // Re-priced whenever the proposal changes and after anything is charged, so
  // the figure on screen is never one charge out of date.
  useEffect(() => {
    if (toFile.length === 0) { setFileQuote(null); return; }
    api.walletQuote("document_filed", toFile.length)
      .then(setFileQuote).catch(() => setFileQuote(null));
  }, [toFile.length, docs.length, memos.length]);

  useEffect(() => {
    api.walletQuote("memo_generated", 1)
      .then(setMemoQuote).catch(() => setMemoQuote(null));
  }, [docs.length, memos.length, pending.length]);

  // Which memoranda this tenant can write. One is the ordinary case and needs
  // no choosing; the selector appears only when there is a choice to make.
  useEffect(() => {
    api.templates().then((r) => {
      setTemplates(r.templates);
      if (r.templates.length > 0) setTemplate(r.templates[0].key);
    }).catch(() => setTemplates([]));
  }, []);
  useEffect(() => { refresh(); }, [id]);

  // A document being read by OCR is still in flight. Generating now would
  // produce a memo missing whatever it is about to say.
  const reading = docs.filter((d) => d.state === "reading").length
    + pending.filter((p) => p.state === "reading").length;
  const unfiled = toFile.length;
  const extracting = docs.filter(
    (d) => d.state === "filed" && !d.extracted_at).length;
  const waitingFiles = expected?.names.length ?? 0;
  const blocked = busy !== "" || reading > 0 || unfiled > 0
    || generating !== null;

  // The screen updates itself (UX-11). It asks while any row is unfinished -
  // a file not yet read, a scan being read, a document being extracted, a
  // memo being written - and stops once every row has reached a state that
  // nothing further will change. A document waiting to be filed is finished
  // as far as the machine goes: it waits on a person.
  const unfinished = busy !== "" || reading > 0 || extracting > 0
    || waitingFiles > 0 || generating !== null;

  // When what is unfinished last changed. Nothing changing for the ceiling
  // means a step died, and the screen says so rather than asking for ever.
  const signature = [busy, reading, extracting, waitingFiles,
                     generating ? generating.before : -1].join("|");
  const changedAt = useRef(Date.now());
  useEffect(() => { changedAt.current = Date.now(); }, [signature]);

  useEffect(() => {
    if (!unfinished || gaveUp) return;
    const timer = setInterval(() => {
      if (Date.now() - changedAt.current > WAIT_CEILING_MS) {
        setGaveUp(true);
        setExpected(null);
        setGenerating(null);
        return;
      }
      refresh();
    }, 5000);
    return () => clearInterval(timer);
  }, [id, unfinished, gaveUp]);

  // What is running, named, for the one indicator (UX-12).
  const plural = (n: number, one: string, many: string) =>
    `${n} ${n === 1 ? one : many}`;
  const working = busy
    || (gaveUp ? "" : generating
      ? "Generating a memo — this takes a minute or two"
      : waitingFiles > 0
        ? "Analysing " + plural(waitingFiles, "uploaded file", "uploaded files")
        : reading > 0
          ? "Reading " + plural(reading, "scanned document", "scanned documents")
          : extracting > 0
            ? "Extracting from " + plural(extracting, "filed document",
                                          "filed documents")
            : "");

  async function upload(files: FileList | null) {
    if (!files) return;
    const list = Array.from(files);
    setError("");
    setGaveUp(false);
    const known = new Set([...pending, ...docs].map((r) => r.document_id));

    for (let i = 0; i < list.length; i++) {
      setBusy(`Uploading ${i + 1} of ${list.length} \u2014 ${list[i].name}`);
      try {
        await api.upload(id, list[i]);
        const name = stored(list[i].name);
        setExpected((e) => ({ names: [...(e?.names ?? []), name],
                              known: e?.known ?? known }));
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

  // What the system actually read, page by page. The filename is not an
  // answer when four cards carry the same one, and a description written by a
  // model is a summary rather than the thing itself.
  async function view(p: Pending, unit: number) {
    setError("");
    setBounds([p.page_from ?? 1, p.page_to ?? p.pages ?? 1]);
    try {
      setPassage(await api.passage(p.document_id, unit));
    } catch (err) {
      setError(String((err as Error)?.message ?? err));
    }
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

  /** A refusal as the server wrote it, unwrapped from the {"error": "..."}
   *  it travels in. A removal refused for state answers with the state -
   *  "reading", "filed" - which is the reason, said in one word. */
  function reason(err: unknown) {
    const text = String((err as Error)?.message ?? err);
    try { return JSON.parse(text).error ?? text; } catch { return text; }
  }

  /**
   * Remove everything ticked, ONE AT A TIME (8.1).
   *
   * Not in parallel, and not in one call: each removal deletes objects from
   * two buckets and then a row, and parts of one uploaded file share that
   * file - the last part to go takes it. Serial is what keeps that count
   * honest, and it is what lets a failure in the middle be reported as a
   * failure of that document rather than of the batch.
   *
   * WHAT FAILS STAYS. A document that could not go keeps its row, its tick
   * and its reason, so the next press retries exactly those.
   */
  async function removePicked() {
    const chosen = pickedAll;
    setRemoving(false);
    if (chosen.length === 0) return;
    setError("");
    setRemoveSaid("");
    setRemoveWhy({});

    const failed: Record<number, string> = {};
    let done = 0;
    for (const p of chosen) {
      setBusy(`Removing ${done + Object.keys(failed).length + 1} of ${chosen.length}`);
      try {
        await api.removeDocument(p.document_id);
        done += 1;
      } catch (err) {
        failed[p.document_id] = reason(err);
      }
    }

    const left = Object.keys(failed).length;
    setRemoveSaid(
      `${done} of ${chosen.length} removed.`
      + (left ? ` ${left} could not be removed.` : ""));
    setRemoveWhy(failed);
    // Only what failed stays ticked; what went is gone from the list anyway.
    setPicked(new Set(Object.keys(failed).map(Number)));
    setChoices((prev) => {
      const next = { ...prev };
      chosen.forEach((p) => { if (!failed[p.document_id]) delete next[p.document_id]; });
      return next;
    });
    setBusy("");
    refresh();
  }

  async function fileAll() {
    const decisions: Decision[] = toFile.map((p) => ({
      document_id: p.document_id,
      document_type: choices[p.document_id]?.type ?? p.proposed_type,
      include: true,
    }));
    setBusy("Filing");
    setError("");
    setGaveUp(false);
    try {
      // One key for one click. A retry of this click is refused as a repeat;
      // filing again tomorrow is a different act and gets its own.
      await api.file(id, decisions, chargeKey());
      setChoices({});
    } catch (err) {
      setError(charged(err));
    } finally {
      setBusy("");
      refresh();
    }
  }

  /** A refusal for want of money, said as a sentence rather than as a status.
   *
   *  Nothing was debited: the charge rolls back before it refuses, so a
   *  person reading this has lost nothing and needs to be told so. */
  function charged(err: unknown) {
    const text = String((err as Error)?.message ?? err);
    try {
      const body = JSON.parse(text);
      if (body.needed_cents !== undefined) {
        return `${money(body.needed_cents)} needed and ${money(body.available_cents)} `
             + "available. Nothing was filed and nothing was charged. "
             + "Top up under Settings, Account management.";
      }
      return body.error ?? text;
    } catch { return text; }
  }

  async function toggleActive(d: Doc) {
    // Optimistic: the row flips at once, and refresh confirms it.
    setDocs((prev) => prev.map((x) =>
      x.document_id === d.document_id ? { ...x, active: !x.active } : x));
    await api.setActive(d.document_id, !d.active);
    refresh();
  }

  // Generating starts the memo and returns. The memo appears in the list when
  // it is written, found by polling rather than by a fixed wait.
  async function generate() {
    setBusy("Starting a memo");
    setError("");
    try {
      await api.generate(id, template || undefined, chargeKey());
      setGaveUp(false);
      setGenerating({ before: memos.length });
      setShut((prev) => {
        const next = new Set(prev);
        next.delete("memos");
        return next;
      });
    } catch (err) {
      setError(charged(err));
    } finally {
      setBusy("");
    }
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

  /** The filed list under the groups its document types sit in - the same
   *  division the configuration screens and the type selector above use.
   *
   *  A filed row names its type, and nothing in api.ts says whether that is
   *  the type's key or its label, so it is matched on the key first and the
   *  label second rather than on a guess.
   *
   *  A type the type list no longer carries is not dropped: its documents sit
   *  under a heading of their own, since a document filed under a retired
   *  type is exactly the one worth noticing. Groups keep the order of the
   *  type list; rows inside a group keep the order the sort chose.
   *
   *  Counts on a heading are over every document in the group, whatever the
   *  filter shows, and "in use" means what it means in the bar above. */
  const groups = useMemo(() => {
    const RETIRED = "\u0000retired";
    const NONE = "\u0000none";
    const groupOf = (d: Doc) => {
      if (!d.document_type) return NONE;
      const t = types.find((x) => x.key === d.document_type)
        ?? types.find((x) => x.label === d.document_type);
      return t ? t.category : RETIRED;
    };

    const order: string[] = [];
    for (const t of types) {
      if (!order.includes(t.category)) order.push(t.category);
    }
    order.push(RETIRED, NONE);

    return order
      .map((key) => {
        const all = docs.filter((d) => groupOf(d) === key);
        return {
          key,
          label: key === RETIRED ? "Not among the current document types"
            : key === NONE ? "Unclassified"
            : key,
          rows: visible.filter((d) => groupOf(d) === key),
          total: all.length,
          inUse: all.filter((d) => d.active && d.state === "filed").length,
        };
      })
      .filter((g) => g.rows.length > 0);
  }, [docs, visible, types]);

  // The filename and the value count both open what was read.
  const openValues = (documentId: number) =>
    api.documentValues(documentId).then(setDetail);

  const byCategory = types.reduce<Record<string, DocType[]>>((acc, t) => {
    (acc[t.category] ||= []).push(t);
    return acc;
  }, {});

  function arrow(key: SortKey) {
    if (key !== sortKey) return "";
    return sortDown ? " \u2193" : " \u2191";
  }

  // Filed and Memos start closed. Fifty documents and a list of memoranda
  // push the thing a person came here to do - upload, and file what came
  // back - off the bottom of the screen.
  const [shut, setShut] = useState<Set<string>>(new Set(["filed", "memos"]));
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

  return (
    <div>
      <h2>{id}</h2>

      <input type="file" multiple onChange={(e) => upload(e.target.files)} />
      {working && <Working what={working} />}
      {gaveUp && !busy && (
        <p className="muted small">
          Nothing has changed for ten minutes, so this screen has stopped
          checking. Reload to check again.
        </p>
      )}
      {error && <p className="error">{error}</p>}

      {/* First, because it is the thing needing a decision. A refusal is
          terminal: nothing further will happen to these on its own, and the
          only move is to remove them and upload something readable. Said
          before the fileable ones so it is not lost under a list of twenty. */}
      {/* What is ticked, across both blocks above the filed table, and the
          one control that acts on it (8.1). Shown only once something is
          ticked: an empty toolbar on a screen with nothing selected is a
          control looking for a purpose. */}
      {(refused.length > 0 || toFile.length > 0) && (
        <div className="filters">
          <button className="secondary" disabled={!!busy || pickedAll.length === 0}
                  onClick={() => setRemoving(true)}>
            Remove selected{pickedAll.length ? ` · ${pickedAll.length}` : ""}
          </button>
          {pickedAll.length > 0 && (
            <a className="small" onClick={() => setPicked(new Set())}>
              Clear the selection
            </a>
          )}
          {removeSaid && <span className="muted small">{removeSaid}</span>}
        </div>
      )}

      {refused.length > 0 && (
        <>
          <h3>Could not be read</h3>
          <div className="filters">{allBox(refused, "of these")}</div>
          {refused.map((p) => (
            <div className="review" key={p.document_id}>
              <div className="review-head">
                {pickBox(p)}
                <strong>{p.filename}</strong>
                <span className="muted">
                  {p.pages ? `${p.pages} pages` : "—"}
                </span>
                {/* Nothing was read, so there is nothing to View. The
                    original is the only thing there is to look at, and a
                    person deciding whether to remove it needs to see it. */}
                <button className="secondary" disabled={!!busy}
                        onClick={() => view(p, 1)}
                        title="Open the file itself. Nothing was read from it.">
                  Open the file
                </button>
                <button className="secondary" disabled={!!busy}
                        onClick={() => remove(p)}
                        title="Remove it. The file and its row both go.">
                  Remove
                </button>
              </div>
              <p className="why warn">{p.refusal_reason}</p>
              {removeWhy[p.document_id] && (
                <p className="why warn">
                  Not removed: {removeWhy[p.document_id]}
                </p>
              )}
            </div>
          ))}
          <p className="muted small">
            Nothing was charged for {refused.length === 1 ? "this" : "these"}.
          </p>
        </>
      )}

      {toFile.length > 0 && (
        <>
          <h3>Ready to file</h3>
          <div className="filters">{allBox(toFile, "of these")}</div>
          {toFile.map((p) => {
            const choice = choices[p.document_id] ??
              { type: p.proposed_type, include: true };
            const chosen = types.find((t) => t.key === choice.type);
            return (
              <div className="review" key={p.document_id}>
                <div className="review-head">
                  {pickBox(p)}
                  <strong>{p.filename}</strong>
                  <span className="muted">
                    {p.page_from
                      ? `pages ${p.page_from}\u2013${p.page_to}`
                      : `${p.pages ?? "?"} pages`}
                  </span>
                  {/* A scan has a row and no text: "View" would open an
                      empty panel. The original is what a person needs to see
                      to choose its type, and the panel links to it. */}
                  <button
                    className="secondary"
                    disabled={p.state === "reading"}
                    onClick={() => view(p, p.page_from ?? 1)}
                    title={p.thin_text && !p.proposed_type
                      ? "Open the file itself. Nothing has been read from it yet."
                      : "Read what the system read, before naming it."}
                  >
                    {p.thin_text && !p.proposed_type ? "Open the file" : "View"}
                  </button>
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
                {removeWhy[p.document_id] && (
                  <p className="why warn">
                    Not removed: {removeWhy[p.document_id]}
                  </p>
                )}
              </div>
            );
          })}

          {/* What this costs, before the click that costs it. The wallet
              specification writes this block; it is reproduced rather than
              reinvented, because the figures have to reconcile with a ledger
              line a person may read months later. */}
          {fileQuote && (
            <div className="quote">
              <div>
                <span>{fileQuote.quantity}{" "}
                  {fileQuote.quantity === 1 ? "document" : "documents"} proposed</span>
                <b>{money(fileQuote.total_cents)}</b>
              </div>
              <div>
                <span>Available</span>
                <b>{money(fileQuote.available_cents)}</b>
              </div>
              {!fileQuote.affordable && (
                <div className="short">
                  <span>Fileable now</span>
                  <b>{fileQuote.affordable_count}</b>
                </div>
              )}
            </div>
          )}

          {fileQuote && !fileQuote.affordable && (
            <p className="why warn">
              {fileQuote.affordable_count === 0
                ? "There is not enough balance to file any of these. Nothing "
                + "has been charged, and the proposal keeps until there is."
                : `There is enough for ${fileQuote.affordable_count} of `
                + `${fileQuote.quantity}. Set the rest aside, or top up and `
                + "file them together."}{" "}
              Top up under Settings, Account management.
            </p>
          )}

          <button onClick={fileAll}
                  disabled={!!busy || toFile.length === 0
                            || (fileQuote ? !fileQuote.affordable : false)}>
            File {toFile.length}{" "}
            {toFile.length === 1 ? "document" : "documents"}
            {fileQuote ? ` \u00b7 ${money(fileQuote.total_cents)}` : ""}
          </button>
        </>
      )}

      {part("filed", "Filed",
            `${docs.length} ${docs.length === 1 ? "document" : "documents"}`)}

      {!shut.has("filed") && docs.length === 0 && (
        <p className="muted">Nothing filed yet.</p>
      )}

      {!shut.has("filed") && docs.length > 0 && (
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
              {groups.map((g) => {
                // A filter opens every group it matched.
                const open = nameFilter.trim() !== "" || openGroup === g.key;
                return (
              <Fragment key={g.key}>
                <tr>
                  <td colSpan={6}>
                    <a onClick={() =>
                      setOpenGroup(openGroup === g.key ? null : g.key)}>
                      {open ? "\u25be" : "\u25b8"} {g.label}
                    </a>{" "}
                    <span className="muted small">
                      {g.inUse} of {g.total} in use
                    </span>
                  </td>
                </tr>
                {open && g.rows.map((d) => (
                <tr key={d.document_id} className={d.active ? "" : "aside"}>
                  <td>
                    <input
                      type="checkbox"
                      checked={d.active}
                      onChange={() => toggleActive(d)}
                      title={d.active
                        ? "In use. Uncheck to leave it out of the next memo."
                        : "Set aside" + (d.deactivated_by
                          ? " by " + d.deactivated_by : "")}
                    />
                  </td>
                  <td>
                    <a onClick={() => openValues(d.document_id)}>
                      {d.filename}
                    </a>
                  </td>
                  <td className="muted">
                    {d.state === "reading"
                      ? (
                        <>
                          <span className="warn">reading&hellip;</span>
                          {/* A way out. A read can stall - a scan whose OCR
                              never came back - and until this the only remedy
                              was a SQL statement, which a client cannot
                              write. Setting aside keeps the row and its file;
                              it says only that this one is not to be used. */}
                          {d.active && (
                            <div>
                              <a className="small"
                                 onClick={() => toggleActive(d)}>
                                Taking too long? Set it aside
                              </a>
                            </div>
                          )}
                        </>
                      )
                      : (d.document_type ?? "unclassified")}
                  </td>
                  <td className="muted">
                    {d.state === "reading" || !d.extracted_at
                      ? <span className="warn">extracting&hellip;</span>
                      : (
                        // Zero opens too: the drawer lists what was looked
                        // for and not found.
                        <a onClick={() => openValues(d.document_id)}>
                          {d.values}
                        </a>
                      )}
                  </td>
                  <td className="muted">{(d.filed_at ?? "").slice(0, 16)}</td>
                  <td className="muted">{d.uploaded_by ?? "\u2014"}</td>
                </tr>
                ))}
              </Fragment>
                );
              })}
            </tbody>
          </table>
        </>
      )}

      {part("memos", "Memos",
            `${memos.length} ${memos.length === 1 ? "memo" : "memos"}`)}

      {!shut.has("memos") && (<>

      {templates.length > 1 && (
        <div className="filters">
          <label className="inline-check">
            Write
            <select value={template}
                    onChange={(e) => setTemplate(e.target.value)}>
              {templates.map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </select>
          </label>
          <span className="muted small">
            The same documents, read a different way. Each memorandum is
            charged separately.
          </span>
        </div>
      )}

      {memoQuote && !memoQuote.affordable && activeCount > 0 && (
        <p className="why warn">
          A memorandum costs {money(memoQuote.total_cents)} and{" "}
          {money(memoQuote.available_cents)} is available. Nothing has been
          charged. Top up under Settings, Account management.
        </p>
      )}

      {/* Generating costs money, so it is asked for twice (4.1). This press
          opens the confirmation; the charge happens on the one inside it.
          Filing has shown its cost before the click since the wallet was
          built - this is that, for the other act that spends. */}
      <button onClick={() => setConfirming(true)}
              disabled={blocked || activeCount === 0
                        || (memoQuote ? !memoQuote.affordable : false)}>
        {reading > 0
          ? `Wait \u2014 reading ${reading} ${reading === 1 ? "document" : "documents"}`
          : unfiled > 0
            ? `Wait \u2014 ${unfiled} to file`
            : busy || generating
              ? "Wait\u2026"
              : `Generate memo from ${activeCount} `
                + `${activeCount === 1 ? "document" : "documents"}`
                + (memoQuote ? ` \u00b7 ${money(memoQuote.total_cents)}` : "")}
      </button>

      <table>
        <tbody>
          {memos.map((m) => (
            <tr key={m.memo_id} onClick={() => onMemo(m.memo_id)}>
              <td><a>Memo {m.label}</a></td>
              {/* The name the memo was written under, which the API carries
                  on the row. Renaming a memorandum does not rename memoranda
                  already written. */}
              <td className="muted small">{m.template_label}</td>
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

      </>)}

      {/* The second press, and the only one that spends (4.1).
          EVERY FIGURE COMES FROM THE QUOTE the server priced - the same
          /wallet/quote the filing block above uses - so the screen never
          states a price of its own. The block is the filing block: the
          figures have to reconcile with a ledger line somebody may read
          months later, and two shapes for one kind of number is how they
          stop reconciling. */}
      {confirming && (
        <div className="panel-backdrop" onClick={() => setConfirming(false)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}
               onKeyDown={(e) => { if (e.key === "Escape") setConfirming(false); }}>
            <a className="panel-close"
               onClick={() => setConfirming(false)}>Close</a>
            <div className="form">
              <h4>Generate a memorandum</h4>

              <p className="muted small">
                {activeCount} {activeCount === 1 ? "document" : "documents"} in
                use{templates.length > 1 && template
                  ? `, written as ${templates.find((t) => t.key === template)
                      ?.label ?? template}` : ""}. One charge, whatever its
                length and however many documents it draws on.
              </p>

              {memoQuote && (
                <div className="quote">
                  <div>
                    <span>1 memorandum</span>
                    <b>{money(memoQuote.total_cents)}</b>
                  </div>
                  <div>
                    <span>Available</span>
                    <b>{money(memoQuote.available_cents)}</b>
                  </div>
                  {!memoQuote.affordable && (
                    <div className="short">
                      <span>Short by</span>
                      <b>{money(memoQuote.total_cents
                                - memoQuote.available_cents)}</b>
                    </div>
                  )}
                </div>
              )}

              {memoQuote && !memoQuote.affordable && (
                <p className="why warn">
                  There is not enough balance for this. Nothing has been
                  charged and nothing will be until there is.
                </p>
              )}

              {error && <p className="error">{error}</p>}

              <div className="form-actions">
                {/* Where the money does not reach, the button that spends is
                    not offered at all - the way out is a top-up, so that is
                    what is here instead. */}
                {memoQuote && !memoQuote.affordable ? (
                  <button onClick={() => navigate("/account")}>
                    Top up
                  </button>
                ) : (
                  <button disabled={blocked || activeCount === 0}
                          onClick={() => { setConfirming(false); generate(); }}>
                    Generate{memoQuote
                      ? ` · ${money(memoQuote.total_cents)}` : ""}
                  </button>
                )}
                <a className="secondary"
                   onClick={() => setConfirming(false)}>Cancel</a>
              </div>

              <p className="muted small">
                The charge is made when the memorandum is started, against the
                balance rather than the card. A repeat of this click is
                refused as a repeat rather than charged twice.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Removing is the one destructive act on this screen, so it is asked
          for twice and the second asking says what it reaches (8.1). The
          drawer is the one every delete uses. */}
      {removing && (
        <div className="panel-backdrop" onClick={() => setRemoving(false)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}
               onKeyDown={(e) => { if (e.key === "Escape") setRemoving(false); }}>
            <a className="panel-close"
               onClick={() => setRemoving(false)}>Close</a>
            <div className="form">
              <h4>
                Remove {pickedAll.length}{" "}
                {pickedAll.length === 1 ? "document" : "documents"}
              </h4>
              <p className="muted small">
                The file and everything read from it are deleted, and so is
                the row. <strong>It cannot be undone</strong> &mdash; there is
                no restoring a removed document, and uploading the file again
                starts it over as a new one.
              </p>
              <p className="muted small">
                Nothing has been filed or charged for, so nothing is refunded
                and no memorandum changes.
              </p>
              <div className="form-actions">
                <button onClick={removePicked} disabled={!!busy}>
                  Remove {pickedAll.length}{" "}
                  {pickedAll.length === 1 ? "document" : "documents"}
                </button>
                <a className="secondary"
                   onClick={() => setRemoving(false)}>Cancel</a>
              </div>
            </div>
          </div>
        </div>
      )}

      {detail && <ValuePanel detail={detail} onClose={() => setDetail(null)} />}

      {passage && (
        <PassagePanel
          passage={passage}
          bounds={bounds}
          onGo={(unit) => api.passage(passage.document_id, unit)
            .then(setPassage)}
          onClose={() => setPassage(null)}
        />
      )}
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

/** One page of a document, as it was read.

    Paging is held inside the part's own range. A part covering pages 21 to 30
    is a document in its own right to the person reading it, and letting the
    arrows wander into a neighbouring part would show them somebody else's
    document under this one's heading. */
function PassagePanel({ passage, bounds, onGo, onClose }: {
  passage: Passage;
  bounds: [number, number];
  onGo: (unit: number) => void;
  onClose: () => void;
}) {
  const [first, last] = bounds;
  const here = passage.unit ?? first;

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <aside className="panel" onClick={(e) => e.stopPropagation()}>
        <a onClick={onClose} className="panel-close">Close</a>
        <h3>{passage.filename}</h3>
        <p className="muted">
          {passage.unit_kind} {here}
          {passage.unit_label ? ` \u2014 ${passage.unit_label}` : ""}
          {first !== last ? ` of ${first}\u2013${last}` : ""}
        </p>

        <div className="filters">
          <button
            className="secondary"
            disabled={here <= first}
            onClick={() => onGo(here - 1)}
          >
            Previous
          </button>
          <button
            className="secondary"
            disabled={here >= last}
            onClick={() => onGo(here + 1)}
          >
            Next
          </button>
          <a href={passage.source_url} target="_blank" rel="noreferrer">
            Open the file
          </a>
        </div>

        {passage.text.trim()
          ? <pre className="passage">{passage.text}</pre>
          : (
            <p className="why warn">
              Nothing has been read from this file yet. Open it above to see
              what it is.
            </p>
          )}
      </aside>
    </div>
  );
}
