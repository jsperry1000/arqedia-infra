import { VIEWER_MEMO as M, TENANT_PALETTE as T, Inert } from "./mock";

/**
 * The viewer. What a recipient sees: one memorandum, no rail, no Back, no
 * product around it beyond what is needed to download it and to register.
 *
 * NOT CONNECTED. A real viewer is served from cache on its own route, outside
 * the signed-in shell, and never touches the database. This renders inside the
 * application so the flow can be walked.
 *
 * THIS IS THE ONE SCREEN WHERE BOTH PALETTES MEET, and it is why it is worth
 * mocking. The memorandum wears the TENANT's four colours - deep, mid,
 * highlight, light - because it is their output. The bar above it wears
 * ARQEDIA's, because it is our product. Nowhere else in the application does a
 * tenant colour appear at all.
 */

export function ViewerView({ onBack }: { onBack: () => void }) {
  return (
    <div className="viewer">
      <div className="viewer-bar">
        <strong>ARQEDIA</strong>
        <span className="muted small">
          Shared by {M.preparedBy} &middot; access expires {M.expires}
        </span>
        <span className="viewer-actions">
          <Inert what="Download">Download</Inert>
          <Inert what="Registering">Register to keep access</Inert>
          <a className="secondary" onClick={onBack}>Leave the viewer</a>
        </span>
      </div>

      <div className="memo doc" style={{ margin: "24px auto" }}>
        <div className="doc-h1" style={{ borderBottomColor: T.deep, color: T.deep }}>
          {M.label}
        </div>

        <table>
          <tbody>
            <tr><td className="muted">Subject</td><td>{M.subject}</td></tr>
            <tr><td className="muted">Prepared by</td><td>{M.preparedBy}</td></tr>
            <tr><td className="muted">Generated</td><td>{M.generated}</td></tr>
            <tr><td className="muted">Template</td><td>{M.label}, revision {M.revision}</td></tr>
          </tbody>
        </table>

        {M.sections.map((s) => (
          <div key={s.numeral}>
            <div className="doc-h2"
                 style={{ background: T.deep, color: "#fff", display: "inline-block",
                          padding: "6px 12px", border: 0, marginTop: 28 }}>
              {s.numeral}. {s.title}
            </div>

            {s.paragraphs.map((p, i) => (
              <p key={i}>
                {p.text}{" "}
                <em style={{ color: T.mid }}>{p.cite}</em>
              </p>
            ))}

            <p>
              <span style={{ background: T.light, color: T.deep, padding: "3px 10px",
                             borderRadius: 999, fontSize: 13 }}>
                {s.pill}
              </span>
            </p>
            <p>{s.after}</p>

            <table style={{ marginTop: 18 }}>
              <thead>
                <tr style={{ borderBottom: `2px solid ${T.highlight}` }}>
                  <th style={{ color: T.deep }}>Facility</th>
                  <th style={{ color: T.deep }}>Drawn</th>
                  <th style={{ color: T.deep }}>Committed</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Senior revolving</td><td>USD 24.6m</td><td>USD 30.0m</td></tr>
                <tr><td>Term</td><td>Not disclosed</td><td>Not disclosed</td></tr>
              </tbody>
            </table>
          </div>
        ))}
      </div>

      <p className="muted small viewer-note">
        The memorandum above carries the tenant&rsquo;s four colours &mdash; deep
        on the headings, mid on citations, highlight on the table rule, light on
        the pill. The bar at the top is ARQEDIA&rsquo;s. This is the only screen
        where the two meet; the application itself uses none of the
        tenant&rsquo;s palette. The colours here are a stand-in, chosen to make
        the boundary visible.
      </p>
    </div>
  );
}
