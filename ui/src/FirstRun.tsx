import { useEffect, useState } from "react";
import { api, type Pack, type TemplatePack, type Validation } from "./api";
import { Working } from "./shell";
import { UpgradePrompt } from "./upgrade";
import { useWorkspace, workspacesChanged } from "./workspace";
import { untitledReport, type OwnStart } from "./Catalogue";
import type { Report } from "./Welcome";
// The backbone, from the Word draft of this copy (Draft copy.docx, 6
// November 2026): workspace, document types, expected facts, templates.
import backbone from "./assets/backbone.png";

/**
 * A new tenant's first sign-in, as a sequence of step panels (onboarding
 * steps, 6 November 2026). One panel at a time, each with Next at its foot:
 *
 *   I    How ARQEDIA works
 *   II   Engagements                          Next - get started
 *   III  A  How to start
 *        B  Create a workspace                own configuration only
 *        C  ARQEDIA workspaces, one or more   ARQEDIA's only
 *        D  Report templates for each chosen  ARQEDIA's only
 *
 * FIRST SIGN-IN ONLY. Add a workspace from the header, the rail's panel and
 * the Catalogue's routes keep the single form in Welcome.tsx.
 *
 * C NAMES EACH WORKSPACE AFTER OURS (decided 6 November 2026, amending the
 * decision of 22 October that a name is never filled in). At first sign-in
 * the tenant holds no workspace, so no name can clash. An offering with no
 * name cannot be taken: the server refuses a fork without one.
 *
 * C KEEPS TO THE PLAN'S LIMIT AND OFFERS AN UPGRADE (decided 6 November).
 * The limit is the shell's display copy; the server still refuses past it.
 *
 * D's NEXT DOES THE WORK, per chosen workspace: fork from our offering under
 * its name, take each ticked template, publish - the same three calls the
 * single form makes, once each. Done in reverse, so the first chosen is the
 * one left active and the one the configuration screen reports on.
 *
 * PRESSED AGAIN AFTER A FAILURE, nothing is made twice: a workspace already
 * forked is adopted rather than forked again, and one already published is
 * passed over. fork_template skips what is already there.
 */
export function FirstRunSteps({ stopAtDraft, onStarted, onOpened }: {
  stopAtDraft: boolean;
  onStarted: (report: Report) => void;
  onOpened: (to: string, state?: unknown) => void;
}) {
  const workspace = useWorkspace();
  const [step, setStep] = useState<"I" | "II" | "A" | "B" | "C" | "D">("I");
  const [route, setRoute] = useState<"ours" | OwnStart | null>(null);
  const [name, setName] = useState("");
  const [offerings, setOfferings] = useState<Pack[] | null>(null);
  // Chosen offerings, in the order they were ticked.
  const [chosen, setChosen] = useState<number[]>([]);
  const [packs, setPacks] = useState<Record<number, TemplatePack[]>>({});
  const [ticked, setTicked] = useState<Record<number, Set<string>>>({});
  // What a press has already made, so a second press makes nothing twice.
  const [made, setMade] = useState<Record<number, number>>({});
  const [finished, setFinished] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [refused, setRefused] = useState<string[]>([]);

  useEffect(() => {
    api.packs()
      .then((o) => setOfferings(o.packs))
      .catch((err) => setError(message(err)));
  }, []);

  function message(err: unknown) {
    let text = String((err as Error)?.message ?? err);
    try { text = JSON.parse(text).error ?? text; } catch { /* as it came */ }
    return text;
  }

  // The plan's limit; null is none. The tenant holds nothing yet.
  const limit = workspace.limit;
  const atLimit = limit !== null && chosen.length >= limit;

  const pick = (id: number) => {
    if (chosen.includes(id)) setChosen(chosen.filter((c) => c !== id));
    else if (!atLimit) {
      setChosen([...chosen, id]);
      // Its templates, read once, when it is first chosen.
      if (!packs[id]) {
        api.templatesAvailable(id)
          .then((t) => setPacks((p) => ({ ...p, [id]: t.templates })))
          .catch((err) => setError(message(err)));
      }
    }
  };

  const tick = (id: number, key: string) => {
    const next = new Set(ticked[id] ?? []);
    if (next.has(key)) next.delete(key); else next.add(key);
    setTicked({ ...ticked, [id]: next });
  };

  const everyTicked = chosen.length > 0
    && chosen.every((id) => (ticked[id]?.size ?? 0) > 0);

  /** B: an empty workspace of the tenant's own, then the configuration
   *  screen - as the single form's startOwn. */
  async function startOwn(how: OwnStart) {
    setError("");
    if (!name.trim()) return;
    try {
      setBusy("Setting up " + name.trim());
      const ws = await api.newWorkspace(name.trim());
      workspace.adopt(ws.workspace_id);
      workspacesChanged();
      if (how === "scratch") {
        const key = await untitledReport();
        onOpened(`/configure?report=${key}&part=sections`);
      } else {
        onOpened("/configure", { propose: true });
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  /** D: each chosen workspace made, filled and published. */
  async function startOurs() {
    setError("");
    setRefused([]);
    if (!everyTicked || !offerings) return;

    let report: Report | null = null;
    const done = new Set(finished);
    const have = { ...made };

    try {
      for (const id of [...chosen].reverse()) {
        const offering = offerings.find((o) => o.workspace_id === id);
        const label = offering?.name ?? "";
        const wanted = (packs[id] ?? [])
          .filter((p) => ticked[id]?.has(p.pack_key));

        if (have[id] === undefined) {
          setBusy("Setting up " + label);
          const ws = await api.forkBase(label, id);
          have[id] = ws.workspace_id;
          setMade({ ...have });
        }
        // Active before anything is taken into it: every call from here
        // carries this workspace.
        workspace.adopt(have[id]);
        workspacesChanged();

        const added = {
          categories: [] as string[], document_types: [] as string[],
          schemas: [] as string[], facts: [] as string[],
        };
        let wasOpen = false;
        let revision: number | null = null;

        if (!done.has(id)) {
          for (const pack of wanted) {
            setBusy(label + ": adding " + pack.label);
            const result = await api.forkTemplate(pack.pack_key);
            wasOpen = wasOpen || result.draft_was_open;
            added.categories.push(...result.added.categories);
            added.document_types.push(...result.added.document_types);
            added.schemas.push(...result.added.schemas);
            added.facts.push(...result.added.facts);
          }

          if (!stopAtDraft) {
            setBusy(label + ": publishing");
            const published: {
              published?: boolean; revision?: number; validation?: Validation;
            } = await api.publish(
              "Get started: " + wanted.map((p) => p.label).join(", "));
            if (published && published.published === false) {
              setRefused((published.validation?.fatal ?? [])
                .map((f) => label + ": " + f.detail));
              setBusy("");
              return;
            }
            revision = published?.revision ?? null;
          }
          done.add(id);
          setFinished(new Set(done));
        }

        report = {
          templates: wanted.map((p) => p.label),
          added: {
            categories: Array.from(new Set(added.categories)),
            document_types: Array.from(new Set(added.document_types)),
            schemas: Array.from(new Set(added.schemas)),
            facts: Array.from(new Set(added.facts)),
          },
          draft_was_open: wasOpen,
          revision,
        };
      }
      if (report) onStarted(report);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  const back = (to: typeof step) => (
    <a className="secondary" onClick={busy ? undefined : () => setStep(to)}>
      Back
    </a>
  );

  return (
    <div className="welcome">
      {step === "I" && (
        <section className="step-panel">
          <p className="muted small">Draft copy</p>
          <h2>Welcome to ARQEDIA</h2>
          <p>
            ARQEDIA allows you to Upload Documents &rarr; Extract Facts &rarr;
            Produce Reports from those Facts
          </p>
          <img className="step-figure" src={backbone}
               alt="A workspace holds many document types; each document type
                    holds many expected facts; report templates each draw on
                    many facts." />

          <h3>I. How ARQEDIA works &ndash; the backbone</h3>
          <ol>
            <li>
              <strong>WORKSPACE:</strong> A WORKSPACE represents a set of
              documents, facts and report configurations related to specific
              industry or sector. If you work in more than one distinct space
              (e.g. Real Estate and Trade Finance), you will set up a workspace
              for each. ARQEDIA offers several standardized workspaces with
              predefined settings.
            </li>
            <li>
              <strong>DOCUMENT TYPES:</strong> In each workspace you define the
              types of documents you expect to encounter. For a Trade Finance
              workspace this might include i) formation documents of a
              borrower, ii) trade finance agreements, iii) market pricing data
              etc. For a Commercial Real Estate Acquisition workspace,
              documents might include property surveys, market and sub-market
              reports, rent-rolls and financial projections. Each of these
              industry specific documents are expected to contain specific
              facts.
            </li>
            <li>
              <strong>FACTS:</strong> The heart of ARQEDIA&rsquo;s approach are
              the extracted facts related to a given ENGAGEMENT (see section II
              below). Facts are specified and defined in each workspace
              configuration and when extracted they are stored in a relational
              database, tracked back to the ENGAGEMENT documents and filed by
              workspace and user. These facts are available for use in any
              report template within a given workspace.
            </li>
            <li>
              <strong>REPORT TEMPLATES:</strong> Report TEMPLATES are set up in
              a WORKSPACE and become available to any ENGAGEMENT within that
              WORKSPACE. Each section is composed of selected facts.
            </li>
          </ol>
          <p>
            <strong>Published Configurations.</strong> A user can edit a
            workspace configuration, adding or removing available document
            types, expected facts and how a report reads. Once edits are made,
            the configured workspace may be published, saving all changes and
            upgrades.
          </p>

          <div className="form-actions">
            <button onClick={() => setStep("II")}>Next</button>
          </div>
        </section>
      )}

      {step === "II" && (
        <section className="step-panel">
          <h2>II. Engagements</h2>
          <p>
            An ENGAGEMENT represents a client or project the user is working
            on. It will have separate documents containing information related
            solely to that ENGAGEMENT. These documents can be filed with
            ARQEDIA within the selected WORKSPACE, and they will be categorized
            by the document types configured in that WORKSPACE, and the
            specified facts will be extracted and stored, related to the
            ENGAGEMENT information filed. Reports are then generated with the
            WORKSPACE templates, using the ENGAGEMENT level information.
          </p>
          <p>
            <strong>Segregation of Data:</strong> No information related to an
            ENGAGEMENT, filed documents and extracted facts, can be accessed
            into another ENGAGEMENT.
          </p>

          <div className="form-actions">
            <button onClick={() => setStep("A")}>Next &ndash; get started</button>
            {back("I")}
          </div>
        </section>
      )}

      {step === "A" && (
        <section className="step-panel">
          <h2>III. How to start</h2>
          <h3>A. Select how you want to get started</h3>
          <label className="inline-check">
            <input type="radio" name="route" checked={route === "ours"}
                   onChange={() => setRoute("ours")} />
            Use an ARQEDIA configuration
          </label>
          <label className="inline-check">
            <input type="radio" name="route" checked={route === "scratch"}
                   onChange={() => setRoute("scratch")} />
            Start your own configuration from scratch
          </label>
          <label className="inline-check">
            <input type="radio" name="route" checked={route === "report"}
                   onChange={() => setRoute("report")} />
            Create a configuration from an existing report you already use
            (.pdf, .docx)
          </label>

          <div className="form-actions">
            <button disabled={route === null}
                    onClick={() => setStep(route === "ours" ? "C" : "B")}>
              Next
            </button>
            {back("II")}
          </div>
        </section>
      )}

      {step === "B" && route !== null && route !== "ours" && (
        <section className="step-panel">
          <h2>III. How to start</h2>
          <h3>B. Create a workspace</h3>
          <input value={name} maxLength={128}
                 placeholder="For example, Trade Finance"
                 aria-label="Workspace name"
                 onChange={(e) => setName(e.target.value)} />
          <p className="muted small">
            What it is for, in a few words. You can hold several &mdash; one
            per line of business &mdash; and choose between them at the top of
            the page.
          </p>

          {error && <p className="error">{error}</p>}
          {busy && <Working what={busy} />}

          <div className="form-actions">
            <button disabled={!!busy || !name.trim()}
                    onClick={() => startOwn(route)}>
              Next
            </button>
            {back("A")}
          </div>
        </section>
      )}

      {step === "C" && (
        <section className="step-panel">
          <h2>III. How to start</h2>
          <h3>C. Select a standardized ARQEDIA workspace</h3>

          {offerings === null && !error && <p className="muted">Loading&hellip;</p>}
          {offerings?.length === 0 && (
            <p className="muted">Nothing of ours is on offer yet.</p>
          )}
          {offerings?.map((o) => {
            const on = chosen.includes(o.workspace_id);
            const closed = !o.name || (!on && atLimit);
            return (
              <label className="inline-check" key={o.workspace_id}>
                <input type="checkbox" checked={on} disabled={closed}
                       onChange={() => pick(o.workspace_id)} />
                {o.name ?? "Unnamed"}{" "}
                <span className="muted small">
                  {o.document_types}{" "}
                  {o.document_types === 1 ? "document type" : "document types"}
                  {" "}&middot; {o.fields} {o.fields === 1 ? "fact" : "facts"}
                </span>
              </label>
            );
          })}

          {atLimit && limit !== null
            && (offerings?.length ?? 0) > chosen.length && (
            <UpgradePrompt>
              Your plan holds {limit}{" "}
              {limit === 1 ? "workspace" : "workspaces"}. A bigger plan is how
              a tenant gets more.
            </UpgradePrompt>
          )}

          {error && <p className="error">{error}</p>}

          <div className="form-actions">
            <button disabled={chosen.length === 0} onClick={() => setStep("D")}>
              Next
            </button>
            {back("A")}
          </div>
        </section>
      )}

      {step === "D" && (
        <section className="step-panel">
          <h2>III. How to start</h2>
          <h3>D. Choose which report template for each ARQEDIA workspace
            selected</h3>

          {chosen.map((id) => {
            const offering = offerings?.find((o) => o.workspace_id === id);
            const list = packs[id];
            return (
              <div key={id}>
                <h4>{offering?.name}</h4>
                {list === undefined && !error && (
                  <p className="muted">Loading&hellip;</p>
                )}
                {list?.length === 0 && (
                  <p className="muted">That workspace has no report templates
                    on offer.</p>
                )}
                {list?.map((pack) => (
                  <label className="template-row" key={pack.pack_key}>
                    <input type="checkbox"
                           checked={ticked[id]?.has(pack.pack_key) ?? false}
                           disabled={finished.has(id)}
                           onChange={() => tick(id, pack.pack_key)} />
                    <span className="template-name">{pack.label}</span>
                    <span className="template-sections" tabIndex={0}>
                      <span className="count">
                        {pack.sections}{" "}
                        {pack.sections === 1 ? "section" : "sections"}
                      </span>
                      <span className="sections-pop">
                        {pack.section_titles.map((title, i) => (
                          <span key={i}>{title}</span>
                        ))}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            );
          })}

          {!everyTicked && (
            <p className="working-note">
              <strong>Nothing is set up until you do this.</strong> Until a
              memorandum is chosen and published, your workspace has no facts
              and no document types: an upload cannot be given a type, and
              nothing can be filed or generated. Leaving now costs nothing and
              creates nothing &mdash; you come back to this screen from
              Template Catalogue.
            </p>
          )}

          {error && <p className="error">{error}</p>}
          {refused.length > 0 && (
            <div className="revision-note fatal">
              <strong>The templates are in the draft, but it cannot be
                published yet.</strong>
              <ul>
                {refused.map((detail, i) => <li key={i}>{detail}</li>)}
              </ul>
            </div>
          )}
          {stopAtDraft && (
            <p className="working-note">
              What you tick goes into each workspace&rsquo;s draft. Nothing is
              published: publishing is a separate step, on the configuration
              screen.
            </p>
          )}
          {busy && <Working what={busy} />}

          <div className="form-actions">
            <button disabled={!!busy || !everyTicked} onClick={startOurs}>
              Next
            </button>
            {/* Not back to C once anything is made: a workspace forked
                cannot be unchosen here. */}
            {Object.keys(made).length === 0 && back("C")}
          </div>
        </section>
      )}
    </div>
  );
}
