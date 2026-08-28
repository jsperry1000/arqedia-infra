import { useEffect, useState } from "react";
import { Amplify } from "aws-amplify";
import { signIn, signOut, confirmSignIn, getCurrentUser, fetchAuthSession } from "aws-amplify/auth";
import ReactMarkdown from "react-markdown";
import { config } from "./config";
import { api, type Engagement, type Doc, type MemoRef } from "./api";

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

function EngagementView({ id, onBack, onMemo }: {
  id: string; onBack: () => void; onMemo: (memoId: number) => void;
}) {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [memos, setMemos] = useState<MemoRef[]>([]);
  const [busy, setBusy] = useState("");

  async function refresh() {
    const [d, m] = await Promise.all([api.documents(id), api.memos(id)]);
    setDocs(d.documents);
    setMemos(m.memos);
  }

  // Documents are processed in the background, so poll - but only while
  // something is actually unfinished. Polling a settled engagement forever
  // is thousands of pointless requests from one open tab.
  const settling = docs.some((d) => !d.document_type || d.values === 0);

  useEffect(() => { refresh(); }, [id]);

  useEffect(() => {
    if (!settling && !busy) return;
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [id, settling, busy]);

  async function upload(files: FileList | null) {
    if (!files) return;
    for (const file of Array.from(files)) {
      setBusy("Uploading " + file.name);
      await api.upload(id, file);
    }
    setBusy("");
    refresh();
  }

  async function generate() {
    setBusy("Generating - this takes a minute or two");
    await api.generate(id);
    setTimeout(() => { setBusy(""); refresh(); }, 90000);
  }

  return (
    <div>
      <a onClick={onBack} className="back">Back</a>
      <h2>{id}</h2>

      <input type="file" multiple onChange={(e) => upload(e.target.files)} />
      {busy && <p className="busy">{busy}</p>}

      <h3>Documents</h3>
      {docs.length === 0 && <p className="muted">No documents yet.</p>}
      <table>
        <tbody>
          {docs.map((d) => (
            <tr key={d.document_id}>
              <td>{d.filename}</td>
              <td className="muted">{d.document_type ?? "unclassified"}</td>
              <td className="muted">{d.pages ?? "-"} pages</td>
              <td className="muted">{d.values} values</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Memos</h3>
      <button onClick={generate} disabled={docs.length === 0 || !!busy}>
        Generate memo
      </button>
      <table>
        <tbody>
          {memos.map((m) => (
            <tr key={m.memo_id} onClick={() => onMemo(m.memo_id)}>
              <td><a>Memo {m.memo_id}</a></td>
              <td className="muted">{m.generated_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- memo ------------------------------------------------------------------

function MemoView({ memoId, onBack }: { memoId: number; onBack: () => void }) {
  const [markdown, setMarkdown] = useState("");

  useEffect(() => {
    api.memo(memoId).then((m) => setMarkdown(m.markdown));
  }, [memoId]);

  return (
    <div>
      <a onClick={onBack} className="back">Back</a>
      <article className="memo">
        <ReactMarkdown>{markdown}</ReactMarkdown>
      </article>
    </div>
  );
}

// --- shell -----------------------------------------------------------------

export default function App() {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [who, setWho] = useState("");
  const [engagement, setEngagement] = useState<string | null>(null);
  const [memoId, setMemoId] = useState<number | null>(null);

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
        <a onClick={async () => { await signOut(); setSignedIn(false); }}>Sign out</a>
      </header>
      <main>
        {memoId !== null ? (
          <MemoView memoId={memoId} onBack={() => setMemoId(null)} />
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


