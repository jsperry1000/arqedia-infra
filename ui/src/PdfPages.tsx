import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy } from "pdfjs-dist";
import { api } from "./api";
import type { Source } from "./footnotefacts";
import { pageAlt, pageFileName, pageScale } from "./pdfimage";

/**
 * Choosing the pages of a PDF that go into a memo (29 October 2026). See
 * pdfimage.ts for why a page goes in as an image.
 *
 * FROM A SOURCE OF THE MEMO, OR FROM A FILE. The memo's own PDFs first - the
 * evidence it was written from - read through the same signed link "Open the
 * original document" uses; and any PDF off the person's own computer, which
 * is read here and never uploaded as a PDF. A PDF dropped or pasted on the
 * memo opens straight on its pages.
 *
 * pdf.js is loaded when this opens, not with the application: it is most of
 * a megabyte, and most people reading a memo never insert a page.
 */

export type PagePicked = { file: File; alt: string };

/** The PDF being read, by where it came from. */
type From = { name: string; read: () => Promise<ArrayBuffer> };

let library: Promise<typeof import("pdfjs-dist")> | null = null;

/** pdf.js, with its worker, once.
 *
 *  THE WORKER IS VITE'S, NOT A URL TO pdf.js's OWN FILE. That file is .mjs,
 *  and web/ reaches S3 by a plain `aws s3 sync`, which guesses a type from
 *  the extension; a module worker served as anything but JavaScript is
 *  refused by the browser, in production only. ?worker bundles it as .js. */
function pdfjs() {
  library ??= Promise.all([
    import("pdfjs-dist"),
    import("pdfjs-dist/build/pdf.worker.min.mjs?worker"),
  ]).then(([lib, worker]) => {
    lib.GlobalWorkerOptions.workerPort = new worker.default();
    return lib;
  });
  return library;
}

/** A filed source's bytes, through the link that opens the original. */
async function readSource(documentId: number): Promise<ArrayBuffer> {
  const { source_url } = await api.passage(documentId, null);
  let answer: Response;
  try {
    answer = await fetch(source_url);
  } catch {
    // The browser's own words are "Failed to fetch", which says nothing. It
    // is what a bucket that does not let this page read it looks like - the
    // docs bucket's CORS (storage.tf) - or a connection that dropped.
    throw new Error("storage did not let this page read it. Try again; if "
      + "it keeps happening, a PDF from your computer still works");
  }
  if (!answer.ok) throw new Error("storage answered " + answer.status);
  return answer.arrayBuffer();
}

/** One page drawn to a PNG at the width the memo uses. */
async function drawPage(doc: PDFDocumentProxy, n: number,
                        shrink = 1): Promise<Blob> {
  const page = await doc.getPage(n);
  const base = page.getViewport({ scale: 1 });
  const viewport = page.getViewport({ scale: pageScale(base.width) * shrink });
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(viewport.width);
  canvas.height = Math.ceil(viewport.height);
  // A page with no ground of its own is transparent, and a transparent PNG
  // on a tinted panel reads as a fault.
  await page.render({ canvas, viewport, background: "#ffffff" }).promise;
  page.cleanup();
  return new Promise((resolve, reject) => canvas.toBlob(
    (b) => (b ? resolve(b) : reject(new Error("the page could not be drawn"))),
    "image/png"));
}

/** A page's thumbnail, drawn when it scrolls into view. */
function Thumb({ doc, n, picked, onToggle }: {
  doc: PDFDocumentProxy;
  n: number;
  picked: boolean;
  onToggle: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    let cancelled = false;
    let task: { cancel: () => void } | null = null;
    const seen = new IntersectionObserver(async ([entry]) => {
      if (!entry.isIntersecting) return;
      seen.disconnect();
      const page = await doc.getPage(n);
      if (cancelled) return;
      const base = page.getViewport({ scale: 1 });
      const viewport = page.getViewport({ scale: 150 / base.width });
      el.width = Math.ceil(viewport.width);
      el.height = Math.ceil(viewport.height);
      const render = page.render({ canvas: el, viewport, background: "#ffffff" });
      task = render;
      render.promise.catch(() => { /* cancelled, or unreadable: left blank */ });
    }, { rootMargin: "200px" });
    seen.observe(el);
    return () => { cancelled = true; seen.disconnect(); task?.cancel(); };
  }, [doc, n]);

  return (
    <button type="button" className={picked ? "pdf-thumb on" : "pdf-thumb"}
            onClick={onToggle} aria-pressed={picked}
            title={picked ? "Leave page " + n + " out" : "Put page " + n + " in"}>
      <canvas ref={canvas} />
      <span className="pdf-thumb-n">{picked ? "✓ " : ""}p. {n}</span>
    </button>
  );
}

export function PdfPagePicker({ sources, dropped, onInsert, onClose }: {
  /** The memo's sources that are PDFs, less any deleted. */
  sources: Source[];
  /** A PDF dropped or pasted on the memo, opened straight away. */
  dropped: File | null;
  onInsert: (pages: PagePicked[]) => void;
  onClose: () => void;
}) {
  const [from, setFrom] = useState<From | null>(
    dropped ? { name: dropped.name, read: () => dropped.arrayBuffer() } : null);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState("");
  // The pages picked. They go in in page order, whatever order they were
  // picked in.
  const [picked, setPicked] = useState<number[]>([]);
  const [busy, setBusy] = useState("");

  /** Another PDF, or none: what was read from the last one goes with it. */
  function choose(next: From | null) {
    setDoc(null);
    setPicked([]);
    setError("");
    setFrom(next);
  }

  useEffect(() => {
    if (!from) return;
    let live = true;
    // What reading it set going, so leaving lets the worker go too. The
    // document is let go through its loading task in pdf.js 6.
    let task: { destroy: () => Promise<void> } | null = null;
    (async () => {
      try {
        const [lib, data] = await Promise.all([pdfjs(), from.read()]);
        if (!live) return;
        const loading = lib.getDocument({ data });
        task = loading;
        const opened = await loading.promise;
        if (live) setDoc(opened);
      } catch (err) {
        if (!live) return;
        const name = (err as Error)?.name;
        setError(name === "PasswordException"
          ? from.name + " is protected by a password, so its pages cannot be read."
          : name === "InvalidPDFException"
            ? from.name + " is not a PDF that can be read."
            : from.name + " could not be read: "
              + String((err as Error)?.message ?? err));
      }
    })();
    return () => { live = false; task?.destroy(); };
  }, [from]);

  function toggle(n: number) {
    setPicked((p) => (p.includes(n) ? p.filter((x) => x !== n) : [...p, n]));
  }

  async function insert() {
    if (!doc || !from || picked.length === 0) return;
    const pages = [...picked].sort((a, b) => a - b);
    const out: PagePicked[] = [];
    setError("");
    try {
      for (const [i, n] of pages.entries()) {
        setBusy(`Drawing page ${n} (${i + 1} of ${pages.length})`);
        let blob = await drawPage(doc, n);
        // A dense scan can come out over the 10 MB an image may be. Once
        // smaller, then refused with the reason rather than sent to fail.
        if (blob.size > 10 * 1024 * 1024) blob = await drawPage(doc, n, 0.6);
        if (blob.size > 10 * 1024 * 1024) {
          throw new Error(`page ${n} is too large as an image even when drawn smaller`);
        }
        out.push({ file: new File([blob], pageFileName(from.name, n),
                                   { type: "image/png" }),
                   alt: pageAlt(from.name, n) });
      }
    } catch (err) {
      setBusy("");
      setError("The pages could not be drawn: " + String((err as Error)?.message ?? err));
      return;
    }
    setBusy("");
    onInsert(out);
  }

  const pageCount = doc?.numPages ?? 0;

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <div className="panel pdf-panel" role="dialog" aria-label="Insert PDF pages"
           onClick={(e) => e.stopPropagation()}
           onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
        <div className="panel-head">
          <a className="panel-close" onClick={onClose}>Close</a>
          <h3>Insert PDF pages</h3>
          {!from ? (
            <p className="muted small">
              Choose a PDF, then the pages to put in. Each goes in as an image,
              in page order.
            </p>
          ) : (
            <p className="muted small">
              <strong>{from.name}</strong>
              {pageCount > 0 && <> &middot; {pageCount} {pageCount === 1 ? "page" : "pages"}</>}
              {" "}&middot; <a onClick={() => choose(null)}>
                Choose another
              </a>
            </p>
          )}
          {from && doc && (
            <div className="form-actions">
              <button type="button" disabled={picked.length === 0 || !!busy}
                      onClick={insert}>
                {busy ? busy + "…"
                  : picked.length === 0 ? "Pick the pages to insert"
                  : `Insert ${picked.length} ${picked.length === 1 ? "page" : "pages"}`}
              </button>
              {picked.length > 0 && !busy && (
                <a className="secondary" onClick={() => setPicked([])}>Clear</a>
              )}
            </div>
          )}
          {error && <p className="error">{error}</p>}
        </div>
        <div className="panel-body">
          {!from ? (
            <>
              <h4>This memo&rsquo;s sources</h4>
              {sources.length === 0 ? (
                <p className="muted">None of this memo&rsquo;s sources is a PDF.</p>
              ) : (
                <ul className="footnote-list">
                  {sources.map((s) => (
                    <li key={s.documentId}>
                      <button type="button" onClick={() => choose(
                        { name: s.name, read: () => readSource(s.documentId) })}>
                        {s.name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <h4>From your computer</h4>
              <input type="file" accept="application/pdf,.pdf"
                     onChange={(e) => {
                       const file = e.target.files?.[0];
                       if (file) choose({ name: file.name, read: () => file.arrayBuffer() });
                     }} />
              <p className="muted small">
                Read here and put in as images. The PDF itself is not uploaded.
              </p>
            </>
          ) : !doc ? (
            !error && <p className="muted">Reading {from.name}&hellip;</p>
          ) : (
            <div className="pdf-thumbs">
              {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
                <Thumb key={n} doc={doc} n={n} picked={picked.includes(n)}
                       onToggle={() => toggle(n)} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
