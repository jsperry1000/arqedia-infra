import type { ConfigColumn } from "./api";

/**
 * The pieces both configuration screens need.
 *
 * `Configure` and `Propose` each grew their own copy of these, and the copies
 * diverged: one minted a column key and the other did not, so a column was
 * stored as `role` rather than `f_vessel_carriers.role` and extraction stopped
 * on every document carrying a table. The fault existed in one screen only,
 * which is exactly what makes two copies expensive.
 *
 * Anything used by both screens belongs here. Anything belonging to one screen
 * alone - the match radios, the acknowledgement, the section pickers - stays
 * where it is.
 */

/** A key from a label. Minted once and never follows the label afterwards:
 *  the key is identity, and identity that moved would orphan everything
 *  already extracted under it. */
export function slugKey(label: string, prefix = ""): string {
  const body = label.toLowerCase().replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return (prefix + (body || "item")).slice(0, 64);
}

/** A field's key. Underscores rather than dashes, which is the shape the
 *  editor mints server-side; the two must agree or a screen sending its own
 *  key creates a second field meaning the same thing. */
export function fieldKey(label: string): string {
  return slugKey(label, "f_").replace(/-/g, "_");
}

export function KeyLine({ value }: { value: string }) {
  return (
    <div className="keyline">
      <span className="muted small">Identity</span> <code>{value}</code>
      <div className="muted small">
        Fixed once saved. Renaming the label afterwards changes nothing that
        was already extracted.
      </div>
    </div>
  );
}

/**
 * The columns of a table fact.
 *
 * NOTE ON KEYS. A column already saved carries one, and it is sent back
 * untouched: `_save_columns` rewrites a table's columns whole, so a column
 * returned without its key is recreated under a new one and everything
 * extracted under the old key stops resolving. A NEW column carries no key at
 * all - the editor mints `<table>.<column>` server-side, and a screen that
 * invents its own gets it wrong.
 */
export function ColumnEditor({ columns, onChange, note }: {
  columns: ConfigColumn[];
  onChange: (next: ConfigColumn[]) => void;
  note?: string;
}) {
  const named = columns.filter((c) => (c.label ?? "").trim()).length;
  const added = columns.filter((c) => !c.key).length;

  return (
    <div className="columns">
      <h4>Columns</h4>
      <p className="muted small">
        {note ?? "What each row holds. A name means nothing without the things"
          + " beside it \u2014 a buyer without its country, a figure without"
          + " its period."}
      </p>

      {columns.map((c, i) => (
        <div className="column-row" key={c.key ?? "new-" + i}>
          <input placeholder="Column" value={c.label ?? ""}
            onChange={(e) => {
              const next = [...columns];
              next[i] = { ...c, label: e.target.value };
              onChange(next);
            }} />
          <input placeholder="What it holds" value={c.description ?? ""}
            onChange={(e) => {
              const next = [...columns];
              next[i] = { ...c, description: e.target.value };
              onChange(next);
            }} />
          <a className="small"
             onClick={() => onChange(columns.filter((_, j) => j !== i))}>
            Remove
          </a>
        </div>
      ))}

      <a className="small" onClick={() => onChange([...columns,
        { label: "", type: "text", description: "" } as ConfigColumn])}>
        Add a column
      </a>

      {named === 0 && (
        <p className="warn small">
          A table needs at least one column, or it holds nothing.
        </p>
      )}

      {added > 0 && (
        <p className="warn small">
          A new column is a new fact. It will be empty on every document
          already filed, and the only way to fill it is to file those
          documents again.
        </p>
      )}
    </div>
  );
}

/** Whether a table is fit to save: at least one column with a name. */
export function columnsReady(columns: ConfigColumn[]): boolean {
  return columns.filter((c) => (c.label ?? "").trim()).length > 0;
}

/** Columns as the editor wants them: blank rows dropped, an existing key
 *  preserved, a new one omitted so the editor mints it. */
export function columnsForSave(columns: ConfigColumn[]) {
  return columns
    .filter((c) => (c.label ?? "").trim())
    .map((c) => ({
      key: c.key || undefined,
      label: (c.label ?? "").trim(),
      type: c.type || "text",
      description: c.description ?? "",
    }));
}

/**
 * How a document is read: the mode, and whether OCR is forced.
 *
 * Only the editor offered these. A document created from a report took the
 * defaults with no way to say otherwise, so a scanned ledger proposed from a
 * client's own memorandum was set to be read as prose and its figures were
 * whatever the text layer happened to hold.
 */
export function ReadModeControls({ readMode, alwaysOcr, onChange }: {
  readMode: string;
  alwaysOcr: boolean;
  onChange: (next: { read_mode: string; always_ocr: boolean }) => void;
}) {
  return (
    <>
      <label className="row">
        <span>Read as</span>
        <select value={readMode}
                onChange={(e) => onChange({
                  read_mode: e.target.value, always_ocr: alwaysOcr })}>
          <option value="text">Prose</option>
          <option value="forms">Forms and tables</option>
          <option value="expense">Invoices</option>
        </select>
      </label>

      <label className="inline-check">
        <input type="checkbox" checked={alwaysOcr}
               onChange={(e) => onChange({
                 read_mode: readMode, always_ocr: e.target.checked })} />
        Always read by OCR, even where the file carries text
      </label>
      <p className="muted small">
        Worth setting where a garbled text layer would corrupt figures
        &mdash; statements and ledgers, chiefly.
      </p>
    </>
  );
}

/** What the system reads to tell one document from another. Said the same
 *  way on both screens, because it is the same warning. */
export const RECOGNISE_NOTE =
  "This is what the system reads to tell this document from every other "
  + "kind. Getting it wrong sends future uploads to the wrong place quietly.";
