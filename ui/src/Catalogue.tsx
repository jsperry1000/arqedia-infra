import { useEffect, useState } from "react";
import { api } from "./api";
import { Working } from "./shell";

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

/** A draft to work in. A tenant with nothing configured takes the base first;
 *  one with only a published revision opens a copy of it.
 *
 *  THE BASE IS TAKEN BY KEY. This forked whatever packs() returned first, and
 *  packs() sorted by revision descending - so adding a pack silently changed
 *  what a new tenant got. Memoranda are not forked here at all: that is the
 *  ARQEDIA chooser, where there is room to say what each one contains. */
async function ensureDraft() {
  let state = await api.configState();
  if (!state.draft && state.revisions.length === 0) {
    await api.forkBase();
    state = await api.configState();
  }
  if (!state.draft) await api.openDraft();
}

function errorText(err: unknown) {
  let text = String((err as Error)?.message ?? err);
  try { text = JSON.parse(text).error ?? text; } catch { /* as it came */ }
  return text;
}

export function CatalogueView({ onOpened }: {
  onOpened: (to: string, state?: unknown) => void;
}) {
  const [reports, setReports] = useState<{ key: string; label: string }[] | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

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
        if (!gone) {
          setReports(found.map((t) => ({ key: t.key, label: t.label || t.key })));
        }
      } catch (err) {
        if (!gone) { setError(errorText(err)); setReports([]); }
      }
    })();
    return () => { gone = true; };
  }, []);

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
    await ensureDraft();
    onOpened(`/configure?report=${encodeURIComponent(key)}`);
  });

  // Ours, rather than theirs. What is on offer is already shown by the ARQEDIA
  // chooser - the same list, the same headings, the same "already yours"
  // marker - so this sends a person there rather than building a second list
  // that drifts from it. stopAtDraft: taking one from here adds it to the
  // draft and publishes nothing.
  const ours = () => onOpened("/welcome", { stopAtDraft: true });

  // An empty report with one untitled section. Numbered where an untitled
  // report already exists, because saving the same key again would rename
  // that one rather than add another.
  const scratch = () => run("Creating", async () => {
    await ensureDraft();
    const taken = new Set((await api.draft()).templates.map((t) => t.key));
    let n = 1;
    while (taken.has(n === 1 ? "untitled-report" : `untitled-report-${n}`)) n++;
    const key = n === 1 ? "untitled-report" : `untitled-report-${n}`;
    await api.saveTemplate({ key, label: n === 1 ? "Untitled report" : `Untitled report ${n}` });
    await api.saveSection({ template_key: key, key: "untitled-section", numeral: "I",
                            title: "Untitled section", kind: "extract", prompt: "",
                            sort_order: 1 });
    onOpened(`/configure?report=${key}&part=sections`);
  });

  // A report of the person's own: the proposer page, which carries its own
  // upload (UX-21). No file dialog fires from here.
  const fromReport = () => run("Opening", async () => {
    await ensureDraft();
    onOpened("/configure", { propose: true });
  });

  const off = (fn: () => void) => (busy ? undefined : fn);

  return (
    <div>
      <h2>Catalogue</h2>
      <p className="muted">
        Every memorandum you write. Open one to change what it says, or add
        another below. A memorandum is layout over the facts you already hold,
        so adding one costs nothing until a document is filed against it.
      </p>

      {error && <p className="error">{error}</p>}

      {reports === null && <p className="muted">Loading&hellip;</p>}
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
        <a onClick={off(scratch)}>Create from scratch</a>
      </p>
      <p className="muted small">
        An empty memorandum. You write the sections and say what each one
        renders.
      </p>

      <p>
        <a onClick={off(fromReport)}>Create from a report you already write</a>
      </p>
      <p className="muted small">
        Give us a report you already write. We read its shape and put a
        configuration to you to correct &mdash; the file itself is read once
        and deleted.
      </p>

      {busy && <Working what={busy} />}
    </div>
  );
}
