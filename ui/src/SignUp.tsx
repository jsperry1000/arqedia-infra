import { useState } from "react";
import { signIn } from "aws-amplify/auth";
import { api } from "./api";
import { Working } from "./shell";
import { config } from "./config";
import { REGIONS, JURISDICTIONS } from "./mock";

/**
 * Signing up. Unattended: no queue, no manual approval, no card.
 *
 * The order is the one in the onboarding specification, and each step exists
 * for a reason rather than for completeness:
 *
 *   1  email and password      one trial per email domain
 *   2  organisation            the declared jurisdiction binds, not the IP
 *   3  region                  suggested, confirmed, and then immutable
 *   4  the code                nothing is created until the address answers
 *
 * THE SECOND-ADMINISTRATOR STEP IS GONE (18.8). It was step 4, it was
 * optional, it had no bearing on reaching a first memorandum, and it was the
 * likeliest place to lose somebody - four screens in, being asked for a
 * colleague's address before they had seen the product.
 *
 * IT ALSO DID NOTHING. The address travelled to the server and was written to
 * pending_signup.second_admin, and nothing ever read that column: verify()
 * selects it and never uses it, no seat_invitation was created, no email was
 * sent. Somebody who typed a colleague in was told "They will be invited as
 * an administrator" and no invitation existed. Checked on dev before this was
 * touched - every pending_signup row has it NULL.
 *
 * So it moves to Get started, where a first sign-in lands, as a prompt
 * pointing at the seats screen - which is the one place in the product that
 * really does invite somebody. The server is unchanged: the field is simply
 * no longer sent, the column stays as it is, and nothing that read it has to
 * be found, because nothing did.
 *
 * THE CODE MOVED TO THE END. It was second, which meant a person waited for
 * an email before they had told us anything - and every refusal we could have
 * given them cheaply arrived after that wait instead of before it. Now every
 * check runs on the last click, and the code is asked for once there is
 * something to create.
 *
 * THE STARTER PACK STEP IS GONE (TPL-02). It asked which memorandum somebody
 * wanted, from six of which one ships, before they had seen what any of them
 * contains and in a place with no room to show them. Get started asks it after
 * signing in, against the memoranda that actually exist, with each one's
 * headings under its section count. Asking here as well was asking twice, and
 * asking first in the worse place.
 *
 * NOTHING IS SENT AS `pack`. Nobody chooses one here any more, so there is
 * nothing honest to record. The handler still accepts the field and the column
 * still exists; see the note in signup/app.py.
 *
 * The password never leaves this component until the final call. It is held
 * in React state and sent with the code, because there is nothing to set it
 * on before then and nowhere we would want it stored in the meantime.
 *
 * SIGNING UP IS REAL. Both routes are live. Sending the code needs SES
 * production access, which is pending - until it is granted, the last step
 * fails at the send and nothing is created.
 */

const STEPS = [
  "Your details",
  "Organisation",
  "Region",
  "Verify",
];

// The last step, and the one before it. Named because the flow turns on them
// in five places - the guard, the two buttons, the panel and where `begin`
// lands - and five bare integers shifted by one is where an off-by-one lives.
// This is the whole cost of removing a step: one number (18.8).
const VERIFY = 3;
const LAST_BEFORE_VERIFY = VERIFY - 1;

export function SignUp({ onSignIn, onSignedUp }: {
  onSignIn: () => void;
  onSignedUp: () => void;
}) {
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [personName, setPersonName] = useState("");
  const [code, setCode] = useState("");
  const [org, setOrg] = useState("");
  const [jurisdiction, setJurisdiction] = useState(JURISDICTIONS[0]);
  const [region, setRegion] = useState(REGIONS[0].code);

  const domain = email.includes("@") ? email.split("@")[1] : "";

  const ready =
    step === 0 ? /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) && password.length >= 12 :
    step === 1 ? org.trim().length > 0 :
    step === VERIFY ? code.trim().length === 6 :
    true;

  function message(err: unknown) {
    const text = String((err as Error)?.message ?? err);
    try { return JSON.parse(text).error ?? text; } catch { return text; }
  }

  /** Leaving the details behind runs every check and sends the code. A person
   *  who is going to be refused learns it here, before they fill in three more
   *  screens. */
  async function begin() {
    setBusy("Checking");
    setError("");
    try {
      await api.signup({
        email, org_name: org, jurisdiction, region,
      });
      setStep(VERIFY);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  async function finish() {
    setBusy("Creating your workspace");
    setError("");
    try {
      await api.signupVerify({ email, code, password, person_name: personName });
      // Straight in. Asking somebody to type the password they set ninety
      // seconds ago, on the screen where they set it, is a checkpoint with
      // nothing behind it.
      await signIn({ username: email, password });
      onSignedUp();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  async function resend() {
    setBusy("Sending another code");
    setError("");
    try {
      await api.signup({
        email, org_name: org, jurisdiction, region,
      });
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  const next = () =>
    (step === LAST_BEFORE_VERIFY ? begin() : setStep((n) => n + 1));

  return (
    <div className="signup">
      <div className="signup-head">
        <h1>ARQEDIA</h1>
        <p className="muted">
          30 days, full use, no card. $5.00 of metered credit while you look.
        </p>
        {/* A way out, on every step (5.3). Nothing has been created at any
            point before the code is answered, so leaving costs nothing and
            nothing has to be undone - but until this there was no door: the
            only control that left the flow was "Sign in" at the very foot,
            which reads as an answer to a different question.
            HOME IS THE MARKETING SITE, not the sign-in card. Somebody
            abandoning a signup has no account to sign in to, and the page
            they came from is the one that persuaded them. The address is
            Terraform's, through the build; see config.ts. */}
        <a className="small signup-home" href={config.siteUrl}>
          Leave and go home
        </a>
      </div>

      <ol className="stepper">
        {STEPS.map((label, i) => (
          <li key={label}
              className={i === step ? "on" : i < step ? "done" : undefined}>
            <span className="n">{i + 1}</span>
            <span className="t">{label}</span>
          </li>
        ))}
      </ol>

      <div className="signup-card">
        {error && <p className="error">{error}</p>}
        {busy && <Working what={busy} />}

        {step === 0 && (
          <>
            <h3>Your details</h3>
            <p className="muted small">
              A business address. One trial per email domain, so a colleague
              signing up separately joins your seats rather than starting again.
            </p>
            <label className="row">
              <span>Email</span>
              <input placeholder="name@yourfirm.com" value={email} autoFocus
                     onChange={(e) => setEmail(e.target.value)} />
            </label>
            {domain && (
              <p className="muted small">
                The trial will belong to <strong>{domain}</strong>.
              </p>
            )}
            <label className="row">
              <span>Your name</span>
              <input value={personName} placeholder="Susan Perry"
                     onChange={(e) => setPersonName(e.target.value)} />
            </label>
            <label className="row">
              <span>Password</span>
              <input type="password" value={password}
                     onChange={(e) => setPassword(e.target.value)} />
              <span className="muted small">
                Twelve characters or more. You set it now and are not asked to
                change it on first sign-in.
              </span>
            </label>
          </>
        )}

        {step === 1 && (
          <>
            <h3>Your organisation</h3>
            <label className="row">
              <span>Name</span>
              <input placeholder="Vantage Mercantile" value={org} autoFocus
                     onChange={(e) => setOrg(e.target.value)} />
              <span className="muted small">
                This is what a recipient sees on a memorandum you share.
              </span>
            </label>
            <label className="row">
              <span>Jurisdiction</span>
              <select value={jurisdiction}
                      onChange={(e) => setJurisdiction(e.target.value)}>
                {JURISDICTIONS.map((j) => <option key={j}>{j}</option>)}
              </select>
              <span className="muted small">
                What you declare here binds, not the address the request came
                from. It decides the terms you contract on.
              </span>
            </label>
          </>
        )}

        {step === 2 && (
          <>
            <h3>Where your documents live</h3>
            <p className="muted small">
              Confirm it. A region cannot be changed afterwards, because the
              documents and everything read from them stay where they were
              first written.
            </p>
            {REGIONS.map((r, i) => (
              <label className="bind" key={r.code}>
                <input type="radio" name="region" checked={region === r.code}
                       onChange={() => setRegion(r.code)} />
                {r.label}
                {i === 0 && <span className="in-use" style={{ marginLeft: 8 }}>suggested</span>}
              </label>
            ))}
            <p className="revision-note" style={{ marginTop: 14 }}>
              <strong>This one cannot be undone.</strong> Moving a tenant to
              another region later means re-filing every document, and every
              memorandum already written would name a revision that no longer
              has the documents behind it.
            </p>

            {/* THE SUMMARY CAME WITH THE STEP THAT WENT (18.8). It sat under
                the second administrator, which was the last step before the
                code; this is that step now, and a person should read what
                they are about to start immediately before starting it. */}
            <h4>What begins when you finish</h4>
            <table className="docs">
              <tbody>
                <tr><td>Trial</td><td className="ref">30 days, full use</td></tr>
                <tr><td>Metered credit</td><td className="ref">$5.00</td></tr>
                <tr><td>Card</td><td className="ref">none held</td></tr>
                <tr><td>Organisation</td><td className="ref">{org || "not set"}</td></tr>
                <tr><td>Jurisdiction</td><td className="ref">{jurisdiction}</td></tr>
                <tr><td>Region</td><td className="ref">{region}</td></tr>
              </tbody>
            </table>
            {/* No memorandum row, and no second-administrator row. Which
                memoranda a tenant gets is chosen on Get started, after
                signing in; so now is a colleague, for the reason at the head
                of this file. Saying anything about either here would be
                promising something this screen does not do. */}
          </>
        )}

        {step === VERIFY && (
          <>
            <h3>Verify your address</h3>
            <p className="muted small">
              A six-figure code has gone to <strong>{email}</strong>. Nothing is
              created until it answers &mdash; which is also what stops a
              throwaway address taking a trial.
            </p>
            <label className="row">
              <span>Code</span>
              <input value={code} autoFocus placeholder="000000"
                     style={{ maxWidth: 180, fontFamily: "var(--mono)",
                              fontSize: 18, letterSpacing: "0.25em" }}
                     onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
            </label>
            <a className="small" onClick={resend}>Send it again</a>
            <p className="muted small">
              It lasts fifteen minutes. Asking for another voids the first.
            </p>
          </>
        )}

        <div className="form-actions">
          {/* BACK KEEPS ITS PLACE ON EVERY STEP (5.4). Rendered even where
              there is nowhere to go back to - the first step, and the verify
              step, where the code has already been sent - because a control
              that appears and disappears moves the button beside it, and a
              person clicking Continue four times in the same spot should not
              find Back under the pointer on the fifth. Hidden rather than
              absent: it holds its width. */}
          <a className="secondary"
             style={step > 0 && step < VERIFY
               ? undefined : { visibility: "hidden" }}
             aria-hidden={!(step > 0 && step < VERIFY)}
             onClick={() => { if (step > 0 && step < VERIFY) setStep((n) => n - 1); }}>
            Back
          </a>
          {step < VERIFY ? (
            <button onClick={next} disabled={!ready || !!busy}>
              {step === LAST_BEFORE_VERIFY ? "Send my code" : "Continue"}
            </button>
          ) : (
            <button onClick={finish} disabled={!ready || !!busy}>
              Start the trial
            </button>
          )}
        </div>
      </div>

      <p className="muted small signup-foot">
        Already have an account? <a onClick={onSignIn}>Sign in</a>
      </p>
    </div>
  );
}
