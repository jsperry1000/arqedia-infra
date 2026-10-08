import { useEffect, useState } from "react";
import { useBackAction, Working } from "./shell";
import {
  api, chargeKey, statusOf,
  type ShareAllowance, type ShareGrant,
} from "./api";
import {
  AllowanceLine, Authority, CannotRecall, FilterRow, Scope, day, errorText,
  money, useSort,
} from "./Share";
import {
  MAX_BATCH, NO_FILTER, filterMemos, planBatch, resendsFor, sortRows, toggle,
  type BatchMemo, type Filter, type Plan,
} from "./shareBatch";

/**
 * Share a memo (feature/share-multi-memo). Up to five memoranda, from any
 * engagement, to one person, in one email.
 *
 * EACH MEMORANDUM IS STILL ITS OWN SHARE. They go one at a time through the
 * same route the memo page uses - its own grant, its own place in the
 * allowance, its own charge and idempotency key - with notify: false. Once
 * they have all been answered, ONE email carries the links of those that
 * went (POST /shares/notify). A retry of the ones that failed gets an email
 * of its own.
 *
 * NOTHING IS SENT OR CHARGED UNTIL A BUTTON SAYS SO. Where the batch runs
 * past the shares the plan includes, the screen stops and shows which are
 * included, which would be charged and what that comes to, before anything
 * happens.
 */

type MemoKey = "label" | "engagement" | "generated_at" | "number";

type Outcome = {
  memo_id: number;
  ok: boolean;
  grant_id?: string;
  charged_cents?: number;
  reinstated?: boolean;
  error?: string;
  /** Refused because it is now past the allowance: what it would cost. */
  price?: number;
};

type Notified = { grantIds: string[]; sent: boolean | null; error?: string };

export function ShareBatchView({ onBack, onHistory, onTopUp }: {
  onBack: () => void;
  onHistory: () => void;
  onTopUp: () => void;
}) {
  useBackAction(onBack);

  const [memos, setMemos] = useState<BatchMemo[] | null>(null);
  const [limit, setLimit] = useState(0);
  const [grants, setGrants] = useState<ShareGrant[]>([]);
  const [allowance, setAllowance] = useState<ShareAllowance | null>(null);
  const [error, setError] = useState("");

  const [selected, setSelected] = useState<number[]>([]);
  const [refused, setRefused] = useState<string | null>(null);
  const sort = useSort<MemoKey>();
  const [filter, setFilter] = useState<Filter>(NO_FILTER);

  const [to, setTo] = useState("");
  const [expiry, setExpiry] = useState<string>("default");
  const [affirmed, setAffirmed] = useState(false);

  // The plan shown when the batch runs past the allowance. Null until Send.
  const [shortfall, setShortfall] = useState<Plan | null>(null);
  const [sending, setSending] = useState(false);
  // One key per memorandum, minted when the batch is first sent and kept
  // for its retries, so a retry is answered rather than charged twice.
  const [keys, setKeys] = useState<Record<number, string>>({});
  // What each send was asked to accept, kept for a retry.
  const [accepts, setAccepts] = useState<Record<number, number | null>>({});
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [notified, setNotified] = useState<Notified[]>([]);

  async function load() {
    try {
      const [listed, shared] = await Promise.all([api.allMemos(), api.shares()]);
      setMemos(listed.memos);
      setLimit(listed.limit);
      setGrants(shared.grants);
      setAllowance(shared.allowance);
    } catch (err) {
      setError(errorText(err));
    }
  }
  useEffect(() => { load(); }, []);

  const byId = new Map((memos ?? []).map((m) => [m.memo_id, m]));
  const name = (id: number) => {
    const m = byId.get(id);
    return m ? `${m.label} ${m.number}` : `memo ${id}`;
  };

  const shown = memos === null ? [] : (() => {
    const kept = filterMemos(memos, filter);
    return sort.key ? sortRows(kept, sort.key, sort.dir) : kept;
  })();
  const th = (k: MemoKey, label: string) => (
    <th onClick={() => sort.by(k)}>{label}{sort.arrow(k)}</th>
  );

  function tick(m: BatchMemo) {
    const r = toggle(selected, m);
    setSelected(r.selected);
    setRefused(r.refused);
    setShortfall(null);
  }

  const started = outcomes.length > 0;
  const ready = selected.length > 0 && !!to.trim() && affirmed && !sending
    && !!allowance && !allowance.capped && !started;

  function plan(): Plan | null {
    if (!allowance) return null;
    return planBatch(selected, allowance, resendsFor(to, grants));
  }

  /** Send pressed. Within the allowance it goes; past it, it stops and
   *  shows the shortfall - nothing sent, nothing charged. */
  function onSend() {
    const p = plan();
    if (!p) return;
    if (p.paid > 0) { setShortfall(p); return; }
    sendRows(p.rows.map((r) => ({ memo_id: r.memo_id, accept: null })));
  }

  /** One at a time, through the memo page's own route, then one email. */
  async function sendRows(rows: { memo_id: number; accept: number | null }[]) {
    setSending(true);
    setShortfall(null);
    setError("");
    const k = { ...keys };
    const a = { ...accepts };
    for (const r of rows) {
      k[r.memo_id] ??= chargeKey();
      a[r.memo_id] = r.accept;
    }
    setKeys(k);
    setAccepts(a);

    const results: Outcome[] = [];
    for (const r of rows) {
      try {
        const sent = await api.sendShare(r.memo_id, {
          recipient: to.trim(),
          authority_affirmed: affirmed,
          expiry_days: expiry === "default" ? null : Number(expiry),
          idempotency_key: k[r.memo_id],
          accept_overage_cents: r.accept,
          notify: false,
        });
        results.push({ memo_id: r.memo_id, ok: true, grant_id: sent.grant_id,
                       charged_cents: sent.charged_cents,
                       reinstated: sent.reinstated });
      } catch (err) {
        let price: number | undefined;
        if (statusOf(err) === 409) {
          try {
            const body = JSON.parse((err as Error).message);
            if (typeof body.overage_cents === "number") price = body.overage_cents;
          } catch { /* not the price refusal */ }
        }
        results.push({ memo_id: r.memo_id, ok: false, error: errorText(err), price });
      }
      // Shown as they arrive, so five renders are not a blank wait.
      // A retried row keeps its place in the list.
      setOutcomes((prev) => {
        const rows = new Map(prev.map((o) => [o.memo_id, o]));
        for (const x of results) rows.set(x.memo_id, x);
        return [...rows.values()];
      });
    }

    const ids = results.filter((o) => o.ok && o.grant_id).map((o) => o.grant_id!);
    if (ids.length > 0) await notify(ids);
    setSending(false);
    load();
  }

  async function notify(grantIds: string[]) {
    let entry: Notified;
    try {
      const r = await api.notifyShares(grantIds);
      entry = { grantIds, sent: r.sent };
    } catch (err) {
      entry = { grantIds, sent: false, error: errorText(err) };
    }
    setNotified((prev) => [
      ...prev.filter((n) => n.grantIds.join() !== grantIds.join()), entry]);
  }

  async function emailAgain(n: Notified) {
    setSending(true);
    await notify(n.grantIds);
    setSending(false);
  }

  const failed = outcomes.filter((o) => !o.ok);
  // A retry of a share refused at a price it now costs accepts that price,
  // and the button says so before it is pressed.
  const retryCost = failed.reduce((sum, o) =>
    sum + (o.price ?? accepts[o.memo_id] ?? 0), 0);

  function retry() {
    sendRows(failed.map((o) => ({
      memo_id: o.memo_id, accept: o.price ?? accepts[o.memo_id] ?? null })));
  }

  function startAgain() {
    setSelected([]);
    setRefused(null);
    setTo("");
    setAffirmed(false);
    setKeys({});
    setAccepts({});
    setOutcomes([]);
    setNotified([]);
    setShortfall(null);
  }

  return (
    <div>
      <h2>Share a memo</h2>
      <p className="muted">
        Tick up to {MAX_BATCH} memoranda, from any engagement, and send them to
        one person. They get one email with a link to each.{" "}
        <a onClick={onHistory}>History</a> shows what has been shared.
      </p>

      {allowance && <AllowanceLine allowance={allowance} />}
      {error && <p className="error">{error}</p>}
      {memos === null && !error && <Working what="Reading the memoranda" />}

      {memos !== null && memos.length === 0 && (
        <p className="muted">No memoranda have been generated yet.</p>
      )}

      {memos !== null && memos.length > 0 && !started && (
        <>
          <FilterRow filter={filter} onChange={setFilter}
                     placeholder="Filter by name, engagement or number"
                     dateLabel="Generated" />
          <p className="muted small">
            {selected.length} of {MAX_BATCH} ticked.
            {memos.length >= limit && ` Showing the ${limit} most recent.`}
          </p>
          {refused && <p className="warn">{refused}</p>}

          {shown.length === 0 ? (
            <p className="muted">No memorandum matches the filter.</p>
          ) : (
            <table className="docs">
              <thead>
                <tr>
                  <th></th>
                  {th("label", "Memorandum")}{th("engagement", "Engagement")}
                  {th("generated_at", "Generated")}{th("number", "Number")}
                </tr>
              </thead>
              <tbody>
                {shown.map((m) => (
                  <tr key={m.memo_id} className={m.unsaved ? "muted" : undefined}
                      title={m.unsaved
                        ? "Unsaved changes. Save or discard them on the memo first."
                        : undefined}>
                    <td>
                      <input type="checkbox"
                             checked={selected.includes(m.memo_id)}
                             disabled={m.unsaved}
                             onChange={() => tick(m)} />
                    </td>
                    <td>
                      {m.label}
                      {m.subject_name && <div className="muted small">{m.subject_name}</div>}
                      {m.unsaved && <div className="small">unsaved changes</div>}
                    </td>
                    <td>{m.engagement ?? "—"}</td>
                    <td className="ref">{day(m.generated_at)}</td>
                    <td className="ref">{m.number}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="form">
            <label className="row">
              <span>Recipient email</span>
              <input placeholder="name@firm.com" value={to}
                     onChange={(e) => { setTo(e.target.value); setShortfall(null); }} />
            </label>

            <label className="row">
              <span>Access</span>
              <select value={expiry} onChange={(e) => setExpiry(e.target.value)}>
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

            <Authority checked={affirmed} onChange={setAffirmed}
                       several={selected.length > 1} />

            {!shortfall && (
              <div className="form-actions">
                <button onClick={onSend} disabled={!ready}
                        title={!affirmed ? "Confirm you are entitled to share them first."
                                         : undefined}>
                  {selected.length > 1 ? `Send ${selected.length} memoranda` : "Send"}
                </button>
              </div>
            )}
          </div>

          {shortfall && (
            <Shortfall plan={shortfall} name={name}
                       onRemove={(id) => {
                         const next = selected.filter((x) => x !== id);
                         setSelected(next);
                         setRefused(null);
                         const p = allowance
                           ? planBatch(next, allowance, resendsFor(to, grants)) : null;
                         setShortfall(p && p.paid > 0 ? p : null);
                       }}
                       onIncludedOnly={() => sendRows(shortfall.rows
                         .filter((r) => r.kind !== "paid")
                         .map((r) => ({ memo_id: r.memo_id, accept: null })))}
                       onAll={() => sendRows(shortfall.rows.map((r) => ({
                         memo_id: r.memo_id,
                         accept: r.kind === "paid" ? shortfall.unitCents : null })))}
                       onTopUp={onTopUp}
                       onCancel={() => setShortfall(null)} />
          )}
        </>
      )}

      {started && (
        <div className="form">
          <h4>Sent to {to.trim()}</h4>
          <table className="docs">
            <tbody>
              {outcomes.map((o) => (
                <tr key={o.memo_id}>
                  <td>{name(o.memo_id)}</td>
                  <td>
                    {o.ok
                      ? <>{o.reinstated ? "shared again, access restored" : "shared"}
                          {!!o.charged_cents && ` — charged ${money(o.charged_cents)}`}</>
                      : <span className="error">
                          {o.error}
                          {o.price !== undefined
                            && ` Not sent or charged. Sending it costs ${money(o.price)}.`}
                        </span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {sending && <Working what="Sending" />}

          {notified.map((n) => (
            <p key={n.grantIds.join()}
               className={n.sent ? "revision-note" : "warn"}>
              {n.sent
                ? `One email sent with ${n.grantIds.length === 1
                    ? "the link" : `${n.grantIds.length} links`}.`
                : <>The email could not be sent{n.error ? `: ${n.error}` : "."}{" "}
                    The shares stand.{" "}
                    <a onClick={() => !sending && emailAgain(n)}>Email them again</a></>}
            </p>
          ))}

          <div className="form-actions">
            {failed.length > 0 && !sending && (
              <button className="plain" onClick={retry}>
                Retry the {failed.length === 1 ? "one" : failed.length} that failed
                {retryCost > 0 && ` — charges up to ${money(retryCost)}`}
              </button>
            )}
            {!sending && <a className="secondary" onClick={startAgain}>Share more</a>}
            {!sending && <a className="secondary" onClick={onHistory}>History</a>}
          </div>
        </div>
      )}
    </div>
  );
}

/** Past the allowance. Which are included, which would be charged and what
 *  that comes to - and nothing happens until one of the buttons is pressed. */
function Shortfall({ plan, name, onRemove, onIncludedOnly, onAll, onTopUp,
                     onCancel }: {
  plan: Plan;
  name: (id: number) => string;
  onRemove: (id: number) => void;
  onIncludedOnly: () => void;
  onAll: () => void;
  onTopUp: () => void;
  onCancel: () => void;
}) {
  const free = plan.included + plan.resend;
  const kindText = (k: string) =>
    k === "included" ? "included in your plan"
    : k === "resend" ? "already shared with them — sent again, free"
    : plan.unitCents === null ? "past your plan, not priced: cannot be sent"
    : `past your plan — ${money(plan.unitCents)}`;
  return (
    <div className="revision-note">
      <p>
        This batch runs past the shares your plan includes.
        {" "}{plan.included} included, {plan.paid} past it
        {plan.unitCents !== null
          && ` at ${money(plan.unitCents)} each, ${money(plan.totalCents)} in all`}
        {plan.resend > 0 && `, and ${plan.resend} re-sent free`}.
        Nothing has been sent or charged.
      </p>
      <table className="docs">
        <tbody>
          {plan.rows.map((r) => (
            <tr key={r.memo_id}>
              <td>{name(r.memo_id)}</td>
              <td className="small">{kindText(r.kind)}</td>
              <td><a className="secondary" onClick={() => onRemove(r.memo_id)}>Remove</a></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="form-actions">
        {free > 0 && (
          <button className="plain" onClick={onIncludedOnly}>
            Send the {free} included only
          </button>
        )}
        {plan.unitCents !== null && (
          <button className="plain" onClick={onAll}>
            Send all and charge {money(plan.totalCents)}
          </button>
        )}
        <a className="secondary" onClick={onTopUp}>Top up balance</a>
        <a className="secondary" onClick={onCancel}>Cancel</a>
      </div>
    </div>
  );
}
