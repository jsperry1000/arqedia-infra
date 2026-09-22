/**
 * The ARQEDIA staff console.
 *
 * WHO THIS IS FOR. ARQEDIA's own people, reading across every tenant. It is
 * not a customer surface: the pool is a different pool, the API is a
 * different API, and a customer's token is refused at the gateway before any
 * code here or there runs.
 *
 * THREE SCREENS, ALL READING. Tenants, one tenant's seats, and signups.
 * Nothing on this console writes, because there is nothing on the other end
 * to write to - the admin API declares three GET routes and no others.
 */
import { useCallback, useEffect, useState } from "react";
import { Amplify } from "aws-amplify";
import {
  confirmSignIn,
  fetchAuthSession,
  getCurrentUser,
  signIn,
  signOut,
} from "aws-amplify/auth";

import { api, type SeatsPage, type SignupsPage, type Tenant } from "./api";
import { config } from "./config";
// The one mark, from /brand - the same two files the application and the
// marketing site reference. There is no third copy.
import logoDeep from "../../brand/logo-deep.svg";

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: config.userPoolId,
      userPoolClientId: config.userPoolClientId,
    },
  },
});

/* --- sign in -------------------------------------------------------------
 *
 * THE FIRST SIGN-IN IS THREE STEPS, not one, and that is the pool's doing:
 * a staff account is admin-created with a temporary password, and the pool
 * has mfa_configuration = "ON". Cognito therefore asks for a new password
 * and then for an authenticator, in that order, inside one sign-in.
 *
 *   password    the temporary one from the invitation email
 *   new         a password meeting the staff policy: 14 characters, upper,
 *               lower, a digit and a symbol
 *   totp-setup  the secret, shown as a link an authenticator can take and as
 *               characters it can be typed from, then the first code it makes
 *   totp        every sign-in after the first: the code, and nothing else
 *
 * Amplify names these steps and we follow them rather than guessing which
 * comes next - CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED,
 * CONTINUE_SIGN_IN_WITH_TOTP_SETUP, CONFIRM_SIGN_IN_WITH_TOTP_CODE. A step
 * we do not recognise says so by name instead of looking like a wrong
 * password.
 */

type Step = "password" | "new" | "totp-setup" | "totp";

function SignIn({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState<Step>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [answer, setAnswer] = useState("");
  const [setupUri, setSetupUri] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  /** One place reads the step Amplify returned, so no caller has to know
   *  which challenge follows which. */
  function advance(next: { signInStep: string; totpSetupDetails?: unknown }) {
    switch (next.signInStep) {
      case "DONE":
        onDone();
        return;
      case "CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED":
        setAnswer("");
        setStep("new");
        return;
      case "CONTINUE_SIGN_IN_WITH_TOTP_SETUP": {
        const details = next.totpSetupDetails as {
          sharedSecret: string;
          getSetupUri: (appName: string, accountName?: string) => URL;
        };
        setSecret(details.sharedSecret);
        setSetupUri(details.getSetupUri(config.totpIssuer, email).toString());
        setAnswer("");
        setStep("totp-setup");
        return;
      }
      case "CONFIRM_SIGN_IN_WITH_TOTP_CODE":
        setAnswer("");
        setStep("totp");
        return;
      default:
        // Named rather than swallowed. A pool setting changed under us is a
        // thing to read, not a sign-in that mysteriously stops.
        setError(
          `This sign-in needs a step this console does not handle yet: ` +
          `${next.signInStep}.`);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (step === "password") {
        const res = await signIn({ username: email, password });
        if (res.isSignedIn) {
          onDone();
          return;
        }
        advance(res.nextStep);
        return;
      }
      const res = await confirmSignIn({ challengeResponse: answer });
      if (res.isSignedIn) {
        onDone();
        return;
      }
      advance(res.nextStep);
    } catch (err) {
      // `||`, not `??`: an error carrying an empty message would otherwise
      // leave the card blank and looking as though nothing happened.
      const said = (err as { message?: string })?.message || String(err);
      setError(said);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <img src={logoDeep} alt="ARQEDIA" />
      <h1>Staff</h1>

      {step === "password" && (
        <>
          <p className="note">ARQEDIA people only. Everyone else has the
            application at app.arqedia.com.</p>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" autoComplete="username" value={email}
                 onChange={(e) => setEmail(e.target.value)} required />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password"
                 value={password} onChange={(e) => setPassword(e.target.value)}
                 required />
        </>
      )}

      {step === "new" && (
        <>
          <p className="note">Set a password. Fourteen characters or more,
            with an upper case letter, a lower case letter, a number and a
            symbol.</p>
          <label htmlFor="new">New password</label>
          <input id="new" type="password" autoComplete="new-password"
                 value={answer} onChange={(e) => setAnswer(e.target.value)}
                 required />
        </>
      )}

      {step === "totp-setup" && (
        <>
          <p className="note">Add ARQEDIA to your authenticator app, then
            enter the code it shows. This is asked once; afterwards the code
            is all you need.</p>
          {/* The link an authenticator takes directly, and the characters it
              can be typed from - a phone set up on a laptop cannot scan
              anything, and a QR image would be a dependency for one case. */}
          <p><a href={setupUri}>Open in your authenticator app</a></p>
          <p className="note">Or enter this key by hand:</p>
          <code className="secret">{secret}</code>
          <label htmlFor="code">Code from the app</label>
          <input id="code" inputMode="numeric" autoComplete="one-time-code"
                 value={answer} onChange={(e) => setAnswer(e.target.value)}
                 required />
        </>
      )}

      {step === "totp" && (
        <>
          <p className="note">Enter the code from your authenticator app.</p>
          <label htmlFor="code">Code</label>
          <input id="code" inputMode="numeric" autoComplete="one-time-code"
                 value={answer} onChange={(e) => setAnswer(e.target.value)}
                 required />
        </>
      )}

      {error && <p className="error">{error}</p>}

      <button className="go" type="submit" disabled={busy}>
        {busy ? "Working…" : "Continue"}
      </button>
    </form>
  );
}

/* --- screens -------------------------------------------------------------- */

function when(value: string | null) {
  // The API returns the database's own timestamps. They are shown as they
  // are: a console read by three people does not need a formatter, and a
  // reformatted date is one more thing that can disagree with the row.
  return value ? value.slice(0, 16) : "—";
}

function Tenants({ onSeats }: { onSeats: (t: Tenant) => void }) {
  const [tenants, setTenants] = useState<Tenant[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.tenants()
      .then((r) => setTenants(r.tenants))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!tenants) return <p className="note">Reading…</p>;

  return (
    <>
      <h1>Tenants</h1>
      <p className="note">{tenants.length} in the system. Plan is shown twice:
        the tenant&rsquo;s own copy and the subscription&rsquo;s. Where they
        disagree, the subscription is the plan.</p>
      <table>
        <thead>
          <tr>
            <th>#</th><th>Name</th><th>Plan</th><th>Subscription</th>
            <th>Status</th><th>Seats</th><th>Created</th><th>Trial ends</th>
            <th>Revision</th><th></th>
          </tr>
        </thead>
        <tbody>
          {tenants.map((t) => {
            const drift = !!t.subscription_plan && t.plan !== t.subscription_plan;
            return (
              <tr key={t.tenant_id}>
                <td className="number">{t.tenant_id}</td>
                <td>{t.name}</td>
                <td className={drift ? "disagrees" : undefined}>{t.plan ?? "—"}</td>
                <td>{t.subscription_plan ?? "—"}</td>
                <td>{t.subscription_status ?? "—"}</td>
                <td className="number">{t.seats}</td>
                <td>{when(t.created_at)}</td>
                <td>{when(t.trial_ends_at)}</td>
                <td className="number">{t.active_revision ?? "—"}</td>
                <td>
                  <button className="link" onClick={() => onSeats(t)}>Seats</button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}

function Seats({ tenant }: { tenant: Tenant }) {
  const [page, setPage] = useState<SeatsPage | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setPage(null);
    setError("");
    api.seats(tenant.tenant_id)
      .then(setPage)
      .catch((e) => setError(e.message));
  }, [tenant.tenant_id]);

  if (error) return <p className="error">{error}</p>;
  if (!page) return <p className="note">Reading…</p>;

  return (
    <>
      <h1>{page.name}</h1>
      <p className="note">Tenant {page.tenant_id}.</p>

      <h2>Seats</h2>
      {page.seats.length === 0
        ? <p className="note">None. Nobody has accepted a seat here.</p>
        : (
          <table>
            <thead>
              <tr><th>#</th><th>Email</th><th>Role</th><th>Invited by</th>
                <th>Accepted</th></tr>
            </thead>
            <tbody>
              {page.seats.map((s) => (
                <tr key={s.seat_id}>
                  <td className="number">{s.seat_id}</td>
                  <td>{s.email}</td>
                  <td>{s.role}</td>
                  <td>{s.invited_by ?? "—"}</td>
                  <td>{when(s.accepted_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

      <h2>Open invitations</h2>
      {/* Open means neither revoked nor lapsed. A seat is reserved for seven
          days and then lapses, so an invitation past its date is not
          outstanding and is not counted as one. */}
      {page.invitations.length === 0
        ? <p className="note">None outstanding.</p>
        : (
          <table>
            <thead>
              <tr><th>#</th><th>Email</th><th>Role</th><th>Invited by</th>
                <th>Sent</th><th>Lapses</th></tr>
            </thead>
            <tbody>
              {page.invitations.map((i) => (
                <tr key={i.invitation_id}>
                  <td className="number">{i.invitation_id}</td>
                  <td>{i.email}</td>
                  <td>{i.role}</td>
                  <td>{i.invited_by ?? "—"}</td>
                  <td>{when(i.created_at)}</td>
                  <td>{when(i.expires_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
    </>
  );
}

const PAGE = 50;

function Signups() {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<SignupsPage | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.signups(PAGE, offset)
      .then(setPage)
      .catch((e) => setError(e.message));
  }, [offset]);

  if (error) return <p className="error">{error}</p>;
  if (!page) return <p className="note">Reading…</p>;

  return (
    <>
      <h1>Signups</h1>
      {/* THE ADDRESS IS NOT HERE AND CANNOT BE. signup_attempt keeps a domain
          and a hash of the address, never the address, so this screen reports
          by domain. The hash is shown because it is what makes two attempts
          from one address recognisable as the same person. */}
      <p className="note">{page.total} attempts, newest first. The address is
        not recorded - only its domain and a hash, which is what tells two
        attempts from one person apart from two people.</p>
      <table>
        <thead>
          <tr><th>#</th><th>Domain</th><th>Outcome</th><th>Detail</th>
            <th>IP</th><th>Hash</th><th>When</th></tr>
        </thead>
        <tbody>
          {page.attempts.map((a) => (
            <tr key={a.attempt_id}>
              <td className="number">{a.attempt_id}</td>
              <td>{a.email_domain}</td>
              <td>{a.outcome}</td>
              <td>{a.detail ?? "—"}</td>
              <td className="fixed">{a.ip ?? "—"}</td>
              <td className="fixed">{a.email_hash.slice(0, 12)}</td>
              <td>{when(a.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="paging">
        <button disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE))}>
          Newer
        </button>
        <button disabled={page.next_offset === null}
                onClick={() => setOffset(page.next_offset ?? offset)}>
          Older
        </button>
        <span>{offset + 1}–{offset + page.attempts.length} of {page.total}</span>
      </div>
    </>
  );
}

/* --- the frame ------------------------------------------------------------ */

type Tab = "tenants" | "seats" | "signups";

export function App() {
  const [ready, setReady] = useState(false);
  const [who, setWho] = useState("");
  const [tab, setTab] = useState<Tab>("tenants");
  const [tenant, setTenant] = useState<Tenant | null>(null);

  const load = useCallback(async () => {
    try {
      await getCurrentUser();
      const session = await fetchAuthSession();
      const claims = session.tokens?.idToken?.payload;
      setWho(String(claims?.email ?? claims?.sub ?? ""));
    } catch {
      setWho("");
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  if (!ready) return null;
  if (!who) return <SignIn onDone={() => { setReady(false); void load(); }} />;

  return (
    <>
      {/* Said out loud on every screen. Somebody looking at this console is
          looking at every firm's data at once, and it should never be
          mistaken for one firm's own workspace. */}
      <div className="banner">Every tenant · read only</div>
      <div className="shell">
        <header>
          <img src={logoDeep} alt="ARQEDIA" />
          <strong>Staff</strong>
          <span className="who">
            {who}
            {" · "}
            <button className="link" onClick={async () => {
              await signOut();
              setWho("");
            }}>Sign out</button>
          </span>
        </header>

        <nav className="tabs">
          <button aria-current={tab === "tenants" ? "page" : undefined}
                  onClick={() => setTab("tenants")}>Tenants</button>
          <button aria-current={tab === "seats" ? "page" : undefined}
                  disabled={!tenant}
                  onClick={() => setTab("seats")}>
            {tenant ? `Seats · ${tenant.name}` : "Seats"}
          </button>
          <button aria-current={tab === "signups" ? "page" : undefined}
                  onClick={() => setTab("signups")}>Signups</button>
        </nav>

        {tab === "tenants" && (
          <Tenants onSeats={(t) => { setTenant(t); setTab("seats"); }} />
        )}
        {tab === "seats" && tenant && <Seats tenant={tenant} />}
        {tab === "signups" && <Signups />}
      </div>
    </>
  );
}
