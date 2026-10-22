import { useEffect, useState } from "react";
import { api, type Offer } from "./api";
import { Working } from "./shell";
import { useRole } from "./upgrade";
import { activeName, useWorkspace } from "./workspace";

/**
 * The Catalogue: every memorandum this tenant writes, and the three ways to
 * add another.
 *
 * WAS A PANEL, IS A PAGE. This was a fly-out from the rail headed "Configure a
 * report", where the memoranda were behind an "Open an existing report" option
 * - a list two clicks deep, in a box 320 pixels wide, that closed if you
 * looked away from it. They are the tenant's own work and the reason for the
 * screen, so they are the screen. The option that led to them is gone with the
 * panel; what is left are the three ways to add one.
 *
 * NOTHING HERE PUBLISHES. Every route from this page ends in the draft. That
 * is the same promise the ARQEDIA chooser makes with stopAtDraft, and the
 * reason it can be made from here at all: publishing ships the whole draft, so
 * it is never something a person does by side effect while adding a report.
 */

/** A draft to work in: one with only a published revision opens a copy of
 *  it. False where there is nothing configured at all, and the caller sends
 *  the person to Get started.
 *
 *  THE BASE IS NOT FORKED HERE ANY MORE (PACK-01). Forking it makes a
 *  workspace, which needs a name, and this page has nowhere to ask for one -
 *  Get started does, and is the one door. Memoranda were never forked here:
 *  that is the ARQEDIA chooser, where there is room to say what each one
 *  contains. */
async function ensureDraft(): Promise<boolean> {
  const state = await api.configState();
  if (!state.draft && state.revisions.length === 0) return false;
  if (!state.draft) await api.openDraft();
  return true;
}

/** An empty report with one untitled section, in the open draft; its key.
 *  Numbered where an untitled report already exists, because saving the same
 *  key again would rename that one rather than add another. Shared with Get
 *  started, which starts a new workspace this way (PACK-01). */
export async function untitledReport(): Promise<string> {
  const taken = new Set((await api.draft()).templates.map((t) => t.key));
  let n = 1;
  while (taken.has(n === 1 ? "untitled-report" : `untitled-report-${n}`)) n++;
  const key = n === 1 ? "untitled-report" : `untitled-report-${n}`;
  await api.saveTemplate({ key, label: n === 1 ? "Untitled report" : `Untitled report ${n}` });
  await api.saveSection({ template_key: key, key: "untitled-section", numeral: "I",
                          title: "Untitled section", kind: "extract", prompt: "",
                          sort_order: 1 });
  return key;
}

/** How a report of the tenant's own is started: empty, or read from one
 *  they already write. */
export type OwnStart = "scratch" | "report";

function errorText(err: unknown) {
  let text = String((err as Error)?.message ?? err);
  try { text = JSON.parse(text).error ?? text; } catch { /* as it came */ }
  return text;
}

type Row = { key: string; label: string };

export function CatalogueView({ curator, onOpened }: {
  curator: boolean;
  onOpened: (to: string, state?: unknown) => void;
}) {
  const [reports, setReports] = useState<Row[] | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  // Why the page could not be read, apart from `error`, which an action
  // clears. The list is left null rather than emptied: [] would say "Nothing
  // yet" about a list nobody has seen.
  const [loadError, setLoadError] = useState("");

  // The curator's half. published is the memoranda of the revision in use -
  // what can be offered, which is never the draft - and ticked is what the
  // marks say today, edited here until it is saved.
  const [offer, setOffer] = useState<Offer | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [published, setPublished] = useState<Row[]>([]);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [saved, setSaved] = useState("");
  // Marked memoranda the revision in use does not hold. They have no box to
  // untick, so they are left out of the ticks and named instead: sent, they
  // made the server refuse the whole save ("revision 30 does not hold ...").
  const [dropped, setDropped] = useState<string[]>([]);

  // The memoranda in the draft where one is open, since that is what will be
  // edited; otherwise the live revision's. Read once, when the page opens.
  useEffect(() => {
    let gone = false;
    (async () => {
      try {
        const state = await api.configState();
        const found = state.draft
          ? (await api.draft()).templates
          : state.revisions.length ? (await api.templates()).templates : [];
        if (gone) return;
        setReports(found.map((t) => ({ key: t.key, label: t.label || t.key })));
        setActive(state.active_revision ?? null);

        // The published revision's memoranda, read separately from the list
        // above: that one follows the draft when there is one, and a draft is
        // the one thing that cannot be offered.
        if (curator) {
          const [marks, live] = await Promise.all([
            api.offer(), api.templates(),
          ]);
          if (gone) return;
          setOffer(marks);
          setPublished(live.templates.map(
            (t) => ({ key: t.key, label: t.label || t.key })));
          const held = new Set(live.templates.map((t) => t.key));
          setTicked(new Set(marks.templates.filter((k) => held.has(k))));
          setDropped(marks.templates.filter((k) => !held.has(k)));
        }
      } catch (err) {
        if (!gone) setLoadError(errorText(err));
      }
    })();
    return () => { gone = true; };
  }, [curator]);

  async function run(what: string, fn: () => Promise<void>) {
    if (busy) return;
    setBusy(what);
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy("");
    }
  }

  const open = (key: string) => run("Opening", async () => {
    if (!(await ensureDraft())) { onOpened("/welcome"); return; }
    onOpened(`/configure?report=${encodeURIComponent(key)}`);
  });

  // Ours, rather than theirs. What is on offer is already shown by the ARQEDIA
  // chooser - the same list, the same headings, the same "already yours"
  // marker - so this sends a person there rather than building a second list
  // that drifts from it. stopAtDraft: taking one from here adds it to the
  // draft and publishes nothing.
  const ours = () => onOpened("/welcome", { stopAtDraft: true });

  // An empty report with one untitled section, in this workspace.
  //
  // NOTHING CONFIGURED YET: Get started, which asks for the workspace's name
  // and offers this same route, already chosen (PACK-01). The base is not
  // forked here - it makes a workspace, and this page has nowhere to name
  // one.
  const scratch = () => run("Creating", async () => {
    if (!(await ensureDraft())) {
      onOpened("/welcome", { start: "scratch" as OwnStart });
      return;
    }
    const key = await untitledReport();
    onOpened(`/configure?report=${key}&part=sections`);
  });

  // A report of the person's own: the proposer page, which carries its own
  // upload (UX-21). No file dialog fires from here.
  const fromReport = () => run("Opening", async () => {
    if (!(await ensureDraft())) {
      onOpened("/welcome", { start: "report" as OwnStart });
      return;
    }
    onOpened("/configure", { propose: true });
  });

  // WHICH WORKSPACE, asked when a person's own report is begun (PACK-01).
  // This one, or a new one - which forks a base and so is an
  // administrator's. Asked only where a new one is possible: a member is
  // never offered a choice the server would refuse, and a tenant with
  // nothing yet makes its first workspace in Get started either way.
  const workspace = useWorkspace();
  const here = activeName(workspace);
  const mayAdd = useRole() === "admin" && workspace.workspaces.length > 0;
  const [asking, setAsking] = useState<OwnStart | null>(null);
  const begin = (how: OwnStart) => {
    if (!mayAdd) { (how === "scratch" ? scratch : fromReport)(); return; }
    setAsking(asking === how ? null : how);
  };
  const where = (how: OwnStart) => asking === how && (
    <p className="muted small">
      <a onClick={off(() => { setAsking(null);
                              (how === "scratch" ? scratch : fromReport)(); })}>
        In {here ?? "this workspace"}
      </a>
      {" · "}
      <a onClick={off(() => onOpened("/welcome",
                                     { newWorkspace: true, start: how }))}>
        In a new workspace
      </a>
    </p>
  );

  const off = (fn: () => void) => (busy ? undefined : fn);

  // --- the curator's half ---------------------------------------------------

  const toggle = (key: string) => {
    const next = new Set(ticked);
    if (next.has(key)) next.delete(key); else next.add(key);
    setTicked(next);
  };

  // Ticking, unticking and moving the offer to a newer revision are one call.
  // The revision saved is the one in use, which is the revision the ticks
  // above were read from - never the draft, which cannot be offered.
  const save = () => run("Saving", async () => {
    if (active === null) return;
    setSaved("");
    const result = await api.setOffer(active, Array.from(ticked));
    setOffer(await api.offer());
    setDropped([]);
    const said = [
      result.moved_from !== null
        ? `Moved from revision ${result.moved_from} to ${result.revision}.` : "",
      result.added.length ? `Added ${result.added.join(", ")}.` : "",
      result.removed.length ? `Took off ${result.removed.join(", ")}.` : "",
    ].filter(Boolean).join(" ");
    setSaved(said || "Saved. Nothing changed.");
  });

  const marked = offer?.revision ?? null;
  const moving = marked !== null && active !== null && marked !== active;
  const sameAsMarks = offer !== null
    && ticked.size === offer.templates.length
    && offer.templates.every((k) => ticked.has(k));

  return (
    <div>
      <h2>Report Catalogue</h2>
      <p className="muted">
        Every memorandum you write. Open one to change what it says, or add
        another below. A memorandum is layout over the facts you already hold,
        so adding one costs nothing until a document is filed against it.
      </p>

      {loadError && <p className="error">{loadError}</p>}
      {error && <p className="error">{error}</p>}

      {reports === null && !loadError && <p className="muted">Loading&hellip;</p>}
      {reports?.length === 0 && (
        <p className="muted">
          Nothing yet. Take one of ours, or start your own below.
        </p>
      )}

      {/* Rows, as Engagements lists engagements. The whole row is the target:
          a one-column table whose only link is the label would leave most of
          the row dead to the pointer. */}
      {reports && reports.length > 0 && (
        <table>
          <tbody>
            {reports.map((r) => (
              <tr key={r.key} onClick={off(() => open(r.key))}>
                <td><a>{r.label}</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Add another</h3>

      <p>
        <a onClick={off(ours)}>Select an ARQEDIA Template</a>
      </p>
      <p className="muted small">
        One of the memoranda we write, laid out over the facts you hold. It
        goes into your draft; publishing is a separate step.
      </p>

      <p>
        <a onClick={off(() => begin("scratch"))}>Create from scratch</a>
      </p>
      {where("scratch")}
      <p className="muted small">
        An empty memorandum. You write the sections and say what each one
        renders.
      </p>

      <p>
        <a onClick={off(() => begin("report"))}>
          Create from a report you already write
        </a>
      </p>
      {where("report")}
      <p className="muted small">
        Give us a report you already write. We read its shape and put a
        configuration to you to correct &mdash; the file itself is read once
        and deleted.
      </p>

      {/* The ARQEDIA workspace only. The server refuses these two calls to
          everybody else; this decides what is drawn, which is not the same
          thing and is not a control. */}
      {curator && (
        <>
          <h3>What ARQEDIA offers</h3>

          {/* A failed read never sets the offer, so without the first arm
              this said Loading for ever. The error itself is at the top. */}
          {offer === null && loadError ? (
            <p className="muted">Not read &mdash; see the error above.</p>
          ) : offer === null ? (
            <p className="muted">Loading&hellip;</p>
          ) : (
            <>
              <p className="muted small">
                {marked === null
                  ? "Nothing is on offer. A new tenant has no base to fork "
                    + "and no memorandum to take."
                  : `Offered from revision ${marked}`
                    + (offer.marked_by ? `, marked by ${offer.marked_by}` : "")
                    + "."}
              </p>

              {/* The base is not ticked separately. It is this revision's
                  base, always: a memorandum takes its missing facts from the
                  base on offer, so one marked at another revision refuses at
                  the customer rather than here. */}
              <p className="muted small">
                Ticking one offers it to every new tenant, from the revision
                in use. The facts behind it go with it &mdash; the base is
                this revision's base and is not a separate choice.
              </p>

              {moving && (
                <p className="working-note">
                  The offer is on revision {marked} and revision {active} is
                  in use. Saving moves the whole catalogue to revision{" "}
                  {active}, memoranda and base together. Marks cannot span two
                  revisions.
                </p>
              )}

              {dropped.length > 0 && (
                <p className="working-note">
                  Revision {active} does not hold {dropped.join(", ")}.{" "}
                  {dropped.length === 1 ? "It comes" : "They come"} off the
                  offer when this is saved.
                </p>
              )}

              {published.length === 0 && (
                <p className="muted">
                  Revision {active} holds no memoranda to offer.
                </p>
              )}

              {published.map((t) => (
                <label className="template-row" key={t.key}>
                  <input type="checkbox" checked={ticked.has(t.key)}
                         onChange={() => toggle(t.key)} />
                  <span className="template-name">{t.label}</span>
                  {!offer.templates.includes(t.key) && ticked.has(t.key) && (
                    <span className="muted small">new</span>
                  )}
                </label>
              ))}

              {saved && <p className="working-note">{saved}</p>}

              <div className="form-actions">
                <button
                  disabled={!!busy || active === null || ticked.size === 0
                            || (sameAsMarks && !moving)}
                  onClick={save}>
                  {moving
                    ? `Move the offer to revision ${active}`
                    : "Save the catalogue"}
                </button>
                {ticked.size === 0 && (
                  <span className="muted small">
                    Tick at least one. An empty catalogue leaves a new tenant
                    with nothing to take.
                  </span>
                )}
              </div>
            </>
          )}
        </>
      )}

      {busy && <Working what={busy} />}
    </div>
  );
}
