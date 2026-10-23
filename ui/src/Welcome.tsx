import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  api, type ConfigState, type Pack, type TemplatePack, type Validation,
} from "./api";
import { Working } from "./shell";
import { SEATS, UpgradePrompt } from "./upgrade";
import { useWorkspace, workspacesChanged } from "./workspace";
import { untitledReport, type OwnStart } from "./Catalogue";

/**
 * Get started (TPL-02 step 3). The front door, and where memoranda are chosen.
 *
 * One base carries the facts, the document types and the routing between them.
 * A template is a memorandum laid out over that base, and a tenant may take as
 * many as they want - at first run, or six months later. So this screen is
 * both: an introduction for somebody who has just signed up, and a way to add
 * another memorandum for somebody who has been here a year.
 *
 * WHAT PRESSING IT DOES. The base is forked only where the tenant has no
 * published revision, then each ticked template, then one publish. The base
 * step is conditional on purpose: fork_base refuses a tenant that already has
 * a published revision, so an unconditional call would make a second press
 * fail at the first step. Conditional, every half-finished state left by a
 * failure is recoverable by pressing the button again - fork_template skips
 * what is already there, and publish refuses rather than throws.
 *
 * EXCEPT WITH stopAtDraft. Reached from the rail's panel or the first-run
 * screen, the publish is not made and the screen says so. Publish is not
 * selective - it ships the whole draft - so taking a memorandum would ship
 * whatever else that person had in there, unfinished, without them choosing
 * to. Signing up still arrives here without the flag and still publishes,
 * which is what makes a new tenant's first run one press: their draft holds
 * nothing but what they just ticked.
 *
 * NOTHING IS CHOSEN BY POSITION. Templates are taken by pack_key. What was
 * chosen at signup pre-ticks the list and decides nothing: that question was
 * asked with one line of description beside it, and this screen has room to
 * say what each memorandum actually contains.
 *
 * DRAFT COPY for the introduction, from ARQEDIA_UI_GUIDE_DRAFT.md.
 *
 * IT NAMES A WORKSPACE (PACK-01). Forking the base makes a workspace, and the
 * server refuses a fork without a name and invents none. So wherever this
 * press will make one - a new tenant's first run, and Add a workspace from
 * the header - the screen asks for the name first, empty, and holds the
 * button until it is given (decision of 22 October 2026). The workspace made
 * becomes the active one before anything is taken into it, so the
 * memoranda, and the publish, land there.
 *
 * THREE WAYS TO START ONE. One of our memoranda, as ever; or a report of the
 * tenant's own - empty, or read from one they already write - which goes on
 * to the configuration screen in the new workspace, exactly as the
 * Catalogue's two routes of the same name do in an existing one. Arriving
 * from either of those, the route is already chosen.
 *
 * WHICH OF OUR OFFERINGS (PACK-02). One of our memoranda comes from an
 * offering - Trade Finance, Real Estate - whose base the new workspace takes,
 * and whose memoranda its Catalogue offers from then on. Asked where there is
 * more than one; named where there is one. A report of the tenant's own takes
 * no offering at all: it starts from what the workspace holds, which is
 * nothing (settled item 7).
 */

/** What Get started did, handed to the configuration screen, which says so at
 *  the top. Somebody who presses one button and lands on an editor full of
 *  facts they did not write is owed an account of where they came from. */
export type Report = {
  templates: string[];
  added: {
    categories: string[];
    document_types: string[];
    schemas: string[];
    facts: string[];
  };
  draft_was_open: boolean;
  revision: number | null;
};

// NOTHING IS PRE-TICKED. This matched signup's answer against what we ship,
// loosely, because a display label is not a key. Signup stopped asking (see
// SignUp.tsx), so forked_pack is NULL for every tenant from now on and the
// match would never fire - dead code wearing the face of live code, which is
// worse than either. The list starts empty and the person chooses here, which
// is the whole point of the screen.

export function WelcomeView({ stopAtDraft = false, newWorkspace = false,
                             offering = false,
                             start: startWith, onStarted, onOpened }: {
  stopAtDraft?: boolean;
  /** Add a workspace, from the header: start a new one rather than add to
   *  the active one. */
  newWorkspace?: boolean;
  /** Add an OFFERING, in the ARQEDIA workspace (PACK-02). It starts empty -
   *  no base is forked, because the pack tenant forks from nobody - and is
   *  built by hand or from a report. One of our memoranda is not a route. */
  offering?: boolean;
  /** A report of the tenant's own, already chosen: from the Catalogue's
   *  "Create from scratch" or "Create from a report you already write". */
  start?: OwnStart;
  onStarted: (report: Report) => void;
  /** Where a report of the tenant's own goes on to: the configuration
   *  screen, in the workspace just made. */
  onOpened: (to: string, state?: unknown) => void;
}) {
  const navigate = useNavigate();
  const workspace = useWorkspace();
  // The new workspace's name. Empty, with an example as a placeholder only:
  // nothing is invented (decision of 22 October 2026).
  const [name, setName] = useState("");
  // How a workspace being made starts: one of ours, or one of their own. An
  // offering has no "ours" to start from.
  const [route, setRoute] = useState<"ours" | OwnStart>(
    startWith ?? (offering ? "scratch" : "ours"));
  const [state, setState] = useState<ConfigState | null>(null);
  const [packs, setPacks] = useState<TemplatePack[] | null>(null);
  // Our offerings, and the one a new workspace is taken from (PACK-02).
  const [offerings, setOfferings] = useState<Pack[] | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [refused, setRefused] = useState<string[]>([]);

  // A NEW TENANT'S FIRST RUN is a tenant with no workspace at all - not a
  // workspace with nothing published, which since PACK-02 is also an empty
  // workspace begun from a report of the tenant's own. Taken that way, Select
  // an ARQEDIA Template in one showed the new-tenant welcome and offered to
  // make another workspace (found walking PACK-02). Read once, as the screen
  // opens - the shell reads the workspaces before any screen is drawn - and
  // held: the list is read again the moment this screen makes one.
  const [firstRun] = useState(() => workspace.workspaces.length === 0);

  useEffect(() => {
    Promise.all([api.configState(), api.templatesAvailable(), api.packs()])
      .then(([s, t, o]) => {
        setState(s);
        // The active workspace's memoranda, unless this makes a workspace
        // from one of ours - then the chosen offering's, loaded below, and
        // this answer must not land on top of them.
        const making = newWorkspace || firstRun;
        if (!making || offering) setPacks(t.templates);
        setOfferings(o.packs);
        // One offering is the offering: nothing to choose.
        if (o.packs.length === 1) setChosen(o.packs[0].workspace_id);
      })
      .catch((err) => setError(message(err)));
  }, []);

  function message(err: unknown) {
    let text = String((err as Error)?.message ?? err);
    try { text = JSON.parse(text).error ?? text; } catch { /* as it came */ }
    return text;
  }

  const draftOpen = !!state?.draft;
  // This press makes a workspace: a tenant's first, or another one.
  const creating = newWorkspace || firstRun;
  // Taking ours into a workspace not yet made: the memoranda listed are the
  // chosen offering's, not the active workspace's (PACK-02).
  const fromOffering = creating && !offering;

  useEffect(() => {
    if (!fromOffering) return;
    setTicked(new Set());
    if (chosen === null) { setPacks([]); return; }
    setPacks(null);
    api.templatesAvailable(chosen)
      .then((t) => setPacks(t.templates))
      .catch((err) => setError(message(err)));
  }, [fromOffering, chosen]);

  const chosenOffering = offerings?.find((o) => o.workspace_id === chosen);

  /**
   * A new workspace started from a report of the tenant's own: EMPTY and
   * named, made active with its draft already open, and then the
   * configuration screen - on an empty report, or on the reader. Nothing is
   * forked and nothing published (PACK-02, settled item 7): it starts from
   * what the workspace holds, which is nothing. An offering is made the same
   * way.
   */
  async function startOwn(how: OwnStart) {
    setError("");
    if (!name.trim()) return;
    try {
      setBusy("Setting up " + name.trim());
      const made = await api.newWorkspace(name.trim());
      workspace.adopt(made.workspace_id);
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

  /**
   * A new workspace where this screen makes one, then each ticked template,
   * then one publish unless stopAtDraft says not to.
   *
   * THE SCREEN DECIDES WHETHER IT MAKES ONE, not "nothing published". The
   * fork used to follow an empty configuration, which was a new tenant and
   * nothing else; since PACK-02 an empty workspace begun from a report of
   * the tenant's own is empty too, and adding a memorandum to it would have
   * forked a whole new workspace instead.
   */
  async function start() {
    setError("");
    setRefused([]);
    const wanted = (packs ?? []).filter((p) => ticked.has(p.pack_key));
    if (wanted.length === 0 || (creating && !name.trim())) return;
    if (fromOffering && chosen === null) return;

    try {
      if (creating) {
        setBusy("Setting up " + name.trim());
        // From the chosen offering (PACK-02), which the workspace records.
        const made = await api.forkBase(name.trim(), chosen ?? undefined);
        // Active before anything is taken into it: every call from here
        // carries the new workspace, so the memoranda and the publish land
        // there and not in whichever was active before.
        workspace.adopt(made.workspace_id);
        workspacesChanged();
      }

      const added = {
        categories: [] as string[],
        document_types: [] as string[],
        schemas: [] as string[],
        facts: [] as string[],
      };
      let wasOpen = false;

      for (const pack of wanted) {
        setBusy("Adding " + pack.label);
        const result = await api.forkTemplate(pack.pack_key);
        wasOpen = wasOpen || result.draft_was_open;
        added.categories.push(...result.added.categories);
        added.document_types.push(...result.added.document_types);
        added.schemas.push(...result.added.schemas);
        added.facts.push(...result.added.facts);
      }

      // Null where nothing was published, which the configuration screen
      // already reads: it reports "are yours" without a revision number.
      let revision: number | null = null;

      if (!stopAtDraft) {
        setBusy("Publishing");
        // publish answers a refusal rather than throwing, so its shape is
        // spelled out here: a validation that failed is a thing to show, not
        // an error to swallow.
        const published: {
          published?: boolean; revision?: number; validation?: Validation;
        } = await api.publish(
          "Get started: " + wanted.map((p) => p.label).join(", "));

        // A refused publish is not an error and does not throw: the memoranda
        // are in the draft, and saying so beats a screen that looks broken.
        if (published && published.published === false) {
          setRefused((published.validation?.fatal ?? []).map((f) => f.detail));
          setBusy("");
          return;
        }
        revision = published?.revision ?? null;
      }

      onStarted({
        templates: wanted.map((p) => p.label),
        added: {
          categories: Array.from(new Set(added.categories)),
          document_types: Array.from(new Set(added.document_types)),
          schemas: Array.from(new Set(added.schemas)),
          facts: Array.from(new Set(added.facts)),
        },
        draft_was_open: wasOpen,
        revision,
      });
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  const toggle = (key: string) => {
    const next = new Set(ticked);
    if (next.has(key)) next.delete(key); else next.add(key);
    setTicked(next);
  };

  return (
    <div className="welcome">
      {offering ? (
        <>
          <h2>Add an offering</h2>
          <p className="muted">
            An offering is what a client starts a workspace from: its own
            document types, facts and memoranda, partitioned from every other
            offering. It starts empty. Nothing in it reaches a client until it
            is published and its memoranda are ticked in the Report
            Catalogue.
          </p>
        </>
      ) : newWorkspace ? (
        <>
          <h2>Add a workspace</h2>
          <p className="muted">
            A workspace holds its own facts, document types and memoranda, and
            its own engagements and documents. Nothing in it is shared with
            your other workspaces: a document needed in both is uploaded to
            each.
          </p>
        </>
      ) : firstRun ? (
        <>
          <p className="muted small">Draft copy</p>
          <h2>Welcome to ARQEDIA</h2>
          <p>
            ARQEDIA reads the documents in a client file against the facts you
            define, and writes your memoranda from what it finds.
          </p>

          <h3>The order of work</h3>
          <ol>
            <li>
              <strong>Configure.</strong> Choose your memoranda below. You get
              the facts they rest on, the document types those facts are found
              in, and each memorandum laid out over them.
            </li>
            <li>
              <strong>Publish.</strong> A draft reaches nothing. Publishing
              makes it the configuration documents are read against.
              {stopAtDraft
                ? " It is a separate step, and you take it when you are ready."
                : " Pressing Get started publishes for you."}
            </li>
            <li>
              <strong>Upload.</strong> Now, and not before. Each document is
              read once, against the configuration that is live when you file
              it.
            </li>
          </ol>
          <p className="muted small">
            Get the facts and their wording right before you upload. A fact
            added later is empty on every document already filed, and the only
            way to fill it is to upload that document again.
          </p>

          <h3>What a filing costs</h3>
          <p>A filing is charged at $0.25 per document filed.</p>

          {/* A SECOND ADMINISTRATOR, ASKED HERE RATHER THAN DURING SIGNUP
              (18.8). It was step 4 of five, optional, before anybody had seen
              the product - and it did nothing at all: the address was written
              to pending_signup.second_admin and no code ever read that column,
              so nobody typing a colleague in was ever invited.

              This is first sign-in, and the control goes to the seats screen,
              which really does invite: it reserves a seat, mints a link and
              sends the mail. Composed from .revision-note and .form-actions.
              No new CSS. */}
          <h3>A second administrator</h3>
          <div className="revision-note">
            <span>
              Worth the thirty seconds. Another administrator can restore your
              access if you lose it; without one, recovery is a manual request
              to us and takes days. The seat is not taken until they accept.
            </span>
            <div className="form-actions">
              <button onClick={() => navigate(SEATS)}>Invite a colleague</button>
              <span className="muted small">
                You can do this at any time under Account management.
              </span>
            </div>
          </div>
        </>
      ) : (
        <>
          <h2>Add a memorandum</h2>
          <p className="muted">
            Every memorandum here is laid out over the facts you already hold.
            Taking one adds its sections and what each renders, and brings back
            any fact it needs that you no longer have. Nothing you have edited
            is touched.
          </p>
        </>
      )}

      {/* AT THE PLAN'S LIMIT (PACK-02), said before the form rather than
          after the press. The form stays: the server is what refuses, and
          its sentence lands below if it is pressed anyway. */}
      {creating && !firstRun && !workspace.room && (
        <UpgradePrompt>
          Your plan holds {workspace.limit}{" "}
          {workspace.limit === 1 ? "workspace" : "workspaces"}, and{" "}
          {workspace.limit === 1 ? "it is" : "all are"} in use. A bigger plan
          is how a tenant gets more.
        </UpgradePrompt>
      )}

      {/* THE NAME, BEFORE ANYTHING ELSE IS ASKED (PACK-01). Required and
          empty; the placeholder is an example, not a value. */}
      {creating && offering && (
        <>
          <h3>Name this offering</h3>
          <input value={name} maxLength={128}
                 placeholder="For example, Real Estate"
                 aria-label="Offering name"
                 onChange={(e) => setName(e.target.value)} />
          <p className="muted small">
            The line of business it serves. Clients choose it by this name
            when they add a workspace.
          </p>

          <h3>How it starts</h3>
          <label className="inline-check">
            <input type="radio" name="start" checked={route === "scratch"}
                   onChange={() => setRoute("scratch")} />
            By hand, from an empty memorandum
          </label>
          <label className="inline-check">
            <input type="radio" name="start" checked={route === "report"}
                   onChange={() => setRoute("report")} />
            From a report (.pdf, .docx)
          </label>
          <p className="muted small">
            Either way it holds no facts and no document types until you add
            them: by hand, or by correcting what we read from the report. The
            draft is the offering&rsquo;s own, and nothing is published until
            you publish it.
          </p>
        </>
      )}

      {creating && !offering && (
        <>
          <h3>Name this workspace</h3>
          <input value={name} maxLength={128}
                 placeholder="For example, Trade Finance"
                 aria-label="Workspace name"
                 onChange={(e) => setName(e.target.value)} />
          <p className="muted small">
            What it is for, in a few words. You can hold several &mdash; one
            per line of business &mdash; and choose between them at the top
            of the page.
          </p>

          <h3>How it starts</h3>
          <label className="inline-check">
            <input type="radio" name="start" checked={route === "ours"}
                   onChange={() => setRoute("ours")} />
            With one or more of our memoranda
          </label>
          <label className="inline-check">
            <input type="radio" name="start" checked={route === "scratch"}
                   onChange={() => setRoute("scratch")} />
            With a memorandum of your own, from scratch
          </label>
          <label className="inline-check">
            <input type="radio" name="start" checked={route === "report"}
                   onChange={() => setRoute("report")} />
            From a report you already write (.pdf, .docx)
          </label>
          <p className="muted small">
            Our memoranda bring the facts and document types they rest on. A
            report of your own starts empty and goes on to the configuration
            screen, where you write it, or correct what we read from yours,
            and add the facts and document types it needs. Nothing is
            published until you publish it.
          </p>

          {/* WHICH OFFERING, for ours only (PACK-02). Asked where there are
              several; named where there is one. Composed from the radios and
              notes above. No new CSS. */}
          {route === "ours" && offerings !== null && (
            offerings.length === 0 ? (
              <p className="muted">Nothing of ours is on offer yet.</p>
            ) : offerings.length === 1 ? (
              <p className="muted small">
                From our {chosenOffering?.name ?? "one"} offering:{" "}
                {chosenOffering?.document_types}{" "}
                {chosenOffering?.document_types === 1
                  ? "document type" : "document types"} and{" "}
                {chosenOffering?.fields}{" "}
                {chosenOffering?.fields === 1 ? "fact" : "facts"}.
              </p>
            ) : (
              <>
                <h3>Which of our offerings</h3>
                {offerings.map((o) => (
                  <label className="inline-check" key={o.workspace_id}>
                    <input type="radio" name="offering"
                           checked={chosen === o.workspace_id}
                           onChange={() => setChosen(o.workspace_id)} />
                    {o.name ?? "Unnamed"}{" "}
                    <span className="muted small">
                      {o.document_types}{" "}
                      {o.document_types === 1 ? "document type"
                                              : "document types"}{" "}
                      &middot; {o.fields} {o.fields === 1 ? "fact" : "facts"}
                    </span>
                  </label>
                ))}
                <p className="muted small">
                  The workspace takes its facts and document types, and its
                  Catalogue offers that offering&rsquo;s memoranda and no
                  other&rsquo;s.
                </p>
              </>
            )
          )}
        </>
      )}

      {(!creating || route === "ours") && (<>
      <h3>{creating ? "Choose its memoranda" : "Which memorandum"}</h3>

      {error && <p className="error">{error}</p>}

      {packs === null && !error && <p className="muted">Loading&hellip;</p>}
      {packs?.length === 0 && (
        <p className="muted">
          {fromOffering
            ? (chosen === null ? "Choose one of our offerings above."
                               : "That offering has no memoranda on offer.")
            : "None of our memoranda are offered to this workspace. It was "
              + "not started from one of our offerings, or that offering "
              + "offers none."}
        </p>
      )}

      {packs?.map((pack) => (
        <label className="template-row" key={pack.pack_key}>
          <input type="checkbox" checked={ticked.has(pack.pack_key)}
                 onChange={() => toggle(pack.pack_key)} />
          <span className="template-name">{pack.label}</span>
          {/* Before the count, not after it. After it, a row carrying this
              marker pushed its count eighty pixels left of the others, and a
              column of numbers that does not line up cannot be compared -
              which is the one thing the numbers are here for. */}
          {/* Held by the ACTIVE workspace. A workspace being made holds
              nothing yet, so it is not said there. */}
          {pack.held && !creating && (
            <span className="muted small">already yours</span>
          )}
          {/* The count says how much there is; the headings say what it is.
              Held under the count rather than listed down the page, which
              would bury the choice itself. Focusable, because hover alone
              reaches nobody working from the keyboard. */}
          <span className="template-sections" tabIndex={0}>
            <span className="count">
              {pack.sections} {pack.sections === 1 ? "section" : "sections"}
            </span>
            <span className="sections-pop">
              {pack.section_titles.map((title, i) => (
                <span key={i}>{title}</span>
              ))}
            </span>
          </span>
        </label>
      ))}

      </>)}

      {/* The memoranda list carries the error above, and is not drawn for a
          report of their own or an offering - where a refusal to create the
          workspace was otherwise shown nowhere. */}
      {creating && route !== "ours" && error && (
        <p className="error">{error}</p>
      )}

      {refused.length > 0 && (
        <div className="revision-note fatal">
          <strong>The memoranda are in your draft, but it cannot be
            published yet.</strong>
          <ul>
            {refused.map((detail, i) => <li key={i}>{detail}</li>)}
          </ul>
        </div>
      )}

      {/* Publish is not selective: it ships the whole draft. Somebody with
          their own unpublished work in it needs to know that before they
          press the button, not afterwards. A first-run tenant has nothing of
          their own to ship, so there is nothing to say - nor has a workspace
          being made: the open draft is the ACTIVE workspace's, and this press
          publishes the new one's (PACK-01). */}
      {draftOpen && !creating && !stopAtDraft && (
        <p className="working-note">
          You have an open draft. Get started publishes it &mdash; the
          memoranda you tick here and any changes already in it, together.
        </p>
      )}

      {/* Said before the button, and said plainly. Somebody who has just
          picked two memoranda will otherwise expect them to be in use. */}
      {stopAtDraft && (
        <p className="working-note">
          What you tick goes into your draft. Nothing is published:
          publishing is a separate step, on the configuration screen, when
          the draft says what you want it to say.
        </p>
      )}

      {/* WHAT LEAVING COSTS (18.8). This screen is the only door: the button
          is dead until something is ticked, and start() returns at once on an
          empty tick - so a person who reads the page and presses Home has a
          workspace with no facts, no document types and no memorandum, and
          nothing in the product mentions it again. "Tick a memorandum to
          begin" says what the button wants; it does not say what walking away
          leaves behind.

          FIRST RUN ONLY. Somebody adding a second memorandum a year later
          loses nothing at all by leaving, and telling them they do would be
          untrue. Composed from .working-note, which this screen already uses
          twice. No new CSS. */}
      {firstRun && ticked.size === 0 && route === "ours" && (
        <p className="working-note">
          <strong>Nothing is set up until you do this.</strong> Until a
          memorandum is chosen and published, your workspace has no facts and
          no document types: an upload cannot be given a type, and nothing can
          be filed or generated. Leaving now costs nothing and creates nothing
          &mdash; you come back to this screen from Report Catalogue.
        </p>
      )}

      {busy && <Working what={busy} />}

      <div className="form-actions">
        {creating && route !== "ours" ? (
          <a className={"start-pill" + (busy || !name.trim() ? " off" : "")}
             onClick={busy || !name.trim() ? undefined
               : () => startOwn(route)}>
            {offering
              ? (route === "scratch" ? "Create the offering"
                                     : "Create the offering and read a report")
              : (route === "scratch" ? "Create the workspace"
                                     : "Create the workspace and read my report")}
          </a>
        ) : (
        <a className={"start-pill" + (busy || ticked.size === 0
                                      || (creating && !name.trim())
                                      || (fromOffering && chosen === null)
                                      ? " off" : "")}
           onClick={busy || ticked.size === 0 || (creating && !name.trim())
                    || (fromOffering && chosen === null)
             ? undefined : start}>
          {stopAtDraft && !creating ? "Add to my draft" : "Get started"}
        </a>
        )}
        {firstRun && (
          <a href="https://arqedia.com" target="_blank" rel="noreferrer">
            Purchase ARQEDIA
          </a>
        )}
        {ticked.size === 0 && !firstRun && (!creating || route === "ours") && (
          <span className="muted small">Tick a memorandum to begin.</span>
        )}
        {creating && !name.trim() && (
          <span className="muted small">
            {offering ? "Name the offering to begin."
                      : "Name the workspace to begin."}
          </span>
        )}
      </div>
    </div>
  );
}
