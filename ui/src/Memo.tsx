import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, chargeKey, statusOf, type Memo, type Passage, type Quote,
         type Rewrite, type UpdateRun } from "./api";
import { MemoDocument, type Ref } from "./MemoReader";
import { useBackAction, usePinTop, Working } from "./shell";
import { money, ShareSendPanel } from "./Share";
import { balanceFor } from "./upgrade";
import { ACT_SAID, diffStep, fitHistory, pushStep, restoreKeys, undoStep,
         type Act, type Step } from "./undo";

/**
 * Reading and revising a memo.
 *
 * Every citation names a file and a page. Clicking one opens the passage the
 * system actually read - not the original page image, which is a later piece
 * of work, but what was extracted from it. For checking an extraction that is
 * arguably the more useful thing: a wrong value is usually a misreading rather
 * than a misprint. The original document is one click further, downloadable.
 *
 * Editing produces a NEW memo, numbered 11.2, not an overwrite. The generated
 * memo keeps its machine evidence record; a revision is explicitly a human
 * document, signed by whoever edited it. Which of the two you are reading is
 * never ambiguous.
 *
 * Rewriting is the other way to revise. A person writes a prompt under any
 * section and presses Go; the model rewrites each such section and the answer
 * is shown beside what it replaces, to accept or discard. Nothing changes
 * until the accepted sections are saved as a revision, and that revision
 * records which sections the model wrote and at whose prompt.
 *
 * Editing happens in the document itself - an edit control on each block,
 * and the block opens where it sits. There is no second pane and no markdown
 * on screen: the stored form is storage, and a person revising a memorandum
 * should be looking at a memorandum.
 *
 * Reading, editing and rewriting all work on ONE working copy: the text as it
 * stands, the prompts typed, the rewrites accepted and the ones still out.
 * Leaving - Back, a reload, another memo - keeps it, on the server, and
 * coming back reopens it where it was. Only saving a revision or Discard
 * changes ends it.
 *
 * Update is the third way, offered on a memo a person has saved (16 October
 * 2026). Every section is written again from the configuration in use and the
 * documents filed now, and what is new comes back as rewrites do: beside the
 * section, to accept or discard. The saved text is never changed by it - an
 * accepted section is the saved one with additions set in - and a section new
 * in the template is offered whole, to go at the end. It costs what a
 * generation costs, so it is confirmed with the price first. It works on the
 * memo as saved, so it waits until unsaved changes are saved or discarded.
 *
 * Undo (UNDO-01, docs/specs/undo_01_design_2026-10-14.md) takes back the last
 * ten acts on the working copy, one at a time, and is kept with it, so it
 * survives a reload and a Discard. Saving ends it with the copy.
 */

// A section heading as composition writes it: "## II. Business". Level two
// only - composition's own rule, so the two cannot disagree about where a
// section starts.
const SECTION_HEADING = /^##(?!#)\s+\S/;

type Part = { key: string; heading: string; text: string };

/**
 * The text as a head and its sections, losslessly: joining them back gives
 * the text exactly as it was, so a section nobody touched is saved unchanged.
 *
 * A section is known by its heading. Where a heading repeats, its occurrence
 * number is part of the key, so two sections never share a prompt.
 */
function splitSections(markdown: string): {
  head: string; hasHead: boolean; sections: Part[];
} {
  const lines = markdown.split("\n");
  const starts: number[] = [];
  lines.forEach((line, i) => { if (SECTION_HEADING.test(line)) starts.push(i); });
  if (starts.length === 0) return { head: markdown, hasHead: true, sections: [] };

  const seen: Record<string, number> = {};
  const sections = starts.map((start, k) => {
    const end = k + 1 < starts.length ? starts[k + 1] : lines.length;
    const heading = lines[start].trim();
    seen[heading] = (seen[heading] ?? 0) + 1;
    return { key: seen[heading] > 1 ? heading + " #" + seen[heading] : heading,
             heading, text: lines.slice(start, end).join("\n") };
  });
  return { head: lines.slice(0, starts[0]).join("\n"), hasHead: starts[0] > 0,
           sections };
}

function joinSections(head: string, hasHead: boolean, sections: Part[]): string {
  return (hasHead ? [head] : []).concat(sections.map((s) => s.text)).join("\n");
}

/** The text with one section replaced. */
function replaceSection(markdown: string, key: string, text: string): string {
  const split = splitSections(markdown);
  return joinSections(split.head, split.hasHead, split.sections.map((s) =>
    s.key === key ? { ...s, text } : s));
}

// What composition calls a citation - the same pattern it masks with.
const CITATION = /\*[^*\n]+?\.(?:pdf|docx|xlsx|txt|json|xml)[^*\n]*?\*/g;

/** Citations present before a rewrite and absent after it. Counted by the
 *  server; named here, because a count does not tell a person what went. */
function lostCitations(before: string, after: string): string[] {
  const had = Array.from(new Set(before.match(CITATION) ?? []));
  return had.filter((c) => !after.includes(c));
}

/** What became of the charge for an Update that failed (UX02 20.1). Said by
 *  the run, which refunded or did not - never assumed here. */
/** The run's reason, closed as a sentence. Some end in a full stop ("Try it
 *  again.") and some do not ("the memorandum was not found"). */
function reasonSaid(error: string | undefined): string {
  const text = (error ?? "no reason was given").trim();
  return /[.!?]$/.test(text) ? text : text + ".";
}

function refundSaid(run: { refunded?: boolean; amount_cents?: number }): string {
  return run.refunded
    ? `The ${money(run.amount_cents ?? 0)} charged for it has been refunded `
      + "to your balance."
    : "The charge for it could not be refunded automatically.";
}

function errorText(err: unknown): string {
  let message = String((err as Error)?.message ?? err);
  try {
    message = JSON.parse(message).error ?? message;
  } catch { /* not JSON; show it as it came */ }
  return message;
}

type Result = Pick<Rewrite, "rewrite_id" | "status" | "error" | "output_text"
                           | "citations_dropped"> & Partial<Pick<Rewrite,
                           "source">>;

// An Update section new in the template is kept under its heading with this
// in front, so it can never share a key with a section already in the memo:
// those keys are headings, and a heading starts "##".
const ADDS = "+";

// Composition stops at fifteen minutes. Past seventeen, the update is not
// coming.
const UPDATE_GIVES_UP_MS = 17 * 60 * 1000;

// A rewrite out for one section: in flight, or finished and waiting to be
// accepted or discarded.
type Run = { id: number; result: Result | null };

// Editing is not a mode: every block carries its own control while reading.
// Rewriting is, because the whole document is laid out differently for it.
type Mode = "read" | "rewrite";

// How long typing pauses before the working copy is kept. Short enough that a
// reload loses a sentence at most; long enough not to write on every key.
const KEEP_AFTER_MS = 1500;

// The server refuses a kept copy over 4 MiB (_WORKING_MAX_BYTES), counting
// the address and time it wraps the copy in; this leaves room for those.
const WORKING_MAX_BYTES = 4 * 1024 * 1024;
const WORKING_WRAP_BYTES = 4096;

export function MemoView({ memoId, onBack, onOpen }: {
  memoId: number;
  onBack: () => void;
  onOpen: (memoId: number) => void;
}) {
  const [memo, setMemo] = useState<Memo | null>(null);
  const [passage, setPassage] = useState<Passage | null>(null);
  const [loadingRef, setLoadingRef] = useState(false);
  // Sharing opens from here, the memorandum's own head, rather than from a
  // list somewhere else asking which one (share-recipient).
  const [sharing, setSharing] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  // The working copy. Rewrite and Edit both read and write these.
  const [mode, setMode] = useState<Mode>("read");
  const [draft, setDraft] = useState("");
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  // Rewrites accepted, by section. Kept even when a hand edit renames the
  // section, so the revision still records every section the model wrote.
  const [acceptedBy, setAcceptedBy] = useState<Record<string, number[]>>({});
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [starting, setStarting] = useState(false);

  // Undo. The history is state for the screen and a ref for the acts, which
  // can come several to a render; so can the text they change.
  const [history, setHistory] = useState<Step[]>([]);
  const historyRef = useRef<Step[]>([]);
  const draftRef = useRef("");
  // Everything typed into one block between opening and closing it is one
  // edit. A session starts when a block opens and ends at any other act; an
  // edit in the session it began is folded into its step.
  const session = useRef(0);
  const lastEdit = useRef<{ session: number; base: string; step: Step } | null>(null);
  // The block open in each document on the screen: undo waits while any is.
  const openBlocks = useRef<Record<string, string | null>>({});
  const [blockOpen, setBlockOpen] = useState(false);

  function record(next: Step[]) {
    historyRef.current = next;
    setHistory(next);
  }

  // Update: the run still out, the confirmation before it is charged, and
  // what the last one to finish found.
  const navigate = useNavigate();
  const [updateRun, setUpdateRun] = useState<string | null>(null);
  const [confirmingUpdate, setConfirmingUpdate] = useState(false);
  const [updateQuote, setUpdateQuote] = useState<Quote | null>(null);
  const [startingUpdate, setStartingUpdate] = useState(false);
  const [updated, setUpdated] = useState<UpdateRun | null>(null);
  // Minted when the confirmation opens, so a retry of the same press is the
  // same charge and the next press is a new one.
  const updateKey = useRef("");

  const [loaded, setLoaded] = useState(false);
  const [keeping, setKeeping] = useState<"" | "keeping" | "kept" | "failed">("");

  // The memo's own head - Rewrite, Edit and the PDF while reading; Go, Save,
  // Edit and Close while revising - is held just under the site header, so a
  // person at the foot of a long memo does not scroll back to the top to act. The site header's height is measured,
  // not assumed: it changes with the width of the window and the length of
  // the signed-in address. Beneath the Back strip as well as the header.
  const pinTop = usePinTop();

  // The shell's Back keeps what has not been kept before it leaves.
  useBackAction(back);

  // What was last written to the server, and what would be written now - so a
  // leave can keep the difference without waiting for the pause.
  const kept = useRef<{ id: number; payload: string }>({ id: 0, payload: "null" });
  const latest = useRef<{ id: number; payload: string }>({ id: 0, payload: "null" });
  const sending = useRef<{ id: number; payload: string } | null>(null);
  // Set when the kept copy could not be read. Keeping anything then would
  // overwrite a copy the person has not seen, so nothing is kept.
  const keepBlocked = useRef(false);

  function keepNow(id: number, payload: string) {
    if (keepBlocked.current) return;
    if (kept.current.id === id && kept.current.payload === payload) return;
    if (sending.current?.id === id && sending.current.payload === payload) return;
    sending.current = { id, payload };
    setKeeping("keeping");
    api.keepMemoWorking(id, JSON.parse(payload))
      .then(() => {
        kept.current = { id, payload };
        if (latest.current.id === id) setKeeping("kept");
      })
      .catch((err) => {
        setKeeping("failed");
        setSaveError("Your changes could not be kept: " + errorText(err));
      })
      .finally(() => {
        if (sending.current?.id === id && sending.current.payload === payload) {
          sending.current = null;
        }
      });
  }

  // Load the memo and any working copy together, and reopen the copy where it
  // was left. Leaving this memo - for another, or for Back - keeps what has
  // not been kept yet.
  useEffect(() => {
    let live = true;
    setLoaded(false);
    setMemo(null);
    setMode("read");
    setSaveError("");
    setKeeping("");
    setConfirmingUpdate(false);
    setUpdated(null);

    keepBlocked.current = false;
    const working = api.memoWorking(memoId).catch(() => null);

    Promise.all([api.memo(memoId), working]).then(([m, w]) => {
      if (!live) return;
      if (w === null) {
        keepBlocked.current = true;
        setSaveError("Your kept changes to this memo could not be read, so "
          + "nothing you change now will be kept. Reload to try again.");
      }
      const copy = w?.working ?? null;
      setMemo(m);
      setDraft(copy?.text ?? m.markdown);
      draftRef.current = copy?.text ?? m.markdown;
      // A copy kept before undo (version 1) has no history.
      record(Array.isArray(copy?.history) ? copy.history : []);
      lastEdit.current = null;
      setPrompts(copy?.prompts ?? {});
      setAcceptedBy(copy?.accepted_by ?? {});
      setRuns(Object.fromEntries(Object.entries(copy?.pending ?? {})
        .map(([key, id]) => [key, { id, result: null }])));
      setUpdateRun(copy?.update_run ?? null);
      // A copy kept before editing moved into the document names a mode that
      // no longer exists; it opens in the reader, where editing now lives.
      setMode(copy?.mode === "rewrite" ? "rewrite" : "read");
      const payload = copy ? JSON.stringify(copy) : "null";
      kept.current = { id: memoId, payload };
      latest.current = { id: memoId, payload };
      setLoaded(true);
    }).catch((err) => live && setSaveError(errorText(err)));

    return () => {
      live = false;
      const { id, payload } = latest.current;
      if (id === memoId) keepNow(id, payload);
    };
  }, [memoId]);

  const acceptedIds = Array.from(new Set(Object.values(acceptedBy).flat()));
  const inFlight = Object.values(runs).filter((r) => r.result === null).length;
  const undecided = Object.values(runs).filter((r) => r.result !== null).length;
  const typedPrompts = Object.fromEntries(
    Object.entries(prompts).filter(([, p]) => p.trim()));

  const hasChanges = !!memo && (draft !== memo.markdown
    || Object.keys(typedPrompts).length > 0 || acceptedIds.length > 0
    || Object.keys(runs).length > 0 || !!updateRun);

  // A copy with history and nothing else changed is still kept: after
  // Discard it holds the original text and the step that undoes it.
  const payload = !memo || (!hasChanges && history.length === 0) ? "null"
    : JSON.stringify(fitHistory({
      version: 2,
      mode,
      text: draft,
      prompts: typedPrompts,
      accepted_by: acceptedBy,
      pending: Object.fromEntries(Object.entries(runs).map(([k, r]) => [k, r.id])),
      ...(updateRun ? { update_run: updateRun } : {}),
      history,
    }, WORKING_MAX_BYTES, WORKING_WRAP_BYTES));

  // Keep the working copy after a pause in the changes.
  useEffect(() => {
    if (!loaded || keepBlocked.current) return;
    latest.current = { id: memoId, payload };
    if (kept.current.id === memoId && kept.current.payload === payload) return;
    const timer = setTimeout(() => keepNow(memoId, payload), KEEP_AFTER_MS);
    return () => clearTimeout(timer);
  }, [payload, loaded, memoId]);

  // Poll while anything is in flight. Keyed on the ids, so the timer restarts
  // only when that set changes.
  const runningKey = Object.values(runs)
    .filter((r) => r.result === null).map((r) => r.id).sort().join(",");

  useEffect(() => {
    if (!runningKey) return;
    const ids = runningKey.split(",").map(Number);
    const began = Date.now();

    const settle = (id: number, result: Result) =>
      setRuns((prev) => Object.fromEntries(Object.entries(prev).map(([k, r]) =>
        [k, r.id === id && r.result === null ? { ...r, result } : r])));

    const timer = setInterval(async () => {
      // A single section takes seconds. Five minutes without an answer is a
      // function that died, and a spinner would say otherwise for ever.
      if (Date.now() - began > 5 * 60 * 1000) {
        ids.forEach((id) => settle(id, {
          rewrite_id: id, status: "failed", output_text: null,
          citations_dropped: null,
          error: "No answer after five minutes. Press Go again." }));
        return;
      }
      try {
        const { rewrites } = await api.rewrites(memoId, ids);
        rewrites.filter((r) => r.status !== "running")
          .forEach((r) => settle(r.rewrite_id, r));
      } catch (err) {
        setSaveError(errorText(err));
      }
    }, 3000);

    return () => clearInterval(timer);
  }, [runningKey, memoId]);

  // The text as it stands, for the moment an Update finishes: its rows are
  // matched to sections by heading, against the memo as it is then.
  const draftNow = useRef(draft);
  draftNow.current = draft;

  // Poll an Update until it finishes. Its rows arrive together, already
  // done, and join the rewrites out - so accepting, discarding, keeping and
  // saving them is exactly what it is for a prompted rewrite.
  useEffect(() => {
    if (!updateRun) return;
    const run = updateRun;
    const began = Date.now();
    let live = true;

    const stop = (message: string) => {
      setUpdateRun(null);
      if (message) setSaveError(message);
    };

    const timer = setInterval(async () => {
      if (Date.now() - began > UPDATE_GIVES_UP_MS) {
        // A run that never finished never reached the refund either: only a
        // run that ends, failed, gives the charge back (20.1). Catching this
        // one is a failure destination, 20.2, and is not built.
        stop("The update gave no answer in seventeen minutes and has been "
          + "given up on. The charge for it has not been refunded.");
        return;
      }
      try {
        const progress = await api.updateProgress(memoId, run);
        if (!live || progress.status === "running") return;
        if (progress.status === "failed") {
          stop("The update could not be finished: "
            + reasonSaid(progress.error) + " "
            + refundSaid(progress));
          return;
        }
        const sections = splitSections(draftNow.current).sections;
        setRuns((prev) => {
          const next = { ...prev };
          for (const row of progress.rewrites) {
            const key = row.adds_section
              ? ADDS + row.section_heading
              : sections.find((s) => s.heading === row.section_heading.trim())
                  ?.key ?? ADDS + row.section_heading;
            next[key] = { id: row.rewrite_id, result: row };
          }
          return next;
        });
        setUpdated(progress);
        setMode("rewrite");
        stop("");
      } catch (err) {
        // The run is gone - a copy kept from an update that no longer
        // exists. Nothing to wait for.
        if (statusOf(err) === 404) {
          stop("That update could not be found.");
          return;
        }
        setSaveError(errorText(err));
      }
    }, 4000);

    return () => { live = false; clearInterval(timer); };
  }, [updateRun, memoId]);

  // filename -> document_id, so a citation naming a file can be opened. The
  // memo text carries no identifiers; this is the map.
  const byFilename = useMemo(() => {
    const map: Record<string, number> = {};
    for (const s of memo?.sources ?? []) map[s.filename] = s.document_id;
    return map;
  }, [memo]);

  // Sources whose document has been deleted (8.2). They stay in the map
  // above, so a citation to one is still FOUND - it is drawn as spent rather
  // than falling through to prose, which is what happened while the server
  // dropped them from the list altogether.
  const gone = useMemo(
    () => new Set((memo?.sources ?? []).filter((s) => s.removed)
                                       .map((s) => s.filename)),
    [memo]);

  async function openRef(ref: Ref) {
    setLoadingRef(true);
    try {
      setPassage(await api.passage(ref.documentId, ref.unit));
    } finally {
      setLoadingRef(false);
    }
  }

  async function downloadPdf() {
    // Rendered on demand, so it takes a couple of seconds on a long memo.
    // Saying so beats a button that appears to do nothing.
    setRendering(true);
    setSaveError("");
    try {
      const { url } = await api.memoPdf(memoId);
      window.open(url, "_blank", "noopener");
    } catch (err) {
      setSaveError(String((err as Error)?.message ?? err));
    } finally {
      setRendering(false);
    }
  }

  /** Into the rewrite screen, or back out of it, keeping the copy either
   *  way. */
  function openRewrite() {
    setSaveError("");
    setMode("rewrite");
  }

  function close() {
    setMode("read");
    keepNow(memoId, latest.current.payload);
  }

  function back() {
    keepNow(memoId, latest.current.payload);
    onBack();
  }

  function discard() {
    if (!window.confirm("Discard your changes to this memo? Accepted rewrites "
        + "and typed prompts are thrown away. The rewrites stay on record, but "
        + "nothing is saved into the memo.")) return;
    if (!memo) return;
    // Undoable: the step keeps everything Discard clears, as it was.
    change("discard", memo.markdown, {
      accepted_by: { ...acceptedBy },
      pending: Object.fromEntries(Object.entries(runs).map(([k, r]) => [k, r.id])),
      prompts: { ...prompts },
      update_run: updateRun,
    });
    setPrompts({});
    setAcceptedBy({});
    setRuns({});
    setUpdateRun(null);
    setUpdated(null);
    setMode("read");
    setSaveError("");
  }

  /** Every change to the working copy's text comes through here, and is
   *  recorded as a step to undo. `was` is what an act changes beyond the
   *  text, as it was before. */
  function change(act: Act, next: string,
                  was?: Pick<Step, "accepted_by" | "pending" | "prompts"
                                  | "update_run">) {
    const prev = draftRef.current;
    draftRef.current = next;
    setDraft(next);

    const edit = lastEdit.current;
    const h = historyRef.current;
    if (act === "edit" && edit && edit.session === session.current
        && h[h.length - 1] === edit.step) {
      const step = diffStep("edit", edit.base, next);
      lastEdit.current = step ? { ...edit, step } : null;
      record(step ? [...h.slice(0, -1), step] : h.slice(0, -1));
      return;
    }
    if (act !== "edit") session.current++;

    const diff = diffStep(act, prev, next)
      ?? (was ? { act, at: 0, before: [], after: [] } : null);
    // The very object recorded, so the next edit can know it is still on top.
    const step = diff && { ...diff, ...was };
    lastEdit.current = act === "edit" && step
      ? { session: session.current, base: prev, step } : null;
    if (step) record(pushStep(h, step));
  }

  /** A document on the screen saying which of its blocks is open. A block
   *  newly open starts a new edit. */
  function opened(doc: string, id: string | null) {
    if (id !== null && id !== (openBlocks.current[doc] ?? null)) session.current++;
    openBlocks.current = { ...openBlocks.current, [doc]: id };
    setBlockOpen(Object.values(openBlocks.current).some((v) => v !== null));
  }

  /** Take back the last step. Refused while a block is open or a rewrite is
   *  out (undoControl); refused, and the history ended, when the text is no
   *  longer what the step left - restoring over it would lose work. */
  function undo() {
    const h = historyRef.current;
    const step = h[h.length - 1];
    if (!step || undoBlocked) return;
    const text = undoStep(draftRef.current, step);
    if (text === null) {
      record([]);
      setSaveError("That could not be undone: the memo no longer matches what "
        + "was recorded, so nothing was changed and the undo history has been "
        + "cleared.");
      return;
    }
    session.current++;
    lastEdit.current = null;
    draftRef.current = text;
    setDraft(text);
    if (step.accepted_by) {
      const was = step.accepted_by;
      setAcceptedBy((prev) => restoreKeys(prev, was));
    }
    if (step.prompts) {
      const was = step.prompts;
      setPrompts((prev) => restoreKeys(prev, was));
    }
    // A rewrite put back is out again, unanswered; the poll finds it done and
    // offers it to accept or discard as before.
    if (step.pending) {
      const was = step.pending;
      setRuns((prev) => restoreKeys(prev, Object.fromEntries(
        Object.entries(was).map(([k, id]) =>
          [k, id === null ? null : { id, result: null }]))));
    }
    if (step.update_run) setUpdateRun(step.update_run);
    record(h.slice(0, -1));
    setSaveError("");
  }

  /** The confirmation, priced by the server before anything is charged. */
  function openUpdate() {
    setSaveError("");
    setUpdateQuote(null);
    updateKey.current = chargeKey();
    setConfirmingUpdate(true);
    api.walletQuote("memo_generated", 1)
      .then(setUpdateQuote)
      .catch((err) => {
        setUpdateQuote(null);
        setSaveError("The update could not be priced, so it cannot be "
          + "started: " + errorText(err));
      });
  }

  async function startUpdate() {
    setStartingUpdate(true);
    setSaveError("");
    try {
      const started = await api.startUpdate(memoId, updateKey.current);
      setUpdated(null);
      setConfirmingUpdate(false);
      // Could not even be started, and already refunded (20.1).
      if (started.status === "failed") {
        setSaveError("The update could not be started: "
          + reasonSaid(started.error) + " "
          + refundSaid(started));
        return;
      }
      setUpdateRun(started.run);
    } catch (err) {
      setSaveError(errorText(err));
    } finally {
      setStartingUpdate(false);
    }
  }

  const split = splitSections(draft);
  const originals = Object.fromEntries(
    splitSections(memo?.markdown ?? "").sections.map((s) => [s.key, s.text]));

  const ready = split.sections.filter((s) =>
    (prompts[s.key] ?? "").trim() && !runs[s.key]);

  async function go() {
    if (ready.length === 0) return;
    const sending = ready;
    setStarting(true);
    setSaveError("");
    try {
      const { rewrites } = await api.startRewrites(memoId, sending.map((s) => (
        { heading: s.heading, text: s.text, prompt: (prompts[s.key] ?? "").trim() })));
      setRuns((prev) => {
        const next = { ...prev };
        sending.forEach((s, k) => {
          const r = rewrites[k];
          next[s.key] = r.status === "failed"
            ? { id: r.rewrite_id, result: { rewrite_id: r.rewrite_id,
                status: "failed", output_text: null, citations_dropped: null,
                error: "The rewrite could not be started." } }
            : { id: r.rewrite_id, result: null };
        });
        return next;
      });
    } catch (err) {
      setSaveError(errorText(err));
    } finally {
      setStarting(false);
    }
  }

  function dropRun(key: string) {
    setRuns((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  function accept(key: string) {
    const run = runs[key];
    if (!run?.result?.output_text) return;
    const text = run.result.output_text.replace(/\s+$/, "") + "\n";
    const d = draftRef.current;
    // A section new in the template replaces nothing: it goes at the end.
    change("accept", key.startsWith(ADDS)
      ? d.replace(/\s+$/, "") + "\n\n" + text
      : replaceSection(d, key, text), {
      accepted_by: { [key]: acceptedBy[key] ?? null },
      pending: { [key]: run.id },
      prompts: { [key]: prompts[key] ?? null },
    });
    setAcceptedBy((prev) => ({ ...prev,
                               [key]: [...(prev[key] ?? []), run.id] }));
    setPrompts((prev) => ({ ...prev, [key]: "" }));
    dropRun(key);
  }

  function putBack(key: string) {
    if (originals[key] === undefined) return;
    change("put-back", replaceSection(draftRef.current, key, originals[key]),
           { accepted_by: { [key]: acceptedBy[key] ?? null } });
    setAcceptedBy((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }

  // An Update still running is a set of rewrites still out: saving now would
  // end the working copy its answer is coming back to.
  const blocked = inFlight > 0 || undecided > 0 || !!updateRun;
  const canSave = !!memo && !saving && !blocked && !!draft.trim()
    && draft !== memo.markdown;

  // Undo restores text an open block would overwrite with its next commit,
  // and a rewrite out could land on text undo has just put back.
  const undoBlocked = blockOpen || inFlight > 0 || !!updateRun;
  const lastStep = history[history.length - 1];
  const undoControl = lastStep && (
    <a className="secondary"
       onClick={undoBlocked ? undefined : undo}
       aria-disabled={undoBlocked}
       title={blockOpen ? "Finish editing first."
         : inFlight > 0 || updateRun ? "Wait for the rewrite to finish."
         : "Undo: " + ACT_SAID[lastStep.act]}>
      Undo
    </a>
  );

  async function save() {
    setSaving(true);
    setSaveError("");
    try {
      const revised = await api.revise(memoId, draft, acceptedIds);
      // The server clears the working copy with the save. Nothing is left to
      // keep, so leaving must not write the old one back.
      kept.current = { id: memoId, payload: "null" };
      latest.current = { id: memoId, payload: "null" };
      setMode("read");
      onOpen(revised.memo_id);
    } catch (err) {
      // A citation naming a document that is not a source of this memo is
      // refused rather than saved. The message names which.
      setSaveError(errorText(err));
    } finally {
      setSaving(false);
    }
  }

  if (!memo) {
    return saveError
      ? <p className="error">{saveError}</p>
      : <p className="muted">Loading&hellip;</p>;
  }

  const isRevision = memo.revision > 1;

  // Every rendering of memo text on this screen - the reader, the editor's
  // preview, both panes of a rewrite - goes through here, so tables are
  // tables and citations behave the same way everywhere.
  const markdownOf = (text: string) => (
    <MemoDocument markdown={text} byFilename={byFilename} gone={gone}
                  onOpen={openRef} />
  );

  // Which sections of this memo the model wrote, grouped by who prompted -
  // and, apart from those, which an Update brought in and at whose request.
  const byWho = (update: boolean) => (memo.rewrites ?? [])
    .filter((w) => (w.source === "update") === update)
    .reduce<Record<string, string[]>>((acc, w) => {
      (acc[w.prompted_by] ||= []).push(w.section_heading.replace(/^#+\s*/, ""));
      return acc;
    }, {});
  const rewrittenBy = byWho(false);
  const updatedBy = byWho(true);
  const updatedUnder = (memo.rewrites ?? [])
    .find((w) => w.source === "update")?.config_revision ?? null;

  const blockedTitle = updateRun ? "Wait for the update to finish."
    : blocked ? "Accept or discard every rewrite first." : undefined;

  // Offered on a memo a person has saved. It works on the memo as saved, so
  // unsaved changes are saved or discarded first - Share's rule, for the
  // same reason.
  const updatable = memo.revision > 1;
  const updateTitle = updateRun ? "The update is running."
    : hasChanges ? "Save or discard your changes first. Update works on the "
                   + "memo as saved."
    : "Write every section again from the configuration in use and the "
      + "documents filed now, and set what is new beside your text.";
  const updateControl = updatable && (
    <a className="secondary"
       onClick={hasChanges ? undefined : openUpdate}
       aria-disabled={hasChanges}
       title={updateTitle}>
      {updateRun ? "Updating…" : "Update"}
    </a>
  );

  return (
    <div className={mode !== "read" ? "wide" : ""}>

      <div className="memo-head pinned" style={{ top: pinTop }}>
        <div>
          <h2>Memo {memo.label}</h2>
          <p className="muted">
            {memo.workspace ? `Workspace ${memo.workspace} · ` : ""}
            Generated {(memo.generated_at ?? "").slice(0, 16)}
            {memo.generated_by ? " by " + memo.generated_by : ""}
            {memo.modified_by
              ? ` \u00b7 revised ${(memo.modified_at ?? "").slice(0, 16)} by ${memo.modified_by}`
              : ""}
          </p>
        </div>

        {mode === "read" ? (
          <>
            {hasChanges && (
              <button onClick={save} disabled={!canSave} title={blockedTitle}>
                {saving ? "Saving\u2026" : "Save as a new revision"}
              </button>
            )}
            {undoControl}
            <a className="secondary" onClick={openRewrite}>
              Have Model Redraft a Section
            </a>
            {updateControl}
            <a className="pdf" onClick={rendering ? undefined : downloadPdf}
               aria-disabled={rendering}>
              {rendering ? "Rendering\u2026" : "Download PDF"}
            </a>
            {/* What is shared is this memorandum as saved. Unsaved changes
                are not in it, so Share waits until they are saved or
                discarded rather than sending something other than what is
                on the screen. */}
            <a className="secondary"
               onClick={hasChanges ? undefined : () => setSharing(true)}
               aria-disabled={hasChanges}
               title={hasChanges ? "Save or discard your changes first." : undefined}>
              Share
            </a>
          </>
        ) : (
          <>
            {mode === "rewrite" && (
              <>
                <button onClick={go} disabled={starting || ready.length === 0}
                        title={ready.length === 0
                          ? "Write a prompt under a section first." : undefined}>
                  {starting
                    ? "Starting\u2026"
                    : ready.length === 0
                      ? "Go"
                      : `Go \u2014 rewrite ${ready.length} ${
                          ready.length === 1 ? "section" : "sections"}`}
                </button>
                {/* NOT the shared Working indicator, deliberately (6.3).
                     This sits in a row beside the Go and Save buttons, and
                     .working is a 240px-minimum card with its own margins
                     and a bar - dropped in here it would push the buttons
                     apart every time a rewrite ran. A span beside a button
                     is the right shape for a count that changes while the
                     row stays still. Held with the two below it as one
                     question rather than changed unseen. */}
                {inFlight > 0 && (
                  <span className="busy">
                    {inFlight} {inFlight === 1 ? "section" : "sections"} rewriting
                  </span>
                )}
              </>
            )}
            <button onClick={save} disabled={!canSave} title={blockedTitle}>
              {saving ? "Saving\u2026" : "Save as a new revision"}
            </button>
            {undoControl}
            {updateControl}
            <a className="secondary" onClick={close}>Close</a>
          </>
        )}
      </div>

      {mode === "read" && hasChanges && (
        // .unsaved, not the plain note Catalogue and Welcome share: this one
        // gates an action in the head - Share - so it has to be seen, not
        // merely present.
        <p className="working-note unsaved">
          <strong>You have unsaved changes to this memo.</strong> They are
          kept if you leave, until you save or{" "}
          <a onClick={discard}>discard them</a>. Save or discard them to
          share this memo: what is shared is the memo as saved.
          {keeping === "keeping" && <span> Keeping&hellip;</span>}
          {keeping === "kept" && <span> Kept.</span>}
        </p>
      )}

      {isRevision && mode === "read" && (
        <p className="revision-note">
          This is a revision. It was edited by a person, so the citations are
          their responsibility rather than the system's.
          {Object.entries(rewrittenBy).map(([who, headings]) => (
            <span key={who}>
              {" "}{headings.join(", ")}{" "}
              {headings.length === 1 ? "was" : "were"} rewritten by the model
              at {who}&rsquo;s prompt.
            </span>
          ))}
          {Object.entries(updatedBy).map(([who, headings]) => (
            <span key={"u:" + who}>
              {" "}{headings.join(", ")}{" "}
              {headings.length === 1 ? "was" : "were"} updated from the
              documents on file and configuration revision {updatedUnder}, at
              {" "}{who}&rsquo;s request.
            </span>
          ))}{" "}
          Memo{" "}
          <a onClick={() => onOpen(memo.parent_memo_id!)}>
            {memo.parent_memo_id}.1
          </a>{" "}
          is the generated original and is unchanged.
        </p>
      )}

      {mode === "rewrite" && (
        <p className="muted small edit-note">
          Write a prompt under any section and press Go. Each rewrite appears
          beside what it would replace; nothing changes until you accept it and
          save. Your changes are kept if you leave, until you save or{" "}
          <a onClick={discard}>discard them</a>. Saving creates a new memo; this
          one stays as it is.
          {keeping === "keeping" && <span> Keeping&hellip;</span>}
          {keeping === "kept" && hasChanges && <span> Kept.</span>}
        </p>
      )}

      {updateRun && (
        <Working what={"Updating every section from the documents on file. "
                       + "It takes a few minutes, and you can leave and come "
                       + "back"} />
      )}

      {updated && mode === "rewrite" && (
        <p className="muted small edit-note">
          The update compared {(updated.changed ?? 0) + (updated.unchanged ?? 0)
          } {(updated.changed ?? 0) + (updated.unchanged ?? 0) === 1
            ? "section" : "sections"} with the documents on file under
          configuration revision {updated.config_revision}:{" "}
          {updated.changed ?? 0} with something new, set beside your text
          below; {updated.unchanged ?? 0} with nothing new.
          {(updated.added_sections ?? []).length > 0 && (
            <> {(updated.added_sections ?? []).length} new in the template,
              offered at the end.</>
          )}
          {(updated.kept ?? []).length > 0 && (
            <> Kept as you wrote {(updated.kept ?? []).length === 1
                ? "it" : "them"}, with no counterpart in the template:{" "}
              {(updated.kept ?? []).map((h) => h.replace(/^#+\s*/, ""))
                .join(", ")}.</>
          )}
          {(updated.failed_sections ?? 0) > 0 && (
            <> {updated.failed_sections} could not be compared and
              {updated.failed_sections === 1 ? " is" : " are"} marked
              below.</>
          )}
        </p>
      )}

      {saveError && <p className="error">{saveError}</p>}
      {loadingRef && <Working what="Opening source" />}

      {mode === "rewrite" ? (
        <div className="rewrite">
          {split.head.trim() && (
            <>
              <div className="rewrite-body">
                <MemoDocument markdown={split.head} byFilename={byFilename}
                              gone={gone} onOpen={openRef}
                              onOpenChange={(id) => opened("head", id)}
                              onChange={updateRun ? undefined : (text, act) => change(
                                act, joinSections(text, split.hasHead, split.sections))} />
              </div>
              <p className="muted small rewrite-note">
                The title and header are not rewritten.
              </p>
            </>
          )}
          {split.sections.length === 0 && (
            <p className="warn">
              This memo has no numbered sections to rewrite.
            </p>
          )}

          {split.sections.map((s) => {
            const run = runs[s.key];
            const result = run?.result ?? null;
            const accepted = acceptedBy[s.key] ?? [];
            const lost = result?.output_text
              ? lostCitations(s.text, result.output_text) : [];
            return (
              <section className="rewrite-section" key={s.key}>
                {result?.status === "done" && result.output_text ? (
                  <div className="rewrite-compare">
                    <div>
                      <h4>Now</h4>
                      <div className="rewrite-body">
                        {markdownOf(s.text)}
                      </div>
                    </div>
                    <div>
                      <h4>{result.source === "update" ? "Updated" : "Rewritten"}</h4>
                      <div className="rewrite-body">
                        {markdownOf(result.output_text)}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rewrite-body">
                    <MemoDocument markdown={s.text} byFilename={byFilename}
                                  gone={gone} onOpen={openRef}
                                  onOpenChange={(id) => opened(s.key, id)}
                                  onChange={updateRun ? undefined : (text, act) => change(
                                    act, replaceSection(draftRef.current, s.key, text))} />
                  </div>
                )}

                {lost.length > 0 && (
                  <p className="warn">
                    This rewrite leaves out {lost.length === 1
                      ? "a citation" : lost.length + " citations"}:{" "}
                    {lost.map((c) => c.replace(/^\*|\*$/g, "")).join("; ")}
                  </p>
                )}

                {result?.status === "failed" && (
                  <p className="error">{result.error}</p>
                )}

                <div className="rewrite-actions">
                  {/* NOT the shared Working indicator, deliberately (6.3).
                      .rewrite-actions is a 13px flex row of links, gap 16px;
                      .working is a 240px-minimum card with margin 12px 0
                      16px and a bar under it. One of these renders per
                      section being rewritten, so the card would stack the
                      row into a column. The span is what keeps Accept and
                      Discard where they were. */}
                  {run && !result && (
                    <span className="busy">Rewriting&hellip;</span>
                  )}
                  {result?.status === "done" && (
                    <>
                      <a onClick={() => accept(s.key)}>Accept</a>
                      <a onClick={() => dropRun(s.key)}>Discard</a>
                    </>
                  )}
                  {result?.status === "failed" && (
                    <a onClick={() => dropRun(s.key)}>Dismiss</a>
                  )}
                  {accepted.length > 0 && !run && (
                    <>
                      <span className="muted">
                        Rewritten{accepted.length > 1
                          ? " " + accepted.length + " times" : ""}
                      </span>
                      {originals[s.key] !== undefined && (
                        <a onClick={() => putBack(s.key)}>
                          Put back the original
                        </a>
                      )}
                    </>
                  )}
                </div>

                {!run && !updateRun && (
                  <textarea className="rewrite-prompt" rows={2}
                    placeholder={"How " + s.heading.replace(/^#+\s*/, "")
                                 + " should be rewritten"}
                    value={prompts[s.key] ?? ""}
                    onChange={(e) => {
                      const value = e.target.value;
                      setPrompts((prev) => ({ ...prev, [s.key]: value }));
                    }} />
                )}
              </section>
            );
          })}

          {/* Sections new in the template since this memo was written,
              offered whole by an Update. Nothing here replaces anything:
              accepting adds the section at the end of the memo. */}
          {Object.entries(runs).filter(([key]) => key.startsWith(ADDS))
            .map(([key, run]) => {
              const result = run.result;
              return (
                <section className="rewrite-section" key={key}>
                  <p className="muted small">
                    New in the template since this memo was written.
                    Accepting adds it at the end.
                  </p>
                  {result?.status === "done" && result.output_text && (
                    <div className="rewrite-body">
                      {markdownOf(result.output_text)}
                    </div>
                  )}
                  {result?.status === "failed" && (
                    <p className="error">{result.error}</p>
                  )}
                  <div className="rewrite-actions">
                    {!result && <span className="busy">Loading&hellip;</span>}
                    {result?.status === "done" && (
                      <>
                        <a onClick={() => accept(key)}>Add to the memo</a>
                        <a onClick={() => dropRun(key)}>Discard</a>
                      </>
                    )}
                    {result?.status === "failed" && (
                      <a onClick={() => dropRun(key)}>Dismiss</a>
                    )}
                  </div>
                </section>
              );
            })}
        </div>
      ) : (
        <MemoDocument markdown={draft} byFilename={byFilename} gone={gone}
                      onOpen={openRef}
                      onOpenChange={(id) => opened("doc", id)}
                      onChange={updateRun ? undefined
                                          : (text, act) => change(act, text)} />
      )}

      {passage && (
        <PassagePanel passage={passage} onClose={() => setPassage(null)} />
      )}

      {/* After the passage drawer: drawers stack in document order. */}
      {sharing && (
        <ShareSendPanel memoId={memo.memo_id} label={memo.label}
                        onClose={() => setSharing(false)} />
      )}

      {/* The press that spends, with its price first. The figures are the
          server's quote, as Generate's are: Update is charged as a
          generation, and the two must read the same on the ledger. */}
      {confirmingUpdate && (
        <div className="panel-backdrop" onClick={() => setConfirmingUpdate(false)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}
               onKeyDown={(e) => { if (e.key === "Escape") setConfirmingUpdate(false); }}>
            <a className="panel-close"
               onClick={() => setConfirmingUpdate(false)}>Close</a>
            <div className="form">
              <h4>Update memo {memo.label}</h4>

              <p className="muted small">
                Every section is written again from the configuration in use
                and the documents filed in this engagement now. What is new
                is set beside your text, section by section, to accept or
                discard. Your text stays exactly as you wrote it. Where the
                documents now say something different from it, that is added
                as an Open Item rather than changed. A section new in the
                template is offered at the end. Nothing is saved until you
                save a revision.
              </p>

              {updateQuote && (
                <div className="quote">
                  <div>
                    <span>1 update, charged as a memorandum</span>
                    <b>{money(updateQuote.total_cents)}</b>
                  </div>
                  <div>
                    <span>Available</span>
                    <b>{money(updateQuote.available_cents)}</b>
                  </div>
                  {!updateQuote.affordable && (
                    <div className="short">
                      <span>Short by</span>
                      <b>{money(updateQuote.total_cents
                                - updateQuote.available_cents)}</b>
                    </div>
                  )}
                </div>
              )}

              {updateQuote && !updateQuote.affordable && (
                <p className="why warn">
                  There is not enough balance for this. Nothing has been
                  charged and nothing will be until there is.
                </p>
              )}

              {saveError && <p className="error">{saveError}</p>}

              <div className="form-actions">
                {updateQuote && !updateQuote.affordable ? (
                  <button onClick={() => navigate(balanceFor(
                    updateQuote.total_cents - updateQuote.available_cents,
                    `Updating memo ${memo.label}`, window.location.pathname))}>
                    Top up
                  </button>
                ) : (
                  // Held until priced: the price is on the button that
                  // spends, and a button with no price on it is not offered.
                  <button className="spend"
                          disabled={!updateQuote || startingUpdate}
                          onClick={startUpdate}>
                    {startingUpdate ? "Starting…" : updateQuote
                      ? `Update · ${money(updateQuote.total_cents)}`
                      : "Pricing…"}
                  </button>
                )}
                <a className="secondary"
                   onClick={() => setConfirmingUpdate(false)}>Cancel</a>
              </div>

              <p className="muted small">
                The charge is made when the update starts, against the
                balance rather than the card. A repeat of this click is not
                charged twice. If the update fails, the charge is refunded
                to your balance.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** What the system read at the cited page, and a link to the document.
 *
 *  `cite-panel` carries no style rule. It marks this drawer as the one a
 *  citation opens, so the footnote highlight survives every way out of it -
 *  Close, the scrim, the link to the original (18.1). Without it the panel
 *  answered where else the passage was used and then cleared the answer on
 *  the way out. The exemption is read in MemoReader's clearing listener; it
 *  is on this drawer and not on .panel-backdrop, which every drawer in the
 *  product wears. */
function PassagePanel({ passage, onClose }: {
  passage: Passage;
  onClose: () => void;
}) {
  return (
    <div className="panel-backdrop cite-panel" onClick={onClose}>
      <aside className="panel" onClick={(e) => e.stopPropagation()}>
        <a onClick={onClose} className="panel-close">Close</a>
        <h3>{passage.filename}</h3>
        <p className="muted">
          {passage.unit
            ? `${passage.unit_kind} ${passage.unit}${passage.unit_label ? " \u2014 " + passage.unit_label : ""} of ${passage.pages}`
            : `${passage.pages} pages`}
        </p>

        <p className="muted small">
          This is the text the system read. It is what every value from this
          document was extracted from.
        </p>

        <pre className="passage">{passage.text}</pre>

        <a href={passage.source_url} target="_blank" rel="noreferrer">
          Open the original document
        </a>
      </aside>
    </div>
  );
}
