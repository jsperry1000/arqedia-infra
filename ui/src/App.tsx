import { CatalogueView } from "./Catalogue";
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
import { InvitationView } from "./Invitation";
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import { Amplify } from "aws-amplify";
import { signIn, signOut, confirmSignIn, getCurrentUser, fetchAuthSession,
         resetPassword, confirmResetPassword } from "aws-amplify/auth";
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

/** Which shape the card is in.
 *
 *  "in"     email and password
 *  "forgot" the address to send a reset code to
 *  "reset"  the code, and the password to set with it
 *
 *  The first-sign-in challenge is not one of these: it is a state of the
 *  sign-in attempt rather than a screen somebody chooses, and it keeps its own
 *  flag. */
type SignInMode = "in" | "forgot" | "reset";

/** What a person is told when resetting cannot be started for their address.
 *
 *  DELIBERATELY SAYS NO CAUSE. Cognito refuses here for more than one reason -
 *  an account that has never had a password set is one of them - and we have
 *  not verified which refusal carries which cause. Naming the wrong one sends
 *  somebody to fix a thing that is not broken. The administrator of their own
 *  workspace can put any of them right, so that is who they are sent to. */
const RESET_REFUSED =
  "A code cannot be sent for that address from here. An administrator in " +
  "your firm can set it right - ask them to remove your seat and invite you " +
  "again.";

/** What a failed code is told, in our words rather than Cognito's.
 *
 *  COGNITO DOES NOT RELIABLY TELL THE TWO APART. ConfirmForgotPassword
 *  documents both CodeMismatchException and ExpiredCodeException, but a plainly
 *  wrong code against a real address comes back as
 *
 *    name    "ExpiredCodeException"
 *    message "Invalid code provided, please request a code again."
 *
 *  - verified against the pool on 20 September. So a card that shows Cognito's
 *  sentence tells somebody who mistyped a digit that their code has run out,
 *  and tells them to request a new one while offering nowhere to do it. Both
 *  names are therefore answered here in one sentence that is true of either,
 *  and CodeMismatch keeps the sharper wording for when it does arrive.
 *
 *  Anything else - a password below the policy, a rate limit - is Cognito's
 *  own sentence, because it is about something other than the code and is
 *  already written for a person to read. */
function codeRefusal(err: any): string {
  if (err?.name === "CodeMismatchException") {
    return "That code is not right. Use the most recent email - asking for a "
      + "new code stops the one before it working.";
  }
  if (err?.name === "ExpiredCodeException") {
    return "That code is not right, or it has run out. Ask for a new one "
      + "below and use the newest email.";
  }
  // `||`, not `??`: an AuthError carrying an empty message would otherwise
  // set the error to "" and the card would fail in silence.
  return err?.message || String(err);
}

function SignIn({ onDone, onCreate }: { onDone: () => void; onCreate: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [needsNew, setNeedsNew] = useState(false);
  const [mode, setMode] = useState<SignInMode>("in");
  const [code, setCode] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function go(to: SignInMode) {
    setMode(to);
    setError("");
    setNote("");
  }

  /** Ask Cognito to send a reset code.
   *
   *  NEVER SAYS WHETHER THE ADDRESS HAS AN ACCOUNT. With user-existence errors
   *  enabled, Cognito's own answer for an unknown address alternates between a
   *  code-sent response naming a simulated destination and an
   *  InvalidParameterException - so both are treated as the same neutral
   *  sentence here, and the screen moves on either way. A card that behaves
   *  differently for the two is the enumeration the pool setting exists to
   *  prevent. */
  async function sendCode() {
    try {
      await resetPassword({ username: email });
    } catch (err: any) {
      // The refusals that are about this person rather than about existence.
      if (err?.name === "LimitExceededException"
          || err?.name === "TooManyRequestsException") {
        setError(err?.message || String(err));
        return;
      }
      if (err?.name !== "InvalidParameterException") {
        setError(RESET_REFUSED);
        return;
      }
    }
    go("reset");
    setNote("If that address has an account, a code is on its way to it. It "
            + "lasts an hour, and it replaces any code sent before it.");
  }

  /** Another code, asked for from the step where the last one failed.
   *
   *  The refusal says to ask for a new one, so there has to be somewhere to
   *  do it. Before this, the only route was Back to signing in and starting
   *  the whole thing again. */
  async function again() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await sendCode();
    } finally {
      setBusy(false);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "forgot") {
        await sendCode();
        return;
      }
      if (mode === "reset") {
        try {
          await confirmResetPassword({
            username: email, confirmationCode: code, newPassword });
        } catch (err) {
          // The note above still says a code is on its way and how long it
          // lasts. Left up beside a refusal it reads as a contradiction, and
          // it was written about a code that has now been answered.
          setNote("");
          setError(codeRefusal(err));
          return;
        }
        setCode("");
        setNewPassword("");
        setPassword("");
        go("in");
        setNote("Password changed. Sign in with it.");
        return;
      }
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
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  const action = mode === "forgot" ? "Send a code"
    : mode === "reset" ? "Set the password"
    : "Sign in";

  return (
    <div className="centre">
      <form onSubmit={submit} className="card">
        <img src={logoDeep} alt="" width="44" height="44" />
        <h1>ARQEDIA</h1>

        {mode === "forgot" && (
          <>
            <p className="muted">
              We will email a code to the address you sign in with.
            </p>
            <input placeholder="Email" value={email}
                   onChange={(e) => setEmail(e.target.value)} autoFocus />
          </>
        )}

        {mode === "reset" && (
          <>
            <p className="muted">
              Enter the code from the email, and the password you want.
            </p>
            <input placeholder="Code" value={code} inputMode="numeric"
                   onChange={(e) => setCode(e.target.value)} autoFocus />
            <input type="password" placeholder="New password" value={newPassword}
                   onChange={(e) => setNewPassword(e.target.value)} />
            <p className="muted small" style={{ margin: 0 }}>
              At least 12 characters, with an upper case letter, a lower case
              letter and a number.
            </p>
            {/* Where "ask for a new one" is actually done, beside the sentence
                that says to. The quiet way out for somebody whose code never
                arrives at all is under it, and names no cause, for the reason
                RESET_REFUSED does not. */}
            <p className="muted small" style={{ margin: 0 }}>
              <a className="small" onClick={again}>Send a new code</a>
              {" "}&middot; no code after a few minutes? Ask an administrator
              in your firm.
            </p>
          </>
        )}

        {mode === "in" && needsNew && (
          <>
            <p className="muted">Choose a new password.</p>
            <input type="password" placeholder="New password" value={newPassword}
                   onChange={(e) => setNewPassword(e.target.value)} autoFocus />
          </>
        )}

        {mode === "in" && !needsNew && (
          <>
            <input placeholder="Email" value={email}
                   onChange={(e) => setEmail(e.target.value)} autoFocus />
            {/* There is no other user id, and somebody who has forgotten
                which address they used is helped more by being told that
                than by a screen that pretends to look one up (10.2). */}
            <p className="muted small" style={{ margin: 0 }}>
              Your user id is the email address you signed up with.
            </p>
            <input type="password" placeholder="Password" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </>
        )}

        {note && <p className="muted small" style={{ margin: 0 }}>{note}</p>}
        {error && <p className="error">{error}</p>}
        <button disabled={busy}>{busy ? "..." : action}</button>

        {mode === "in" && !needsNew && (
          <p className="muted small" style={{ textAlign: "center", margin: 0 }}>
            <a onClick={() => go("forgot")}>Forgotten your password?</a>
          </p>
        )}

        {mode !== "in" && (
          <p className="muted small" style={{ textAlign: "center", margin: 0 }}>
            <a onClick={() => { setCode(""); setNewPassword(""); go("in"); }}>
              Back to signing in
            </a>
          </p>
        )}

        {/* Somebody arriving from the site has no account yet. Until this
            existed the sign-in card was the end of the road for them. */}
        {mode === "in" && (
          <p className="muted small" style={{ textAlign: "center", margin: 0 }}>
            No account? <a onClick={onCreate}>Start a 30-day trial</a>
          </p>
        )}
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

// Keyed on the count kept by the shell: the screen reads the configuration
// when it mounts, and a draft opened or a report added from the Catalogue
// would not show.
function ConfigureRoute({ epoch }: { epoch: number }) {
  return <ConfigureView key={epoch} onBack={useBack()} />;
}

// Not keyed, unlike Configure. This route carries no query, so every arrival
// at it is a route change and a fresh mount, and the list is read again.
function CatalogueRoute({ curator, onOpened }: {
  curator: boolean;
  onOpened: (to: string, state?: unknown) => void;
}) {
  return <CatalogueView curator={curator} onOpened={onOpened} />;
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
  // The ARQEDIA workspace, which curates what every other tenant is offered.
  //
  // COMPARED AS A STRING, DELIBERATELY. The claim arrives as "0", and 0 is
  // falsy - a Number() here with a truthiness test anywhere downstream would
  // make tenant 0 the one tenant the check never fires for, which is exactly
  // backwards. The screen only decides what is DRAWN; the refusal itself
  // lives in the API dispatcher, which is what the server trusts.
  const [curator, setCurator] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  async function check() {
    try {
      await getCurrentUser();
      const session = await fetchAuthSession();
      const claims: any = session.tokens?.idToken?.payload ?? {};
      const tenant = String(claims["custom:tenant_id"] ?? "");
      setWho(`${claims.email ?? ""} - tenant ${tenant || "?"}`);
      setCurator(tenant === "0");
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

  // Opening a report from the Catalogue reloads the configuration screen,
  // which counts here.
  const [configEpoch, setConfigEpoch] = useState(0);

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
        {/* Accepting a seat (10.7). It lands on Engagements and never on Get
            started: /welcome forks a base and publishes a configuration, and
            a colleague joining a workspace that already has one must not be
            shown that screen. Before this route existed the catch-all below
            took the link and showed a sign-in card for an account that did
            not exist yet. */}
        <Route path="/invitation"
               element={<InvitationView signedIn={false} who=""
                                        onSignOut={() => undefined}
                                        onDone={done} />} />
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
  // colour. Matched on the prefix: a screen reached with a query is still that
  // destination, and the rail should still read as open.
  const here = location.pathname;
  const railClass = (path: string) =>
    (path === "/" ? here === "/" : here.startsWith(path)) ? "on" : undefined;

  // The Catalogue is the destination; configuring a report and taking one of
  // ours are both reached from it, so the entry stays lit through all three.
  const catalogueClass = ["/catalogue", "/configure", "/welcome"]
    .some((p) => here.startsWith(p)) ? "on" : undefined;

  const opened = (to: string, state?: unknown) => {
    setConfigEpoch((n) => n + 1);
    navigate(to, { state });
  };

  return (
    <div className="shell" style={shellVars}>
      {/* The mark goes home, as a mark does on every site anybody has used
          (6.1). It was decoration; a person who wanted out of a screen had
          Back, which goes one step, or the rail, which asks them to know
          that Engagements is where home lives. */}
      <header ref={header}>
        <a className="mark" onClick={() => navigate("/")} title="Home">
          <img src={logoWhite} alt="" width="22" height="22" />
          <strong>ARQEDIA</strong>
        </a>
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
        {/* A screen rather than a choice. UX-04 made this a panel of options
            with the tenant's own memoranda behind one of them; they are the
            work and the reason for the screen, so they are the screen. */}
        <a className={catalogueClass} onClick={() => navigate("/catalogue")}>
          Template Catalogue
        </a>
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
          {/* Back goes one step; Home goes to Engagements, which is where
              every journey in the product starts (6.1). Both are drawn once,
              here, so they are in the same place on every screen and held
              there while the page scrolls (UX-16). Home is the quieter of
              the two: leaving a screen is ordinary, abandoning what you were
              doing is not. */}
          <div className="back-strip">
            <BackPill onClick={() => (leave.current ?? back)()} />
            <a className="home-pill" onClick={() => navigate("/")}>Home</a>
          </div>
          <main>
            <Routes>
              <Route path="/" element={<EngagementsRoute />} />
              <Route path="/engagements/:id" element={<EngagementRoute />} />
              <Route path="/memos/:id" element={<MemoRoute />} />
              <Route path="/catalogue"
                     element={<CatalogueRoute curator={curator} onOpened={opened} />} />
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
              {/* The same link, followed by a browser already signed in - as
                  themselves, or as a colleague on a shared machine. Accepting
                  would make an account for the invited address while this
                  session belongs to another, so it is refused with the one
                  control that fixes it rather than with a dead page (10.7). */}
              <Route path="/invitation"
                     element={<InvitationView signedIn who={who}
                                onSignOut={async () => {
                                  await signOut();
                                  setSignedIn(false);
                                }}
                                onDone={() => navigate("/")} />} />
              {/* Anything else would render an empty page. */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </BackContext.Provider>
      </div>
    </div>
  );
}
