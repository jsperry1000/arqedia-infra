/**
 * The front door (UX-14). Shown after signing in, before any editor: what
 * the product does, the order of work, and what a filing costs.
 *
 * DRAFT COPY, taken from docs/backlog-items/ARQEDIA_UI_GUIDE_DRAFT.md, which
 * has had no product review. The page itself is routed and works.
 */
export function WelcomeView({ onStart }: { onStart: () => void }) {
  return (
    <div>
      <p className="muted small">Draft copy</p>
      <h2>Welcome to ARQEDIA</h2>
      <p>
        ARQEDIA reads the documents in a client file against the facts you
        define, and writes your memoranda from what it finds.
      </p>

      <h3>The order of work</h3>
      <ol>
        <li>
          <strong>Configure.</strong> Say which facts you rely on, which
          documents each is found in, and the sections of each memorandum.
        </li>
        <li>
          <strong>Publish.</strong> A draft reaches nothing. Publishing makes
          it the configuration documents are read against.
        </li>
        <li>
          <strong>Upload.</strong> Now, and not before. Each document is read
          once, against the configuration that is live when you file it.
        </li>
      </ol>
      <p className="muted small">
        Get the facts and their wording right before you upload. A fact added
        later is empty on every document already filed, and the only way to
        fill it is to upload that document again.
      </p>

      <h3>What a filing costs</h3>
      <p>A filing is charged at $0.25 per document.</p>

      <div className="form-actions">
        <a className="start-pill" onClick={onStart}>Get started</a>
        <a href="https://arqedia.com" target="_blank" rel="noreferrer">
          Purchase ARQEDIA
        </a>
      </div>
    </div>
  );
}
