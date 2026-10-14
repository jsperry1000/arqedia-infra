import { useEffect, useState } from "react";
import { useBackAction, Working } from "./shell";
import { sharedWithMe, statusOf, type ViewerPage, type ViewerShare } from "./api";

/**
 * Shared with me (feature/viewer-tenant-integration). What other firms have
 * shared with this person's own address, seen from the application rather
 * than /viewer.
 *
 * NOT SHARING. Sharing, on the rail above, is everything this workspace
 * sends. This is what was sent TO the person signed in, by anybody - the same
 * grants they would see as a viewer, and nothing else: no other colleague's,
 * and nothing this workspace sent out.
 *
 * Reached only once the workspace account is linked to the viewer account
 * for the same address - at signup, or on the first visit (the rail item is
 * hidden until then). The memorandum is the watermarked PDF, as on /viewer.
 */

const day = (iso: string | null | undefined) => (iso ?? "").slice(0, 10);

export function SharedWithMeView({ onBack }: { onBack: () => void }) {
  useBackAction(onBack);

  const [shares, setShares] = useState<ViewerShare[] | null>(null);
  const [linked, setLinked] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<ViewerPage | null>(null);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    sharedWithMe.list().then((r) => {
      setLinked(r.linked);
      setShares(r.shares);
    }).catch((err) => setError(String((err as Error).message)));
  }, []);

  async function show(grantId: string) {
    setBusy(grantId);
    setError("");
    try {
      setOpen(await sharedWithMe.open(grantId));
    } catch (err) {
      setError(statusOf(err) === 404
        ? "That memorandum is no longer shared with you."
        : String((err as Error).message));
    } finally {
      setBusy("");
    }
  }

  async function download(grantId: string) {
    setBusy("download");
    setError("");
    try {
      const { download_url } = await sharedWithMe.download(grantId);
      window.location.assign(download_url);
    } catch (err) {
      setError(String((err as Error).message));
    } finally {
      setBusy("");
    }
  }

  if (open) {
    return (
      <div>
        <h2>{open.memo_label}</h2>
        <p className="muted">
          {open.subject ? `${open.subject} · ` : ""}shared by {open.tenant_name}
          {" · "}access ends {day(open.expires_at)}
        </p>
        <div className="form-actions">
          <button className="plain" onClick={() => download(open.grant_id)}
                  disabled={busy === "download"}>
            {busy === "download" ? "Preparing…" : "Download"}
          </button>
          <a className="secondary" onClick={() => setOpen(null)}>All shared with me</a>
        </div>
        {error && <p className="error">{error}</p>}
        <iframe className="viewer-frame" src={open.view_url}
                title={`${open.memo_label} — ${open.subject ?? ""}`} />
        <p className="muted small">
          Shared with {open.recipient_email}. Every page carries that address,
          and a downloaded copy also carries the time it was taken.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2>Shared with me</h2>
      <p className="muted">
        Memoranda other firms have shared with your address. What this
        workspace sends is under Sharing.
      </p>
      {error && <p className="error">{error}</p>}
      {shares === null && !error && <Working what="Reading what has been shared with you" />}
      {shares !== null && !linked && (
        <p className="muted">Nothing has been shared with your address.</p>
      )}
      {shares !== null && linked && shares.length === 0 && (
        <p className="muted">Nothing is shared with you at the moment.</p>
      )}
      {shares !== null && shares.length > 0 && (
        <table className="docs">
          <thead>
            <tr><th>Memorandum</th><th>Shared by</th><th>Sent</th><th>Access</th></tr>
          </thead>
          <tbody>
            {shares.map((s) => (
              <tr key={s.grant_id}>
                <td>
                  {s.expired ? s.memo_label
                    : <a onClick={() => busy ? undefined : show(s.grant_id)}>{s.memo_label}</a>}
                  {s.subject && <div className="muted small">{s.subject}</div>}
                </td>
                <td>{s.tenant_name}</td>
                <td className="ref">{day(s.sent_at)}</td>
                <td className="ref">
                  {s.expired ? <span className="warn">ended {day(s.expires_at)}</span>
                             : <>until {day(s.expires_at)}</>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
