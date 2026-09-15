import { useEffect, useState } from "react";
import { useBackAction } from "./shell";
import { api, type Wallet, type LedgerEntry, type Seats as SeatState,
         type Invited } from "./api";
import { SUBSCRIPTION, PLANS, INVOICES, Inert, NotConnected } from "./mock";

/** Cents, as money. One place, so a balance and a ledger row never disagree
 *  about how many decimals a dollar has. */
function money(cents: number) {
  return "$" + (cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** A bucket's kind, said in words. The database calls it monthly_credit
 *  because a column should; a person should not have to. */
const KINDS: Record<string, string> = {
  trial: "Trial credit",
  monthly_credit: "Monthly credit",
  purchased: "Purchased",
  daily_test: "Daily test allowance",
};

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
 * BALANCE IS LIVE. It reads /wallet and /wallet/ledger, which are real: the
 * figures on that tab are this tenant's actual money.
 *
 * SEATS IS LIVE. It reads /seats and writes through the four routes beside
 * it. Inviting somebody genuinely reserves a seat.
 *
 * SUBSCRIPTION IS NOT. There is no subscription endpoint, so that tab reads
 * mock.tsx and every control on it is inert. It says so on the tab rather
 * than at the top, now that two of the three are real.
 */

type Tab = "subscription" | "balance" | "seats";

export function AccountView({ onBack }: { onBack: () => void }) {
  useBackAction(onBack);
  const [tab, setTab] = useState<Tab>("subscription");

  return (
    <div>
      <h2>Account management</h2>

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
      <NotConnected what="Subscription" />

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
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [entries, setEntries] = useState<LedgerEntry[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.wallet().then(setWallet).catch((e) => setError(String(e.message ?? e)));
    api.walletLedger(50).then((r) => setEntries(r.ledger)).catch(() => setEntries([]));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!wallet) return <p className="muted">Loading&hellip;</p>;

  const live = wallet.buckets.filter((b) => !b.expired);
  const gone = wallet.buckets.filter((b) => b.expired);
  const filing = wallet.prices.document_filed;
  const memo = wallet.prices.memo_generated;

  // Said in work rather than in money. "$2.00" is a number; "eight documents
  // or two memoranda" is the thing a person is actually deciding about.
  const inWork = [
    filing ? `${Math.floor(wallet.available_cents / filing)} documents` : null,
    memo ? `${Math.floor(wallet.available_cents / memo)} memoranda` : null,
  ].filter(Boolean).join(", or ");

  const low = memo ? wallet.available_cents < memo * 3 : false;

  return (
    <>
      <div className="stat-cards">
        <div className="stat">
          <span className="lbl">Available</span>
          <span className="big">{wallet.available}</span>
          <span className="muted small">{inWork || "\u00a0"}</span>
        </div>
        <div className="stat">
          <span className="lbl">Each document filed</span>
          <span className="big">{filing ? money(filing) : "\u2014"}</span>
          <span className="muted small">Charged when you accept the proposal</span>
        </div>
        <div className="stat">
          <span className="lbl">Each memorandum</span>
          <span className="big">{memo ? money(memo) : "\u2014"}</span>
          <span className="muted small">Whatever its length, however many documents</span>
        </div>
      </div>

      {low && (
        <p className="revision-note">
          <strong>Running low.</strong> {wallet.available} left
          {inWork ? `, which is ${inWork}` : ""}. Filing and generating stop at
          zero; reading, downloading and editing your configuration do not.
        </p>
      )}

      <div className="form-actions">
        <Inert what="Top-up">Top up</Inert>
        <span className="muted small">
          No payment provider is connected yet. When one is, a click will buy
          one increment &mdash; there is no standing mandate and nothing is ever
          charged unprompted.
        </span>
      </div>

      <h3>Balance, by bucket</h3>
      <p className="muted small">
        Spent soonest-expiry first, then oldest. Credit normally goes before
        cash, but a cash tranche maturing sooner is burned first rather than
        stranded.
      </p>

      {live.length === 0 && (
        <p className="muted">Nothing available. Every bucket has expired or been spent.</p>
      )}

      {live.length > 0 && (
        <table className="docs">
          <thead>
            <tr><th>Bucket</th><th>Granted</th><th>Spent</th><th>Remaining</th><th>Expires</th></tr>
          </thead>
          <tbody>
            {live.map((b) => (
              <tr key={b.bucket_id}>
                <td>
                  {KINDS[b.kind] ?? b.kind}
                  {b.reference && <div className="muted small">{b.reference}</div>}
                </td>
                <td className="ref">{money(b.granted_cents)}</td>
                <td className="ref">{money(b.spent_cents)}</td>
                <td className="ref">{money(b.remaining_cents)}</td>
                <td className="ref">{b.expires_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {gone.length > 0 && (
        <>
          <h4>Expired</h4>
          <p className="muted small">
            Shown rather than hidden. Money that ran out on a date is easier to
            understand than money that was simply never there.
          </p>
          <table className="docs">
            <tbody>
              {gone.map((b) => (
                <tr key={b.bucket_id}>
                  <td className="muted">{KINDS[b.kind] ?? b.kind}</td>
                  <td className="ref">{money(b.granted_cents)} granted</td>
                  <td className="ref">{money(b.spent_cents)} spent</td>
                  <td className="ref">expired {b.expires_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <h3>Ledger</h3>
      {entries === null && <p className="muted">Loading&hellip;</p>}
      {entries !== null && entries.length === 0 && (
        <p className="muted">Nothing charged yet.</p>
      )}
      {entries !== null && entries.length > 0 && (
        <table className="docs">
          <thead>
            <tr><th>When</th><th>Event</th><th>Reference</th><th>By</th><th>Amount</th></tr>
          </thead>
          <tbody>
            {entries.map((e) => (
              <tr key={e.entry_id}>
                <td className="ref">{e.created_at}</td>
                <td>
                  {e.event_type === "document_filed"
                    ? `${e.quantity} document${e.quantity === 1 ? "" : "s"} filed`
                    : e.event_type === "memo_generated"
                    ? "Memorandum generated"
                    : e.event_type}
                  <div className="muted small">
                    {e.quantity} &times; {money(e.unit_cents)}
                  </div>
                </td>
                <td className="muted small">{e.reference}</td>
                <td className="muted small">{e.created_by}</td>
                <td className="ref">{e.amount}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <p className="muted small">
        The ledger is append-only. There are no reversals, because unreadable
        material is blocked before filing rather than charged and refunded.
      </p>

      <p className="muted small">
        The price on each line is the price as it stood that day, not as it
        stands now.
      </p>
    </>
  );
}

// --- seats -----------------------------------------------------------------

function Seats() {
  const [state, setState] = useState<SeatState | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");
  const [invited, setInvited] = useState<Invited | null>(null);
  const [copied, setCopied] = useState(false);

  const load = () =>
    api.seats().then(setState).catch((e) => setError(message(e)));

  useEffect(() => { load(); }, []);

  function message(err: unknown) {
    const text = String((err as Error)?.message ?? err);
    try { return JSON.parse(text).error ?? text; } catch { return text; }
  }

  /** Every write reloads. The seat count, the free count and what the last
   *  administrator may do all move together, and a screen that updates one of
   *  them from a local guess will eventually disagree with the server. */
  async function act(what: string, run: () => Promise<unknown>) {
    setBusy(what);
    setError("");
    try {
      await run();
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  async function sendInvite() {
    setBusy("Inviting");
    setError("");
    setInvited(null);
    setCopied(false);
    try {
      const result = await api.invite(email, role);
      setInvited(result);
      setEmail("");
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  if (error && !state) return <p className="error">{error}</p>;
  if (!state) return <p className="muted">Loading&hellip;</p>;

  const onlyAdmin = state.admins <= 1;

  return (
    <>
      {error && <p className="error">{error}</p>}
      {busy && <p className="busy">{busy}&hellip;</p>}

      <p className="muted">
        {state.taken} of {state.bought} seats taken
        {state.reserved > 0 && `, ${state.reserved} reserved`}
        {state.free > 0 ? `, ${state.free} free` : ", none free"}
        {state.external > 0 && state.home_domain &&
          ` \u00b7 ${state.external} outside ${state.home_domain}`}
      </p>

      <table className="docs">
        <thead>
          <tr><th>Person</th><th>Rights</th><th>Since</th><th></th></tr>
        </thead>
        <tbody>
          {state.seats.map((s) => (
            <tr key={s.seat_id}>
              <td>
                {s.email}
                {s.you && <div className="in-use">you</div>}
                {s.external && !s.you && (
                  <div className="muted small">outside {state.home_domain}</div>
                )}
              </td>
              <td>
                <select value={s.role} disabled={!!busy}
                        onChange={(e) => act("Changing rights", () =>
                          api.setSeatRole(s.seat_id,
                            e.target.value as "admin" | "member"))}>
                  <option value="admin">Administrator</option>
                  <option value="member">Member</option>
                </select>
                {s.role === "admin" && onlyAdmin && (
                  <div className="muted small">the only one</div>
                )}
              </td>
              <td className="ref">{(s.accepted_at ?? "").slice(0, 10)}</td>
              <td>
                {!s.you && (
                  <a className="small" onClick={() =>
                    act("Removing", () => api.removeSeat(s.seat_id))}>
                    Remove
                  </a>
                )}
              </td>
            </tr>
          ))}

          {state.invitations.map((i) => (
            <tr key={"i" + i.invitation_id} className="aside">
              <td>
                {i.email}
                <div className="muted small">
                  invited by {i.invited_by} &middot; lapses{" "}
                  {(i.expires_at ?? "").slice(0, 10)}
                  {i.external && ` \u00b7 outside ${state.home_domain}`}
                </div>
              </td>
              <td className="muted">
                {i.role === "admin" ? "Administrator" : "Member"}
              </td>
              <td className="ref">reserved</td>
              <td>
                <a className="small" onClick={() =>
                  act("Revoking", () =>
                    api.revokeInvitation(i.invitation_id))}>
                  Revoke
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {state.invitations.length > 0 && (
        <p className="muted small">
          A reserved seat is as unavailable as a taken one. An invitation
          nobody accepts lapses after seven days and gives the seat back,
          so nothing has to be chased.
        </p>
      )}

      <h3>Invite someone</h3>
      <p className="muted small">
        You name the address and the rights. The seat is not taken until they
        accept and set a password; nothing about this workspace is visible to
        them before that.
      </p>
      <p className="muted small">
        An address outside {state.home_domain ?? "your domain"} is allowed
        &mdash; outside counsel, a consultant, somebody on the client side
        &mdash; and is marked in the list above so you can see at a glance who
        is not one of yours.
      </p>

      <div className="form">
        <label className="row">
          <span>Email address</span>
          <input placeholder="name@yourfirm.com" value={email}
                 onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="row">
          <span>Rights</span>
          <select value={role} disabled={!!busy}
                  onChange={(e) => setRole(e.target.value as "admin" | "member")}>
            <option value="member">Member</option>
            <option value="admin">Administrator</option>
          </select>
        </label>
        <div className="form-actions">
          <button onClick={sendInvite}
                  disabled={!!busy || !email.includes("@") || state.free === 0}>
            {state.free === 0 ? "No seat free" : "Invite"}
          </button>
          <span className="muted small">
            {state.free === 0
              ? "Remove a seat or revoke an invitation first."
              : email.includes("@")
                ? `${email} will be invited as ${role === "admin" ? "an administrator" : "a member"}.`
                : "\u00a0"}
          </span>
        </div>
      </div>

      {invited && (
        <div className="panel" style={{ marginTop: 18, padding: "16px 18px" }}>
          <h4 style={{ marginTop: 0 }}>Send {invited.email} this link</h4>
          <p className="muted small">
            No email has gone out &mdash; we cannot send one yet. This link is
            shown once and cannot be recovered; if it is lost, invite them
            again and a new one replaces it.
          </p>
          <pre className="passage" style={{ whiteSpace: "pre-wrap" }}>
            {invited.accept_url}
          </pre>
          <div className="form-actions">
            <button onClick={() => {
              navigator.clipboard?.writeText(invited.accept_url);
              setCopied(true);
            }}>
              {copied ? "Copied" : "Copy the link"}
            </button>
            <span className="muted small">
              It lapses {(invited.expires_at ?? "").slice(0, 10)}.
            </span>
          </div>
        </div>
      )}

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
        recovery, and the only one that never involves us. The last one cannot
        be removed or demoted.
      </p>

      <p className="muted small">
        A change of rights reaches somebody already signed in when their
        session next refreshes. Removing the seat takes effect at once, which
        is why removal rather than demotion is what to reach for in a hurry.
      </p>
    </>
  );
}
