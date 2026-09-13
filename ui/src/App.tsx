import { ConfigureView } from "./Configure";
import { SettingsView } from "./Settings";
import { MemoView } from "./Memo";
import { EngagementView } from "./Review";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { BackContext, BackPill } from "./shell";
import { WelcomeView } from "./Welcome";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { Amplify } from "aws-amplify";
import { signIn, signOut, confirmSignIn, getCurrentUser, fetchAuthSession } from "aws-amplify/auth";
import { config } from "./config";
import { api, type Engagement } from "./api";

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: config.userPoolId,
      userPoolClientId: config.userPoolClientId,
    },
  },
});

// --- sign in ---------------------------------------------------------------

function SignIn({ onDone }: { onDone: () => void }) {
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
        <img src="/icon-deep.png" alt="" width="44" height="44" />
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

// --- the tenant's colours --------------------------------------------------

/** The tenant's light where it has set none: its mid taken most of the way to
 *  white, as the rendered memorandum does (style.palette_for, LIGHT_MIX). */
function towardsWhite(hex: string) {
  const n = parseInt(hex.slice(1), 16);
  const mix = (c: number) =>
    Math.round(c + (255 - c) * 0.7).toString(16).padStart(2, "0");
  return "#" + mix(n >> 16) + mix((n >> 8) & 255) + mix(n & 255);
}

// --- choosing a report -----------------------------------------------------

/** A draft to work in. A tenant with nothing configured starts from our pack,
 *  as the first-run screen does; one with only a published revision opens a
 *  copy of it. */
async function ensureDraft() {
  let state = await api.configState();
  if (!state.draft && state.revisions.length === 0) {
    const { packs } = await api.packs();
    if (!packs[0]) throw new Error("No starting points are available yet.");
    await api.forkPack(packs[0].revision);
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

// --- shell -----------------------------------------------------------------

export default function App() {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [who, setWho] = useState("");
  const navigate = useNavigate();

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

  // The tenant's own colours, for the controls that wear them: Back in its
  // deep, a pill in its light, a rule in its mid. The platform's where the
  // tenant has set none, or the settings cannot be read.
  const [brand, setBrand] = useState<{ deep?: string; mid?: string; light?: string }>({});
  useEffect(() => {
    if (!signedIn) return;
    api.settings().then((s) => setBrand({
      deep: s.deep ?? undefined,
      mid: s.mid ?? undefined,
      light: s.light ?? (s.mid ? towardsWhite(s.mid) : undefined),
    })).catch(() => setBrand({}));
  }, [signedIn]);

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
  // Signing in lands on the introduction, before any editor (UX-14). A
  // session already open on load keeps the address it was opened at.
  if (!signedIn) {
    return <SignIn onDone={() => { navigate("/welcome"); check(); }} />;
  }

  const shellVars = {
    "--header-h": headerHeight + "px",
    ...(brand.deep ? { "--tenant-deep": brand.deep } : {}),
    ...(brand.mid ? { "--tenant-mid": brand.mid } : {}),
    ...(brand.light ? { "--tenant-light": brand.light } : {}),
  } as React.CSSProperties;

  const opened = (to: string, state?: unknown) => {
    setChoosing(false);
    setConfigEpoch((n) => n + 1);
    navigate(to, { state });
  };

  return (
    <div className="shell" style={shellVars}>
      <header ref={header}>
        <img src="/icon-white.png" alt="" width="22" height="22" />
        <strong>ARQEDIA</strong>
        <span className="account" ref={account}>
          <a aria-expanded={accountOpen}
             onClick={() => setAccountOpen(!accountOpen)}>
            {who} {accountOpen ? "▴" : "▾"}
          </a>
          {accountOpen && (
            <a onClick={async () => {
              setAccountOpen(false);
              await signOut();
              setSignedIn(false);
            }}>Sign out</a>
          )}
        </span>
      </header>
      {/* The top-level destinations, on a rail of their own so the header of
          a working screen is free for that screen's controls (UX-03). Home
          is first: every other screen is reached from it. */}
      <nav className="rail">
        <a onClick={() => navigate("/")}>Engagements</a>
        {/* A choice rather than a screen (UX-04): which report, or how to
            start a new one. */}
        <div className="rail-item">
          <a onClick={() => setChoosing(!choosing)}>Configure a report</a>
          {choosing && <ReportChooser onClose={closeChooser} onOpened={opened} />}
        </div>
        <a onClick={() => navigate("/settings")}>Settings</a>
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
              <Route path="/welcome"
                     element={<WelcomeView onStart={() => setChoosing(true)} />} />
              {/* Anything else would render an empty page. */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </BackContext.Provider>
      </div>
    </div>
  );
}




