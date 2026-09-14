import { useState } from "react";
import { SIGNUP_PACKS, REGIONS, JURISDICTIONS, Inert } from "./mock";

/**
 * Signing up. Unattended: no queue, no manual approval, no card.
 *
 * The order is the one in the onboarding specification, and each step exists
 * for a reason rather than for completeness:
 *
 *   1  email and password      one trial per email domain
 *   2  verify the address      nothing is created until the address answers
 *   3  organisation            the declared jurisdiction binds, not the IP
 *   4  region                  suggested, confirmed, and then immutable
 *   5  a starter pack          first run is a fork, never an empty editor
 *   6  a second administrator  the cheapest account recovery is the one
 *                              nobody ever has to invoke
 *
 * NOT CONNECTED. Nothing here creates anything. There is no signup endpoint
 * and no tenant-creation call; the pool does not offer self-registration
 * today. What this establishes is the shape, the order and the wording.
 *
 * Three things must exist on the server before it is real:
 *   - self-registration enabled on the user pool, with the email verified
 *   - a create-tenant call that mints the tenant and the custom:tenant_id
 *     claim, declares the jurisdiction and pins the region
 *   - the abuse controls: disposable-domain blocking, one trial per domain,
 *     and a rate limit per address at the edge
 */

const STEPS = [
  "Your details",
  "Verify",
  "Organisation",
  "Region",
  "Starter pack",
  "Second administrator",
];

export function SignUp({ onSignIn }: { onSignIn: () => void }) {
  const [step, setStep] = useState(0);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [org, setOrg] = useState("");
  const [jurisdiction, setJurisdiction] = useState(JURISDICTIONS[0]);
  const [region, setRegion] = useState(REGIONS[0].code);
  const [pack, setPack] = useState(0);
  const [second, setSecond] = useState("");

  const domain = email.includes("@") ? email.split("@")[1] : "";
  const back = () => setStep((n) => Math.max(0, n - 1));
  const on = () => setStep((n) => Math.min(STEPS.length - 1, n + 1));

  return (
    <div className="signup">
      <div className="signup-head">
        <h1>ARQEDIA</h1>
        <p className="muted">
          30 days, full use, no card. $5.00 of metered credit while you look.
        </p>
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
        <p className="revision-note mock-flag">
          <strong>Mock.</strong> Nothing here creates an account. There is no
          signup endpoint yet and the user pool does not offer
          self-registration. The order and the wording are the thing to judge.
        </p>

        {step === 0 && (
          <>
            <h3>Your details</h3>
            <p className="muted small">
              A business address. One trial per email domain, so a colleague
              signing up separately joins your seats rather than starting again.
            </p>
            <label className="row">
              <span>Email</span>
              <input placeholder="name@yourfirm.com" value={email}
                     onChange={(e) => setEmail(e.target.value)} autoFocus />
            </label>
            {domain && (
              <p className="muted small">
                The trial will belong to <strong>{domain}</strong>.
              </p>
            )}
            <label className="row">
              <span>Password</span>
              <input type="password" value={password}
                     onChange={(e) => setPassword(e.target.value)} />
            </label>
            <p className="muted small">
              Twelve characters or more. You set it now and are not asked to
              change it on first sign-in.
            </p>
          </>
        )}

        {step === 1 && (
          <>
            <h3>Verify your address</h3>
            <p className="muted small">
              A six-figure code has gone to {email || "your address"}. Nothing
              is created until it answers &mdash; which is also what stops a
              throwaway address taking a trial.
            </p>
            <label className="row">
              <span>Code</span>
              <input value={code} onChange={(e) => setCode(e.target.value)}
                     placeholder="000000" style={{ maxWidth: 160 }} />
            </label>
            <a className="small">Send it again</a>
          </>
        )}

        {step === 2 && (
          <>
            <h3>Your organisation</h3>
            <label className="row">
              <span>Name</span>
              <input placeholder="Vantage Mercantile" value={org}
                     onChange={(e) => setOrg(e.target.value)} autoFocus />
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

        {step === 3 && (
          <>
            <h3>Where your documents live</h3>
            <p className="muted small">
              Suggested from where you are. Confirm it: a region cannot be
              changed afterwards, because the documents and everything read
              from them stay where they were first written.
            </p>
            {REGIONS.map((r) => (
              <label className="bind" key={r.code}>
                <input type="radio" name="region" checked={region === r.code}
                       onChange={() => setRegion(r.code)} />
                {r.label}
                {r.code === REGIONS[0].code && (
                  <span className="in-use" style={{ marginLeft: 8 }}>suggested</span>
                )}
              </label>
            ))}
            <p className="revision-note" style={{ marginTop: 14 }}>
              <strong>This one cannot be undone.</strong> Moving a tenant to
              another region later means re-filing every document, and every
              memorandum already written would name a revision that no longer
              has the documents behind it.
            </p>
          </>
        )}

        {step === 4 && (
          <>
            <h3>Start on a pack</h3>
            <p className="muted small">
              A preconfiguration you can change afterwards: document types, the
              facts each carries, and a memorandum laid out to use them. You can
              fork more than one later. Nobody starts in an empty editor.
            </p>
            {SIGNUP_PACKS.map((p, i) => (
              <label className={`pack-row${i === pack ? " on" : ""}`} key={p.name}>
                <input type="radio" name="pack" checked={i === pack}
                       onChange={() => setPack(i)} />
                <span>
                  <strong>{p.name}</strong>
                  <span className="muted small">{p.note}</span>
                </span>
              </label>
            ))}
          </>
        )}

        {step === 5 && (
          <>
            <h3>A second administrator</h3>
            <p className="muted small">
              Optional, and worth the thirty seconds. An administrator can
              restore access if you lose yours. Without one, recovery is a
              manual request to us and takes days.
            </p>
            <label className="row">
              <span>Their email</span>
              <input placeholder="colleague@yourfirm.com" value={second}
                     onChange={(e) => setSecond(e.target.value)} />
            </label>
            <p className="muted small">
              They will be invited as an administrator. The seat is not taken
              until they accept.
            </p>

            <h4>What begins when you finish</h4>
            <table className="docs">
              <tbody>
                <tr><td>Trial</td><td className="ref">30 days, full use</td></tr>
                <tr><td>Metered credit</td><td className="ref">$5.00</td></tr>
                <tr><td>Card</td><td className="ref">none held</td></tr>
                <tr><td>Organisation</td><td className="ref">{org || "not set"}</td></tr>
                <tr><td>Jurisdiction</td><td className="ref">{jurisdiction}</td></tr>
                <tr><td>Region</td><td className="ref">{region}</td></tr>
                <tr><td>Starter pack</td><td className="ref">{SIGNUP_PACKS[pack].name}</td></tr>
              </tbody>
            </table>
          </>
        )}

        <div className="form-actions">
          {step > 0 && <a className="secondary" onClick={back}>Back</a>}
          {step < STEPS.length - 1 ? (
            <button onClick={on}>Continue</button>
          ) : (
            <Inert what="Creating the account">Start the trial</Inert>
          )}
          {step === 5 && second === "" && (
            <a className="small" onClick={() => undefined}>Skip for now</a>
          )}
        </div>
      </div>

      <p className="muted small signup-foot">
        Already have an account? <a onClick={onSignIn}>Sign in</a>
      </p>
    </div>
  );
}
