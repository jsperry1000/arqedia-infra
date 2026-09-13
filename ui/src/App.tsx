import { ConfigureView } from "./Configure";
import { SettingsView } from "./Settings";
import { MemoView } from "./Memo";
import { EngagementView } from "./Review";
import { useEffect, useState } from "react";
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

function ConfigureRoute() {
  return <ConfigureView onBack={useBack()} />;
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

  if (signedIn === null) return <div className="centre"><p className="muted">...</p></div>;
  if (!signedIn) return <SignIn onDone={check} />;

  return (
    <div className="shell">
      <header>
        <img src="/icon-white.png" alt="" width="22" height="22" />
        <strong>ARQEDIA</strong>
        <span className="muted">{who}</span>
        {/* Home. Every other screen is reached from here and there was no way
            back to the list except the Back link on whichever page you were
            on, which is several clicks from a memo. */}
        <a className="settings" onClick={() => navigate("/")}>Engagements</a>
        <a className="settings" onClick={() => navigate("/configure")}>Configure a Report</a>
        <a className="settings" onClick={() => navigate("/settings")}>Settings</a>
        <a onClick={async () => { await signOut(); setSignedIn(false); }}>Sign out</a>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<EngagementsRoute />} />
          <Route path="/engagements/:id" element={<EngagementRoute />} />
          <Route path="/memos/:id" element={<MemoRoute />} />
          <Route path="/configure" element={<ConfigureRoute />} />
          <Route path="/settings" element={<SettingsRoute />} />
          {/* Anything else would render an empty page. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}




