"""Remove a document before it is filed.

Four files, eleven edits. Every edit asserts its anchor first, so a file that
has moved on since it was read fails loudly rather than being patched wrongly.
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
    """Substitute exactly one occurrence, or stop."""
    found = re.findall(pattern, text, flags)
    if len(found) != 1:
        sys.exit("ANCHOR %s matched %d times, expected 1" % (label, len(found)))
    return re.sub(pattern, lambda _m: replacement, text, count=1, flags=flags)


# --- lambda/api/app.py -----------------------------------------------------

APP = "lambda/api/app.py"
s = read(APP)

s = once(
    s,
    r"  POST /documents/\{document_id\}/active   include or exclude from future memos\n",
    "  POST /documents/{document_id}/active   include or exclude from future memos\n"
    "  DELETE /documents/{document_id}         discard one not yet filed\n",
    "app.py route list",
)

REMOVE_FN = '''def remove_document(tenant_id, document_id):
    """Discard a document that has not been filed.

    The only destructive action outside account deletion, and deliberately so.
    A file chosen by mistake may belong to another client or to nobody's
    business but the uploader's, and marking it rejected would leave it in this
    tenant's storage indefinitely. Both objects go - the upload and the
    analysed envelope holding its text - and then the row.

    Refused once filing has started. A document in `reading` has a Textract job
    in flight that would write back to a row no longer there, and a filed one
    has been extracted and paid for. Neither is a misclick.
    """
    row = _sql("SELECT s3_key, state FROM document "
               "WHERE tenant_id = :t AND document_id = :d",
               [_p("t", tenant_id), _p("d", document_id)])
    records = row.get("records", [])
    if not records:
        return None

    s3_key = _col(records[0], 0)
    state = _col(records[0], 1)
    if state != "analysed":
        return {"refused": state}

    # Storage first. A failure here leaves the row intact and the card on
    # screen, which is retryable. The reverse orphans an object nobody can see.
    # Deleting a key that is not there is not an error in S3, so the second
    # call is safe whether or not the normalizer got that far.
    _s3.delete_object(Bucket=DOCS_BUCKET, Key=s3_key)
    _s3.delete_object(Bucket=REVIEW_BUCKET, Key=s3_key + ".analysed.json")

    _sql("DELETE FROM document WHERE tenant_id = :t AND document_id = :d",
         [_p("t", tenant_id), _p("d", document_id)])
    return {"removed": document_id}


'''

s = once(
    s,
    r"\ndef list_documents\(tenant_id, engagement\):",
    "\n" + REMOVE_FN + "def list_documents(tenant_id, engagement):",
    "app.py insertion point",
)

ROUTER = '''        if route == "DELETE /documents/{document_id}":
            removing = int((event.get("pathParameters") or {})
                           .get("document_id"))
            outcome = remove_document(tenant_id, removing)
            if outcome is None:
                return _reply(404, {"error": "no such document"})
            if "refused" in outcome:
                return _reply(409, {"error": outcome["refused"]})
            return _reply(200, outcome)

'''

s = once(
    s,
    r'        if route == "GET /engagements/\{id\}/pending":',
    ROUTER + '        if route == "GET /engagements/{id}/pending":',
    "app.py router",
)

write(APP, s)
print("patched " + APP)


# --- api.tf ----------------------------------------------------------------

TF = "api.tf"
s = read(TF)

s = once(
    s,
    r'actions   = \["s3:PutObject"\]',
    'actions   = ["s3:PutObject", "s3:DeleteObject"]',
    "api.tf docs bucket permission",
)

s = once(
    s,
    r'actions   = \["s3:GetObject", "s3:PutObject"\]\n(\s*)resources = '
    r'\["\$\{aws_s3_bucket\.data\["review"\]\.arn\}/\*"\]',
    'actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]\n'
    '    resources = ["${aws_s3_bucket.data["review"].arn}/*"]',
    "api.tf review bucket permission",
)

s = once(
    s,
    r'    "GET /document-types",\n',
    '    "GET /document-types",\n    "DELETE /documents/{document_id}",\n',
    "api.tf route registration",
)

write(TF, s)
print("patched " + TF)


# --- ui/src/api.ts ---------------------------------------------------------

API = "ui/src/api.ts"
s = read(API)

s = once(
    s,
    r"  documentValues: \(documentId: number\): Promise<DocumentDetail> =>",
    "  // Discard something picked by mistake, before it is filed. The upload\n"
    "  // and what was read from it both go, and so does the row. Refused once\n"
    "  // filing has started.\n"
    "  removeDocument: (documentId: number) =>\n"
    "    call(`/documents/${documentId}`, { method: \"DELETE\" }),\n"
    "\n"
    "  documentValues: (documentId: number): Promise<DocumentDetail> =>",
    "api.ts insertion point",
)

write(API, s)
print("patched " + API)


# --- ui/src/Review.tsx -----------------------------------------------------

RV = "ui/src/Review.tsx"
s = read(RV)

REMOVE_HANDLER = '''  // Picking a file uploads it, so there is no cancelling before it exists.
  // Removing is the cancel, and it is final: nothing has been extracted and
  // nothing has been charged, so there is nothing worth keeping.
  async function remove(p: Pending) {
    if (busy || p.state === "reading") return;
    setError("");
    setBusy(`Removing ${p.filename}`);
    try {
      await api.removeDocument(p.document_id);
    } catch (err) {
      setError(String((err as Error)?.message ?? err));
    }
    setChoices((prev) => {
      const next = { ...prev };
      delete next[p.document_id];
      return next;
    });
    setBusy("");
    refresh();
  }

'''

s = once(
    s,
    r"  async function fileAll\(\) \{",
    REMOVE_HANDLER + "  async function fileAll() {",
    "Review.tsx handler insertion point",
)

# The checkbox promised a decision the File button would not carry out: with
# every box clear the button was disabled, so the one path to rejection was
# shut in exactly the case that needed it.
NEW_HEAD = '''<strong>{p.filename}</strong>
                  <span className="muted">{p.pages ?? "?"} pages</span>
                  <button
                    className="secondary"
                    disabled={!!busy || p.state === "reading"}
                    onClick={() => remove(p)}
                    title={p.state === "reading"
                      ? "Being read. It can no longer be removed here."
                      : "Remove. The file and what was read from it both go."}
                  >
                    Remove
                  </button>'''

s = once(
    s,
    r"<label>\s*<input\s+type=\"checkbox\"\s+checked=\{choice\.include\}"
    r".*?</label>\s*<span className=\"muted\">\{p\.pages \?\? \"\?\"\} pages</span>",
    NEW_HEAD,
    "Review.tsx pending card head",
    re.S,
)

s = once(
    s,
    r"      include: choices\[p\.document_id\]\?\.include \?\? true,",
    "      include: true,",
    "Review.tsx filing decision",
)

s = once(
    s,
    r"  const includedCount = pending\.filter\(\s*"
    r"\(p\) => choices\[p\.document_id\]\?\.include \?\? true\)\.length;\n\n",
    "",
    "Review.tsx includedCount definition",
    re.S,
)

s = once(
    s,
    r"<button onClick=\{fileAll\} disabled=\{!!busy \|\| includedCount === 0\}>\s*"
    r"File \{includedCount\} \{includedCount === 1 \? \"document\" : \"documents\"\}\s*"
    r"</button>",
    '<button onClick={fileAll} disabled={!!busy || pending.length === 0}>\n'
    '            File {pending.length}{" "}\n'
    '            {pending.length === 1 ? "document" : "documents"}\n'
    '          </button>',
    "Review.tsx file button",
    re.S,
)

write(RV, s)
print("patched " + RV)
print("all four files patched")
