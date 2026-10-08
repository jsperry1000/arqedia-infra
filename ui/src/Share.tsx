import { useEffect, useState } from "react";
import { useBackAction, Working } from "./shell";
import {
  api, chargeKey, statusOf,
  type ShareAllowance, type ShareGrant, type ShareSent,
} from "./api";
import {
  NO_FILTER, filterHistory, sortRows, type Filter, type SortDir,
} from "./shareBatch";

/**
 * Sharing. Who a memorandum has been sent to, what they did with it, and
 * taking it back.
 *
 * SENDING OPENS FROM THE MEMORANDUM'S OWN PAGE (ShareSendPanel, below, used
 * by Memo.tsx). This screen is the list: every grant the workspace has made,
 * revoke, and send again.
 *
 * Three things the screen has to make true, all from the share
 * specification: a grant carries the rendered memorandum and nothing else,
 * revoking is available in every state including capped, and revoking cannot
 * recall a copy already downloaded - which is said where somebody sends, not
 * in terms nobody reads.
 */

export function errorText(err: unknown): string {
  let message = String((err as Error)?.message ?? err);
  try {
    message = JSON.parse(message).error ?? message;
  } catch { /* not JSON; show it as it came */ }
  return message;
}

export const day = (iso: string | null | undefined) => (iso ?? "").slice(0, 10);
export const money = (cents: number) => `$${(cents / 100).toFixed(2)}`;

/** The allowance in one sentence, and what the next share costs once it is
 *  used up. A trial is ten for the whole trial; a plan is per billing month. */
export function AllowanceLine({ allowance: a }: { allowance: ShareAllowance }) {
  if (a.capped) {
    return (
      <p className="warn">
        This workspace has no balance, so it cannot share. Revoking still
        works. Top up under Settings, Account management.
      </p>
    );
  }
  const span = a.trial ? "during the trial" : `this month (to ${day(a.period_ends_at)})`;
  if (a.allowance === null) {
    return <p className="muted small">{a.used} shared {span}. No limit on this plan.</p>;
  }
  const over = a.overage_cents === null
    ? "Sharing past it is not priced yet, so it is refused."
    : `Each one past it costs ${money(a.overage_cents)}.`;
  return (
    <p className="muted small">
      {a.used} of {a.allowance} included shares used {span}
      {a.remaining === 0 ? " — all of them. " : `, ${a.remaining} left. `}
      {over} At most {a.daily_limit} a day ({a.today} today).
    </p>
  );
}

/** What a recipient gets, and what they do not. The scope is settled in the
 *  share specification (section 2); this is its statement, not a figure. */
export function Scope() {
  return (
    <table className="docs">
      <tbody>
        <tr><td>The rendered memorandum, watermarked with their address</td>
            <td className="ref" style={{ width: 60 }}>yes</td></tr>
        <tr><td>The source documents behind each claim</td>
            <td className="ref">no</td></tr>
        <tr><td>Your configuration</td><td className="ref">no</td></tr>
        <tr><td>Anything else in the engagement</td><td className="ref">no</td></tr>
      </tbody>
    </table>
  );
}

/** §7.2. The tenant's own assurance, at the moment of sending. */
export function Authority({ checked, onChange, several = false }: {
  checked: boolean; onChange: (v: boolean) => void; several?: boolean;
}) {
  return (
    <label className="affirm">
      <input type="checkbox" checked={checked}
             onChange={(e) => onChange(e.target.checked)} />
      <span>
        {several
          ? "I am entitled to share these memoranda with this person. They "
            + "carry third-party identity material, and that assurance is "
            + "mine to give."
          : "I am entitled to share this memorandum with this person. It "
            + "carries third-party identity material, and that assurance is "
            + "mine to give."}
      </span>
    </label>
  );
}

/** Said at the point of sending, in plain words (share_viewer_spec §4). */
export function CannotRecall() {
  return (
    <p className="revision-note">
      Revoking ends access in ARQEDIA. It cannot recall a copy the recipient
      has already downloaded. Every page of that copy carries their address
      and the time they took it.
    </p>
  );
}

// --- sending, from a memorandum ----------------------------------------------

export function ShareSendPanel({ memoId, label, onClose }: {
  memoId: number;
  label: string;
  onClose: () => void;
}) {
  const [allowance, setAllowance] = useState<ShareAllowance | null>(null);
  const [to, setTo] = useState("");
  const [expiry, setExpiry] = useState<string>("default");
  const [affirmed, setAffirmed] = useState(false);
  // Minted when the panel opens, and again after a send: one click, one key,
  // so a retry of the same click is answered rather than charged twice.
  const [key, setKey] = useState(chargeKey());
  // The overage price, once the person has been shown it. Sent with the
  // request; the server refuses any other figure.
  const [accepted, setAccepted] = useState<number | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState<ShareSent | null>(null);

  async function load() {
    try {
      setAllowance((await api.shares()).allowance);
    } catch (err) {
      setError(errorText(err));
    }
  }
  useEffect(() => { load(); }, []);

  const past = !!allowance && allowance.allowance !== null && allowance.remaining === 0;
  const price = allowance?.overage_cents ?? null;
  const charging = past && price !== null;

  async function send() {
    setSending(true);
    setError("");
    try {
      const result = await api.sendShare(memoId, {
        recipient: to.trim(),
        authority_affirmed: affirmed,
        expiry_days: expiry === "default" ? null : Number(expiry),
        idempotency_key: key,
        accept_overage_cents: charging ? price : accepted,
      });
      setSent(result);
      setTo("");
      setAffirmed(false);
      setAccepted(null);
      setKey(chargeKey());
      load();
    } catch (err) {
      // Past the allowance since the screen last looked: nothing was sent or
      // charged. The price comes back with the refusal, and the next press
      // accepts it.
      if (statusOf(err) === 409) {
        try {
          const body = JSON.parse((err as Error).message);
          if (typeof body.overage_cents === "number") {
            setAccepted(body.overage_cents);
            setError(body.error);
            load();
            return;
          }
        } catch { /* fall through */ }
      }
      setError(errorText(err));
    } finally {
      setSending(false);
    }
  }

  const cost = charging ? price : accepted;
  const ready = !!to.trim() && affirmed && !sending && !!allowance && !allowance.capped;

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <aside className="panel narrow" onClick={(e) => e.stopPropagation()}>
        <a onClick={onClose} className="panel-close">Close</a>
        <h3>Share memo {label}</h3>
        <p className="muted small">
          The recipient gets a link by email. Opening it shows this memorandum
          and nothing else; registering keeps their access longer.
        </p>

        {allowance ? <AllowanceLine allowance={allowance} />
                   : !error && <Working what="Reading the allowance" />}

        <div className="form">
          <label className="row">
            <span>Recipient email</span>
            <input placeholder="name@firm.com" value={to}
                   onChange={(e) => setTo(e.target.value)} />
          </label>

          <label className="row">
            <span>Access</span>
            <select value={expiry} onChange={(e) => setExpiry(e.target.value)}>
              {/* The default is not a date the tenant set: it is two weeks,
                  and six months from sending once the recipient registers
                  (share_viewer_spec §6). A chosen period is a ceiling that
                  registering never moves. */}
              <option value="default">
                2 weeks, or 6 months if they register (default)
              </option>
              <option value="30">30 days, fixed</option>
              <option value="90">90 days, fixed</option>
            </select>
          </label>

          <h4>What the recipient gets</h4>
          <Scope />

          <CannotRecall />

          <Authority checked={affirmed} onChange={setAffirmed} />

          {cost !== null && (
            <p className="warn">
              This is past the shares your plan includes. Sending it costs{" "}
              {money(cost)}, charged when you press Send.
            </p>
          )}

          <div className="form-actions">
            <button onClick={send} disabled={!ready}
                    title={!affirmed ? "Confirm you are entitled to share it first."
                                     : undefined}>
              {sending ? "Sending…"
                       : cost !== null ? `Send — ${money(cost)}` : "Send"}
            </button>
          </div>
        </div>

        {error && <p className="error">{error}</p>}

        {sent && (
          <p className="revision-note">
            {sent.reinstated ? "Sent again, and access restored, " : "Sent "}
            to {sent.recipient_email}. Access ends {day(sent.expires_at)}.
            {sent.charged_cents > 0 && ` Charged ${money(sent.charged_cents)}.`}
            {!sent.sent && " The email could not be delivered; the share stands, "
              + "and sending it again from Sharing retries the email."}
          </p>
        )}
      </aside>
    </div>
  );
}

// --- sorting and filtering, shared with Share a memo -------------------------

/** One sorted column, as the Filed list on an engagement does it: a click
 *  sorts by that column, a second click turns it round. Nothing is sorted
 *  until somebody clicks, so the server's own order stands. */
export function useSort<K extends string>() {
  const [key, setKey] = useState<K | null>(null);
  const [dir, setDir] = useState<SortDir>("asc");
  const by = (k: K) => {
    if (k === key) setDir(dir === "asc" ? "desc" : "asc");
    else { setKey(k); setDir("asc"); }
  };
  const arrow = (k: K) => (k !== key ? "" : dir === "desc" ? " ↓" : " ↑");
  return { key, dir, by, arrow };
}

/** Text, and a date range inclusive at both ends. */
export function FilterRow({ filter, onChange, placeholder, dateLabel }: {
  filter: Filter;
  onChange: (f: Filter) => void;
  placeholder: string;
  dateLabel: string;
}) {
  return (
    <div className="filters">
      <input placeholder={placeholder} value={filter.text}
             onChange={(e) => onChange({ ...filter, text: e.target.value })} />
      <label className="muted small">
        {dateLabel} from{" "}
        <input type="date" value={filter.from}
               onChange={(e) => onChange({ ...filter, from: e.target.value })} />
      </label>
      <label className="muted small">
        to{" "}
        <input type="date" value={filter.to}
               onChange={(e) => onChange({ ...filter, to: e.target.value })} />
      </label>
      {(filter.text || filter.from || filter.to) && (
        <a className="secondary" onClick={() => onChange(NO_FILTER)}>Clear</a>
      )}
    </div>
  );
}

// --- the list ----------------------------------------------------------------

type HistoryKey = "recipient_email" | "memo_label" | "sent_at"
  | "first_opened_at" | "opens" | "downloads" | "expires_at";

export function ShareView({ onBack, onMemo }: {
  onBack: () => void;
  onMemo: (memoId: number) => void;
}) {
  useBackAction(onBack);

  const [grants, setGrants] = useState<ShareGrant[] | null>(null);
  const [allowance, setAllowance] = useState<ShareAllowance | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string>("");
  // The grant being sent again, and its own §7.2 box.
  const [again, setAgain] = useState<string>("");
  const [affirmed, setAffirmed] = useState(false);
  const sort = useSort<HistoryKey>();
  const [filter, setFilter] = useState<Filter>(NO_FILTER);

  async function load() {
    try {
      const listed = await api.shares();
      setGrants(listed.grants);
      setAllowance(listed.allowance);
    } catch (err) {
      setError(errorText(err));
    }
  }
  useEffect(() => { load(); }, []);

  async function revoke(g: ShareGrant) {
    setBusy(g.grant_id);
    setError("");
    try {
      await api.revokeShare(g.grant_id);
      await load();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy("");
    }
  }

  async function sendAgain(g: ShareGrant) {
    setBusy(g.grant_id);
    setError("");
    try {
      // The same grant: reinstated if it was revoked, a fresh two weeks, the
      // same link. No allowance and no charge.
      await api.sendShare(g.memo_id, {
        recipient: g.recipient_email,
        authority_affirmed: affirmed,
        expiry_days: null,
        idempotency_key: chargeKey(),
      });
      setAgain("");
      setAffirmed(false);
      await load();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy("");
    }
  }

  const shown = grants === null ? [] : (() => {
    const kept = filterHistory(grants, filter);
    return sort.key ? sortRows(kept, sort.key, sort.dir) : kept;
  })();
  const th = (k: HistoryKey, label: string) => (
    <th onClick={() => sort.by(k)}>{label}{sort.arrow(k)}</th>
  );

  return (
    <div>
      <h2>Sharing history</h2>
      <p className="muted">
        Every memorandum this workspace has shared. To share one, open it and
        choose Share, or choose Share a memo under Sharing.
      </p>

      {allowance && <AllowanceLine allowance={allowance} />}
      {error && <p className="error">{error}</p>}
      {grants === null && !error && <Working what="Reading what has been shared" />}

      {grants !== null && grants.length === 0 && (
        <p className="muted">Nothing has been shared yet.</p>
      )}

      {grants !== null && grants.length > 0 && (
        <FilterRow filter={filter} onChange={setFilter}
                   placeholder="Filter by recipient or memorandum"
                   dateLabel="Sent" />
      )}

      {grants !== null && grants.length > 0 && shown.length === 0 && (
        <p className="muted">Nothing shared matches the filter.</p>
      )}

      {shown.length > 0 && (
        <table className="docs">
          <thead>
            <tr>
              {th("recipient_email", "Recipient")}{th("memo_label", "Memorandum")}
              {th("sent_at", "Sent")}{th("first_opened_at", "First opened")}
              {th("opens", "Opens")}{th("downloads", "Downloads")}
              {th("expires_at", "Access ends")}<th></th>
            </tr>
          </thead>
          <tbody>
            {shown.map((g) => (
              <tr key={g.grant_id}>
                <td>
                  {g.recipient_email}
                  {g.registered && <div className="in-use">registered</div>}
                </td>
                <td className="small">
                  <a onClick={() => onMemo(g.memo_id)}>{g.memo_label}</a>
                  {g.subject && <div className="muted">{g.subject}</div>}
                </td>
                <td className="ref">
                  {day(g.sent_at)}
                  <div className="muted small">{g.sent_by}</div>
                </td>
                <td className="ref">{g.first_opened_at ? day(g.first_opened_at) : "—"}</td>
                <td className="ref">{g.opens}</td>
                <td className="ref">{g.downloads}</td>
                <td className="ref">
                  {g.revoked
                    ? <span className="muted">revoked {day(g.revoked_at)}
                        <div className="small">by {g.revoked_by}</div></span>
                    : <>
                        {day(g.expires_at)}
                        {g.expired && <div className="warn">ended</div>}
                        {g.expiry_set_by_tenant && <div className="muted small">fixed</div>}
                      </>}
                </td>
                <td>
                  {again === g.grant_id ? (
                    <div className="share-again">
                      <Authority checked={affirmed} onChange={setAffirmed} />
                      <button onClick={() => sendAgain(g)}
                              disabled={!affirmed || busy === g.grant_id}>
                        {busy === g.grant_id ? "Sending…" : "Send again"}
                      </button>
                      <a className="secondary"
                         onClick={() => { setAgain(""); setAffirmed(false); }}>
                        Cancel
                      </a>
                    </div>
                  ) : (
                    <div className="row-tools">
                      {!g.revoked && (
                        <button onClick={() => revoke(g)}
                                disabled={busy === g.grant_id}>
                          {busy === g.grant_id ? "Revoking…" : "Revoke"}
                        </button>
                      )}
                      <a className="secondary"
                         onClick={() => { setAgain(g.grant_id); setAffirmed(false); }}>
                        {g.revoked ? "Restore and send again" : "Send again"}
                      </a>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <CannotRecall />

      <p className="muted small">
        A recipient who only opens the link has no relationship with us &mdash;
        you collected that address and we delivered a file to it. One who
        registers keeps access for six months from when it was sent and has
        accepted our terms directly. Revoking works in every state, including
        when the account has no balance.
      </p>
    </div>
  );
}
