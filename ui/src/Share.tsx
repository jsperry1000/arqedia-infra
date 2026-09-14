import { useState } from "react";
import { useBackAction } from "./shell";
import { SHAREABLE, GRANTS, GRANT_SCOPE, Inert, NotConnected } from "./mock";

/**
 * Sharing. Who a memorandum has been sent to, what they got, and what they
 * did with it.
 *
 * NOT CONNECTED. There is no sharing endpoint. In the built product this
 * opens from a memorandum's own head rather than from the rail; it is a rail
 * entry here so the flow can be walked without a memo open.
 *
 * Three things the screen has to make true, all from the share specification:
 * a grant carries the rendered memorandum and nothing else, revoking is
 * available in every state including capped, and registration - not delivery -
 * is the line at which a recipient becomes ours to contact.
 */

export function ShareView({ onBack, onViewer }: {
  onBack: () => void;
  onViewer: () => void;
}) {
  useBackAction(onBack);

  const [memoId, setMemoId] = useState(SHAREABLE[0].memo_id);
  const [to, setTo] = useState("");
  const [expiry, setExpiry] = useState("30");

  return (
    <div>
      <h2>Sharing</h2>
      <NotConnected what="Sharing" />

      <h3>Send a memorandum</h3>

      <div className="form">
        <label className="row">
          <span>Which memorandum</span>
          <select value={memoId} onChange={(e) => setMemoId(Number(e.target.value))}>
            {SHAREABLE.map((m) => (
              <option key={m.memo_id} value={m.memo_id}>
                {m.label} &mdash; {m.subject} ({m.generated})
              </option>
            ))}
          </select>
        </label>

        <label className="row">
          <span>Recipient email</span>
          <input placeholder="name@firm.com" value={to}
                 onChange={(e) => setTo(e.target.value)} />
        </label>

        <label className="row">
          <span>Access expires</span>
          <select value={expiry} onChange={(e) => setExpiry(e.target.value)}>
            <option value="14">14 days</option>
            <option value="30">30 days (default)</option>
            <option value="90">90 days</option>
          </select>
        </label>

        <h4>What the recipient gets</h4>
        <table className="docs">
          <tbody>
            {GRANT_SCOPE.map((s) => (
              <tr key={s.what}>
                <td>{s.what}</td>
                <td className="ref" style={{ width: 60 }}>{s.given ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <p className="muted small">
          Sending {SHAREABLE.find((m) => m.memo_id === memoId)?.label} for{" "}
          {SHAREABLE.find((m) => m.memo_id === memoId)?.subject}
          {to ? ` to ${to}` : ""}, expiring in {expiry} days.
        </p>

        <div className="form-actions">
          <Inert what="Sending">Send</Inert>
          <a className="secondary" onClick={onViewer}>
            See what the recipient sees
          </a>
        </div>
      </div>

      <p className="muted small">
        A recipient who only opens the link has no relationship with us &mdash;
        you collected that address and we delivered a file to it. One who
        registers keeps access for six months and has accepted our terms
        directly. Registration is the line, not delivery.
      </p>

      <h3>Outstanding grants</h3>

      <table className="docs">
        <thead>
          <tr>
            <th>Recipient</th><th>Memorandum</th><th>Sent</th>
            <th>First opened</th><th>Opens</th><th>Downloads</th>
            <th>Expires</th><th></th>
          </tr>
        </thead>
        <tbody>
          {GRANTS.map((g) => (
            <tr key={g.to + g.memo}>
              <td>
                {g.to}
                {g.registered && <div className="in-use">registered</div>}
              </td>
              <td className="muted small">{g.memo}</td>
              <td className="ref">{g.sent}</td>
              <td className="ref">{g.opened ?? "\u2014"}</td>
              <td className="ref">{g.opens}</td>
              <td className="ref">{g.downloads}</td>
              <td className="ref">{g.expires}</td>
              <td><Inert what="Revoking">Revoke</Inert></td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="muted small">
        Every grant records who sent it, when it was first opened, every open,
        every download and who revoked it. Downloads carry the viewer's
        identity, so the record says who took a copy.
      </p>

      <p className="muted small">
        Revoking works in every state, including when the account is capped
        &mdash; a tenant locked out for non-payment must still be able to pull a
        memorandum back.
      </p>
    </div>
  );
}
