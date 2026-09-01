"""Let a person read a document before naming it.

A card on the review screen asks what a document is and gives no way to look at
it. The filename is not an answer when four cards share one, and a description
written by a model is a summary, not the thing itself.

document_passage already returns the text of one page. It reads
s3_key + ".normalized.json", which is wrong twice for this: a part's envelope
carries a part suffix, and a document that has not been filed has no normalized
envelope at all - only the analysed one. Both are fixed here.

Run from c:\\terraform\\arqedia.
"""

import io
import re
import sys


def read(path):
    with io.open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def once(text, pattern, replacement, label, flags=0):
    found = re.findall(pattern, text, flags)
    if len(found) != 1:
        sys.exit("ANCHOR %s matched %d times, expected 1" % (label, len(found)))
    return re.sub(pattern, lambda _m: replacement, text, count=1, flags=flags)


# --- lambda/api/app.py ------------------------------------------------------

API = "lambda/api/app.py"
s = read(API)

s = once(
    s,
    r'''    row = _sql\(
        "SELECT s3_key, filename, page_count FROM document "
        "WHERE tenant_id = :t AND document_id = :d",
        \[_p\("t", tenant_id\), _p\("d", int\(document_id\)\)\],
    \)
    records = row\.get\("records", \[\]\)
    if not records:
        return None

    s3_key = _col\(records\[0\], 0\)
    envelope = json\.loads\(
        _s3\.get_object\(Bucket=REVIEW_BUCKET,
                       Key=s3_key \+ "\.normalized\.json"\)\["Body"\]\.read\(\)
        \.decode\("utf-8"\)\)''',
    '''    row = _sql(
        "SELECT s3_key, filename, page_count, state, page_from, part_index "
        "FROM document WHERE tenant_id = :t AND document_id = :d",
        [_p("t", tenant_id), _p("d", int(document_id))],
    )
    records = row.get("records", [])
    if not records:
        return None

    s3_key = _col(records[0], 0)
    state = _col(records[0], 3)
    suffix = _envelope_suffix(_col(records[0], 4), _col(records[0], 5))

    # A document waiting to be filed has only the analysed envelope. Reading
    # before filing is the point: it is how a person decides what the thing is
    # without paying to find out.
    if state != "filed":
        suffix = suffix.replace(".analysed.", ".analysed.")
    else:
        suffix = suffix.replace(".analysed.", ".normalized.")

    envelope = json.loads(
        _s3.get_object(Bucket=REVIEW_BUCKET,
                       Key=s3_key + suffix)["Body"].read()
        .decode("utf-8"))''',
    "passage envelope key",
)

write(API, s)
print("patched " + API)


# --- ui/src/Review.tsx ------------------------------------------------------

RV = "ui/src/Review.tsx"
s = read(RV)

s = once(
    s,
    r"  type DocumentDetail,\n\} from \"\./api\";",
    "  type DocumentDetail,\n  type Passage,\n} from \"./api\";",
    "Review.tsx import",
)

s = once(
    s,
    r"  const \[detail, setDetail\] = useState<DocumentDetail \| null>\(null\);",
    "  const [detail, setDetail] = useState<DocumentDetail | null>(null);\n"
    "  const [passage, setPassage] = useState<Passage | null>(null);\n"
    "  const [bounds, setBounds] = useState<[number, number]>([1, 1]);",
    "Review.tsx state",
)

VIEW_HANDLER = '''  // What the system actually read, page by page. The filename is not an
  // answer when four cards carry the same one, and a description written by a
  // model is a summary rather than the thing itself.
  async function view(p: Pending, unit: number) {
    setError("");
    setBounds([p.page_from ?? 1, p.page_to ?? p.pages ?? 1]);
    try {
      setPassage(await api.passage(p.document_id, unit));
    } catch (err) {
      setError(String((err as Error)?.message ?? err));
    }
  }

'''

s = once(
    s,
    r"  // Picking a file uploads it, so there is no cancelling before it exists\.",
    VIEW_HANDLER
    + "  // Picking a file uploads it, so there is no cancelling before it exists.",
    "Review.tsx view handler",
)

s = once(
    s,
    r'''                  <button
                    className="secondary"
                    disabled=\{!!busy \|\| p\.state === "reading"\}
                    onClick=\{\(\) => remove\(p\)\}''',
    '''                  <button
                    className="secondary"
                    disabled={p.state === "reading"}
                    onClick={() => view(p, p.page_from ?? 1)}
                    title="Read what the system read, before naming it."
                  >
                    View
                  </button>
                  <button
                    className="secondary"
                    disabled={!!busy || p.state === "reading"}
                    onClick={() => remove(p)}''',
    "Review.tsx view button",
)

s = once(
    s,
    r"      \{detail && <ValuePanel detail=\{detail\} onClose=\{\(\) => setDetail\(null\)\} />\}",
    '''      {detail && <ValuePanel detail={detail} onClose={() => setDetail(null)} />}

      {passage && (
        <PassagePanel
          passage={passage}
          bounds={bounds}
          onGo={(unit) => api.passage(passage.document_id, unit)
            .then(setPassage)}
          onClose={() => setPassage(null)}
        />
      )}''',
    "Review.tsx panel mount",
)

PANEL = '''

/** One page of a document, as it was read.

    Paging is held inside the part's own range. A part covering pages 21 to 30
    is a document in its own right to the person reading it, and letting the
    arrows wander into a neighbouring part would show them somebody else's
    document under this one's heading. */
function PassagePanel({ passage, bounds, onGo, onClose }: {
  passage: Passage;
  bounds: [number, number];
  onGo: (unit: number) => void;
  onClose: () => void;
}) {
  const [first, last] = bounds;
  const here = passage.unit ?? first;

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <aside className="panel" onClick={(e) => e.stopPropagation()}>
        <a onClick={onClose} className="panel-close">Close</a>
        <h3>{passage.filename}</h3>
        <p className="muted">
          {passage.unit_kind} {here}
          {passage.unit_label ? ` \\u2014 ${passage.unit_label}` : ""}
          {first !== last ? ` of ${first}\\u2013${last}` : ""}
        </p>

        <div className="filters">
          <button
            className="secondary"
            disabled={here <= first}
            onClick={() => onGo(here - 1)}
          >
            Previous
          </button>
          <button
            className="secondary"
            disabled={here >= last}
            onClick={() => onGo(here + 1)}
          >
            Next
          </button>
          <a href={passage.source_url} target="_blank" rel="noreferrer">
            Open the file
          </a>
        </div>

        <pre className="passage">{passage.text}</pre>
      </aside>
    </div>
  );
}
'''

s = once(s, r"\n$", PANEL, "Review.tsx panel component")

write(RV, s)
print("patched " + RV)


# --- ui/src/index.css -------------------------------------------------------

CSS = "ui/src/index.css"
s = read(CSS)

s = s + '''
/* A page of source text. Preformatted because the layout of a statement or a
   table is part of what it says, and reflowing it would misrepresent what was
   read. */
.passage {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.85rem;
  line-height: 1.5;
  background: #f7f9fc;
  border: 1px solid #dde3ec;
  border-radius: 4px;
  padding: 0.75rem;
  max-height: 60vh;
  overflow-y: auto;
}
'''

write(CSS, s)
print("patched " + CSS)
print("all three files patched")
