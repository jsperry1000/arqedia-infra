import { ConfigureView } from "./Configure";
import { SettingsView } from "./Settings";
import { MemoView } from "./Memo";
import { EngagementView } from "./Review";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { BackContext, BackPill } from "./shell";
import { WelcomeView } from "./Welcome";
import { AccountView } from "./Account";
import { ShareView } from "./Share";
import { ViewerView } from "./Viewer";
import { SignUp } from "./SignUp";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { Amplify } from "aws-amplify";
import { signIn, signOut, confirmSignIn, getCurrentUser, fetchAuthSession } from "aws-amplify/auth";
import { config } from "./config";
import { api, type Engagement } from "./api";
// The mark lives in one place, /brand, and both the application and the
// marketing site reference it from there. Replace those two files and both
// surfaces change in the same commit.
import logoDeep from "../../brand/logo-deep.svg";
import logoWhite from "../../brand/logo-white.svg";

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: config.userPoolId,
      userPoolClientId: config.userPoolClientId,
    },
  },
});

// --- sign in ---------------------------------------------------------------

function SignIn({ onDone, onCreate }: { onDone: () => void; onCreate: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [needsNew, setNeedsNew] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (needsNew) {
        await confirmSignIn({ challengeResponse: newPassword });
        onDone();
        return;
      }
      const res = await signIn({ username: email, password });
      if (res.nextStep.signInStep === "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED") {
        setNeedsNew(true);
      } else {
        onDone();
      }
    } catch (err: any) {
      setError(err.message ?? String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="centre">
      <form onSubmit={submit} className="card">
        <img src={logoDeep} alt="" width="44" height="44" />
        <h1>ARQEDIA</h1>
        {needsNew ? (
          <>
            <p className="muted">Choose a new password.</p>
            <input type="password" placeholder="New password" value={newPassword}
                   onChange={(e) => setNewPassword(e.target.value)} autoFocus />
          </>
        ) : (
          <>
            <input placeholder="Email" value={email}
                   onChange={(e) => setEmail(e.target.value)} autoFocus />
            <input type="password" placeholder="Password" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </>
        )}
        {error && <p className="error">{error}</p>}
        <button disabled={busy}>{busy ? "..." : "Sign in"}</button>
        {/* Somebody arriving from the site has no account yet. Until this
            existed the sign-in card was the end of the road for them. */}
        <p className="muted small" style={{ textAlign: "center", margin: 0 }}>
          No account? <a onClick={onCreate}>Start a 30-day trial</a>
        </p>
      </form>
    </div>
  );
}

// --- engagements -----------------------------------------------------------

function Engagements({ onOpen }: { onOpen: (id: string) => void }) {
  const [rows, setRows] = useState<Engagement[]>([]);
  const [newName, setNewName] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.engagements()
      .then((r) => setRows(r.engagements))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="muted">Loading...</p>;

  return (
    <div>
      <h2>Engagements</h2>
      {rows.length === 0 && (
        <p className="muted">Nothing yet. Name an engagement below to start.</p>
      )}
      <table>
        <tbody>
          {rows.map((r) => (
            <tr key={r.engagement} onClick={() => onOpen(r.engagement)}>
              <td><a>{r.engagement}</a></td>
              <td className="muted">{r.documents} documents</td>
              <td className="muted">{r.last_activity}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <form className="inline" onSubmit={(e) => { e.preventDefault();
              if (newName.trim()) onOpen(newName.trim()); }}>
        <input placeholder="New engagement name" value={newName}
               onChange={(e) => setNewName(e.target.value)} />
        <button>Open</button>
      </form>
    </div>
  );
}

// --- choosing a report -----------------------------------------------------

/** A draft to work in. A tenant with nothing configured takes the base first;
 *  one with only a published revision opens a copy of it.
 *
 *  THE BASE IS TAKEN BY KEY. This forked whatever packs() returned first, and
 *  packs() sorted by revision descending - so adding a pack silently changed
 *  what a new tenant got. Memoranda are not forked here at all: that is Get
 *  started, where there is room to say what each one contains. */
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

/** Configure a report, as a choice rather than a screen: open one, start from
 *  nothing, or start from a report the tenant already writes (UX-04). */
function ReportChooser({ onClose, onOpened }: {
  onClose: () => void;
  onOpened: (to: string, state?: unknown) => void;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  // What the panel shows: the three options, or the reports to open. A choice
  // replaces the options rather than opening a list beneath them (UX-17).
  const [view, setView] = useState<"options" | "reports">("options");
  const [reports, setReports] = useState<{ key: string; label: string }[] | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // A click elsewhere, or Escape, puts it away. The link that opened it is
  // not elsewhere: it toggles the panel itself.
  useEffect(() => {
    const away = (e: MouseEvent) => {
      const at = e.target as Node | null;
      const item = box.current?.parentElement;
      if (item && at && !item.contains(at)) onClose();
    };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [onClose]);

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

  // The memoranda in the draft where one is open, since that is what will be
  // edited; otherwise the live revision's. One row each, read once.
  async function list() {
    setView("reports");
    if (reports !== null) return;
    try {
      const state = await api.configState();
      const found: { key: string; label: string }[] = state.draft
        ? (await api.draft()).templates
        : state.revisions.length ? (await api.templates()).templates : [];
      setReports(found.map((t) => ({ key: t.key, label: t.label || t.key })));
    } catch (err) {
      setError(errorText(err));
      setReports([]);
    }
  }

  const open = (key: string) => run("Opening", async () => {
    await ensureDraft();
    onOpened(`/configure?report=${encodeURIComponent(key)}`);
  });

  // Ours, rather than theirs. What is on offer is already shown by the Get
  // started chooser - the same list, the same headings, the same "already
  // yours" marker - so this sends a person there rather than building a
  // second list that drifts from it. stopAtDraft: taking one from here adds
  // it to the draft and publishes nothing.
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

  return (
    <div className="chooser" ref={box}>
      {view === "options" ? (
        <>
          <a onClick={list}>Open an existing report</a>
          <a onClick={scratch}>Create from scratch</a>
          <a onClick={fromReport}>
            Create from a report you already write
          </a>
          {/* A rule between what they have and what we offer. */}
          <span className="sep" />
          <a onClick={ours}>Select an ARQEDIA Template</a>
        </>
      ) : (
        <>
          <a onClick={() => setView("options")}>&lsaquo; All options</a>
          <div className="chooser-list">
            {reports === null && <span className="muted">Loading&hellip;</span>}
            {reports?.length === 0 && <span className="muted">No reports yet.</span>}
            {reports?.map((r) => (
              <a key={r.key} onClick={() => open(r.key)}>{r.label}</a>
            ))}
          </div>
        </>
      )}
      {busy && <p className="busy small">{busy}&hellip;</p>}
      {error && <p className="error small">{error}</p>}
    </div>
  );
}

// --- routes ----------------------------------------------------------------

// Back is the browser's back, so a view returns to wherever it was opened
// from. A view reached by a pasted link has nowhere in the app behind it, and
// goes home rather than leaving the app.
function useBack() {
  const navigate = useNavigate();
  const location = useLocation();
  return () => { if (location.key === "default") navigate("/"); else navigate(-1); };
}

function EngagementsRoute() {
  const navigate = useNavigate();
  return <Engagements onOpen={(id) => navigate(`/engagements/${encodeURIComponent(id)}`)} />;
}

function EngagementRoute() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const back = useBack();
  return <EngagementView id={id} onBack={back} onMemo={(memoId) => navigate(`/memos/${memoId}`)} />;
}

function MemoRoute() {
  const { id } = useParams();
  const navigate = useNavigate();
  const back = useBack();
  return <MemoView memoId={Number(id)} onBack={back} onOpen={(memoId) => navigate(`/memos/${memoId}`)} />;
}

// Keyed on the chooser's count: the screen reads the configuration when it
// mounts, and a draft opened or a report added from the rail would not show.
function ConfigureRoute({ epoch }: { epoch: number }) {
  return <ConfigureView key={epoch} onBack={useBack()} />;
}

function SettingsRoute() {
  return <SettingsView onBack={useBack()} />;
}

/** Get started, and the same screen reached to take a memorandum.
 *
 *  Signing up lands here with no state and publishes at the end, which is
 *  what makes a new tenant's first run one press. The rail's panel and the
 *  first-run screen arrive with stopAtDraft, and then nothing is published:
 *  their draft is their own, and shipping it is their decision. */
function WelcomeRoute({ onOpened }: {
  onOpened: (to: string, state?: unknown) => void;
}) {
  const location = useLocation();
  const stopAtDraft = Boolean(
    (location.state as { stopAtDraft?: boolean } | null)?.stopAtDraft);
  return <WelcomeView stopAtDraft={stopAtDraft}
                      onStarted={(report) =>
                        onOpened("/configure?part=sections", { report })} />;
}

// --- not connected yet -----------------------------------------------------
//
// Account management, Sharing and the Viewer have no endpoints behind them.
// They are routed and navigable so the flow can be walked and judged; every
// figure in them comes from mock.tsx and every control is inert. Sharing will
// open from a memorandum's own head rather than from the rail once it is real,
// and the Viewer will be served outside this shell entirely.

function AccountRoute() {
  return <AccountView onBack={useBack()} />;
}

function ShareRoute() {
  const navigate = useNavigate();
  return <ShareView onBack={useBack()} onViewer={() => navigate("/viewer")} />;
}

function ViewerRoute() {
  return <ViewerView onBack={useBack()} />;
}

// --- shell -----------------------------------------------------------------

export default function App() {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [who, setWho] = useState("");
  const navigate = useNavigate();
  const location = useLocation();

  async function check() {
    try {
      await getCurrentUser();
      const session = await fetchAuthSession();
      const claims: any = session.tokens?.idToken?.payload ?? {};
      setWho(`${claims.email ?? ""} - tenant ${claims["custom:tenant_id"] ?? "?"}`);
      setSignedIn(true);
    } catch {
      setSignedIn(false);
    }
  }

  useEffect(() => { check(); }, []);

  // A tenant's colours are NOT read here. They belong to what the tenant
  // produces - a rendered memorandum and anything they share - and are applied
  // at render time. Inside this application everyone sees ARQEDIA, so the
  // chrome takes the platform tokens and nothing is fetched for it.

  // The rail sits beneath the header and runs to the foot of the window, so it
  // needs the header's height. Measured, as Memo.tsx does, because it changes
  // with the width of the window and the length of the signed-in address.
  const header = useRef<HTMLElement | null>(null);
  const [headerHeight, setHeaderHeight] = useState(0);
  useLayoutEffect(() => {
    const el = header.current;
    if (!el) return;
    const measure = () => setHeaderHeight(el.getBoundingClientRect().height);
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const watch = new ResizeObserver(measure);
    watch.observe(el);
    return () => watch.disconnect();
  }, [signedIn]);

  // Configure a report opens a choice. Whichever option is taken reloads the
  // configuration screen, which counts here.
  const [choosing, setChoosing] = useState(false);
  const [configEpoch, setConfigEpoch] = useState(0);
  const closeChooser = useCallback(() => setChoosing(false), []);

  // The Settings choice. Closes on a click elsewhere or Escape, as every other
  // panel on the screen does.
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsPanel = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!settingsOpen) return;
    const away = (e: MouseEvent) => {
      const item = settingsPanel.current?.parentElement;
      if (item && !item.contains(e.target as Node)) setSettingsOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSettingsOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [settingsOpen]);

  // The one Back. A screen hands up its own leave action; with none, Back
  // goes to the previous page.
  const leave = useRef<(() => void) | null>(null);
  const registerBack = useCallback((fn: () => void) => {
    leave.current = fn;
    return () => { if (leave.current === fn) leave.current = null; };
  }, []);
  const back = useBack();

  // The signed-in line opens the account's own controls - Sign out, and room
  // for more (UX-19). A click elsewhere or Escape puts them away.
  const [accountOpen, setAccountOpen] = useState(false);
  const account = useRef<HTMLSpanElement | null>(null);
  useEffect(() => {
    if (!accountOpen) return;
    const away = (e: MouseEvent) => {
      if (account.current && !account.current.contains(e.target as Node)) {
        setAccountOpen(false);
      }
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAccountOpen(false);
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", escape);
    };
  }, [accountOpen]);

  if (signedIn === null) return <div className="centre"><p className="muted">...</p></div>;
  // Two entries, and they are not the same thing. Signing in goes home, to
  // Engagements: somebody with an account has work to get back to. Starting a
  // trial goes to Get started, because a new tenant has nothing yet and that
  // is where memoranda are chosen. A session already open on load keeps the
  // address it was opened at.
  if (!signedIn) {
    const done = () => { navigate("/"); check(); };
    return (
      <Routes>
        <Route path="/signup"
               element={<SignUp onSignIn={() => navigate("/")}
                                onSignedUp={() => { navigate("/welcome"); check(); }} />} />
        {/* Anything else signed out is the sign-in card, whatever was asked
            for. The address is kept, so a link followed into the product
            lands where it meant to once signed in. */}
        <Route path="*"
               element={<SignIn onDone={done} onCreate={() => navigate("/signup")} />} />
      </Routes>
    );
  }

  const shellVars = {
    "--header-h": headerHeight + "px",
  } as React.CSSProperties;

  // Which rail destination is open, so it can come forward to the page's own
  // colour. Configure is matched on its prefix: the chooser navigates to
  // /configure with a query, and the rail should still read as open.
  const here = location.pathname;
  const railClass = (path: string) =>
    (path === "/" ? here === "/" : here.startsWith(path)) ? "on" : undefined;

  const opened = (to: string, state?: unknown) => {
    setChoosing(false);
    setConfigEpoch((n) => n + 1);
    navigate(to, { state });
  };

  return (
    <div className="shell" style={shellVars}>
      <header ref={header}>
        <img src={logoWhite} alt="" width="22" height="22" />
        <strong>ARQEDIA</strong>
        <span className="account" ref={account}>
          <a aria-expanded={accountOpen}
             onClick={() => setAccountOpen(!accountOpen)}>
            {who} {accountOpen ? "▴" : "▾"}
          </a>
          {/* A panel beneath the name, not three more links strung along the
              header - in a row of white text on navy they read as part of the
              masthead and are lost. */}
          {accountOpen && (
            <div className="account-menu">
              <a onClick={() => { setAccountOpen(false); navigate("/settings/brand"); }}>
                Brand settings
              </a>
              <a onClick={() => { setAccountOpen(false); navigate("/account"); }}>
                Account management
              </a>
              <span className="sep" />
              <a onClick={async () => {
                setAccountOpen(false);
                await signOut();
                setSignedIn(false);
              }}>Sign out</a>
            </div>
          )}
        </span>
      </header>
      {/* The top-level destinations, on a rail of their own so the header of
          a working screen is free for that screen's controls (UX-03). Home
          is first: every other screen is reached from it. */}
      <nav className="rail">
        <a className={railClass("/")} onClick={() => navigate("/")}>Engagements</a>
        {/* A choice rather than a screen (UX-04): which report, or how to
            start a new one. */}
        <div className="rail-item">
          <a className={railClass("/configure")} onClick={() => setChoosing(!choosing)}>Configure a report</a>
          {choosing && <ReportChooser onClose={closeChooser} onOpened={opened} />}
        </div>
        <a className={railClass("/shares")} onClick={() => navigate("/shares")}>Sharing</a>
        {/* Settings opens a choice, as Configure does. Two things live under
            it and they are not alike: how memoranda look, and who pays for
            them. The balance belongs to the second - it is an account matter,
            not a destination of its own. */}
        <div className="rail-item">
          <a className={here.startsWith("/settings") || here.startsWith("/account")
                        ? "on" : undefined}
             onClick={() => setSettingsOpen(!settingsOpen)}>Settings</a>
          {settingsOpen && (
            <div className="chooser" ref={settingsPanel}>
              <a onClick={() => { setSettingsOpen(false); navigate("/settings/brand"); }}>
                Brand settings
              </a>
              <p className="muted small">Your logo and the four colours a memorandum wears.</p>
              <a onClick={() => { setSettingsOpen(false); navigate("/account"); }}>
                Account management
              </a>
              <p className="muted small">Subscription, balance, and who holds a seat.</p>
            </div>
          )}
        </div>
      </nav>
      {/* The working column. Back is drawn once, here, in the same place on
          every screen and held there while the page scrolls (UX-16). */}
      <div className="work">
        <BackContext.Provider value={registerBack}>
          <div className="back-strip">
            <BackPill onClick={() => (leave.current ?? back)()} />
          </div>
          <main>
            <Routes>
              <Route path="/" element={<EngagementsRoute />} />
              <Route path="/engagements/:id" element={<EngagementRoute />} />
              <Route path="/memos/:id" element={<MemoRoute />} />
              <Route path="/configure" element={<ConfigureRoute epoch={configEpoch} />} />
              <Route path="/settings" element={<SettingsRoute />} />
              <Route path="/settings/brand" element={<SettingsRoute />} />
              <Route path="/account" element={<AccountRoute />} />
              <Route path="/shares" element={<ShareRoute />} />
              <Route path="/viewer" element={<ViewerRoute />} />
              {/* Get started forks and publishes, then hands what it added
                  to the configuration screen, which says so at the top.
                  Reached from the rail's panel or the first-run screen it
                  stops at the draft instead, and says so: taking a
                  memorandum is not the moment to ship somebody's own
                  unpublished work. */}
              <Route path="/welcome" element={<WelcomeRoute onOpened={opened} />} />
              {/* Signing up ends here. onSignedUp navigates to /welcome and
                  then check() flips signedIn, but react-router applies the new
                  location inside a transition while setSignedIn is urgent - so
                  the shell can mount while the location still reads /signup.
                  Without this route the catch-all below took it, replaced the
                  /welcome entry with /, and a new tenant landed on Engagements
                  and never saw Get started. Holding /signup here makes both
                  orders land in the same place. */}
              <Route path="/signup" element={<Navigate to="/welcome" replace />} />
              {/* Anything else would render an empty page. */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </BackContext.Provider>
      </div>
    </div>
  );
}
