import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  viewerApi, statusOf, ViewerError,
  type ViewerCredential, type ViewerPage, type ViewerShare,
} from "./api";
import { config } from "./config";
import logoWhite from "../../brand/logo-white.svg";

/**
 * The viewer. What a recipient sees: one memorandum, no rail, no Back, and
 * nothing of the product beyond downloading it and registering.
 *
 * OUTSIDE THE SIGNED-IN SHELL. App renders this before it asks whether
 * anybody is signed in, so a tenant who opens a link on their own machine
 * sees what the recipient sees, and a recipient never meets the sign-in card.
 *
 * THE MEMORANDUM IS THE WATERMARKED PDF, shown as itself. No HTML of the
 * memorandum is ever fetched here: that would be its text without the
 * recipient's address across it (decision of 1 October 2026, item 4). The
 * colours inside it are the tenant's; the bar above it is ARQEDIA's - the
 * one screen where the two palettes meet.
 *
 * THE LINK TOKEN IS IN THE #FRAGMENT, which the browser never sends to any
 * server, and it travels to ours in a header. It is not kept anywhere once
 * the tab is closed.
 *
 * A REGISTERED VIEWER signs in at /viewer to a pool of their own - never the
 * customer pool - and their token is kept for this tab only.
 *
 * THE LINK ALONE OPENS NOTHING (fix/share-link-possession-read). The first
 * open on a browser asks for a code emailed to the recipient, and keeps a
 * device token for them once it is entered (api.ts). A forwarded link asks
 * whoever holds it for a code they cannot get.
 */

const SESSION_KEY = "arqedia.viewer.id_token";

function day(iso: string | null | undefined) {
  return (iso ?? "").slice(0, 10);
}

function tokenFromHash(hash: string): string {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  return params.get("t") ?? "";
}

function readSession(): string {
  try { return sessionStorage.getItem(SESSION_KEY) ?? ""; } catch { return ""; }
}

function keepSession(idToken: string) {
  try {
    if (idToken) sessionStorage.setItem(SESSION_KEY, idToken);
    else sessionStorage.removeItem(SESSION_KEY);
  } catch { /* a private window; the page still works, just not on reload */ }
}

/** The bar above the memorandum, in ARQEDIA's palette.
 *
 *  THE MARK GOES TO THE MARKETING SITE, not to the application. Somebody who
 *  has never heard of ARQEDIA and has just been sent a document through it
 *  should be able to find out who we are before trusting it. In a new tab, so
 *  the memorandum and the link that opened it stay where they are. The address
 *  is the build's (config.siteUrl, from site_host in dns.tf), not a second
 *  copy of it. */
function Bar({ children }: { children?: React.ReactNode }) {
  return (
    <div className="viewer-bar">
      <a className="viewer-mark" href={config.siteUrl}
         target="_blank" rel="noopener noreferrer"
         title="What ARQEDIA is (opens in a new tab)">
        <img src={logoWhite} alt="" width="20" height="20" />
        <strong>ARQEDIA</strong>
      </a>
      {children}
    </div>
  );
}

// --- one memorandum --------------------------------------------------------

function Memorandum({ grantId, credential, onSignedIn }: {
  grantId: string;
  credential: ViewerCredential;
  onSignedIn?: (idToken: string) => void;
}) {
  const [page, setPage] = useState<ViewerPage | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [registering, setRegistering] = useState(false);
  // This browser is not verified for the share's recipient: what the server
  // said, so the screen can name where the code goes and offer sign-in.
  const [device, setDevice] = useState<{ sentTo: string; registered: boolean } | null>(null);

  async function load() {
    setError("");
    setDevice(null);
    try {
      setPage(await viewerApi.open(grantId, credential));
    } catch (err) {
      if (err instanceof ViewerError && err.deviceRequired) {
        setDevice({ sentTo: String(err.detail?.sent_to ?? ""),
                    registered: err.detail?.registered === true });
        return;
      }
      setError(String((err as Error).message));
    }
  }
  useEffect(() => { load(); }, [grantId, credential.kind]);

  async function download() {
    setDownloading(true);
    setError("");
    try {
      const { download_url } = await viewerApi.download(grantId, credential);
      window.location.assign(download_url);
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setDownloading(false);
    }
  }

  if (device && credential.kind === "link") {
    return (
      <div className="viewer public">
        <Bar />
        <VerifyDevice grantId={grantId} token={credential.token}
                      sentTo={device.sentTo} registered={device.registered}
                      onVerified={load} />
      </div>
    );
  }
  if (error && !page) {
    return (
      <div className="viewer public">
        <Bar />
        <div className="viewer-message">
          <p>{error}</p>
          <p className="muted small">
            Registered already? <a href="/viewer">Sign in</a> to see what has
            been shared with you.
          </p>
        </div>
      </div>
    );
  }
  if (!page) {
    return (
      <div className="viewer public">
        <Bar />
        <p className="viewer-message muted">Opening&hellip;</p>
      </div>
    );
  }

  return (
    <div className="viewer public">
      <Bar>
        <span className="muted small">
          {page.memo_label}{page.subject ? ` · ${page.subject}` : ""}
          {" · "}shared by {page.tenant_name}
          {" · "}access ends {day(page.expires_at)}
        </span>
        <span className="viewer-actions">
          <button onClick={download} disabled={downloading}>
            {downloading ? "Preparing…" : "Download"}
          </button>
          {credential.kind === "link" && !page.registered && (
            <a className="secondary" onClick={() => setRegistering(true)}>
              Register to keep access
            </a>
          )}
        </span>
      </Bar>

      {error && <p className="error viewer-message">{error}</p>}

      {page.unused_device_code_at && !dismissed(page.unused_device_code_at) && (
        <UnusedCode at={page.unused_device_code_at} />
      )}

      {registering && credential.kind === "link" && (
        <Register grantId={grantId} token={credential.token} page={page}
                  onDone={(idToken, expiresAt) => {
                    setRegistering(false);
                    setPage({ ...page, registered: true, expires_at: expiresAt });
                    onSignedIn?.(idToken);
                  }}
                  onCancel={() => setRegistering(false)} />
      )}

      <iframe className="viewer-frame" src={page.view_url}
              title={`${page.memo_label} — ${page.subject ?? ""}`} />

      <p className="muted small viewer-note">
        Shared with {page.recipient_email}. Every page carries that address,
        and a downloaded copy also carries the time it was taken.
      </p>
    </div>
  );
}

// --- verifying this browser ----------------------------------------------------

/** The first open on a browser: a code to the recipient's own inbox, then
 *  the memorandum. Nothing of it is shown before. */
function VerifyDevice({ grantId, token, sentTo, registered, onVerified }: {
  grantId: string;
  token: string;
  sentTo: string;
  registered: boolean;
  onVerified: () => void;
}) {
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send() {
    setBusy(true);
    setError("");
    try {
      await viewerApi.verifyCode(grantId, token);
      setSent(true);
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true);
    setError("");
    try {
      await viewerApi.verify(grantId, token, code.trim());
      onVerified();
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="viewer-register form">
      <h4>Confirm it&rsquo;s you</h4>
      <p className="small">
        This memorandum was shared with {sentTo}. To open it on this device,
        we&rsquo;ll email a code to that address. You only do this once on
        each device.
      </p>
      {!sent ? (
        <div className="form-actions">
          <button onClick={send} disabled={busy}>
            {busy ? "Sending…" : "Email me a code"}
          </button>
        </div>
      ) : (
        <>
          <label className="row">
            <span>Code sent to {sentTo} &mdash; it lasts ten minutes</span>
            <input inputMode="numeric" autoComplete="one-time-code" value={code}
                   onChange={(e) => setCode(e.target.value)} />
          </label>
          <p className="small">
            Not arrived? <a onClick={busy ? undefined : send}>Send another</a>.
          </p>
          <div className="form-actions">
            <button onClick={verify} disabled={busy || code.trim().length < 6}>
              {busy ? "Checking…" : "Open"}
            </button>
          </div>
        </>
      )}
      {registered && (
        <p className="muted small">
          Registered? <a href="/viewer">Sign in instead</a>.
        </p>
      )}
      <p className="muted small">
        If this link was forwarded to you, it won&rsquo;t open here: ask the
        person who shared it to share it with you directly.
      </p>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

// An unused new-device code, said once per code. Dismissing it is a matter
// for this browser only, so it is kept in local storage by the code's time.
const SEEN_KEY = "arqedia.unused-code-seen";

function dismissed(at: string): boolean {
  try { return localStorage.getItem(SEEN_KEY) === at; } catch { return false; }
}

/** Asked for on 7 October: the recipient's sign, besides the warning email,
 *  that a new-device code went out and was never entered. */
function UnusedCode({ at }: { at: string }) {
  const [gone, setGone] = useState(false);
  if (gone) return null;
  return (
    <p className="warn viewer-message">
      A code to open your shares on a new device was emailed to you on{" "}
      {at.slice(0, 16).replace("T", " ")} UTC and hasn&rsquo;t been used. If
      that wasn&rsquo;t you, someone else may have your link &mdash; tell the
      person who sent it.{" "}
      <a onClick={() => {
        try { localStorage.setItem(SEEN_KEY, at); } catch { /* fine */ }
        setGone(true);
      }}>Dismiss</a>
    </p>
  );
}

// --- registering -------------------------------------------------------------

function Register({ grantId, token, page, onDone, onCancel }: {
  grantId: string;
  token: string;
  page: ViewerPage;
  onDone: (idToken: string, expiresAt: string) => void;
  onCancel: () => void;
}) {
  const [password, setPassword] = useState("");
  const [terms, setTerms] = useState(false);
  // UNTICKED, whatever the jurisdiction, until counsel says which default
  // applies where (share_viewer_spec §7.1). Unticked is never wrong.
  const [marketing, setMarketing] = useState(false);
  const [setup, setSetup] = useState<{ session: string; secret_code: string;
                                       otpauth: string; qr_svg: string | null;
                                       restarted: boolean } | null>(null);
  // The authenticator step cannot go on - the session timed out - and the
  // way forward is a new emailed code, not another try at this one.
  const [mustRestart, setMustRestart] = useState(false);
  const [code, setCode] = useState("");
  // The code emailed to the recipient's own address. A link can be
  // forwarded; registering needs what only the recipient's inbox has.
  const [sentTo, setSentTo] = useState("");
  const [emailCode, setEmailCode] = useState("");
  // A browser verified in the last fifteen minutes has just proved the
  // inbox, and registers without a second code. If those minutes pass while
  // the form is open, the server asks after all, and the code step appears.
  const [needsCode, setNeedsCode] = useState(page.register_needs_code);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function sendCode() {
    setBusy(true);
    setError("");
    try {
      setSentTo((await viewerApi.registerCode(grantId, token)).sent_to);
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function begin() {
    setBusy(true);
    setError("");
    try {
      setSetup(await viewerApi.register(grantId, token, {
        email_code: needsCode ? emailCode.trim() : "", password,
        accept_terms: terms, marketing_opt_in: marketing }));
    } catch (err) {
      // Only the server's own "a code is needed" - never any 400, which
      // would turn a rejected password into a request for a code.
      if (err instanceof ViewerError && err.detail?.code_required === true) {
        setNeedsCode(true);
        setSentTo("");
        setError(String(err.message));
        return;
      }
      setError(String((err as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!setup) return;
    setBusy(true);
    setError("");
    try {
      const done = await viewerApi.confirm(grantId, token, {
        session: setup.session, code: code.trim(), accept_terms: terms,
        marketing_opt_in: marketing });
      onDone(done.id_token, done.expires_at ?? page.expires_at);
    } catch (err) {
      setError(String((err as Error).message));
      setMustRestart(err instanceof ViewerError && err.restart);
    } finally {
      setBusy(false);
    }
  }

  /** Back to the first step: a new emailed code, then the password, then a
   *  new key. The old key is spent - the screen says so when the new one
   *  arrives (restarted). The password typed is kept. */
  function startAgain() {
    setSetup(null);
    setSentTo("");
    setEmailCode("");
    setCode("");
    setError("");
    setMustRestart(false);
  }

  return (
    <div className="viewer-register form">
      <h4>Register to keep access</h4>
      {page.expiry_set_by_tenant ? (
        <p className="muted small">
          {page.tenant_name} set this share to end on {day(page.expires_at)},
          and registering does not change that. It does keep anything shared
          with you without a fixed date for six months from when it was sent.
        </p>
      ) : (
        <p className="muted small">
          Registered, you keep this memorandum for six months from when it
          was shared, instead of two weeks. You need a password and an
          authenticator app.
        </p>
      )}

      {!setup && needsCode && !sentTo ? (
        <>
          <p className="small">
            First we email a code to {page.recipient_email}, the address this
            was shared with. Registering needs it, so nobody else holding
            this link can register in your name.
          </p>
          <div className="form-actions">
            <button onClick={sendCode} disabled={busy}>
              {busy ? "Sending…" : "Email me a code"}
            </button>
            <a className="secondary" onClick={onCancel}>Not now</a>
          </div>
        </>
      ) : !setup ? (
        <>
          <label className="row">
            <span>Email</span>
            <input value={page.recipient_email} disabled />
          </label>
          {needsCode && (
            <>
              <label className="row">
                <span>Code sent to {sentTo} &mdash; it lasts ten minutes</span>
                <input inputMode="numeric" autoComplete="one-time-code"
                       value={emailCode}
                       onChange={(e) => setEmailCode(e.target.value)} />
              </label>
              <p className="small">
                Not arrived? <a onClick={busy ? undefined : sendCode}>Send another</a>.
              </p>
            </>
          )}
          <label className="row">
            <span>Password &mdash; at least 12 characters, upper case, lower case and a number</span>
            <input type="password" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </label>
          {/* No link: the terms and privacy policy are not published yet,
              and a link to nothing is worse than none. Held as open in the
              share-recipient report. */}
          <label className="affirm">
            <input type="checkbox" checked={terms}
                   onChange={(e) => setTerms(e.target.checked)} />
            <span>I accept ARQEDIA&rsquo;s terms of use and privacy policy.</span>
          </label>
          <label className="affirm">
            <input type="checkbox" checked={marketing}
                   onChange={(e) => setMarketing(e.target.checked)} />
            <span>Email me about ARQEDIA. You can stop this at any time.</span>
          </label>
          <div className="form-actions">
            <button onClick={begin}
                    disabled={busy || !terms || !password
                              || (needsCode && emailCode.trim().length < 6)}>
              {busy ? "Working…" : "Continue"}
            </button>
            <a className="secondary" onClick={onCancel}>Not now</a>
          </div>
        </>
      ) : (
        <>
          {/* Once the session has gone, the key and QR below are spent:
              hidden, so nobody tries again with them. Start again issues
              new ones. */}
          {!mustRestart && (
            <>
              {/* Only after a restart: the key below replaces the one the
                  earlier attempt issued, so its authenticator entry now makes
                  codes that never match (stale-entry notice, approved wording). */}
              {setup.restarted && (
                <p className="warn">
                  You started registering before. Delete the earlier ARQEDIA
                  entry from your authenticator app first. This new key replaces
                  it, and the old entry&rsquo;s codes won&rsquo;t work.
                </p>
              )}
              <p className="small">
                Scan this with your authenticator app, or add the key by hand,
                then enter the six-digit code it shows. You have 15 minutes.
              </p>
              {/* Beside the typed key, not instead of it: somebody may be
                  setting up on a device with no camera. Drawn by the server from
                  the same setup link as the key, so the two cannot disagree. */}
              {setup.qr_svg && (
                <img className="setup-qr" alt="QR code for your authenticator app"
                     width={180} height={180}
                     src={"data:image/svg+xml;charset=utf-8,"
                          + encodeURIComponent(setup.qr_svg)} />
              )}
              <p><code className="secret">{setup.secret_code.replace(/(.{4})/g, "$1 ").trim()}</code></p>
              <p className="small">
                On a phone, <a href={setup.otpauth}>open it in your authenticator</a>.
              </p>
            </>
          )}
          {!mustRestart && (
            <>
              <label className="row">
                <span>Code</span>
                <input inputMode="numeric" autoComplete="one-time-code" value={code}
                       onChange={(e) => setCode(e.target.value)} />
              </label>
              <div className="form-actions">
                <button onClick={confirm} disabled={busy || code.trim().length < 6}>
                  {busy ? "Checking…" : "Register"}
                </button>
                <a className="secondary" onClick={onCancel}>Not now</a>
              </div>
            </>
          )}
        </>
      )}
      {error && <p className="error">{error}</p>}
      {mustRestart && (
        <div className="form-actions">
          <button onClick={startAgain}>Start again</button>
          <a className="secondary" onClick={onCancel}>Not now</a>
        </div>
      )}
    </div>
  );
}

// --- a registered viewer -------------------------------------------------------

function SignIn({ onSignedIn }: { onSignedIn: (idToken: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [session, setSession] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function first() {
    setBusy(true);
    setError("");
    try {
      setSession((await viewerApi.signIn(email.trim(), password)).session);
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function second() {
    setBusy(true);
    setError("");
    try {
      onSignedIn((await viewerApi.signInCode(email.trim(), session, code.trim())).id_token);
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="viewer-register form">
      <h4>Sign in to see what has been shared with you</h4>
      <p className="muted small">
        For people who registered from a shared memorandum. This is not the
        ARQEDIA workspace sign-in.
      </p>
      {!session ? (
        <>
          <label className="row"><span>Email</span>
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="row"><span>Password</span>
            <input type="password" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
          </label>
          <div className="form-actions">
            <button onClick={first} disabled={busy || !email || !password}>
              {busy ? "Working…" : "Continue"}
            </button>
          </div>
        </>
      ) : (
        <>
          <label className="row"><span>Code from your authenticator</span>
            <input inputMode="numeric" autoComplete="one-time-code" value={code}
                   onChange={(e) => setCode(e.target.value)} />
          </label>
          <div className="form-actions">
            <button onClick={second} disabled={busy || code.trim().length < 6}>
              {busy ? "Checking…" : "Sign in"}
            </button>
          </div>
        </>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function Mine({ idToken, onOpen, onSignOut }: {
  idToken: string;
  onOpen: (grantId: string) => void;
  onSignOut: () => void;
}) {
  const [shares, setShares] = useState<ViewerShare[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    viewerApi.mine(idToken).then((r) => setShares(r.shares)).catch((err) => {
      // An hour on, the token has run out. Back to signing in, not a dead end.
      if (statusOf(err) === 401) onSignOut();
      else setError(String((err as Error).message));
    });
  }, [idToken]);

  return (
    <div className="viewer-register form">
      <h4>Shared with you</h4>
      {error && <p className="error">{error}</p>}
      {shares === null && !error && <p className="muted">Reading&hellip;</p>}
      {shares !== null && shares.length === 0 && (
        <p className="muted">Nothing is shared with you at the moment.</p>
      )}
      {shares !== null && shares.length > 0 && (
        <table className="docs">
          <tbody>
            {shares.map((s) => (
              <tr key={s.grant_id}>
                <td>
                  {s.expired ? s.memo_label : <a onClick={() => onOpen(s.grant_id)}>{s.memo_label}</a>}
                  {s.subject && <div className="muted small">{s.subject}</div>}
                </td>
                <td className="small">shared by {s.tenant_name}</td>
                <td className="ref">
                  {s.expired ? <span className="warn">ended {day(s.expires_at)}</span>
                             : <>until {day(s.expires_at)}</>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="small"><a onClick={onSignOut}>Sign out</a></p>
    </div>
  );
}

// --- the two routes ------------------------------------------------------------

/** /view/:grantId#t=<token> - a link from a share email. */
export function ViewerByLink() {
  const { grantId = "" } = useParams();
  const location = useLocation();
  const token = tokenFromHash(location.hash);
  return <Memorandum grantId={grantId} credential={{ kind: "link", token }}
                     onSignedIn={keepSession} />;
}

/** /viewer - a registered viewer, signed in to the viewer pool. */
export function ViewerSignedIn() {
  const [idToken, setIdToken] = useState(readSession());
  const [open, setOpen] = useState("");
  const navigate = useNavigate();

  const signOut = () => { keepSession(""); setIdToken(""); setOpen(""); };

  if (idToken && open) {
    return (
      <>
        <Memorandum grantId={open} credential={{ kind: "signed-in", idToken }} />
        <p className="viewer-note small"><a onClick={() => setOpen("")}>All shared with you</a></p>
      </>
    );
  }

  return (
    <div className="viewer public">
      <Bar />
      {idToken
        ? <Mine idToken={idToken} onOpen={setOpen} onSignOut={signOut} />
        : <SignIn onSignedIn={(t) => { keepSession(t); setIdToken(t); navigate("/viewer"); }} />}
    </div>
  );
}
