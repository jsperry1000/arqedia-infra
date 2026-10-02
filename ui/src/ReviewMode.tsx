import { useEffect, useMemo, useState } from "react";
import { Working } from "./shell";
import {
  api, statusOf,
  type Draft, type ProposedNewField, type Review, type ReviewSuggestion,
  type ReviewTarget,
} from "./api";

/**
 * AI Review of the draft (REV-01).
 *
 * The reviewer reads the open draft and suggests changes: field and document
 * descriptions, section prompts, where a fact is sought, and facts a
 * memorandum asks for that nothing supplies. Nothing reaches the draft without
 * an accept, and an accept writes the draft only - nothing reaches a
 * memorandum until the draft is published, as with every other edit.
 *
 * THE PRICE IS SHOWN BEFORE THE FIRST ACCEPT, NOT ON OPENING (decision of
 * 1 October 2026). Reading costs the tenant nothing; the first accepted change
 * in a session is its charge, and every later one in it is free. A session
 * nobody accepts anything from is never charged.
 *
 * SUGGESTIONS ABOUT ONE THING ARE SHOWN TOGETHER (S1). A field, a document
 * type or a section is one group, and accepting one suggestion in it sets the
 * others aside - on this screen only: the reviewer keeps no "declined"
 * state, so setting aside is never sent and can be undone. Nothing smarter
 * than "the same target" is matched.
 *
 * A QUESTION IS ANSWERED, NOT ACCEPTED (S2). The answer goes back to the
 * reviewer, which turns it into one change; that change arrives on a later
 * poll, under its question, and is accepted like any other. Answering writes
 * and charges nothing.
 */

/** The session this tab is working in, so closing the drawer and opening it
 *  again resumes rather than starts over. Per tab, and a convenience only:
 *  lost, the session lapses on its own after a day. */
const SESSION_KEY = "arqedia.review.session";
const DISMISSED_KEY = "arqedia.review.dismissed.";

function remembered(key: string): string | null {
  try { return sessionStorage.getItem(key); } catch { return null; }
}
function remember(key: string, value: string | null) {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch { /* storage refused; the screen works without it */ }
}

/** One thing a suggestion is about. Suggestions sharing it are a group. A
 *  new fact is about the section that needs it, so it groups with that
 *  section's prompt - which is exactly the pair S1 was written about. */
function targetKey(t: ReviewTarget): string {
  if (t.field_key) return "field:" + t.field_key;
  if (t.type_key) return "type:" + t.type_key;
  if (t.section_key) return "section:" + (t.template_key ?? "") + "/"
    + t.section_key;
  return "other";
}

type Group = { key: string; items: ReviewSuggestion[] };

/** Suggestions in groups, in the order the review made them. A change an
 *  answer produced belongs to its question's group, wherever it points. */
function grouped(suggestions: ReviewSuggestion[]): Group[] {
  const byId = new Map(suggestions.map((s) => [s.id, s]));
  const groups: Group[] = [];
  const index = new Map<string, Group>();
  for (const s of suggestions) {
    const anchor = s.from_question ? byId.get(s.from_question) ?? s : s;
    const key = targetKey(anchor.target);
    let g = index.get(key);
    if (!g) {
      g = { key, items: [] };
      index.set(key, g);
      groups.push(g);
    }
    g.items.push(s);
  }
  return groups;
}

/** What a suggestion is about, by the names a person gave things. */
function nameOf(draft: Draft | null, t: ReviewTarget): string {
  if (!draft) return "";
  if (t.field_key) {
    const f = draft.fields.find((x) => x.key === t.field_key);
    return "Fact · " + (f?.label ?? t.field_key);
  }
  if (t.type_key) {
    const d = draft.document_types.find((x) => x.key === t.type_key);
    return "Document · " + (d?.label ?? t.type_key);
  }
  if (t.section_key) {
    const s = draft.sections.find((x) => x.key === t.section_key
      && (!t.template_key || x.template_key === t.template_key));
    const memo = draft.templates.find((x) => x.key === t.template_key);
    return (memo ? (memo.label || memo.key) + " · " : "")
      + (s ? `${s.numeral}. ${s.title}` : t.section_key);
  }
  return "";
}

const KIND_LABEL: Record<ReviewSuggestion["kind"], string> = {
  field_description: "What the fact is",
  section_prompt: "How the section should read",
  document_type_description: "How to recognise the document",
  field_found_in: "Where the fact is sought",
  new_field: "A fact this section needs",
  question: "A question",
};

/** The kinds whose suggested text a person may edit before accepting it. */
const EDITABLE = new Set<ReviewSuggestion["kind"]>(
  ["section_prompt", "field_description"]);

// What a suggestion or question says about binding - "bound", "unbound",
// "bind", "binding". Matched on the words the reviewer wrote, nothing more.
const BINDING_WORDS = /\b(un)?bound\b|\bbind(s|ing|ings)?\b/i;

/** The section a binding problem is about, where there is one to open: a
 *  suggestion or question on a section whose reason or question talks about
 *  binding. Not a composed section - it reads other sections, not bound
 *  facts, and has no fact list to open. */
function bindingSection(draft: Draft | null, s: ReviewSuggestion):
    { template_key: string; section_key: string } | null {
  const t = s.target;
  if (!draft || !t.template_key || !t.section_key) return null;
  if (!BINDING_WORDS.test(`${s.reason ?? ""} ${s.question ?? ""}`)) {
    return null;
  }
  const section = draft.sections.find(
    (x) => x.template_key === t.template_key && x.key === t.section_key);
  if (!section || section.kind === "composed") return null;
  return { template_key: t.template_key, section_key: t.section_key };
}

function Value({ draft, value }: {
  draft: Draft | null;
  value: ReviewSuggestion["current"] | ReviewSuggestion["proposed"];
}) {
  if (value === null || value === undefined || value === "") {
    return <span className="muted small">(nothing)</span>;
  }
  if (typeof value === "string") {
    return <div style={{ whiteSpace: "pre-wrap" }}>{value}</div>;
  }
  if (Array.isArray(value)) {
    const names = value.map((k) =>
      draft?.document_types.find((t) => t.key === k)?.label ?? k);
    return <div>{names.length ? names.join(", ") : "no document"}</div>;
  }
  const f = value as ProposedNewField;
  return (
    <div>
      <strong>{f.label}</strong>{f.is_table ? " (a table)" : ""}
      <div style={{ whiteSpace: "pre-wrap" }}>{f.description}</div>
      {f.columns.length > 0 && (
        <div className="muted small">
          Columns: {f.columns.map((c) => c.label).join(", ")}
        </div>
      )}
      <div className="muted small">
        Sought in: {f.found_in.map((k) =>
          draft?.document_types.find((t) => t.key === k)?.label ?? k)
          .join(", ") || "no document yet"}
      </div>
    </div>
  );
}

function message(err: unknown) {
  let text = String((err as Error)?.message ?? err);
  try { text = JSON.parse(text).error ?? text; } catch { /* as it came */ }
  return text;
}

export function ReviewMode({ draft, onClose, onChanged, onEditBindings }: {
  draft: Draft | null;
  /** The drawer closes; the session stays open until ended or a day old. */
  onClose: () => void;
  /** Something was written to the draft, so the editor should read it again. */
  onChanged: () => void;
  /** Open the editor's own fact list for one section. The editor closes this
   *  drawer to show it; the session stays open and resumes when AI Review is
   *  opened again. */
  onEditBindings: (templateKey: string, sectionKey: string) => void;
}) {
  const [session, setSession] = useState<string | null>(
    () => remembered(SESSION_KEY));
  const [review, setReview] = useState<Review | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notes, setNotes] = useState<Record<string, string>>({});
  // The suggestion whose Accept is waiting on the price being accepted.
  const [paying, setPaying] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  // A new fact is added to the section that needs it unless this is unticked
  // (D5).
  const [unbound, setUnbound] = useState<Set<string>>(new Set());
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [showDismissed, setShowDismissed] = useState(false);
  // The person's own wording of a suggestion, while they are editing it. A
  // suggestion with no entry is written as it came.
  const [edits, setEdits] = useState<Record<string, string>>({});

  // What was set aside belongs to the session, and comes back with it.
  useEffect(() => {
    if (!session) { setDismissed(new Set()); return; }
    const kept = remembered(DISMISSED_KEY + session);
    setDismissed(new Set(kept ? kept.split(",").filter(Boolean) : []));
  }, [session]);

  const dismiss = (ids: string[], on: boolean) => {
    setDismissed((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (on) next.add(id); else next.delete(id);
      }
      if (session) remember(DISMISSED_KEY + session, [...next].join(","));
      return next;
    });
  };

  const forget = () => {
    if (session) remember(DISMISSED_KEY + session, null);
    remember(SESSION_KEY, null);
    setSession(null);
    setReview(null);
  };

  const poll = async (id: string) => {
    try {
      const r = await api.reviewPoll(id);
      setReview(r);
      // A session that cannot be acted on any more is let go of, so the next
      // opening starts a fresh one rather than resuming a dead one.
      if (r.closed) forget();
    } catch (e) {
      if (statusOf(e) === 400 || statusOf(e) === 404) forget();
      else setError(message(e));
    }
  };

  // Reading takes minutes and an answer a few seconds; both are polled, and
  // nothing is polled once there is nothing to wait for.
  const waiting = !!review && (["starting", "reading"].includes(review.status)
    || review.suggestions.some((s) => s.answer?.status === "answering"));

  // poll is left out of both dependency lists on purpose: it is remade every
  // render, and listing it would restart the timer on every poll it caused.
  useEffect(() => {
    if (session) poll(session);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  useEffect(() => {
    if (!session || !waiting) return;
    const timer = window.setInterval(() => poll(session), 4000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, waiting]);

  const start = async () => {
    setBusy("Starting the review");
    setError("");
    try {
      const opened = await api.reviewOpen();
      remember(SESSION_KEY, opened.session_id);
      setSession(opened.session_id);
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy("");
    }
  };

  const end = async () => {
    if (!session) { onClose(); return; }
    setBusy("Ending the review");
    try {
      await api.reviewClose(session);
    } catch (e) {
      // A session already gone is ended whichever way.
      if (statusOf(e) !== 400 && statusOf(e) !== 404) {
        setError(message(e));
        setBusy("");
        return;
      }
    }
    setBusy("");
    forget();
    onClose();
  };

  const suggestions = useMemo(() => review?.suggestions ?? [], [review]);
  const groups = useMemo(() => grouped(suggestions), [suggestions]);
  // Paid for once something in it has been accepted.
  const charged = suggestions.some((s) => s.status === "accepted");
  const price = review?.price_cents ?? 100;

  const accept = async (s: ReviewSuggestion, group: Group) => {
    if (!session) return;
    if (!charged && paying !== s.id) {
      setPaying(s.id);
      return;
    }
    setPaying(null);
    setBusy("Writing it to the draft");
    setError("");
    setNotes((n) => ({ ...n, [s.id]: "" }));
    const bind = s.kind === "new_field" && !unbound.has(s.id)
      && s.target.template_key && s.target.section_key
      ? { template_key: s.target.template_key,
          section_key: s.target.section_key } : undefined;
    // Sent only when the wording was actually changed, so an edit opened and
    // left alone writes the suggestion exactly as it came.
    const edited = edits[s.id];
    const value = edited !== undefined && typeof s.proposed === "string"
      && edited.trim() !== s.proposed.trim() ? edited : undefined;
    try {
      const done = await api.reviewAccept(session, s.id, bind, value);
      const how = value !== undefined ? " as you edited it" : "";
      setNotes((n) => ({ ...n, [s.id]: done.repeated
        ? "Already accepted."
        : done.charged_cents
          ? `Written to the draft${how}. This review has been charged `
            + `$${(done.charged_cents / 100).toFixed(2)}; further changes `
            + `in it are free.`
          : `Written to the draft${how}.` }));
      setEdits((e) => {
        const next = { ...e };
        delete next[s.id];
        return next;
      });
      // S1: the rest of what was suggested about this thing is set aside.
      dismiss(group.items.filter((x) => x.id !== s.id && x.kind !== "question"
        && x.status === "open").map((x) => x.id), true);
      onChanged();
    } catch (e) {
      setNotes((n) => ({ ...n, [s.id]: message(e) }));
    } finally {
      setBusy("");
      await poll(session);
    }
  };

  const sendAnswer = async (s: ReviewSuggestion) => {
    if (!session) return;
    const text = (answers[s.id] ?? "").trim();
    if (!text) return;
    setBusy("Sending your answer");
    setNotes((n) => ({ ...n, [s.id]: "" }));
    try {
      await api.reviewAnswer(session, s.id, text);
      setAnswers((a) => ({ ...a, [s.id]: "" }));
    } catch (e) {
      setNotes((n) => ({ ...n, [s.id]: message(e) }));
    } finally {
      setBusy("");
      await poll(session);
    }
  };

  const card = (s: ReviewSuggestion, group: Group) => {
    const aside = dismissed.has(s.id) && s.status === "open";
    if (aside && !showDismissed) return null;
    const usable = review?.status === "ready" && !review.expired
      && !review.closed;

    return (
      <div className="review" key={s.id}>
        <div className="review-head">
          <label>
            <strong>{KIND_LABEL[s.kind]}</strong>
            {s.from_question && (
              <span className="muted small">from your answer</span>
            )}
          </label>
          {s.status === "accepted" && <span className="in-use">accepted</span>}
          {s.status === "stale" && (
            <span className="warn">changed since it was read</span>
          )}
          {aside && <span className="muted small">set aside</span>}
        </div>

        {s.reason && <p className="muted small">{s.reason}</p>}

        {/* A binding problem is fixed in the editor's own fact list for the
            section, not here. Nothing re-checks the suggestion afterwards:
            once it is fixed, set it aside, as with anything else handled by
            hand. */}
        {(() => {
          const where = bindingSection(draft, s);
          return where && (
            <p className="small">
              <a onClick={() => onEditBindings(where.template_key,
                                               where.section_key)}>
                Edit bindings
              </a>
              <span className="muted">
                {" "}&middot; opens {nameOf(draft, s.target)} in the editor;
                this review stays open to come back to
              </span>
            </p>
          );
        })()}

        {s.kind === "question" ? (
          <>
            <p>{s.question}</p>
            {s.answer && (
              <p className="muted small">
                {s.answer.status === "answering"
                  && "Turning your answer into a change…"}
                {s.answer.status === "ready"
                  && `You answered: “${s.answer.answer}”`}
                {(s.answer.status === "no_change"
                  || s.answer.status === "failed") && s.answer.reason}
              </p>
            )}
            {usable && (!s.answer || s.answer.status === "no_change"
                        || s.answer.status === "failed") && (
              <div className="form">
                <textarea rows={3} value={answers[s.id] ?? ""}
                  placeholder="Your answer. It is turned into one change you can accept or not; answering costs nothing."
                  onChange={(e) => setAnswers(
                    (a) => ({ ...a, [s.id]: e.target.value }))} />
                <div className="form-actions">
                  <button disabled={!!busy || !(answers[s.id] ?? "").trim()}
                          onClick={() => sendAnswer(s)}>
                    Answer
                  </button>
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            {s.kind !== "new_field" && (
              <>
                <p className="muted small">Now</p>
                <Value draft={draft} value={s.current} />
              </>
            )}
            {/* Once accepted, what was written - which is the person's edit
                where they made one. Showing the suggestion as it came made an
                edited accept look as though the edit had been lost. */}
            {s.status === "accepted" && s.written !== undefined && (
              <>
                <p className="muted small">
                  Written to the draft
                  {JSON.stringify(s.written) !== JSON.stringify(s.proposed)
                    && " — your edit of the suggestion"}
                </p>
                <Value draft={draft} value={s.written} />
              </>
            )}

            {!(s.status === "accepted" && s.written !== undefined) && (<>
            <p className="muted small">
              {edits[s.id] !== undefined ? "Suggested, as you are editing it"
                                         : "Suggested"}
            </p>
            {/* The memo screen's free-standing prompt box: full width of the
                card, the editor's font, resizable downward. Outside a .form,
                a bare textarea took the browser's default width. */}
            {edits[s.id] !== undefined ? (
              <textarea className="rewrite-prompt" rows={6} value={edits[s.id]}
                onChange={(e) => setEdits(
                  (x) => ({ ...x, [s.id]: e.target.value }))} />
            ) : (
              <Value draft={draft} value={s.proposed} />
            )}
            </>)}

            {s.status === "open" && usable && (
              <>
                {s.kind === "new_field" && s.target.section_key && (
                  <label className="inline-check small">
                    <input type="checkbox" checked={!unbound.has(s.id)}
                      onChange={() => setUnbound((prev) => {
                        const next = new Set(prev);
                        if (next.has(s.id)) next.delete(s.id);
                        else next.add(s.id);
                        return next;
                      })} />
                    Also add it to {nameOf(draft, s.target)}
                  </label>
                )}

                {paying === s.id && (
                  <p className="warn">
                    Accepting the first change in this review costs
                    ${(price / 100).toFixed(2)}. Every further change you
                    accept in it is free.
                  </p>
                )}

                <div className="form-actions">
                  <button disabled={!!busy || (edits[s.id] !== undefined
                                               && !edits[s.id].trim())}
                          onClick={() => accept(s, group)}>
                    {paying === s.id
                      ? `Accept and pay $${(price / 100).toFixed(2)}`
                      : "Accept"}
                  </button>
                  {/* The person's own wording, before accepting. Accept then
                      writes this instead of the suggestion; the rest of the
                      field or section is written back as it was. */}
                  {EDITABLE.has(s.kind) && typeof s.proposed === "string"
                    && paying !== s.id && (edits[s.id] === undefined ? (
                    <a className="secondary" onClick={() => setEdits(
                      (x) => ({ ...x, [s.id]: s.proposed as string }))}>
                      Edit
                    </a>
                  ) : (
                    <a className="secondary" onClick={() => setEdits((x) => {
                      const next = { ...x };
                      delete next[s.id];
                      return next;
                    })}>
                      Undo edit
                    </a>
                  ))}
                  {paying === s.id && (
                    <a className="secondary" onClick={() => setPaying(null)}>
                      Cancel
                    </a>
                  )}
                  {aside ? (
                    <a className="secondary"
                       onClick={() => dismiss([s.id], false)}>Restore</a>
                  ) : paying !== s.id && (
                    <a className="secondary"
                       onClick={() => dismiss([s.id], true)}>Set aside</a>
                  )}
                </div>
              </>
            )}
          </>
        )}

        {notes[s.id] && <p className="muted small">{notes[s.id]}</p>}
      </div>
    );
  };

  const setAside = suggestions.filter(
    (s) => dismissed.has(s.id) && s.status === "open").length;

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <aside className="panel" onClick={(e) => e.stopPropagation()}
             onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
        <div className="panel-head">
          {/* CLOSE AND END REVIEW ARE DIFFERENT ACTS (REV-01, "Close and End
              review"). Close - and Escape, and a click outside - only shuts
              this drawer: nothing is sent, the session stays open, and
              opening AI Review again in this tab resumes it. End review, in
              the toolbar below, closes the session on the server: nothing
              more can be accepted or answered in it, and this tab forgets it
              and what was set aside. */}
          <a className="panel-close" onClick={onClose}>Close</a>
          <h3>AI Review</h3>
          <p className="muted small">
            The draft is read and changes are suggested. Nothing is written
            until you accept it, and nothing reaches a memorandum until you
            publish.
          </p>
          {error && <p className="error">{error}</p>}
          {busy && <Working what={busy} />}

          {review && review.status === "ready" && (
            <div className="filters">
              <span className="muted small">
                {suggestions.length} suggestions
                {review.parts.some((p) => p.cut_off)
                  && " · one part was cut off and may be incomplete"}
              </span>
              {setAside > 0 && (
                <a className="small"
                   onClick={() => setShowDismissed(!showDismissed)}>
                  {showDismissed ? "Hide" : "Show"} {setAside} set aside
                </a>
              )}
              <a className="small" onClick={end}>End review</a>
            </div>
          )}
        </div>

        <div className="panel-body">
          {!session && (
            <div className="form">
              <p>
                The review reads every fact, document type and section in the
                draft and says what it would change. It takes a few minutes.
              </p>
              <div className="form-actions">
                <button disabled={!!busy} onClick={start}>
                  Review the draft
                </button>
              </div>
            </div>
          )}

          {session && !review && <Working what="Opening the review" />}

          {review && ["starting", "reading"].includes(review.status) && (
            <Working what={review.parts_total
              ? `Reading part ${Math.min(review.parts_done + 1,
                  review.parts_total)} of ${review.parts_total}`
              : "Reading the draft"} />
          )}

          {review && !["starting", "reading", "ready"].includes(review.status)
            && (
            <div className="revision-note fatal">
              <strong>The review did not finish.</strong>
              <p>{review.reason}</p>
              <a className="secondary" onClick={() => { forget(); }}>
                Start again
              </a>
            </div>
          )}

          {review?.expired && (
            <p className="warn">
              This review is more than a day old, so nothing more can be
              accepted from it. End it and start another.
            </p>
          )}

          {review?.status === "ready" && suggestions.length === 0 && (
            <p className="muted">Nothing to suggest.</p>
          )}

          {groups.map((g) => {
            const shown = g.items.filter((s) => showDismissed
              || !(dismissed.has(s.id) && s.status === "open"));
            if (shown.length === 0) return null;
            const head = g.items.find((s) => !s.from_question) ?? g.items[0];
            return (
              <div key={g.key}>
                <h4>{nameOf(draft, head.target)}</h4>
                {g.items.filter((s) => s.kind !== "question").length > 1 && (
                  <p className="muted small">
                    These are about the same thing. Accepting one sets the
                    others aside; you can restore them.
                  </p>
                )}
                {g.items.map((s) => card(s, g))}
              </div>
            );
          })}
        </div>
      </aside>
    </div>
  );
}
