import { useEffect, useState } from "react";
import { updatePassword } from "aws-amplify/auth";
import { useNavigate, useSearchParams } from "react-router-dom";
import { TableScroll, useBackAction, Working } from "./shell";
import { ENTERPRISE_COLUMN, EnterpriseLink, UpgradePrompt,
         useRole } from "./upgrade";
import { api, chargeKey, type Wallet, type LedgerEntry,
         type Seats as SeatState, type Invited,
         type SubscriptionView, type Plan, type Invoice, type InvoicePage,
         type WorkspaceList, type HeldWorkspace } from "./api";
import { openCheckout } from "./paddle";
import { useWorkspace, workspacesChanged } from "./workspace";
import { Inert } from "./mock";

/** Cents, as money. One place, so a balance and a ledger row never disagree
 *  about how many decimals a dollar has. */
function money(cents: number) {
  return "$" + (cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/** A MySQL datetime, as a Date. The API answers "2026-10-16 14:24:44" in UTC,
 *  which is not ISO 8601 and which browsers have been free to refuse. Made
 *  explicit rather than left to chance. */
function when(value: string | null): Date | null {
  if (!value) return null;
  const parsed = new Date(value.replace(" ", "T") + "Z");
  return isNaN(parsed.getTime()) ? null : parsed;
}

function on(value: string | null) {
  const date = when(value);
  return date ? date.toLocaleDateString(undefined,
    { day: "numeric", month: "long", year: "numeric" }) : "—";
}

/** Whole days from now, never negative. Something that has ended is over,
 *  not minus three days from ending. */
function daysUntil(value: string | null) {
  const date = when(value);
  if (!date) return null;
  return Math.max(0, Math.ceil((date.getTime() - Date.now()) / 86400000));
}

/** A refusal the server wrote to be read by a person, unwrapped from the
 *  {"error": "..."} it travels in. */
function message(err: unknown) {
  const text = String((err as Error)?.message ?? err);
  try { return JSON.parse(text).error ?? text; } catch { return text; }
}

/** A bucket's kind, said in words. The database calls it monthly_credit
 *  because a column should; a person should not have to. */
const KINDS: Record<string, string> = {
  trial: "Trial credit",
  monthly_credit: "Monthly credit",
  purchased: "Purchased",
  daily_test: "Daily test allowance",
};

/* TOPUP_CENTS IS GONE (18.5 stage 3). It read:
 *
 *     const TOPUP_CENTS = 500;
 *
 * and its own comment said the server computes the amount and returns it -
 * which was true of the answer and not of the question. The button, the
 * confirmation and the line about how many more memoranda it buys all stated
 * a figure this file held, and billing.top_up() charged
 * TOPUP_INCREMENT_CENTS * increments. Two numbers that happened to agree.
 *
 * /billing/subscription now reports the server's own constant as
 * topup_increment_cents, and every figure on the Balance tab is computed from
 * that. See the note beside it in billing.py for why it rides on that
 * endpoint rather than on /wallet. */

/** One row of the plan table: the label, what it reads for a plan, and what
 *  it reads for Enterprise.
 *
 *  THE ROWS THE PRICING PAGE SHOWS, in its order. "How it starts" is not one
 *  of them here: on the site it is how somebody signs up, and on this screen
 *  that is the radio in the column header and the button beneath the table.
 *
 *  A DASH FOR NULL, and never a zero. A limit the plan has not been given is
 *  not a limit of none - see the note on Plan in api.ts. share_allowance is
 *  the exception and has always been: null there means unlimited, which is
 *  what migration 018 says. */
type PlanRow = {
  label: string;
  of: (plan: Plan) => string | number;
  enterprise: string;
};

const limit = (value: number | null) => (value === null ? "—" : value);

const ROWS: PlanRow[] = [
  { label: "Seats",
    of: (p) => p.seat_count,
    enterprise: ENTERPRISE_COLUMN.seats },
  // PACK-02: in the app only until the pricing page is redone before launch.
  // A dash for null, as the limits below: a plan with no number set has no
  // limit, which is not the same as none.
  { label: "Workspaces",
    of: (p) => limit(p.workspace_count),
    enterprise: ENTERPRISE_COLUMN.workspaces },
  { label: "Monthly credit toward metered use",
    of: (p) => money(p.monthly_credit_cents),
    enterprise: ENTERPRISE_COLUMN.monthly_credit },
  { label: "Shared memoranda per month",
    of: (p) => (p.share_allowance === null ? "unlimited" : p.share_allowance),
    enterprise: ENTERPRISE_COLUMN.shares },
  // "Field sets per document type" and "Daily classification allowance" sat
  // here until 6 October 2026. Neither is sold any more (22.5) - see the two
  // dropped notes in config/plans.json. The columns stay in the plan table
  // and the API still returns them; nothing reads them to decide anything.
  { label: "Sections per template",
    of: (p) => limit(p.sections_per_template),
    enterprise: ENTERPRISE_COLUMN.sections },
];

/**
 * Account management. Everything to do with money and with who may spend it.
 *
 * Four parts, because they answer four different questions and a person
 * arrives knowing which one they have:
 *
 *   Subscription - what am I on, and what would I be on instead
 *   Balance      - what have I got left, and what went where
 *   Seats        - who may use this, and what may they do
 *   Password     - how I get in
 *
 * Password is the odd one: it touches no endpoint of ours at all, and is here
 * because this is where a person looks for it rather than because it belongs
 * with money (10.3).
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
 * SUBSCRIPTION IS LIVE. It reads /billing/subscription and writes through
 * /billing/checkout, /billing/plan, /billing/payment-method and
 * /billing/resume; subscribing and changing the payment method open
 * Paddle's overlay. The invoices read /billing/invoices, from Paddle (item 8
 * superseded, 24 October 2026).
 *
 * NOTHING ON THIS SCREEN GRANTS MONEY. Every payment is granted by Paddle's
 * webhooks through our own processor (item 6). What the screen does after a
 * checkout is ASK AGAIN, and say plainly that the answer may take a moment.
 */

type Tab = "subscription" | "balance" | "seats" | "workspaces" | "password";

const TABS: Tab[] = ["subscription", "balance", "seats", "workspaces",
                     "password"];

/**
 * THE TAB IS IN THE ADDRESS (11.1). It was local state, so every arrival
 * opened on Subscription and no screen could send anybody anywhere else -
 * which is why the one control in the product that says "Top up" landed a
 * person on the plan table. /account?tab=balance now lands on the balance,
 * and a bare /account still opens where it always did.
 *
 * Replace rather than push: choosing a tab is not a place to come back to
 * with the browser's Back, which on this screen means leaving it.
 */
export function AccountView({ onBack }: { onBack: () => void }) {
  useBackAction(onBack);
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab") as Tab | null;
  // Workspaces is an administrator's (PACK-02 D): every route behind it
  // refuses a member, so a member is not shown it.
  const role = useRole();
  const admin = role === "admin";
  const tab: Tab = asked && TABS.includes(asked)
    && (asked !== "workspaces" || admin) ? asked : "subscription";
  const setTab = (to: Tab) => setParams({ tab: to }, { replace: true });

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
        {admin && (
          <button className={tab === "workspaces" ? "on" : undefined}
                  onClick={() => setTab("workspaces")}>Workspaces</button>
        )}
        <button className={tab === "password" ? "on" : undefined}
                onClick={() => setTab("password")}>Password</button>
      </nav>

      {tab === "subscription" && <Subscription />}
      {tab === "balance" && <Balance />}
      {tab === "seats" && <Seats />}
      {tab === "workspaces" && <Workspaces />}
      {tab === "password" && <Password />}
    </div>
  );
}

// --- subscription ----------------------------------------------------------

/**
 * What am I on, and what would I be on instead.
 *
 * FOUR STATES, and they are not a spectrum: a trial has no subscription at
 * all, active is paying, past_due has failed a payment, cancelled has run
 * out. Each gets the sentence that is true of it rather than one paragraph
 * hedged to cover all four.
 *
 * standing is what may be SPENT, and it is the server's word rather than a
 * guess made here from the status: past_due, paused and an expired
 * cancellation all come back purchased_only, where filing and generating
 * spend unexpired top-up cash and nothing else (items 12 and 13, as amended).
 */
function Subscription() {
  // EVERY ACTION HERE IS AN ADMINISTRATOR'S, and the server refuses a member
  // each one. A member reads the tab and is told so once, in place of the
  // buttons, as on Seats. Null until the token is read: nothing is offered
  // before the role is known.
  const role = useRole();
  const admin = role === "admin";
  const [view, setView] = useState<SubscriptionView | null>(null);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [waiting, setWaiting] = useState("");
  const [said, setSaid] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  // Bumped when a wait ends, so the invoice list reads Paddle again: it read
  // once on arrival and went on showing a renewal as failed after it was
  // paid (walk of 24 October 2026).
  const [settled, setSettled] = useState(0);

  const load = () => api.subscription().then((fresh) => {
    setView(fresh);
    setChosen((current) => current ?? fresh.plan);
    return fresh;
  });

  useEffect(() => {
    load().catch((e) => setError(message(e)));
    // The trial credit, from the bucket that holds it rather than from a
    // figure typed here. $5.00 is the grant; what is left is the question.
    api.wallet().then(setWallet).catch(() => setWallet(null));
  }, []);

  /**
   * Ask the server again until the webhook has landed, or give up saying so.
   *
   * The overlay answering "completed" means Paddle took the payment, NOT that
   * our side knows: the webhook is a separate journey and arrives in its own
   * time. Fifteen tries, two seconds apart - half a minute, long enough for
   * the ordinary case and short enough that nobody is left watching a
   * spinner. Giving up is not a failure and does not say it is.
   *
   * The two sentences are a resume's own where it passes them: a resume asks
   * Paddle to charge, and that charge may yet be refused.
   */
  async function settle(done: (fresh: SubscriptionView) => boolean,
                        meanwhile = "Paddle has taken the payment. Recording "
                          + "it here…",
                        late = "The payment went through. It has not reached "
                          + "this screen yet, which can take a minute - "
                          + "reload and it will be here. Nothing is lost, and "
                          + "nothing will be charged twice.") {
    setWaiting(meanwhile);
    try {
      for (let i = 0; i < 15; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
          if (done(await load())) { setWaiting(""); return; }
        } catch { /* keep asking: one refused read is not an answer */ }
      }
      setWaiting(late);
    } finally {
      setSettled((n) => n + 1);
    }
  }

  async function subscribe(planKey: string) {
    setError("");
    setBusy("Opening checkout");
    try {
      const { transaction_id } = await api.checkout(planKey);
      setBusy("");
      const outcome = await openCheckout(transaction_id);
      // Closed without paying leaves the tenant exactly as it was: nothing
      // was created here, and the transaction Paddle holds is simply never
      // paid. We re-read anyway, because it may have completed elsewhere.
      if (outcome === "completed") {
        await settle((fresh) => fresh.paddle_status === "active");
      } else {
        await load();
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  async function change(planKey: string) {
    setError("");
    setBusy("Changing plan");
    try {
      await api.changePlan(planKey);
      await settle((fresh) => fresh.plan === planKey);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  /**
   * Change the payment method, in Paddle's overlay. Paddle holds the card and
   * nothing of it reaches us (amendment of 18 September).
   *
   * ACTIVE: a zero-value transaction. Nothing is charged, nothing is granted,
   * and nothing on this screen changes, so there is nothing to wait for.
   *
   * PAST DUE: the overdue renewal itself, paid on the new method in the
   * overlay. The subscription returns to active when Paddle's webhook lands,
   * so the screen waits for that as it does after a checkout.
   */
  async function changeMethod() {
    setError("");
    setSaid("");
    setBusy("Opening Paddle");
    try {
      const { transaction_id, status } = await api.paymentMethod();
      setBusy("");
      const outcome = await openCheckout(transaction_id);
      if (outcome !== "completed") return;
      if (status === "past_due") {
        await settle((fresh) => fresh.paddle_status === "active");
      } else {
        setSaid("Payment method changed. Paddle uses it from the next "
                + "renewal; nothing was charged.");
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  /**
   * Resume a paused subscription. Paddle has no payment-method transaction
   * for one that is paused, so this is the way back: Paddle charges the card
   * it holds for a new month at once. If that is refused the subscription
   * comes back past due, and Change Payment Method is offered there.
   *
   * THE CHARGE'S OUTCOME COMES WITH THE ANSWER. On resume Paddle reports
   * the subscription active and only then tries the card, and a refusal's
   * past_due has reached us eighteen seconds behind it - so the status alone
   * cannot say whether the card was charged (walks of 24 October 2026). The
   * server reads the charge from Paddle before answering, and the screen
   * says what it found, then waits for the status that matches it.
   */
  async function resumeSubscription() {
    setError("");
    setSaid("");
    setBusy("Resuming");
    try {
      const { outcome } = await api.resume();
      setBusy("");
      if (outcome === "paid") {
        await settle((fresh) => fresh.paddle_status === "active");
      } else if (outcome === "failed") {
        await settle((fresh) => fresh.paddle_status === "past_due",
          "The card Paddle holds was refused. Recording it here…",
          "The card Paddle holds was refused. That has not reached this "
            + "screen yet, which can take a minute - reload and change the "
            + "payment method there. Nothing was charged.");
      } else {
        await load();
        setWaiting("Resumed. Paddle has not yet said whether the card it "
          + "holds was charged - reload in a minute to see. Nothing will be "
          + "charged twice.");
        setSettled((n) => n + 1);
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  if (error && !view) return <p className="error">{error}</p>;
  if (!view) return <p className="muted">Loading&hellip;</p>;

  const status = view.paddle_status;
  // FROM standing, NOT FROM THE ABSENCE OF A PADDLE STATUS. A tenant whose
  // trial ran out has no paddle_status either, so `!status` called it a
  // live trial for ever and the banner went on counting down to a date in
  // the past (18.5 follow-up).
  const onTrial = view.standing === "trial";
  const trialOver = view.standing === "trial_ended";
  const active = status === "active";
  const pastDue = status === "past_due" || status === "paused";
  const canceled = status === "canceled";
  // The radios choose for Change plan or Subscribe, so they show only where
  // one of those is offered: to an administrator, and not while paused or
  // past due, where the button beneath is Resume or Change Payment Method.
  const choosing = admin && !pastDue;
  const plan = view.plans.find((p) => p.plan_key === view.plan) ?? null;
  const target = view.plans.find((p) => p.plan_key === chosen) ?? null;
  const trialLeft = daysUntil(view.trial_ends_at);
  const trialBucket = wallet?.buckets.find((b) => b.kind === "trial");

  return (
    <>
      {error && <p className="error">{error}</p>}
      {busy && <Working what={busy} />}
      {waiting && <p className="revision-note">{waiting}</p>}
      {said && <p className="revision-note">{said}</p>}

      {onTrial && (
        <p className="revision-note">
          <strong>
            {trialLeft === null ? "Trial — no end date recorded."
              : trialLeft === 0 ? "Trial — ends today."
              : `Trial — ${trialLeft} day${trialLeft === 1 ? "" : "s"} left.`}
          </strong>{" "}
          Full use until {on(view.trial_ends_at)}, with no card held.
          {trialBucket
            ? ` ${money(trialBucket.remaining_cents)} of the `
              + `${money(trialBucket.granted_cents)} metered credit is left.`
            : " The metered credit is on the Balance tab."}{" "}
          Memoranda generated in the trial stay downloadable afterwards.
          Subscribing does not end the trial early &mdash; the credit keeps its
          own expiry and is spent first.
        </p>
      )}

      {/* SAID, RATHER THAN LEFT TO BE DISCOVERED. Before this the screen
          went on calling it a trial, and the first a person knew was File
          answering "Not enough balance" (18.5 follow-up). Nothing here
          changes what may be spent: the trial credit carries the same date
          as its own expiry and the wallet already refuses it. */}
      {trialOver && (
        <p className="revision-note">
          <strong>Trial ended {on(view.trial_ends_at)}.</strong>{" "}
          The metered credit that came with it has expired, so filing and
          generating stop until you subscribe. Everything already filed or
          generated stays readable and downloadable, and your configuration is
          untouched. Subscribing starts the plan from that moment.
        </p>
      )}

      {pastDue && (
        <p className="revision-note">
          <strong>
            {status === "paused" ? "Subscription paused." : "Payment failed."}
          </strong>{" "}
          Filing and generating can still spend unexpired top-up credit until
          it runs out or expires; everything else that costs money waits.
          Reading, downloading and editing your configuration are unaffected.
          {status === "paused"
            ? " Resuming charges the card Paddle holds for a new month. If it "
              + "is refused, the payment method can be changed then."
            : " Paddle retries on its own schedule, and changing the payment "
              + "method clears it at once."}
        </p>
      )}

      {canceled && (
        <p className="revision-note">
          <strong>Subscription cancelled.</strong> Nothing further will be
          charged. Unexpired top-up credit can still be spent on filing and
          generating until it runs out or reaches its own expiry &mdash; it was
          paid for and it is not forfeited. Everything already filed or
          generated stays readable and downloadable. Subscribing again starts a
          new subscription rather than resuming this one.
        </p>
      )}

      <div className="stat-cards">
        <div className="stat">
          <span className="lbl">Status</span>
          <span className="big serif">
            {onTrial ? "Trial"
              : trialOver ? "Trial ended"
              : active ? "Active"
              : status === "past_due" ? "Payment failed"
              : status === "paused" ? "Paused"
              : "Cancelled"}
          </span>
          <span className="muted small">
            {onTrial ? `Ends ${on(view.trial_ends_at)}`
              : trialOver ? `Ended ${on(view.trial_ends_at)}`
              : canceled ? `Paid to ${on(view.current_period_ends_at)}`
              // Paused renews nothing: the row keeps the old period's end,
              // and resuming starts a new one from that day.
              : status === "paused" ? "Resuming starts a new month"
              : `Renews ${on(view.current_period_ends_at)}`}
          </span>
        </div>
        <div className="stat">
          <span className="lbl">Plan</span>
          <span className="big serif">{plan ? plan.name : "None"}</span>
          <span className="muted small">
            {plan ? `${money(plan.monthly_price_cents)} / month`
                  : "No plan while on trial"}
          </span>
        </div>
        <div className="stat">
          <span className="lbl">What you may spend</span>
          <span className="big serif">
            {view.standing === "active" ? "Everything"
              : view.standing === "trial" ? "Trial credit"
              : trialOver ? "Nothing"
              : "Top-up only"}
          </span>
          <span className="muted small">
            {view.standing === "purchased_only"
              ? "Cash you bought, until it expires"
              : trialOver
                ? "Nothing left to spend until you subscribe"
                : "Filing and generating, against the balance"}
          </span>
        </div>
      </div>

      <h3>{!choosing ? "Plans" : active ? "Change plan" : "Choose a plan"}</h3>
      <p className="muted small">
        Seats are a fixed attribute of the plan. Adding a seat is a plan change
        rather than a proration, and a downgrade is refused while more seats are
        taken or reserved than the smaller plan holds.
      </p>
      {/* THE PLAN TABLE, THE WAY THE PRICING PAGE DRAWS IT (18.5 stage 3).
          It was one row per plan and six columns of attribute; it is now one
          column per plan and one row per attribute, which is the shape
          somebody comparing two plans actually reads - and the shape the page
          that sold them to this tenant used.

          THE THREE LIMITS COME FROM THE API, which reads them from the plan
          table, which migration 033 fills from config/plans.json. They were
          sold on the pricing page and held nowhere, so this screen could not
          show them at all.

          ENTERPRISE IS THE THIRD COLUMN and carries no radio: it is not a
          plan row, it cannot be bought here, and a control that answers 403
          is worse than no control. Its words are ENTERPRISE_COLUMN - the one
          copy in this codebase, declared there with the reason. */}
      <TableScroll label="Plans">
      <table className="docs plans-table">
        <thead>
          <tr>
            <th></th>
            {view.plans.map((p: Plan) => (
              <th key={p.plan_key}
                  onClick={choosing ? () => setChosen(p.plan_key) : undefined}
                  className={choosing && p.plan_key === chosen
                    ? "chosen" : undefined}>
                {/* The radio chooses for the button beneath, which a member
                    is not offered, nor anybody while paused or past due. */}
                {choosing && (
                  <input type="radio" name="plan" aria-label={p.name}
                         checked={p.plan_key === chosen}
                         onChange={() => setChosen(p.plan_key)} />
                )}
                <span className="plan-name">{p.name}</span>
                <span className="plan-price">
                  {money(p.monthly_price_cents)} / month
                </span>
                {p.plan_key === view.plan && (
                  <span className="in-use">current</span>
                )}
              </th>
            ))}
            {/* No radio, and the link the paragraph beneath the table used to
                carry. The column says what the paragraph said. */}
            <th className="quoted">
              <span className="plan-name">{ENTERPRISE_COLUMN.name}</span>
              <span className="plan-price">{ENTERPRISE_COLUMN.price}</span>
              <EnterpriseLink className="small" />
            </th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              {view.plans.map((p: Plan) => (
                <td key={p.plan_key} className="ref">{row.of(p)}</td>
              ))}
              <td className="ref quoted">{row.enterprise}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </TableScroll>

      {role === "member" && (
        <p className="muted small">
          Only an administrator changes the plan, the payment method or the
          balance.
        </p>
      )}

      {admin && (
      <div className="form-actions">
        {active ? (
          <>
            <button className="spend"
                    disabled={!!busy || !chosen || chosen === view.plan}
                    onClick={() => chosen && change(chosen)}>
              {target && chosen !== view.plan
                ? `Change to ${target.name}` : "Change plan"}
            </button>
            {/* Navy: changing the method on an active subscription charges
                nothing. */}
            <button disabled={!!busy} onClick={changeMethod}>
              Change Payment Method
            </button>
            <span className="muted small">
              An upgrade is billed now, at the difference, and the extra monthly
              credit arrives with it. A downgrade grants nothing back and takes
              nothing away &mdash; the ledger is append-only.
            </span>
          </>
        ) : status === "paused" ? (
          <>
            <button className="spend" disabled={!!busy}
                    onClick={resumeSubscription}>
              Resume subscription
            </button>
            <span className="muted small">
              Charges the card Paddle holds for a new month, now, and the
              month&rsquo;s credit arrives with it. Paddle cannot change the
              payment method of a paused subscription; if the card is
              refused, the subscription shows as payment failed and the
              method can be changed there.
            </span>
          </>
        ) : pastDue ? (
          <>
            {/* Gold: saving the new method charges the overdue renewal. */}
            <button className="spend" disabled={!!busy} onClick={changeMethod}>
              Change Payment Method
            </button>
            {/* Paddle's window shows no amount: it takes the method and
                charges what is outstanding once it is saved (walk of 24
                October 2026). */}
            <span className="muted small">
              Once the new method is saved, Paddle charges the overdue renewal
              to it and the subscription is active again; Paddle keeps the
              method for every renewal after. Subscribing again is not offered
              here &mdash; there is already a subscription, and the payment
              method is what needs fixing.
            </span>
          </>
        ) : (
          <>
            <button className="spend" disabled={!!busy || !chosen}
                    onClick={() => chosen && subscribe(chosen)}>
              {target ? `Subscribe on ${target.name}` : "Subscribe"}
            </button>
            <span className="muted small">
              A card is taken at this point and the first month is charged now.
              Metered use is never charged to the card without a further click.
            </span>
          </>
        )}
      </div>
      )}

      <Invoices key={settled} subscribed={!!status} />

      <h3>Closing the account</h3>
      <p className="muted small">
        Deleting the account is permitted in every state. It scrubs the
        tenant&rsquo;s rows, storage and derived artifacts, and revokes every
        outstanding share grant. A single document cannot be deleted &mdash; the
        ledger has to stay reconcilable against what was filed.
      </p>
      {admin && (
        <div className="form-actions">
          <Inert what="Closing the account">Close this account</Inert>
        </div>
      )}
    </>
  );
}

// --- invoices --------------------------------------------------------------

/** Paddle's word for an invoice, as this screen says the subscription's. */
const INVOICE_STATUS: Record<string, string> = {
  completed: "Paid",
  paid: "Paid",
  past_due: "Payment failed",
  canceled: "Cancelled",
};

/**
 * The invoices, read from Paddle on every visit; nothing of ours stores
 * them.
 *
 * ADMINISTRATOR ONLY (decided 24 October 2026). The server refuses a member,
 * in the sentence it uses for changing the plan, so a member is told here
 * instead and nothing is asked.
 *
 * ITS OWN ERROR, apart from the tab's, as the ledger's is on Balance: Paddle
 * not answering must not take the plan table with it.
 *
 * THE PDF IS ASKED FOR ON THE CLICK. Paddle's link expires in an hour, so
 * one fetched with the list could be dead by the time it is pressed.
 */
function Invoices({ subscribed }: { subscribed: boolean }) {
  const role = useRole();
  const [rows, setRows] = useState<Invoice[] | null>(null);
  const [after, setAfter] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  function show(page: InvoicePage, older: boolean) {
    setRows((had) => (older && had ? [...had, ...page.invoices]
                                   : page.invoices));
    setMore(page.has_more);
    setAfter(page.after);
  }

  useEffect(() => {
    if (role !== "admin") return;
    api.invoices().then((page) => show(page, false))
      .catch((e) => setError(message(e)));
  }, [role]);

  async function older() {
    setError("");
    setBusy("Reading older invoices");
    try {
      show(await api.invoices(after), true);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  async function download(transactionId: string) {
    setError("");
    setBusy("Opening the invoice");
    try {
      const { url } = await api.invoicePdf(transactionId);
      window.open(url, "_blank", "noopener");
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <h3>Invoices</h3>
      {role === "member" && (
        <p className="muted small">Only an administrator sees the invoices.</p>
      )}
      {role === "admin" && (
        <>
          {error && <p className="error">{error}</p>}
          {rows === null && !error && <Working what="Reading invoices" />}
          {busy && <Working what={busy} />}
          {rows !== null && rows.length === 0 && (
            <p className="muted">
              {subscribed ? "No invoices yet."
                : "Invoices appear here once a subscription is paid."}
            </p>
          )}
          {rows !== null && rows.length > 0 && (
            <TableScroll label="Invoices">
            <table className="docs">
              <thead>
                <tr><th>Date</th><th>What</th><th>Amount</th><th>Status</th>
                    <th></th></tr>
              </thead>
              <tbody>
                {rows.map((inv) => (
                  <tr key={inv.transaction_id}>
                    <td className="ref">{on(inv.billed_at)}</td>
                    <td>
                      {inv.what ?? "—"}
                      {inv.invoice_number && (
                        <div className="muted small">{inv.invoice_number}</div>
                      )}
                    </td>
                    <td className="ref">{money(inv.amount_cents)}</td>
                    <td className="ref">
                      {INVOICE_STATUS[inv.status] ?? inv.status}
                    </td>
                    <td>
                      {inv.has_pdf && (
                        <a className="small"
                           onClick={() => !busy && download(inv.transaction_id)}>
                          Download
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </TableScroll>
          )}
          {more && (
            <div className="form-actions">
              <button disabled={!!busy} onClick={older}>
                Show older
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}

// --- balance ---------------------------------------------------------------

function Balance() {
  // Topping up is an administrator's (billing.top_up refuses a member). A
  // member reads the balance, the buckets and the ledger, and is not offered
  // the box, the button or the confirmation.
  const role = useRole();
  const admin = role === "admin";
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [entries, setEntries] = useState<LedgerEntry[] | null>(null);
  // The ledger's own failure, kept apart from `error` (which replaces the
  // tab). It was turned into [] and read as "Nothing charged yet".
  const [ledgerError, setLedgerError] = useState("");
  const [error, setError] = useState("");
  const [increments, setIncrements] = useState(1);
  const [busy, setBusy] = useState("");
  const [said, setSaid] = useState("");
  // The confirmation between pressing Top up and charging the card (4.2).
  const [confirming, setConfirming] = useState(false);

  /** What one increment costs, as the server reports it (18.5 stage 3).
   *
   *  NULL UNTIL IT ANSWERS, and Top up is held until then. Every figure below
   *  is this number times the count, and a screen that states a charge it has
   *  guessed - then sends a request charging something else - is the one
   *  outcome a confirmation exists to prevent. Waiting a moment is cheap; the
   *  read happens with the two beside it.
   *
   *  FROM /billing/subscription, which is where the constant that charges is
   *  reported. Topping up is refused without an active subscription in any
   *  case, so this tab is already downstream of it. */
  const [topup, setTopup] = useState<number | null>(null);

  /** WHY SOMEBODY ARRIVED, where a screen said (21.2). The link from a
   *  refused filing or generation carries the shortfall, what it was for and
   *  where to go back to.
   *
   *  A STARTING POINT, NEVER A CHARGE. `need` presets the increments and is
   *  stated; the amount charged is still increments times the increment the
   *  server reports, and the confirmation shows that figure before the card
   *  is touched. So nothing written into the address can change a charge.
   *
   *  `back` is followed only where it is a path inside this application. */
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const needCents = Math.max(0, parseInt(params.get("need") ?? "", 10) || 0);
  const needFor = (params.get("for") ?? "").slice(0, 160);
  const asked = params.get("back") ?? "";
  const backTo = asked.startsWith("/") && !asked.startsWith("//") ? asked : "";

  useEffect(() => {
    api.wallet().then(setWallet).catch((e) => setError(String(e.message ?? e)));
    api.walletLedger(50).then((r) => setEntries(r.ledger))
      .catch((e) => setLedgerError(message(e)));
    api.subscription().then((v) => {
      setTopup(v.topup_increment_cents);
      // Enough increments to cover what was short, once the increment is
      // known. Still just the box's starting value: it can be changed.
      if (needCents > 0 && v.topup_increment_cents > 0) {
        setIncrements(Math.min(50, Math.max(1,
          Math.ceil(needCents / v.topup_increment_cents))));
      }
    }).catch(() => setTopup(null));
  }, [needCents]);

  /**
   * Buy credit. The charge goes to the card Paddle already holds.
   *
   * THE KEY IS MINTED ON THE CLICK, which is what makes a double click, a
   * retry or a stalled network one purchase rather than two. A repeat comes
   * back {repeated: true} and is reported as such rather than as an error:
   * nothing went wrong, it simply already happened.
   *
   * 202, AND THE MONEY IS NOT HERE YET. The credit is granted by Paddle's
   * transaction.completed webhook (item 6), so this polls the wallet instead
   * of adding the amount locally. A balance that goes up because the browser
   * decided it should is a balance that disagrees with the ledger.
   */
  async function topUp() {
    setBusy("Charging your card");
    setError("");
    setSaid("");
    const before = wallet?.available_cents ?? 0;
    try {
      const result = await api.topUp(increments, chargeKey());
      setSaid(result.repeated
        ? `Already bought: ${money(result.amount_cents)}. Nothing was charged `
          + "twice."
        : `${money(result.amount_cents)} charged. The credit lands when the `
          + "payment completes, which is usually seconds.");
      // Ten tries, three seconds apart: the webhook is its own journey.
      for (let i = 0; i < 10; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const fresh = await api.wallet().catch(() => null);
        if (!fresh) continue;
        setWallet(fresh);
        if (fresh.available_cents > before) {
          api.walletLedger(50).then((r) => {
            setEntries(r.ledger);
            setLedgerError("");
          }).catch(() => undefined);
          break;
        }
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

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

      {/* What sent them here, and the way back (21.2). The same
          .revision-note the running-low line uses: no new CSS. */}
      {needCents > 0 && (
        <p className="revision-note">
          <strong>
            {needFor ? `${needFor} is short by` : "Short by"}{" "}
            {money(needCents)}.
          </strong>{" "}
          Nothing has been charged.
          {role === "member" && " Only an administrator can top up."}
          {admin && topup !== null && ` ${increments} × ${money(topup)} `
            + (increments * topup >= needCents
              ? "covers it."
              : `leaves ${money(needCents - increments * topup)} still short.`)}
          {backTo && (
            <>
              {" "}
              <a onClick={() => navigate(backTo)}>Back to where you were</a>
            </>
          )}
        </p>
      )}

      {low && (
        <p className="revision-note">
          <strong>Running low.</strong> {wallet.available} left
          {inWork ? `, which is ${inWork}` : ""}. Filing and generating stop at
          zero; reading, downloading and editing your configuration do not.
        </p>
      )}

      {role === "member" && (
        <p className="muted small">
          Only an administrator changes the plan, the payment method or the
          balance.
        </p>
      )}

      {admin && (
      <div className="form-actions">
        <input type="number" min={1} max={50} value={increments}
               disabled={!!busy} style={{ width: 70 }}
               onChange={(e) => setIncrements(
                 Math.min(50, Math.max(1, Number(e.target.value) || 1)))} />
        {/* This press opens the confirmation; the card is charged on the one
            inside it (4.2). Every other act that spends is asked for twice,
            and this is the only one that reaches a card. */}
        <button className="spend" onClick={() => setConfirming(true)}
                disabled={!!busy || topup === null}
                title={topup === null
                  ? "Reading what an increment costs." : undefined}>
          {busy ? "Charging…"
            : topup === null ? "Top up"
            : `Top up ${money(increments * topup)}`}
        </button>
        <span className="muted small">
          {said || "In $5 increments, charged to the card Paddle holds. There "
            + "is no standing mandate: nothing is charged without this click, "
            + "and purchased credit expires 30 days after purchase."}
        </span>
      </div>
      )}

      {/* The second press, and the only one that charges (4.2). The figures
          are laid out as the filing and generating quotes are, so money on
          this screen reads the same way wherever it appears. */}
      {admin && confirming && topup !== null && (
        <div className="panel-backdrop" onClick={() => setConfirming(false)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}
               onKeyDown={(e) => { if (e.key === "Escape") setConfirming(false); }}>
            <a className="panel-close"
               onClick={() => setConfirming(false)}>Close</a>
            <div className="form">
              <h4>Top up the balance</h4>

              <div className="quote">
                <div>
                  <span>
                    {increments} &times; {money(topup)}
                    {increments === 1 ? " increment" : " increments"}
                  </span>
                  <b>{money(increments * topup)}</b>
                </div>
                <div>
                  <span>Available now</span>
                  <b>{wallet.available}</b>
                </div>
                <div>
                  <span>Once it lands</span>
                  <b>{money(wallet.available_cents
                            + increments * topup)}</b>
                </div>
              </div>

              <p className="muted small">
                Charged to the card Paddle holds, now. The credit arrives when
                Paddle reports the payment, which is usually seconds and is
                not instant &mdash; nothing here grants money, the webhook
                does. Purchased credit expires 30 days after purchase.
              </p>

              {needCents > 0 && (
                <p className="muted small">
                  {increments * topup >= needCents
                    ? `That covers the ${money(needCents)} needed.`
                    : `That leaves ${money(needCents - increments * topup)} `
                      + `of the ${money(needCents)} needed still short.`}
                </p>
              )}

              {memo && (
                <p className="muted small">
                  {increments * topup / memo} more{" "}
                  {increments * topup / memo === 1
                    ? "memorandum" : "memoranda"}, at today&rsquo;s price.
                </p>
              )}

              <div className="form-actions">
                <button className="spend" disabled={!!busy}
                        onClick={() => { setConfirming(false); topUp(); }}>
                  Charge {money(increments * topup)}
                </button>
                <a className="secondary"
                   onClick={() => setConfirming(false)}>Cancel</a>
              </div>
            </div>
          </div>
        </div>
      )}

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
        <TableScroll label="Balance, by bucket">
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
        </TableScroll>
      )}

      {gone.length > 0 && (
        <>
          <h4>Expired</h4>
          <p className="muted small">
            Shown rather than hidden. Money that ran out on a date is easier to
            understand than money that was simply never there.
          </p>
          <TableScroll label="Expired">
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
          </TableScroll>
        </>
      )}

      <h3>Ledger</h3>
      {entries === null && ledgerError && <p className="error">{ledgerError}</p>}
      {entries === null && !ledgerError && <p className="muted">Loading&hellip;</p>}
      {entries !== null && entries.length === 0 && (
        <p className="muted">Nothing charged yet.</p>
      )}
      {entries !== null && entries.length > 0 && (
        <TableScroll label="Ledger">
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
        </TableScroll>
      )}

      <p className="muted small">
        The ledger is append-only. A document paid for and then not filed
        &mdash; one that could not be read even with OCR &mdash; is refunded as
        a line of its own, and the charge stays beside it.
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

  // WHICH WORKSPACES A MEMBER SEES (PACK-02 C). An administrator sees every
  // one; a member only those ticked here, at least one. The list is the
  // tenant's, which an administrator - the only one on this screen who can
  // change it - is shown in full. The invitation starts with the workspace
  // in use ticked, so the common case is no extra click.
  const workspace = useWorkspace();
  const nameOf = (id: number) =>
    workspace.workspaces.find((w) => w.workspace_id === id)?.name
      ?? `Workspace ${id}`;
  const [inviteTo, setInviteTo] = useState<number[]>(
    workspace.active !== null ? [workspace.active] : []);
  // The member whose workspaces are being changed, and the ticks so far.
  const [editing, setEditing] = useState<number | null>(null);
  const [editTo, setEditTo] = useState<number[]>([]);
  const flip = (list: number[], id: number) =>
    list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
  const ticks = (chosen: number[], change: (next: number[]) => void,
                 name: string) => (
    <>
      {workspace.workspaces.map((w) => (
        <label className="inline-check" key={w.workspace_id}>
          <input type="checkbox" name={name}
                 checked={chosen.includes(w.workspace_id)}
                 onChange={() => change(flip(chosen, w.workspace_id))} />
          {w.name}
        </label>
      ))}
    </>
  );

  const load = () =>
    api.seats().then(setState).catch((e) => setError(message(e)));

  useEffect(() => { load(); }, []);

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
      const result = await api.invite(email, role,
                                      role === "member" ? inviteTo : []);
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
  // A MEMBER READS THIS SCREEN AND CHANGES NOTHING ON IT. Every write here is
  // refused to a member by the server; offering the controls only to have
  // them fail was the walk's finding (PACK-02 C). The viewer's role is their
  // own seat's, which the listing marks `you`.
  const admin = state.seats.find((s) => s.you)?.role === "admin";

  return (
    <>
      {error && <p className="error">{error}</p>}
      {busy && <Working what={busy} />}

      <p className="muted">
        {state.taken} of {state.bought} seats taken
        {state.reserved > 0 && `, ${state.reserved} reserved`}
        {state.free > 0 ? `, ${state.free} free` : ", none free"}
        {state.external > 0 && state.home_domain &&
          ` \u00b7 ${state.external} outside ${state.home_domain}`}
      </p>

      <TableScroll label="Seats">
      <table className="docs">
        <thead>
          <tr><th>Person</th><th>Rights</th><th>Workspaces</th><th>Since</th><th></th></tr>
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
                {admin ? (
                  <select value={s.role} disabled={!!busy}
                          onChange={(e) => act("Changing rights", () =>
                            api.setSeatRole(s.seat_id,
                              e.target.value as "admin" | "member"))}>
                    <option value="admin">Administrator</option>
                    <option value="member">Member</option>
                  </select>
                ) : (
                  s.role === "admin" ? "Administrator" : "Member"
                )}
                {s.role === "admin" && onlyAdmin && (
                  <div className="muted small">the only one</div>
                )}
              </td>
              <td>
                {s.workspaces === null ? (
                  <span className="muted small">Every workspace</span>
                ) : !admin && !s.you ? (
                  // A member's list of workspaces names only their own, so
                  // another member's could read "Workspace 9". Not theirs to see.
                  <span className="muted small">&mdash;</span>
                ) : editing === s.seat_id ? (
                  <>
                    {ticks(editTo, setEditTo, `seat-${s.seat_id}`)}
                    <div className="form-actions">
                      <button disabled={!!busy || editTo.length === 0}
                              onClick={() => act("Saving workspaces", async () => {
                                await api.setSeatWorkspaces(s.seat_id, editTo);
                                setEditing(null);
                              })}>
                        Save
                      </button>
                      <a className="secondary small"
                         onClick={() => setEditing(null)}>Cancel</a>
                      {editTo.length === 0 && (
                        <span className="muted small">At least one.</span>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    {s.workspaces.length === 0
                      ? <span className="warn small">None &mdash; sees nothing</span>
                      : <span className="small">
                          {s.workspaces.map(nameOf).join(", ")}
                        </span>}
                    {admin && (
                      <>
                        {" "}
                        <a className="small" onClick={() => {
                          setEditing(s.seat_id);
                          setEditTo(s.workspaces ?? []);
                        }}>Change</a>
                      </>
                    )}
                  </>
                )}
              </td>
              <td className="ref">{(s.accepted_at ?? "").slice(0, 10)}</td>
              <td>
                {admin && !s.you && (
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
              <td className="muted small">
                {i.workspaces === null ? "Every workspace"
                  : i.workspaces.map(nameOf).join(", ")}
              </td>
              <td className="ref">reserved</td>
              <td>
                {admin && (
                  <a className="small" onClick={() =>
                    act("Revoking", () =>
                      api.revokeInvitation(i.invitation_id))}>
                    Revoke
                  </a>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </TableScroll>

      {state.invitations.length > 0 && (
        <p className="muted small">
          A reserved seat is as unavailable as a taken one. An invitation
          nobody accepts lapses after seven days and gives the seat back,
          so nothing has to be chased.
        </p>
      )}

      {!admin && (
        <p className="muted small">
          Only an administrator invites, removes or re-ranks a seat, or
          changes which workspaces a member sees.
        </p>
      )}

      {admin && (<>
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
        {/* A member sees only the workspaces ticked here (PACK-02 C); an
            administrator sees every one, so is asked nothing. */}
        {role === "member" && (
          <div className="row">
            <span>Workspaces</span>
            <div>
              {ticks(inviteTo, setInviteTo, "invite-workspaces")}
              {inviteTo.length === 0 && (
                <p className="muted small">
                  Tick at least one. A member sees only these.
                </p>
              )}
            </div>
          </div>
        )}
        <div className="form-actions">
          <button onClick={sendInvite}
                  disabled={!!busy || !email.includes("@") || state.free === 0
                            || (role === "member" && inviteTo.length === 0)}>
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

      {/* The other way out of a full workspace, which the screen never
          offered although the server's own refusal names it: "All N seats are
          taken or reserved. Remove one, or change the plan." (seats.py:260).
          Removing somebody was the only thing on offer here (11.1). */}
      {state.free === 0 && (
        <UpgradePrompt action="See plans">
          All {state.bought}{" "}
          {state.bought === 1 ? "seat is" : "seats are"} taken or reserved.
          Seats come with the plan &mdash; a bigger one is how a workspace
          gets more of them, and nobody has to be removed to make room.
        </UpgradePrompt>
      )}

      {invited && (
        <div className="panel" style={{ marginTop: 18, padding: "16px 18px" }}>
          <h4 style={{ marginTop: 0 }}>
            {invited.sent
              ? `Invitation sent to ${invited.email}`
              : `Send ${invited.email} this link`}
          </h4>
          {/* The seat is reserved either way. What changes is who has to
              deliver the link (10.5). */}
          <p className="muted small">
            {invited.sent
              ? "It has gone to them from no-reply@arqedia.com, and a reply "
                + "to it reaches you. The same link is below: it is shown "
                + "once and cannot be recovered, so keep it until they are "
                + "in. If it is lost, invite them again and a new one "
                + "replaces it."
              : "The seat is reserved, but the email could not be sent. Send "
                + "them this link yourself. It is shown once and cannot be "
                + "recovered; if it is lost, invite them again and a new one "
                + "replaces it."}
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
      </>)}

      <h3>What the two rights mean</h3>
      <table className="docs">
        <thead>
          <tr><th></th><th>Administrator</th><th>Member</th></tr>
        </thead>
        <tbody>
          <tr><td>Upload, file and generate</td><td className="ref">yes</td><td className="ref">yes</td></tr>
          <tr><td>Edit and publish the configuration</td><td className="ref">yes</td><td className="ref">no</td></tr>
          <tr><td>Share a memorandum, and revoke</td><td className="ref">yes</td><td className="ref">yes</td></tr>
          <tr><td>Change the plan or the payment method</td><td className="ref">yes</td><td className="ref">no</td></tr>
          <tr><td>Invite, remove or re-rank a seat</td><td className="ref">yes</td><td className="ref">no</td></tr>
          <tr><td>Set the brand</td><td className="ref">yes</td><td className="ref">no</td></tr>
          <tr><td>Close the account</td><td className="ref">yes</td><td className="ref">no</td></tr>
          <tr><td>See a workspace</td><td className="ref">every one</td><td className="ref">those ticked</td></tr>
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

// --- workspaces ------------------------------------------------------------

/**
 * Deleting a workspace, and restoring one (PACK-02 D, settled 23 October
 * 2026). Administrators only.
 *
 * HIDDEN, THEN REMOVED. Deleting hides a workspace at once - out of the
 * picker, its shares suspended, not counted against the plan - and it is
 * removed for good six months later. Until then it is listed below with
 * Restore.
 *
 * THE STEPS, as settled: what it holds is shown first; a code is emailed to
 * the administrator; the name is typed; and members who see only this
 * workspace are moved to one the administrator names. The server checks
 * every one of them again - this screen only asks.
 *
 * Composed from the panel, quote and form the top-up confirmation uses. No
 * new CSS.
 */
function Workspaces() {
  const [list, setList] = useState<WorkspaceList | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [said, setSaid] = useState("");

  // The one being deleted, and what has been entered for it.
  const [deleting, setDeleting] = useState<HeldWorkspace | null>(null);
  const [codeSent, setCodeSent] = useState(false);
  const [code, setCode] = useState("");
  const [typed, setTyped] = useState("");
  const [moveTo, setMoveTo] = useState<number | null>(null);
  const [panelError, setPanelError] = useState("");

  const load = () =>
    api.workspacesList().then(setList).catch((e) => setError(message(e)));

  useEffect(() => { load(); }, []);

  function open(w: HeldWorkspace) {
    setDeleting(w);
    setCodeSent(false);
    setCode("");
    setTyped("");
    setMoveTo(null);
    setPanelError("");
  }

  async function sendCode() {
    if (!deleting) return;
    setPanelError("");
    setBusy("Sending the code");
    try {
      const out = await api.workspaceDeletionCode(deleting.workspace_id);
      setCodeSent(true);
      if (!out.sent) {
        setPanelError("The code could not be emailed just now. Nothing was "
                      + "deleted - ask again in a minute.");
      }
    } catch (err) {
      setPanelError(message(err));
    } finally {
      setBusy("");
    }
  }

  async function confirmDelete() {
    if (!deleting) return;
    setPanelError("");
    setBusy("Deleting " + deleting.name);
    try {
      const out = await api.deleteWorkspace(deleting.workspace_id, typed,
                                            code.trim(), moveTo);
      setDeleting(null);
      setSaid(`${deleting.name} is deleted. It can be restored until `
              + `${on(out.remove_after)}.`);
      // The picker reads the list again; a deleted active workspace gives
      // way to the first that is left.
      workspacesChanged();
      await load();
    } catch (err) {
      setPanelError(message(err));
    } finally {
      setBusy("");
    }
  }

  async function restore(id: number, name: string) {
    setError("");
    setSaid("");
    setBusy("Restoring " + name);
    try {
      await api.restoreWorkspace(id);
      setSaid(`${name} is back, with its shares.`);
      workspacesChanged();
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  if (error && !list) return <p className="error">{error}</p>;
  if (!list) return <p className="muted">Loading&hellip;</p>;

  const onlyOne = list.workspaces.length <= 1;
  const stranded = deleting
    ? [...deleting.members_only_here, ...deleting.invitations_only_here] : [];
  const others = deleting
    ? list.workspaces.filter((w) => w.workspace_id !== deleting.workspace_id)
    : [];
  // IN ORDER (25 October 2026): the members' workspace and the name first,
  // and only then may a code be asked for. A code sent before the name was
  // typed was entered, and Delete stayed dead because the name was missing.
  const before = !deleting ? ""
    : stranded.length > 0 && moveTo === null
      ? "Choose the workspace its members move to."
    : typed.trim() !== deleting.name.trim()
      ? `Type the name exactly as shown: ${deleting.name}.`
    : "";
  // WHAT IS STILL MISSING after that, said beside the disabled Delete. It
  // said nothing, so a person who entered the code and not the name pressed
  // a dead button and saw nothing happen (tenant 5, 25 October 2026). What
  // comes before the code is said beside Email me a code instead.
  const missing = !deleting || before ? ""
    : !codeSent ? "Ask for the code, then enter it."
    : code.trim().length !== 6 ? "Enter the six-digit code from the email."
    : "";
  const ready = !!deleting && before === "" && missing === "";
  // Enter in the name or the code deletes once nothing is missing, as a
  // form would.
  const enter = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && ready && !busy) confirmDelete();
  };

  return (
    <>
      {error && <p className="error">{error}</p>}
      {busy && <Working what={busy} />}
      {said && <p className="revision-note">{said}</p>}

      <h3>Your workspaces</h3>
      <p className="muted small">
        Deleting a workspace hides it at once: it leaves the list at the top
        of the page, links shared from its memoranda stop opening, and it no
        longer counts toward your plan. It is removed for good{" "}
        {list.keep_months} months later, and until then it can be restored
        below. Nothing charged is refunded.
      </p>
      <TableScroll label="Workspaces">
      <table className="docs">
        <thead>
          <tr><th>Workspace</th><th>Engagements</th><th>Documents</th>
              <th>Memoranda</th><th>Live shares</th><th></th></tr>
        </thead>
        <tbody>
          {list.workspaces.map((w) => (
            <tr key={w.workspace_id}>
              <td>{w.name}</td>
              <td className="ref">{w.engagements}</td>
              <td className="ref">{w.documents}</td>
              <td className="ref">{w.memos}</td>
              <td className="ref">{w.shares}</td>
              <td>
                {/* An offering something depends on is kept, and says why
                    (amended 23 October 2026). The server refuses it too. */}
                {onlyOne
                  ? <span className="muted small">your only one</span>
                  : (w.clients ?? 0) > 0
                    ? <span className="muted small">
                        {w.clients} client{" "}
                        {w.clients === 1 ? "workspace" : "workspaces"} use it
                      </span>
                    : (w.on_offer ?? 0) > 0
                      ? <span className="muted small">on offer</span>
                      : <a className="small" onClick={() => open(w)}>Delete</a>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </TableScroll>
      {onlyOne && (
        <p className="muted small">
          The last workspace cannot be deleted. Closing the account is a
          separate step.
        </p>
      )}

      {list.deleted.length > 0 && (
        <>
          <h3>Deleted</h3>
          <TableScroll label="Deleted workspaces">
          <table className="docs">
            <thead>
              <tr><th>Workspace</th><th>Deleted</th><th>Removed for good</th>
                  <th></th></tr>
            </thead>
            <tbody>
              {list.deleted.map((w) => (
                <tr key={w.workspace_id} className="aside">
                  <td>{w.name}</td>
                  <td className="muted small">
                    {on(w.deleted_at)} by {w.deleted_by}
                  </td>
                  <td className="ref">{on(w.remove_after)}</td>
                  <td>
                    {w.restorable
                      ? <a className="small" onClick={() =>
                          restore(w.workspace_id, w.name)}>Restore</a>
                      : <span className="muted small">being removed</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </TableScroll>
        </>
      )}

      {/* THE STEPS, in a panel over the list, as Top up's confirmation is. */}
      {deleting && (
        <div className="panel-backdrop" onClick={() => setDeleting(null)}>
          <div className="panel narrow" onClick={(e) => e.stopPropagation()}
               onKeyDown={(e) => { if (e.key === "Escape") setDeleting(null); }}>
            <a className="panel-close" onClick={() => setDeleting(null)}>Close</a>
            <div className="form">
              <h4>Delete {deleting.name}</h4>

              <div className="quote">
                <div><span>Engagements</span><b>{deleting.engagements}</b></div>
                <div><span>Documents</span><b>{deleting.documents}</b></div>
                <div><span>Memoranda</span><b>{deleting.memos}</b></div>
                <div><span>Shares that stop opening</span>
                     <b>{deleting.shares}</b></div>
              </div>

              <p className="muted small">
                All of it is hidden now and removed for good in{" "}
                {list.keep_months} months. Restoring it before then brings
                it all back, its shares included. A copy a recipient already
                downloaded is not recalled.
              </p>

              {stranded.length > 0 && (
                <label className="row">
                  <span>
                    {stranded.join(", ")}{" "}
                    {stranded.length === 1 ? "sees" : "see"} only this
                    workspace. Move them to
                  </span>
                  <select value={moveTo ?? ""}
                          onChange={(e) => setMoveTo(
                            e.target.value ? Number(e.target.value) : null)}>
                    <option value="">Choose a workspace</option>
                    {others.map((w) => (
                      <option key={w.workspace_id} value={w.workspace_id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <label className="row">
                <span>Type <b>{deleting.name}</b> to confirm</span>
                <input value={typed} autoComplete="off" onKeyDown={enter}
                       onChange={(e) => setTyped(e.target.value)} />
              </label>

              <div className="form-actions">
                <button disabled={!!busy || before !== ""} onClick={sendCode}>
                  {codeSent ? "Send another code" : "Email me a code"}
                </button>
                <span className="muted small">
                  {before
                    ? before
                    : codeSent
                    ? "Sent to your address. It works for 15 minutes."
                    : "Deleting needs a code we email to you."}
                </span>
              </div>

              {codeSent && (
                <label className="row">
                  <span>The code</span>
                  <input value={code} inputMode="numeric" maxLength={6}
                         autoComplete="one-time-code" onKeyDown={enter}
                         onChange={(e) => setCode(e.target.value)} />
                </label>
              )}

              {panelError && <p className="error">{panelError}</p>}

              <div className="form-actions">
                <button disabled={!!busy || !ready} onClick={confirmDelete}>
                  Delete {deleting.name}
                </button>
                <a className="secondary" onClick={() => setDeleting(null)}>
                  Cancel
                </a>
                {missing && <span className="muted small">{missing}</span>}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// --- password --------------------------------------------------------------

/**
 * The password of whoever is signed in, changed by them.
 *
 * NOTHING OF OURS IS IN THE PATH. Amplify talks to Cognito directly, as the
 * sign-in card does, so there is no route, no Lambda and no record of this on
 * our side. The old password is Cognito's requirement, not a second thought
 * added here: a session left open on a shared machine is exactly what it is
 * for.
 *
 * COGNITO'S REFUSAL IS WHAT THE SCREEN SAYS. A wrong old password, a password
 * below the policy, too many attempts - each has a sentence already written
 * for a person to read, and rewording them here would mean maintaining a copy
 * of a policy we do not own.
 *
 * The one check that is ours is typing it twice, because Cognito has no
 * opinion about that and a mistyped new password locks somebody out of their
 * own account.
 */
function Password() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [changed, setChanged] = useState(false);

  const mismatch = again.length > 0 && next !== again;
  const ready = current.length > 0 && next.length > 0 && !mismatch;

  async function change() {
    setBusy(true);
    setError("");
    setChanged(false);
    try {
      await updatePassword({ oldPassword: current, newPassword: next });
      setCurrent("");
      setNext("");
      setAgain("");
      setChanged(true);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {error && <p className="error">{error}</p>}
      {/* Left as it is (6.3), with the two in Memo.tsx. This one would
           convert cleanly - it is a block paragraph like the four that did -
           and it is held with them so the three are settled in one decision
           rather than two now and one later. Nothing about it is special
           except that company. */}
      {busy && <p className="busy">Changing&hellip;</p>}
      {changed && !busy && <p className="saved">Password changed.</p>}

      <h3>Change your password</h3>
      <p className="muted small">
        At least 12 characters, with an upper case letter, a lower case letter
        and a number. This changes the password of the account you are signed
        in with and nobody else&rsquo;s &mdash; an administrator cannot set
        another person&rsquo;s password, and never sees one.
      </p>

      <div className="form">
        <label className="row">
          <span>Current password</span>
          <input type="password" value={current} disabled={busy}
                 onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label className="row">
          <span>New password</span>
          <input type="password" value={next} disabled={busy}
                 onChange={(e) => setNext(e.target.value)} />
        </label>
        <label className="row">
          <span>New password again</span>
          <input type="password" value={again} disabled={busy}
                 onChange={(e) => setAgain(e.target.value)} />
        </label>
        <div className="form-actions">
          <button onClick={change} disabled={busy || !ready}>
            Change password
          </button>
          <span className="muted small">
            {mismatch
              ? "The two new passwords are not the same."
              : "Forgotten the current one? Sign out, and use "
                + "“Forgotten your password?” on the sign-in card."}
          </span>
        </div>
      </div>
    </>
  );
}
