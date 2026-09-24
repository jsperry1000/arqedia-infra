import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  chargeKey,
  statusOf,
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
import { BALANCE, UpgradePrompt } from "./upgrade";

/* stored() is gone (17.4).
 *
 * It copied the server's _clean - whitespace to a dash, anything else unsafe
 * dropped - so that a name this screen was waiting for matched the row that
 * arrived. Two implementations of the rule that decides where a file is
 * kept, agreeing character for character and one edit away from not, which
 * is exactly how 17.3 arrived. POST /uploads answers with the name it stored
 * the file under, and the row carries that same name because the normalizer
 * reads it off the key - so there is nothing left to compute here.
 */

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
  // NULL UNTIL THE READ ANSWERS, and null again if it failed (18.12). An
  // empty array now MEANS something - this workspace has no memorandum, so
  // generating is impossible and the screen says so - and [] as a starting
  // value would say that for the moment before the read lands, and for ever
  // if it never did. A failure is not an assertion about what is published.
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [template, setTemplate] = useState("");
  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // Show archived, for the memo list (14.3). Off by default, so the list is
  // what is in play; on, the archived lines join it marked, and can be
  // restored from where they left. The engagements list carries its own.
  const [showArchived, setShowArchived] = useState(false);

  // Why the engagement could not be read, where it could not. Distinct from
  // `error`, which is a refusal of something somebody just did and belongs
  // beside the controls; this one means there is nothing to show controls
  // for, and replaces the screen.
  const [loadFailed, setLoadFailed] =
    useState<{ status: number; said: string } | null>(null);

  // The company these memoranda are about (SUBJ-01). Null until somebody
  // names one, which is every engagement opened before migration 031.
  // Nothing is filed without it, because extraction reads a document for
  // the SUBJECT's facts and cannot tell which company that is unless it is
  // told - so this screen holds File and says why, rather than letting the
  // server refuse a click it could have prevented.
  const [subject, setSubject] = useState<string | null>(null);
  const [subjectDraft, setSubjectDraft] = useState("");
  const [editingSubject, setEditingSubject] = useState(false);
  const [subjectSaid, setSubjectSaid] = useState("");

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
  // Which groups of the filed list are open. A SET, NOT ONE KEY (21.4): each
  // opens and closes on its own and opening one never closes another, as on
  // the configuration screens. None on arrival.
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set());

  // The pending list's own search, order and filter (21.3). What is SHOWN
  // only: they never change what is ticked, and never what File sends - File
  // still files every row waiting, hidden or not.
  const [pendingSearch, setPendingSearch] = useState("");
  const [pendingSort, setPendingSort] =
    useState<"upload" | "name" | "type" | "confidence">("upload");
  const [needsLook, setNeedsLook] = useState(false);
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

  // 8.2 - a FILED document being deleted, with the facts read out of it. The
  // detail is fetched first, because the confirmation states what deleting
  // reaches - how many memoranda cite it, whether a charge paid for it - and
  // those are the server's counts rather than anything this screen knows.
  const [deleting, setDeleting] = useState<DocumentDetail | null>(null);
  const [typedName, setTypedName] = useState("");

  /** Read the engagement, or say why not.
   *
   *  IT USED TO SAY NOTHING. The three reads answer 404 for a name with no
   *  row (13.3 stage 4), and this function is called from an effect that
   *  does not hold its promise - so a 404 rejected into nobody's hands, not
   *  one of the setState calls below ran, and the screen rendered its
   *  initial state: no documents, no memoranda, no subject and an empty
   *  error line. An engagement that does not exist looked exactly like an
   *  empty one that does.
   *
   *  The failure is kept rather than thrown on, because every other caller
   *  of refresh() - after an upload, a removal, a filing - is in the middle
   *  of something and must not have an exception land in it. */
  async function refresh() {
    let p, d, m;
    try {
      [p, d, m] = await Promise.all([
        api.pending(id), api.documents(id), api.memos(id, showArchived),
      ]);
    } catch (err) {
      setLoadFailed({ status: statusOf(err), said: reason(err) });
      return;
    }
    setLoadFailed(null);

    setPending(p.pending);
    setDocs(d.documents);
    setMemos(m.memos);
    setSubject(p.subject_name);

    // A sent file is seen once a row it produced is on screen.
    setExpected((e) => {
      if (!e) return e;
      // Compared as they are. Both sides are the server's: the name came
      // back from POST /uploads and the row's filename was read off the key
      // the same call built (17.4).
      const rows = [...p.pending, ...d.documents];
      const left = e.names.filter((n) => !rows.some(
        (r) => !e.known.has(r.document_id) && r.filename === n));
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

  // Which memoranda this tenant can write, and which one is about to be
  // written. The first is preselected, so the choice is always made and never
  // has to be made twice.
  //
  // SHOWN WHETHER THERE IS A CHOICE OR NOT (18.6). It used to appear only
  // where there was more than one, on the reasoning that one needs no
  // choosing - which is true of choosing and false of knowing. A person
  // about to spend on a memorandum was told how many documents it would draw
  // on and what it would cost, and not what it was going to be. With one
  // template the control says what will be written; with several it also
  // changes it.
  useEffect(() => {
    api.templates().then((r) => {
      setTemplates(r.templates);
      if (r.templates.length > 0) setTemplate(r.templates[0].key);
    // Left null rather than emptied. It was setTemplates([]), which under
    // 18.6's gate drew nothing and was harmless; under 18.12's it would tell
    // a person their workspace has no memorandum because a request failed.
    }).catch(() => undefined);
  }, []);
  // Reloads when the tick changes, because the archived rows were never sent
  // and there is nothing on the screen to filter.
  useEffect(() => { refresh(); }, [id, showArchived]);

  // A document being read by OCR is still in flight. Generating now would
  // produce a memo missing whatever it is about to say.
  const reading = docs.filter((d) => d.state === "reading").length
    + pending.filter((p) => p.state === "reading").length;
  const unfiled = toFile.length;
  // WHAT IS STILL BEING WORKED ON, and nothing else. Three conditions were
  // missing and each one kept the screen asking about something no process
  // would ever finish: a document set aside is not waiting on anything, and
  // one that failed extraction is not waiting either - it has its answer.
  // 51 rows from 5 September said "Extracting from 51 filed documents" every
  // morning for a fortnight because of it.
  const extracting = docs.filter(
    (d) => d.active && d.state === "filed"
      && !d.extracted_at && !d.extraction_error).length;
  const waitingFiles = expected?.names.length ?? 0;
  const blocked = busy !== "" || reading > 0 || unfiled > 0
    || generating !== null;

  // No memorandum published, so the press would be refused (18.12). Only
  // where the read answered - null is "we have not been told", and a screen
  // must not disable the one act this page exists for on a failed request.
  const nothingToWrite = templates !== null && templates.length === 0;

  /** The directory picker's own element (18.7).
   *
   *  `webkitdirectory` is a real attribute on every browser this product
   *  supports and is absent from React's InputHTMLAttributes, so setting it
   *  in JSX needs either a cast at the call site or a global declaration.
   *  Set on the node instead: one effect, no type surgery, and nothing about
   *  the rest of the codebase has to learn a new attribute. */
  const folderInput = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    const el = folderInput.current;
    if (!el) return;
    el.setAttribute("webkitdirectory", "");
    el.setAttribute("directory", "");
  }, []);

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

    // Where the files actually went. The server cleans the engagement name
    // for the key, so a screen opened under a name it cleaned - an old link,
    // a pasted address - is watching an engagement nothing is being written
    // to (17.3). It says so and moves, rather than polling for ever.
    let landedIn = id;

    for (let i = 0; i < list.length; i++) {
      setBusy(`Uploading ${i + 1} of ${list.length} \u2014 ${list[i].name}`);
      try {
        // BOTH NAMES COME BACK (17.4). The engagement decides which screen
        // this is, and the filename is what the row will carry - neither is
        // worked out here any more.
        const put = await api.upload(id, list[i]);
        landedIn = put.engagement || id;
        setExpected((e) => ({ names: [...(e?.names ?? []), put.filename],
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

    // The screen follows the files. Nothing is lost either way - the rows
    // exist under the stored name whatever this screen does - but staying
    // here would show an empty list and call it "analysing".
    if (landedIn && landedIn !== id) {
      navigate(`/engagements/${encodeURIComponent(landedIn)}`, { replace: true });
      return;
    }

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

  /** Open the confirmation for a filed document, having first asked the
   *  server what deleting it would reach (8.2). */
  async function askDelete(documentId: number) {
    setError("");
    setBusy("Reading what this would reach");
    try {
      setTypedName("");
      setDeleting(await api.documentValues(documentId));
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy("");
    }
  }

  /** Delete a filed document. The server does the work in one transaction;
   *  this only reports it. */
  async function deleteFiled() {
    if (!deleting) return;
    const doomed = deleting;
    setDeleting(null);
    setBusy(`Deleting ${doomed.filename}`);
    setError("");
    setRemoveSaid("");
    try {
      await api.removeDocument(doomed.document_id);
      setRemoveSaid(
        `${doomed.filename} deleted, with ${doomed.values.length} `
        + `${doomed.values.length === 1 ? "fact" : "facts"} read from it.`
        + (doomed.memos
          ? ` ${doomed.memos} ${doomed.memos === 1 ? "memorandum" : "memoranda"}`
            + " still cite it and are unchanged."
          : ""));
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy("");
      refresh();
    }
  }

  /** Name the subject, or change it.
   *
   *  The server resolves or creates the engagement row by name, so this is
   *  the same call whether the engagement has one already or not.
   *
   *  A CHANGE REACHES ONLY WHAT IS GENERATED AFTERWARDS. Values already
   *  extracted were read under the old subject and stay as they are;
   *  re-extracting is a separate act and is charged. Said on screen rather
   *  than left to be discovered. */
  async function saveSubject() {
    const wanted = subjectDraft.trim();
    if (!wanted || busy) return;
    const was = subject;
    setBusy("Saving the subject");
    setError("");
    setSubjectSaid("");
    try {
      const saved = await api.setSubject(id, wanted);
      setSubject(saved.subject_name);
      setEditingSubject(false);
      setSubjectSaid(
        was && was !== saved.subject_name
          ? `Subject changed from ${was} to ${saved.subject_name}. `
            + "Memoranda generated from now on say so; facts already read "
            + "were read under the old one and are unchanged."
          : "");
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy("");
      refresh();
    }
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

  /** A document whose extraction failed and which read nothing at all.
   *
   *  It has no bearing on any memorandum. Composition reads documents only
   *  through extracted_value - the JOIN is FROM extracted_value, never from
   *  document - so a row with no values contributes no fact, no source and
   *  no citation whether it is in use or not. Including it and excluding it
   *  produce the same memorandum.
   *
   *  So the tick is ABSENT rather than disabled or unticked. Unticking it
   *  would write active = 0 and say a person made a judgement they never
   *  made; disabling it would invite them to work out why, and there is no
   *  answer they could act on. Nothing is written for these rows at all. */
  const nothingToInclude = (d: Doc) =>
    !!d.extraction_error && d.values === 0;

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

  /** The pending list as shown (21.3). A batch of fifty-seven, across
   *  fourteen types, took a quarter of an hour to categorise on dev with no
   *  way to find a row but scrolling.
   *
   *  THE TYPE IS THE ONE IN THE DROPDOWN - the person's choice where they
   *  made one, the proposal where they did not - because that is what the row
   *  says and what File will send.
   *
   *  Everything here narrows or orders what is SHOWN. The ticks live in
   *  `picked` and File sends `toFile`, and neither reads this. */
  const typeOf = (p: Pending) =>
    (choices[p.document_id] ?? { type: p.proposed_type }).type;
  const typeLabel = (key: string | null) => key
    ? (types.find((t) => t.key === key)?.label ?? key) : "Not classified";
  // Unclassified, or proposed with low confidence: the rows worth a second
  // look before paying to file them.
  const doubtful = (p: Pending) => !typeOf(p) || p.confidence === "low";
  // Least certain first. No confidence at all is a scan nothing was read
  // from, which is the least certain of all.
  const rank = (p: Pending) =>
    ({ low: 1, medium: 2, high: 3 } as Record<string, number>)[
      p.confidence ?? ""] ?? 0;

  const pendingNeedle = pendingSearch.trim().toLowerCase();
  const shownToFile = toFile
    .filter((p) => (!needsLook || doubtful(p)) && (!pendingNeedle
      || [p.filename, p.source_folder ?? "", typeLabel(typeOf(p))]
           .some((s) => s.toLowerCase().includes(pendingNeedle))))
    .sort((a, b) =>
      pendingSort === "name" ? a.filename.localeCompare(b.filename)
      : pendingSort === "type"
        ? typeLabel(typeOf(a)).localeCompare(typeLabel(typeOf(b)))
          || a.filename.localeCompare(b.filename)
      : pendingSort === "confidence"
        ? rank(a) - rank(b) || a.filename.localeCompare(b.filename)
      : a.document_id - b.document_id);

  // How many of each type, over the whole batch rather than what the search
  // leaves, so the count does not move as somebody types. Largest first.
  const perType = Object.entries(toFile.reduce<Record<string, number>>(
    (acc, p) => {
      const label = typeLabel(typeOf(p));
      acc[label] = (acc[label] ?? 0) + 1;
      return acc;
    }, {}))
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  // Ticked and out of sight. Said, so a Remove selected that reaches rows
  // the search is hiding is never a surprise.
  const shownIds = new Set(shownToFile.map((p) => p.document_id));
  const hiddenPicked = pickedIn(toFile)
    .filter((p) => !shownIds.has(p.document_id)).length;

  function arrow(key: SortKey) {
    if (key !== sortKey) return "";
    return sortDown ? " \u2193" : " \u2191";
  }

  // Filed and Memos start closed. Fifty documents and a list of memoranda
  // push the thing a person came here to do - upload, and file what came
  // back - off the bottom of the screen.
  const [shut, setShut] = useState<Set<string>>(new Set(["filed", "memos"]));

  /** MEMOS OPENS THE MOMENT A MEMORANDUM CAN BE WRITTEN (18.8).
   *
   *  Generate lives inside this part, and the part started shut - so a person
   *  who had just paid to file eighteen documents was shown an upload box, a
   *  "Filed" heading and a "Memos" heading, and NO GENERATE BUTTON at all.
   *  The collapse is right for the Filed list, which is fifty rows nobody
   *  asked for; it was wrong for the one control the whole journey aims at.
   *
   *  THE CONDITION IS THE BUTTON'S OWN. It opens exactly when Generate would
   *  be pressable - documents in use and nothing in flight - so the two
   *  cannot drift into saying different things about the same moment. Filed
   *  is untouched and still starts shut.
   *
   *  ONCE. The ref is set when it opens, so a person who shuts Memos again
   *  keeps it shut through every poll that follows. Somebody who arrives with
   *  work already in flight gets it on the first tick that clears, rather
   *  than never - which is why this watches rather than seeding useState,
   *  where neither count is known yet. */
  const openedMemos = useRef(false);
  useEffect(() => {
    if (openedMemos.current || activeCount === 0 || blocked) return;
    openedMemos.current = true;
    setShut((prev) => {
      if (!prev.has("memos")) return prev;
      const next = new Set(prev);
      next.delete("memos");
      return next;
    });
  }, [activeCount, blocked]);
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

  // NOTHING TO SHOW, AND SAYING SO. A 404 means the name in the address is
  // not an engagement: a typo, an old link, one deleted. Anything else -
  // a refusal, a network failure - is shown as itself. Either way this
  // replaces the screen rather than sitting above an empty one, because
  // every control below would be operating on nothing.
  //
  // The way out is the list. Back would work too, but somebody who arrived
  // by pasting an address has nowhere behind them.
  if (loadFailed) {
    return (
      <div>
        <h2>{id}</h2>
        <p className="error">
          {loadFailed.status === 404
            ? `There is no engagement called ${id}.`
            : loadFailed.said}
        </p>
        <p><a onClick={() => navigate("/")}>Back to Engagements</a></p>
      </div>
    );
  }

  return (
    <div>
      <h2>{id}</h2>

      {/* The subject, above the upload control and above everything else
          (SUBJ-01). It is here rather than in a drawer because a person
          uploading into an engagement with no subject must not have to go
          looking for the reason nothing will file. Composed from the
          classes this screen already uses - no new CSS. */}
      <div className="review">
        <div className="review-head">
          <strong>Subject</strong>
          {subject && !editingSubject && <span>{subject}</span>}
          {!editingSubject && (
            <button className="secondary" disabled={!!busy}
                    onClick={() => {
                      setSubjectDraft(subject ?? "");
                      setSubjectSaid("");
                      setEditingSubject(true);
                    }}
                    title={subject
                      ? "Change the company these memoranda are about."
                      : "Name the company these memoranda are about."}>
              {subject ? "Change" : "Name the subject"}
            </button>
          )}
        </div>

        {editingSubject && (
          <div className="filters" style={{ marginTop: 10, marginBottom: 0 }}>
            <input autoFocus value={subjectDraft}
                   placeholder="The company these memoranda are about"
                   maxLength={255}
                   onChange={(e) => setSubjectDraft(e.target.value)}
                   onKeyDown={(e) => {
                     if (e.key === "Enter") saveSubject();
                     if (e.key === "Escape") setEditingSubject(false);
                   }} />
            <button disabled={!!busy || subjectDraft.trim() === ""}
                    onClick={saveSubject}>Save</button>
            <a className="secondary small"
               onClick={() => setEditingSubject(false)}>Cancel</a>
          </div>
        )}

        {!subject && (
          <p className="why warn">
            This engagement has no subject, so nothing in it can be filed.
            Every document is read for the subject's facts &mdash; a buyer,
            supplier, lender or inspector named in the same file is not the
            subject &mdash; and nothing here says which company that is.
          </p>
        )}

        {subject && !editingSubject && (
          <p className="why">
            Written differently in a document &mdash; with or without a legal
            suffix, abbreviated, or in full &mdash; it is still the subject.
            Every other company in the file is not.
          </p>
        )}

        {subjectSaid && <p className="why warn">{subjectSaid}</p>}
      </div>

      <input type="file" multiple onChange={(e) => upload(e.target.files)} />
      {/* A WHOLE FOLDER, AND THE FOLDER IS RECORDED (18.7). A second input
          rather than webkitdirectory on the one above, because that attribute
          makes an input directory-ONLY: a person with three files to send
          would have to put them in a folder first.

          THE FOLDER IS ONLY KNOWN FROM HERE. webkitRelativePath is populated
          by the directory picker and by nothing else - an ordinary pick, and
          a drag-and-drop, both give "" - so this control is what makes
          document.source_folder ever hold a value. Uploading is otherwise
          identical: the same upload(), the same charge, the same review.

          webkitdirectory is not in React's HTML types. It is set through a
          ref, which is the way that does not require declaring a global
          attribute this codebase uses nowhere else. */}
      <label className="inline-check" style={{ marginTop: 8 }}>
        <span className="muted small">or a whole folder:</span>
        <input type="file" multiple ref={folderInput}
               onChange={(e) => upload(e.target.files)} />
      </label>
      <p className="muted small">
        A folder upload records which folder each file came out of, and shows
        it beside the file. It is provenance only: it is never read when
        proposing what a document is.
      </p>
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
          {/* AN EMPTY TYPE DROPDOWN SAYS WHY IT IS EMPTY (18.8).
              With no configuration the list offers "Not classified" and
              nothing else, and the server then refuses the filing with
              "Choose a type for x.pdf before filing" - an instruction that
              cannot be obeyed, because there is no type to choose and the
              screen never says where types come from.

              ONCE, ABOVE THE LIST, rather than beside each dropdown. It is
              one fact about the workspace, not about any document; repeated
              under twenty rows it is noise, and noise teaches people to stop
              reading. Nothing new in CSS - .why warn, which this block uses
              for the scan warning already. */}
          {types.length === 0 && (
            <p className="why warn">
              No document types yet. They come with a memorandum &mdash;
              Template Catalogue.
            </p>
          )}
          {/* What the batch is made of, and a way through it (21.3). The
              same .filters row and .inline-check the Filed list and the
              template choice already use: no new CSS. */}
          <p className="muted small">
            {perType.map(([label, n]) => `${label} ${n}`).join(" · ")}
          </p>
          <div className="filters">
            <input placeholder="Search by name, folder or type"
                   value={pendingSearch}
                   onChange={(e) => setPendingSearch(e.target.value)} />
            {pendingSearch && (
              <a className="small" onClick={() => setPendingSearch("")}>Clear</a>
            )}
            <label className="inline-check">
              Sort
              <select value={pendingSort}
                      onChange={(e) => setPendingSort(
                        e.target.value as typeof pendingSort)}>
                <option value="upload">Upload order</option>
                <option value="name">Name</option>
                <option value="type">Type</option>
                <option value="confidence">Confidence, least sure first</option>
              </select>
            </label>
            <label className="inline-check"
                   title="Not classified, or proposed with low confidence.">
              <input type="checkbox" checked={needsLook}
                     onChange={(e) => setNeedsLook(e.target.checked)} />
              Needs a look &middot; {toFile.filter(doubtful).length}
            </label>
            <span className="muted">
              {shownToFile.length} of {toFile.length} shown
            </span>
          </div>
          {/* Select all is over the whole batch, as it always was: the
              search narrows what is shown and never what is ticked. */}
          <div className="filters">
            {allBox(toFile, "of these")}
            {hiddenPicked > 0 && (
              <span className="muted small">
                {hiddenPicked} ticked and hidden by the search
              </span>
            )}
          </div>
          {shownToFile.length === 0 && (
            <p className="muted">
              Nothing waiting matches. Filing still files all {toFile.length}.
            </p>
          )}
          {shownToFile.map((p) => {
            const choice = choices[p.document_id] ??
              { type: p.proposed_type, include: true };
            const chosen = types.find((t) => t.key === choice.type);
            return (
              <div className="review" key={p.document_id}>
                <div className="review-head">
                  {pickBox(p)}
                  <strong>{p.filename}</strong>
                  {/* WHERE IT CAME FROM (18.7). Beside the name, because that
                      is what it qualifies: four cards reading "Accounts.pdf"
                      are told apart by the folder and by nothing else on the
                      row. Absent on an ordinary upload, and nothing is drawn
                      then - "no folder" is not a fact worth a line. */}
                  {p.source_folder && (
                    <span className="muted small"
                          title="The folder this file came out of. Recorded
                                 and shown; never read when proposing what the
                                 document is.">
                      {p.source_folder}
                    </span>
                  )}
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

                {/* WHAT THE PROPOSAL WAS MADE FROM (18.7/18.13). A person
                    overriding a type is usually doing it because the name
                    told them something, so they are owed the knowledge that
                    the name was read - and that the folder was not.

                    ONLY WHERE THERE IS A PROPOSAL. A scan arrives with no
                    type because nothing was read from it, and telling
                    somebody what a reading weighed when there was no reading
                    would be untrue. Its own sentence is below. */}
                {p.proposed_type && (
                  <p className="why">
                    Proposed from what the document says and its file name,
                    weighed together. Not from its folder.
                  </p>
                )}

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

          {/* The way out used to be prose - "Top up under Settings, Account
              management" - which asks a person to go and find a screen while
              holding a proposal they cannot file. It is a control now, as the
              generate drawer's already was (11.1), and it lands on Balance
              rather than on whichever tab Account happens to open. */}
          {fileQuote && !fileQuote.affordable && (
            <UpgradePrompt tone="warn" action="Top up" to={BALANCE}>
              {fileQuote.affordable_count === 0
                ? "There is not enough balance to file any of these. Nothing "
                + "has been charged, and the proposal keeps until there is."
                : `There is enough for ${fileQuote.affordable_count} of `
                + `${fileQuote.quantity}. Set the rest aside, or top up and `
                + "file them together."}
            </UpgradePrompt>
          )}

          {/* Held for want of a subject, and it says so rather than going
              quiet. The server refuses this call above the charge in any
              case; this is so a person is told before the click instead of
              after it, which is what the money gate above already does. */}
          <button onClick={fileAll}
                  disabled={!!busy || toFile.length === 0 || !subject
                            || (fileQuote ? !fileQuote.affordable : false)}
                  title={subject ? undefined
                    : "Name the subject of this engagement first."}>
            {!subject
              ? "Name the subject to file"
              : `File ${toFile.length} `
                + `${toFile.length === 1 ? "document" : "documents"}`
                + (fileQuote ? ` \u00b7 ${money(fileQuote.total_cents)}` : "")}
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
                {/* Deleting a filed document, with the facts read out of it
                    (8.2). Its own column, at the far end, away from the tick
                    that means in use. */}
                <th></th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => {
                // A filter opens every group it matched. Clearing it returns
                // to the groups that were open, which it never wrote to.
                const open = nameFilter.trim() !== "" || openGroups.has(g.key);
                return (
              <Fragment key={g.key}>
                <tr>
                  <td colSpan={7}>
                    <a onClick={() => setOpenGroups((prev) => {
                      const next = new Set(prev);
                      if (next.has(g.key)) next.delete(g.key);
                      else next.add(g.key);
                      return next;
                    })}>
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
                    {/* No tick where there is nothing to include. Every other
                        row keeps the one it has always had, and so does the
                        column: this is the absence of a control on the rows
                        it means nothing for, not a change to what it does. */}
                    {nothingToInclude(d)
                      ? (
                        <span className="muted"
                              title="Nothing was read from this document, so
                                     including it or leaving it out makes no
                                     difference to any memorandum.">
                          {"—"}
                        </span>
                      )
                      : (
                        <input
                          type="checkbox"
                          checked={d.active}
                          onChange={() => toggleActive(d)}
                          title={d.active
                            ? "In use. Uncheck to leave it out of the next memo."
                            : "Set aside" + (d.deactivated_by
                              ? " by " + d.deactivated_by : "")}
                        />
                      )}
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
                    {/* Three answers, not two. A document that failed
                        extraction says so AND shows what it did read: a
                        failure part way through leaves real facts behind it,
                        and hiding them behind "extracting..." was how fifteen
                        extracted values looked like none at all. */}
                    {d.extraction_error
                      ? (
                        <>
                          <span className="warn">extraction failed</span>{" "}
                          <a onClick={() => openValues(d.document_id)}>
                            {d.values}
                          </a>
                        </>
                      )
                      : d.state === "reading" || !d.extracted_at
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
                  <td>
                    {/* Set aside is the ordinary act and lives in the tick at
                        the other end of the row. This one does not come
                        back (8.2). */}
                    <a className="danger small"
                       onClick={() => { if (!busy) askDelete(d.document_id); }}
                       title="Delete this document and everything read from it">
                      Delete
                    </a>
                  </td>
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

      {/* WHAT IS ABOUT TO BE WRITTEN, ALWAYS (18.6). The gate was
          templates.length > 1, so a tenant with the one memorandum most of
          them have saw the count of documents and the price and no name for
          the thing they were buying. The control is the same either way,
          which is also what makes it read the same way on the day a second
          template is published.

          The sentence beside it is not. "The same documents, read a
          different way" is an answer to a choice, and with one template
          there is no choice for it to answer - it would be explaining an
          alternative that does not exist. Composed from .filters and
          .inline-check, as it already was: no new CSS. */}
      {/* NOTHING PUBLISHED, SO NOTHING TO GENERATE (18.12). The same
          sentence the server refuses with, said before the click rather than
          after it - and in place of the strip, because a memorandum chooser
          with nothing in it is not a thing to draw. Reached by signing up and
          leaving Get started without ticking anything, which is allowed: the
          base brings the facts and the document types, and which memoranda a
          tenant holds is their own choice.

          .revision-note with a .form-actions inside it, which is what
          UpgradePrompt is made of and what the subject block above already
          composes from. No new CSS. */}
      {templates !== null && templates.length === 0 && (
        <div className="revision-note">
          <span className="warn">
            This workspace has no published memorandum, so there is nothing to
            generate. Take one under Template Catalogue and publish it.
          </span>
          <div className="form-actions">
            <button onClick={() => navigate("/catalogue")}>
              Template Catalogue
            </button>
          </div>
        </div>
      )}

      {templates !== null && templates.length > 0 && (
        <div className="filters">
          <label className="inline-check">
            Write
            {/* NOT disabled where there is one. A disabled select greys, and
                grey says NOT AVAILABLE where what is meant is THIS IS THE
                ONE - the value is the answer, and it has to read at full
                strength. A select holding a single option is inert enough
                on its own. */}
            <select value={template}
                    onChange={(e) => setTemplate(e.target.value)}
                    title={templates.length === 1
                      ? "The only memorandum published. Configure is where "
                        + "another is added."
                      : "Which memorandum to write from these documents."}>
              {templates.map((t) => (
                <option key={t.key} value={t.key}>{t.label}</option>
              ))}
            </select>
          </label>
          {templates.length > 1 && (
            <span className="muted small">
              The same documents, read a different way. Each memorandum is
              charged separately.
            </span>
          )}
        </div>
      )}

      {/* The last "go and find a screen" sentence on this page. The Generate
          button beneath is disabled for want of money, so the only thing to
          do here is the one thing this now offers. */}
      {memoQuote && !memoQuote.affordable && activeCount > 0 && (
        <UpgradePrompt tone="warn" action="Top up" to={BALANCE}>
          A memorandum costs {money(memoQuote.total_cents)} and{" "}
          {money(memoQuote.available_cents)} is available. Nothing has been
          charged.
        </UpgradePrompt>
      )}

      {/* Generating costs money, so it is asked for twice (4.1). This press
          opens the confirmation; the charge happens on the one inside it.
          Filing has shown its cost before the click since the wallet was
          built - this is that, for the other act that spends. */}
      <button onClick={() => setConfirming(true)}
              disabled={blocked || activeCount === 0 || nothingToWrite
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

      {/* The tick, above the list it changes (14.3). */}
      <label className="inline-check">
        <input type="checkbox" checked={showArchived}
               onChange={(e) => setShowArchived(e.target.checked)} />
        Show archived
      </label>

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
              {/* Marked, never mixed in unannounced. */}
              <td className="muted small">
                {m.state === "archived" ? "Archived" : ""}
              </td>
              <td>
                {/* THE WHOLE REVISION LINE moves, which is why this says the
                    memorandum rather than this row: 9.1 and 9.2 go together,
                    because they are one document. Nothing is deleted - the
                    text, its sources and its claims stay, and the memo still
                    opens from a link.

                    An <a className="small">, the same low-key row action
                    "Set it aside" uses on a filed document, rather than a
                    button: a full-strength button on every row of a list
                    shouts, and the classes it would need are declared only
                    inside .memo-head and five other parents. No new CSS. */}
                <a className="small"
                   title={m.state === "archived"
                     ? "Bring this memorandum and its revisions back."
                     : "Put this memorandum and its revisions away. "
                       + "Nothing is deleted."}
                   onClick={async (e) => {
                     e.stopPropagation();
                     if (busy) return;
                     setError("");
                     setBusy(m.state === "archived"
                       ? `Restoring memo ${m.label}`
                       : `Archiving memo ${m.label}`);
                     try {
                       await api.setMemoState(
                         m.memo_id,
                         m.state === "archived" ? "live" : "archived");
                     } catch (err) {
                       setError(reason(err));
                     }
                     setBusy("");
                     refresh();
                   }}>
                  {m.state === "archived" ? "Restore" : "Archive"}
                </a>
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

              {/* THE NAME OF WHAT IS BEING BOUGHT, whether there was a
                  choice or not (18.6). This is the last sentence before the
                  press that spends, and it named the memorandum only where
                  there was more than one - so the tenant with a single
                  template read the count and the price and never the thing
                  itself. */}
              <p className="muted small">
                {activeCount} {activeCount === 1 ? "document" : "documents"} in
                use{template
                  ? `, written as ${templates?.find((t) => t.key === template)
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
                  // Was /account, which opens on Subscription - so the one
                  // control on the screen that says "Top up" landed a person
                  // on the plan table instead of the balance. The tab is in
                  // the address now (11.1).
                  <button onClick={() => navigate(BALANCE)}>
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

      {/* Deleting a filed document (8.2). The heaviest thing this product
          lets a tenant do to their own work, so it is asked for with the
          name typed, as deleting a whole memorandum is - and it says all
          four of the things that are true, including the one nobody
          expects about the ledger. */}
      {deleting && (
        <div className="panel-backdrop" onClick={() => setDeleting(null)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}
               onKeyDown={(e) => { if (e.key === "Escape") setDeleting(null); }}>
            <a className="panel-close"
               onClick={() => setDeleting(null)}>Close</a>
            <div className="form">
              <h4>Delete {deleting.filename}</h4>

              <p className="muted small">
                This deletes the document, everything read from it &mdash;{" "}
                {deleting.values.length}{" "}
                {deleting.values.length === 1 ? "fact" : "facts"} &mdash; and
                its file. <strong>It cannot be undone.</strong>
              </p>

              {deleting.memos > 0 ? (
                <p className="why warn">
                  {deleting.memos}{" "}
                  {deleting.memos === 1 ? "memorandum cites" : "memoranda cite"}{" "}
                  it. They are not changed and their text stands, but the
                  citations to this document will no longer open and it will
                  show in their sources as removed.
                </p>
              ) : (
                <p className="muted small">
                  No memorandum cites it.
                </p>
              )}

              {deleting.charged && (
                <p className="muted small">
                  You were charged for filing it. That charge stays on the
                  ledger and is not refunded &mdash; and once this is done,
                  nothing connects that line to the document it paid for.
                </p>
              )}

              <p className="muted small">
                A clean memorandum means generating a new one, which is
                charged.
              </p>

              <label className="row">
                <span>Type {deleting.filename} to confirm</span>
                <input value={typedName} autoFocus
                       onChange={(e) => setTypedName(e.target.value)} />
              </label>

              <div className="form-actions">
                <button disabled={!!busy || typedName.trim() !== deleting.filename}
                        onClick={deleteFiled}>
                  Delete this document
                </button>
                <a className="secondary"
                   onClick={() => setDeleting(null)}>Cancel</a>
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
