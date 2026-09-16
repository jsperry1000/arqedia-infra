import { useEffect, useState } from "react";
import { api, type ConfigState, type TemplatePack, type Validation } from "./api";
import { Working } from "./shell";

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
 * NOTHING IS CHOSEN BY POSITION. Templates are taken by pack_key. What was
 * chosen at signup pre-ticks the list and decides nothing: that question was
 * asked with one line of description beside it, and this screen has room to
 * say what each memorandum actually contains.
 *
 * DRAFT COPY for the introduction, from ARQEDIA_UI_GUIDE_DRAFT.md.
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

/** What signup recorded, matched to what we ship. One or two names, written
 *  as they appeared on the signup screen, so they are matched loosely - a
 *  display label is not a key, which is why the key exists. */
function preTicked(chosen: string | null, packs: TemplatePack[]) {
  const flat = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
  const wanted = (chosen ?? "").split(",").map(flat).filter(Boolean);
  if (wanted.length === 0) return new Set<string>();
  return new Set(packs
    .filter((p) => wanted.some((w) =>
      w === flat(p.pack_key) || w === flat(p.label)
      || flat(p.label).includes(w) || w.includes(flat(p.pack_key))))
    .map((p) => p.pack_key));
}

export function WelcomeView({ onStarted }: {
  onStarted: (report: Report) => void;
}) {
  const [state, setState] = useState<ConfigState | null>(null);
  const [packs, setPacks] = useState<TemplatePack[] | null>(null);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [refused, setRefused] = useState<string[]>([]);

  useEffect(() => {
    Promise.all([api.configState(), api.templatesAvailable()])
      .then(([s, t]) => {
        setState(s);
        setPacks(t.templates);
        setTicked(preTicked(s.forked_pack, t.templates));
      })
      .catch((err) => setError(message(err)));
  }, []);

  function message(err: unknown) {
    let text = String((err as Error)?.message ?? err);
    try { text = JSON.parse(text).error ?? text; } catch { /* as it came */ }
    return text;
  }

  const firstRun = !!state && state.revisions.length === 0;
  const draftOpen = !!state?.draft;

  /**
   * The base where there is none, then each ticked template, then one publish.
   *
   * Read again at the start rather than trusting what the screen loaded with:
   * a tenant who forked in another tab must not have the base forked twice,
   * and that is the call that refuses.
   */
  async function start() {
    setError("");
    setRefused([]);
    const wanted = (packs ?? []).filter((p) => ticked.has(p.pack_key));
    if (wanted.length === 0) return;

    try {
      setBusy("Reading your configuration");
      const now = await api.configState();

      if (now.revisions.length === 0) {
        setBusy("Setting up your facts and document types");
        await api.forkBase();
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

      setBusy("Publishing");
      // publish answers a refusal rather than throwing, so its shape is
      // spelled out here: a validation that failed is a thing to show, not an
      // error to swallow.
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

      onStarted({
        templates: wanted.map((p) => p.label),
        added: {
          categories: Array.from(new Set(added.categories)),
          document_types: Array.from(new Set(added.document_types)),
          schemas: Array.from(new Set(added.schemas)),
          facts: Array.from(new Set(added.facts)),
        },
        draft_was_open: wasOpen,
        revision: published?.revision ?? null,
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
      {firstRun ? (
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
              makes it the configuration documents are read against, and
              pressing Get started publishes for you.
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
          <p>A filing is charged at $0.25 per document.</p>
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

      <h3>{firstRun ? "Choose your memoranda" : "Which memorandum"}</h3>
      {state?.forked_pack && firstRun && (
        <p className="muted small">
          Ticked from what you chose when you signed up. Change it freely
          &mdash; nothing was decided then.
        </p>
      )}

      {error && <p className="error">{error}</p>}

      {packs === null && !error && <p className="muted">Loading&hellip;</p>}
      {packs?.length === 0 && (
        <p className="muted">No memoranda are available yet.</p>
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
          {pack.held && (
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
          their own to ship, so there is nothing to say. */}
      {draftOpen && !firstRun && (
        <p className="working-note">
          You have an open draft. Get started publishes it &mdash; the
          memoranda you tick here and any changes already in it, together.
        </p>
      )}

      {busy && <Working what={busy} />}

      <div className="form-actions">
        <a className={"start-pill" + (busy || ticked.size === 0 ? " off" : "")}
           onClick={busy || ticked.size === 0 ? undefined : start}>
          Get started
        </a>
        {firstRun && (
          <a href="https://arqedia.com" target="_blank" rel="noreferrer">
            Purchase ARQEDIA
          </a>
        )}
        {ticked.size === 0 && (
          <span className="muted small">Tick a memorandum to begin.</span>
        )}
      </div>
    </div>
  );
}
