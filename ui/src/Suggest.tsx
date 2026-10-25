import { useState } from "react";
import { useLocation } from "react-router-dom";
import { api } from "./api";

/** A refusal the server wrote to be read by a person, unwrapped from the
 *  {"error": "..."} it travels in. */
function message(err: unknown) {
  const text = String((err as Error)?.message ?? err);
  try { return JSON.parse(text).error ?? text; } catch { return text; }
}

const MAX = 5000;

/**
 * We want your suggestions (25 October 2026), opened from the foot of the
 * rail. Any seat.
 *
 * Send emails it to info@arqedia.com, with the sender as its Reply-To, and
 * emails the sender a note saying it arrived - only once it has: a send
 * that fails says so here, keeps what was typed, and thanks nobody.
 *
 * The screen it was written on travels with it, because "this" in a
 * suggestion usually means the page behind the drawer.
 *
 * Composed from the drawer and form the Workspaces tab's delete uses. No
 * new CSS.
 */
export function SuggestionPanel({ onClose }: { onClose: () => void }) {
  const location = useLocation();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<{ thanked: boolean } | null>(null);

  async function send() {
    if (busy || !text.trim()) return;
    setBusy(true);
    setError("");
    try {
      const out = await api.suggest(text, location.pathname);
      setDone({ thanked: out.thanked });
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <div className="panel narrow" onClick={(e) => e.stopPropagation()}
           onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
        <a className="panel-close" onClick={onClose}>Close</a>
        <div className="form">
          <h4>We want your suggestions</h4>

          {done ? (
            <>
              <p>Thank you &mdash; it has reached the ARQEDIA team.</p>
              <p className="muted small">
                {done.thanked
                  ? "A note saying so is on its way to your email. We value "
                    + "your input, and we will respond as soon as we can."
                  : "We value your input, and we will respond as soon as we "
                    + "can."}
              </p>
              <div className="form-actions">
                <button onClick={onClose}>Close</button>
              </div>
            </>
          ) : (
            <>
              <p className="muted small">
                What would make ARQEDIA better for you? A missing feature,
                something confusing, something that did not work &mdash; it
                goes straight to the people building it, and we will respond
                as soon as we can.
              </p>

              <label className="row">
                <span>Your suggestion</span>
                <textarea value={text} rows={9} maxLength={MAX} autoFocus
                          disabled={busy}
                          onChange={(e) => setText(e.target.value)} />
              </label>

              {error && <p className="error">{error}</p>}

              <div className="form-actions">
                <button disabled={busy || !text.trim()} onClick={send}>
                  {busy ? "Sending…" : "Send"}
                </button>
                <a className="secondary" onClick={onClose}>Cancel</a>
                <span className="muted small">
                  {text.length > MAX - 500
                    ? `${MAX - text.length} characters left.`
                    : "Sent from your address, so we can reply to you."}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
