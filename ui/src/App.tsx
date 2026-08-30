import { SettingsView } from "./Settings";
import { MemoView } from "./Memo";
import { EngagementView } from "./Review";
import { useEffect, useState } from "react";
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

// --- one engagement --------------------------------------------------------

// --- memo ------------------------------------------------------------------

// --- shell -----------------------------------------------------------------

export default function App() {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [who, setWho] = useState("");
  const [engagement, setEngagement] = useState<string | null>(null);
  const [memoId, setMemoId] = useState<number | null>(null);
  const [settings, setSettings] = useState(false);

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
        <a className="settings" onClick={() => { setSettings(true); setMemoId(null); }}>Settings</a>
        <a onClick={async () => { await signOut(); setSignedIn(false); }}>Sign out</a>
      </header>
      <main>
        {settings ? (
          <SettingsView onBack={() => setSettings(false)} />
        ) : memoId !== null ? (
          <MemoView memoId={memoId} onBack={() => setMemoId(null)} onOpen={setMemoId} />
        ) : engagement !== null ? (
          <EngagementView id={engagement} onBack={() => setEngagement(null)}
                          onMemo={setMemoId} />
        ) : (
          <Engagements onOpen={setEngagement} />
        )}
      </main>
    </div>
  );
}



