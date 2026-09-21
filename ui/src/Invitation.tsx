import { useState } from "react";
import { signIn } from "aws-amplify/auth";
import { useSearchParams } from "react-router-dom";
import { api } from "./api";
import logoDeep from "../../brand/logo-deep.svg";

/**
 * Accepting a seat somebody reserved (10.7).
 *
 * The link is `/invitation?email=…&token=…`, built by the API and carried in
 * the invitation email. Until this page existed it landed on the sign-in
 * card - a card asking for an account that does not exist yet, with the token
 * read by nothing.
 *
 * THE ADDRESS IS FIXED. The token was minted against it, so a typed-over
 * address turns a valid invitation into a refusal nobody can explain. It is
 * shown, not offered.
 *
 * IT DOES NOT NAME WHO INVITED THEM, or the firm, or the role. Nothing here
 * can: reading any of that needs a route that trades the token for it, and
 * there is none (10.8). The email they arrived from named the person; this
 * page says "an ARQEDIA workspace" and stops there rather than guessing.
 *
 * THE ACCOUNT IS MADE HERE AND NOWHERE ELSE. Inviting reserves a seat and
 * writes no user: until this form is sent there is nothing in Cognito for
 * this address at all.
 */

const POLICY =
  "At least 12 characters, with an upper case letter, a lower case letter "
  + "and a number.";

export function InvitationView({ signedIn, who, onSignOut, onDone }: {
  signedIn: boolean;
  /** Who the browser is signed in as, for the sentence that tells them why
   *  this page will not proceed. */
  who: string;
  onSignOut: () => void;
  onDone: () => void;
}) {
  const [params] = useSearchParams();
  const email = (params.get("email") || "").trim();
  const token = (params.get("token") || "").trim();

  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const mismatch = again.length > 0 && password !== again;
  const ready = !!email && !!token && password.length > 0 && !mismatch;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.acceptInvitation({
        email, token, password, person_name: name.trim() || undefined });
      // Straight in, as signing up is: asking somebody to type the password
      // they set ninety seconds ago, on the screen where they set it, is a
      // checkpoint with nothing behind it.
      await signIn({ username: email, password });
      onDone();
    } catch (err: any) {
      setError(err?.message || String(err));
    } finally {
      setBusy(false);
    }
  }

  // Somebody already signed in - as themselves, or as a colleague on a shared
  // machine - clicking the link in their email. Accepting would make an
  // account for the invited address while the browser holds another's
  // session, so it is refused with the one thing that fixes it.
  if (signedIn) {
    return (
      <div className="centre">
        <div className="card">
          <img src={logoDeep} alt="" width="44" height="44" />
          <h1>ARQEDIA</h1>
          <p className="muted">
            This invitation is for <strong>{email || "another address"}</strong>,
            and this browser is signed in as {who || "somebody else"}.
          </p>
          <p className="muted small" style={{ margin: 0 }}>
            Sign out and open the link in your invitation again. Nothing about
            the invitation changes in the meantime &mdash; it stays open until
            it lapses.
          </p>
          <button onClick={onSignOut}>Sign out</button>
        </div>
      </div>
    );
  }

  return (
    <div className="centre">
      <form onSubmit={submit} className="card">
        <img src={logoDeep} alt="" width="44" height="44" />
        <h1>ARQEDIA</h1>

        <p className="muted">You have been invited to ARQEDIA.</p>

        {!email || !token ? (
          <p className="error">
            That invitation link is incomplete. Use the link in your
            invitation exactly as it was sent.
          </p>
        ) : (
          <>
            {/* Shown, not offered: the token was minted against this
                address. */}
            <p className="muted small" style={{ margin: 0 }}>
              A seat has been reserved for <strong>{email}</strong> in an
              ARQEDIA workspace. Set a password and it is yours.
            </p>

            <input placeholder="Your name" value={name} autoFocus
                   onChange={(e) => setName(e.target.value)} />
            <input type="password" placeholder="Password" value={password}
                   onChange={(e) => setPassword(e.target.value)} />
            <input type="password" placeholder="Password again" value={again}
                   onChange={(e) => setAgain(e.target.value)} />
            <p className="muted small" style={{ margin: 0 }}>
              {mismatch ? "The two passwords are not the same." : POLICY}
            </p>
          </>
        )}

        {error && <p className="error">{error}</p>}

        <button disabled={busy || !ready}>
          {busy ? "…" : "Accept and sign in"}
        </button>
      </form>
    </div>
  );
}
