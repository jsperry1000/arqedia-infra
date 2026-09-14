import { useState } from "react";
import { useBackAction } from "./shell";
import {
  SUBSCRIPTION, PLANS, SEATS, INVOICES, BUCKETS, LEDGER, WALLET,
  Inert, NotConnected,
} from "./mock";

/**
 * Account management. Everything to do with money and with who may spend it.
 *
 * Three parts, because they answer three different questions and a person
 * arrives knowing which one they have:
 *
 *   Subscription - what am I on, and what would I be on instead
 *   Balance      - what have I got left, and what went where
 *   Seats        - who may use this, and what may they do
 *
 * The wallet is not a separate destination. A balance is an account matter,
 * and putting it on its own rail entry asked people to know the difference
 * between a plan and a balance before they had one.
 *
 * NOT CONNECTED. There are no subscription, seat or wallet endpoints. Every
 * figure is from mock.tsx; the plan table in it is the settled one.
 */

type Tab = "subscription" | "balance" | "seats";

export function AccountView({ onBack }: { onBack: () => void }) {
  useBackAction(onBack);
  const [tab, setTab] = useState<Tab>("subscription");

  return (
    <div>
      <h2>Account management</h2>
      <NotConnected what="Account management" />

      <nav className="tabs">
        <button className={tab === "subscription" ? "on" : undefined}
                onClick={() => setTab("subscription")}>Subscription</button>
        <button className={tab === "balance" ? "on" : undefined}
                onClick={() => setTab("balance")}>Balance</button>
        <button className={tab === "seats" ? "on" : undefined}
                onClick={() => setTab("seats")}>Seats and permissions</button>
      </nav>

      {tab === "subscription" && <Subscription />}
      {tab === "balance" && <Balance />}
      {tab === "seats" && <Seats />}
    </div>
  );
}

// --- subscription ----------------------------------------------------------

function Subscription() {
  const [chosen, setChosen] = useState(
    PLANS.findIndex((p) => p.name === SUBSCRIPTION.plan));

  const onTrial = SUBSCRIPTION.status === "Trial";

  return (
    <>
      {onTrial && (
        <p className="revision-note">
          <strong>Trial &mdash; {SUBSCRIPTION.trialDaysLeft} days left.</strong>{" "}
          Full use until {SUBSCRIPTION.trialEnds}, with $5.00 of metered credit
          and no card held. Memoranda generated in the trial stay downloadable
          afterwards. Starting a subscription does not end the trial early
          &mdash; it takes over when the trial runs out.
        </p>
      )}

      <div className="stat-cards">
        <div className="stat">
          <span className="lbl">Status</span>
          <span className="big serif">{SUBSCRIPTION.status}</span>
          <span className="muted small">
            {onTrial ? `Ends ${SUBSCRIPTION.trialEnds}` : `Renews ${SUBSCRIPTION.renews}`}
          </span>
        </div>
        <div className="stat">
          <span className="lbl">Plan</span>
          <span className="big serif">{SUBSCRIPTION.plan}</span>
          <span className="muted small">{SUBSCRIPTION.price}</span>
        </div>
        <div className="stat">
          <span className="lbl">Payment method</span>
          <span className="big serif">{SUBSCRIPTION.card ? "On file" : "None"}</span>
          <span className="muted small">
            {SUBSCRIPTION.card ?? "No card held. Nothing can be charged."}
          </span>
        </div>
      </div>

      <h3>Choose a plan</h3>
      <p className="muted small">
        Seats are a fixed attribute of the plan. Adding a seat is a plan change
        rather than a proration.
      </p>

      <table className="docs">
        <thead>
          <tr>
            <th></th><th>Plan</th><th>Seats</th><th>Monthly credit</th>
            <th>Shares</th><th>Field sets</th><th>Sections</th><th>Top-up</th>
          </tr>
        </thead>
        <tbody>
          {PLANS.map((p, i) => (
            <tr key={p.name} onClick={() => setChosen(i)}
                className={i === chosen ? "chosen" : undefined}>
              <td style={{ width: 34 }}>
                <input type="radio" name="plan" checked={i === chosen}
                       onChange={() => setChosen(i)} style={{ width: "auto" }} />
              </td>
              <td>
                <strong>{p.name}</strong>
                <div className="muted small">{p.price}</div>
                {p.current && <div className="in-use">selected at signup</div>}
              </td>
              <td className="ref">{p.seats || "as contracted"}</td>
              <td className="ref">{p.credit}</td>
              <td className="ref">{p.shares}</td>
              <td className="ref">{p.fieldSets}</td>
              <td className="ref">{p.sections}</td>
              <td className="ref">{p.topUp}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="form-actions">
        <Inert what={onTrial ? "Starting a subscription" : "Changing plan"}>
          {onTrial ? `Start on ${PLANS[chosen].name}` : `Change to ${PLANS[chosen].name}`}
        </Inert>
        <span className="muted small">
          A card is taken at this point, and the monthly charge begins when the
          trial ends. Metered use is never charged to the card without a further
          click.
        </span>
      </div>

      <h3>Invoices</h3>
      <table className="docs">
        <thead>
          <tr><th>Date</th><th>What</th><th>Amount</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {INVOICES.map((inv, i) => (
            <tr key={i}>
              <td className="ref">{inv.date}</td>
              <td>{inv.what}</td>
              <td className="ref">{inv.amount}</td>
              <td className="ref">{inv.status}</td>
              <td><a className="small">Download</a></td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Closing the account</h3>
      <p className="muted small">
        Deleting the account is permitted in every state. It scrubs the
        tenant&rsquo;s rows, storage and derived artifacts, and revokes every
        outstanding share grant. A single document cannot be deleted &mdash; the
        ledger has to stay reconcilable against what was filed.
      </p>
      <div className="form-actions">
        <Inert what="Closing the account">Close this account</Inert>
      </div>
    </>
  );
}

// --- balance ---------------------------------------------------------------

function Balance() {
  return (
    <>
      <div className="stat-cards">
        <div className="stat">
          <span className="lbl">Available</span>
          <span className="big">{WALLET.available}</span>
          <span className="muted small">8 documents, or 2 memoranda</span>
        </div>
        <div className="stat">
          <span className="lbl">Each document filed</span>
          <span className="big">$0.25</span>
          <span className="muted small">Charged when you accept the proposal</span>
        </div>
        <div className="stat">
          <span className="lbl">Each memorandum</span>
          <span className="big">$1.00</span>
          <span className="muted small">Whatever its length, however many documents</span>
        </div>
      </div>

      <p className="revision-note">
        <strong>Running low.</strong> {WALLET.available} left, which is two
        memoranda. Filing and generating stop at zero; reading, downloading and
        editing your configuration do not.
      </p>

      <div className="form-actions">
        <Inert what="Top-up">{`Top up ${WALLET.topUp}`}</Inert>
        <span className="muted small">
          One click buys one increment. There is no standing mandate and nothing
          is ever charged unprompted.
        </span>
      </div>

      <h3>Balance, by bucket</h3>
      <p className="muted small">
        Spent soonest-expiry first, then oldest. Credit normally goes before
        cash, but a cash tranche maturing sooner is burned first rather than
        stranded.
      </p>
      <table className="docs">
        <thead>
          <tr><th>Bucket</th><th>Granted</th><th>Spent</th><th>Remaining</th><th>Expires</th></tr>
        </thead>
        <tbody>
          {BUCKETS.map((b) => (
            <tr key={b.label}>
              <td>{b.label}</td>
              <td className="ref">{b.granted}</td>
              <td className="ref">{b.spent}</td>
              <td className="ref">{b.left}</td>
              <td className="ref">{b.expires}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        Test runs debit their own bucket at the normal $0.25 &mdash; four a day.
        They never spill into your real balance, and your real balance can never
        be spent on testing.
      </p>

      <h3>Ledger</h3>
      <table className="docs">
        <thead>
          <tr><th>When</th><th>Event</th><th>Reference</th><th>Amount</th></tr>
        </thead>
        <tbody>
          {LEDGER.map((row, i) => (
            <tr key={i}>
              <td className="ref">{row.at}</td>
              <td>{row.event}</td>
              <td className="muted small">{row.ref}</td>
              <td className="ref">{row.amount}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">
        The ledger is append-only. There are no reversals, because unreadable
        material is blocked before filing rather than charged and refunded.
      </p>
    </>
  );
}

// --- seats -----------------------------------------------------------------

function Seats() {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("Member");

  const free = SUBSCRIPTION.seatsIncluded - SUBSCRIPTION.seatsUsed;

  return (
    <>
      <p className="muted">
        {SUBSCRIPTION.seatsUsed} of {SUBSCRIPTION.seatsIncluded} seats in use
        {free > 0 ? `, ${free} free` : ", none free"} &middot;{" "}
        {SUBSCRIPTION.plan} plan
      </p>

      <table className="docs">
        <thead>
          <tr><th>Person</th><th>Rights</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          {SEATS.map((s) => (
            <tr key={s.email}>
              <td>
                {s.email}
                {s.you && <div className="in-use">you</div>}
              </td>
              <td>
                <select defaultValue={s.role} disabled={s.you}>
                  <option>Administrator</option>
                  <option>Member</option>
                </select>
              </td>
              <td className="ref">
                {s.status}
                {s.status === "invited" && (
                  <div className="muted small">invitation sent, not yet accepted</div>
                )}
              </td>
              <td>
                {!s.you && <Inert what="Removing a seat">Remove</Inert>}
              </td>
            </tr>
          ))}
          {free > 0 && (
            <tr>
              <td className="muted">{free} seat{free > 1 ? "s" : ""} unused</td>
              <td className="muted">&mdash;</td>
              <td className="muted">&mdash;</td>
              <td></td>
            </tr>
          )}
        </tbody>
      </table>

      <h3>Invite someone</h3>
      <p className="muted small">
        An administrator names the address and the rights. We send an
        invitation; the seat is not taken until it is accepted and a password
        set. Nothing about the tenant is visible to the recipient before then.
      </p>

      <div className="form">
        <label className="row">
          <span>Email address</span>
          <input placeholder="name@yourfirm.com" value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="row">
          <span>Rights</span>
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            <option>Member</option>
            <option>Administrator</option>
          </select>
        </label>
        <div className="form-actions">
          <Inert what="Sending an invitation">
            {free > 0 ? "Send the invitation" : "No seat free"}
          </Inert>
          <span className="muted small">
            {email ? `${email} will be invited as ${role.toLowerCase()}.` : "\u00a0"}
          </span>
        </div>
      </div>

      <h3>What the two rights mean</h3>
      <table className="docs">
        <thead>
          <tr><th></th><th>Administrator</th><th>Member</th></tr>
        </thead>
        <tbody>
          <tr><td>Upload, file and generate</td><td className="ref">yes</td><td className="ref">yes</td></tr>
          <tr><td>Edit and publish the configuration</td><td className="ref">yes</td><td className="ref">yes</td></tr>
          <tr><td>Share a memorandum, and revoke</td><td className="ref">yes</td><td className="ref">yes</td></tr>
          <tr><td>Change the plan or the card</td><td className="ref">yes</td><td className="ref">no</td></tr>
          <tr><td>Invite, remove or re-rank a seat</td><td className="ref">yes</td><td className="ref">no</td></tr>
          <tr><td>Set the brand</td><td className="ref">yes</td><td className="ref">no</td></tr>
          <tr><td>Close the account</td><td className="ref">yes</td><td className="ref">no</td></tr>
        </tbody>
      </table>

      <p className="muted small">
        Keep a second administrator. It is the cheapest form of account
        recovery, and the only one that never involves us.
      </p>
    </>
  );
}
