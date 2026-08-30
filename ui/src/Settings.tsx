import { useEffect, useState } from "react";
import { api, type Settings } from "./api";

/**
 * Settings. Branding today; seats, plan and billing will join it.
 *
 * The controls are shown on every plan, disabled with the reason stated where
 * the plan does not include them. Telling somebody what a paid plan would give
 * them is more useful than an empty screen, and a good deal more honest than
 * hiding it.
 */

const PLATFORM = { deep: "#002561", mid: "#278ACA", highlight: "#FFDD00" };

const SWATCHES: {
  key: "deep" | "mid" | "highlight";
  label: string;
  note: string;
}[] = [
  { key: "deep", label: "Deep", note: "Masthead, headings and table headers" },
  { key: "mid", label: "Mid", note: "Citations and the subject line" },
  { key: "highlight", label: "Highlight", note: "The rule and gap markers" },
];

export function SettingsView({ onBack }: { onBack: () => void }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [busy, setBusy] = useState("");
  const [previewUrl, setPreviewUrl] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => { api.settings().then(setSettings); }, []);

  function message(err: unknown) {
    let text = String((err as Error)?.message ?? err);
    try {
      text = JSON.parse(text).error ?? text;
    } catch { /* not JSON; show it as it came */ }
    return text;
  }

  async function setColour(key: "deep" | "mid" | "highlight", value: string | null) {
    if (!settings) return;
    setSettings({ ...settings, [key]: value });
    setError("");
    setSaved(false);
    try {
      setSettings(await api.saveSettings({ [key]: value }));
      setSaved(true);
    } catch (err) {
      setError(message(err));
      setSettings(await api.settings());
    }
  }

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy("Uploading");
    setError("");
    setSaved(false);
    try {
      setSettings(await api.uploadLogo(files[0]));
      setSaved(true);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  async function preview() {
    setBusy("Rendering a sample");
    setError("");
    try {
      const { url } = await api.previewBranding();
      setPreviewUrl(url);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy("");
    }
  }

  async function removeLogo() {
    setError("");
    try {
      setSettings(await api.saveSettings({ logo_key: null }));
      setSaved(true);
    } catch (err) {
      setError(message(err));
    }
  }

  if (!settings) return <p className="muted">Loading&hellip;</p>;

  const locked = !settings.may_brand;

  return (
    <div>
      <a onClick={onBack} className="back">Back</a>
      <h2>Settings</h2>

      <p className="muted">
        {settings.name} &middot; {settings.plan} plan
      </p>

      {locked && (
        <p className="revision-note">
          Memos carry ARQEDIA's mark and colours on the Base plan. Business and
          Enterprise let you set your own; Enterprise also removes the ARQEDIA
          line from the footer.
        </p>
      )}

      {error && <p className="error">{error}</p>}
      {busy && <p className="busy">{busy}&hellip;</p>}
      {saved && !error && !busy && <p className="saved">Saved.</p>}

      <h3>Logo</h3>
      <p className="muted small">
        PNG or JPEG. It renders about 22 pixels tall at the top of every memo,
        so a wide mark reads better than a tall one.
      </p>

      <div className="logo-row">
        <div className="logo-preview">
          {settings.logo_url ? (
            <img src={settings.logo_url} alt="Your logo" />
          ) : (
            <span className="muted small">ARQEDIA default</span>
          )}
        </div>

        <div className="logo-actions">
          <input type="file" accept="image/png,image/jpeg" disabled={locked}
                 onChange={(e) => upload(e.target.files)} />
          {settings.logo_key && !locked && (
            <a className="secondary" onClick={removeLogo}>
              Use the ARQEDIA mark instead
            </a>
          )}
        </div>
      </div>

      <h3>Colours</h3>

      <table className="docs">
        <tbody>
          {SWATCHES.map(({ key, label, note }) => {
            const value = settings[key] ?? PLATFORM[key];
            const isDefault = !settings[key];
            return (
              <tr key={key}>
                <td style={{ width: 90 }}>
                  <input
                    type="color"
                    className="swatch"
                    value={value}
                    disabled={locked}
                    onChange={(e) => setColour(key, e.target.value)}
                  />
                </td>
                <td>
                  <strong>{label}</strong>
                  <div className="muted small">{note}</div>
                </td>
                <td className="ref">{value}{isDefault ? " (default)" : ""}</td>
                <td>
                  {!isDefault && !locked && (
                    <a className="small" onClick={() => setColour(key, null)}>
                      Reset
                    </a>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <h3>Preview</h3>
      <p className="muted small">
        A colour or logo applies to memos rendered from now on. Existing PDFs
        are unchanged &mdash; they are records of what was issued, and a
        setting changed today does not rewrite a document already sent. This
        renders a sample so you can see the effect before the next memo.
      </p>

      <button onClick={preview} disabled={!!busy}>
        {busy ? "Rendering\u2026" : "Render a sample memo"}
      </button>

      {previewUrl && (
        <>
          <iframe className="preview-pdf" src={previewUrl} title="Sample memo" />
          <p>
            <a href={previewUrl} target="_blank" rel="noreferrer">
              Open the sample in a new tab
            </a>
          </p>
        </>
      )}
    </div>
  );
}
