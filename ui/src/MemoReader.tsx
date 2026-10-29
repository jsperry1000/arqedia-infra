import { Fragment, useEffect, useMemo, useRef, useState,
         type DragEvent } from "react";
import { parseBlocks, serializeBlocks, blockToMarkdown, trailingOf, citationsIn,
         isCitable, footnoteRef, type Block, type Inline } from "./memodoc";
import { citeChipHtml, inlinesToHtml, nodesToInlines } from "./memoedit";
import type { Act } from "./undo";
import { api, type DocumentDetail } from "./api";
import { groupByType, type Place, type Source } from "./footnotefacts";
import { PdfPagePicker, type PagePicked } from "./PdfPages";

/**
 * The memo as it reads.
 *
 * A memorandum is prose and tables, and that is what this draws: real tables,
 * headings, gap callouts. What it does NOT draw is the markdown underneath -
 * the pipes, the asterisks, the filenames - which is storage, not something a
 * person should have to read past.
 *
 * Editing happens here too, in the document rather than beside it. An edit
 * icon on a block opens that block where it sits: same type, same table, same
 * spacing, so nothing moves when a person starts typing. What comes out is
 * markdown of the shape the renderer expects, and every other block is
 * written back exactly as it came.
 *
 * Citations are the other half of that. A finished sentence carrying seven
 * references ended in a paragraph of filenames longer than the sentence. Each
 * run of references is one small mark instead, and the marks stay out of the
 * way until somebody wants them - which is what checking a memo means, and is
 * a thing done a paragraph at a time rather than all at once.
 */

export type Ref = {
  documentId: number;
  filename: string;
  unit: number | null;
  text: string;
};

/**
 * Split a citation run into the documents it names.
 *
 * "Sources: a.pdf, page 1; b.docx, section 2" is eight citations on some
 * sections, not one - matching only the first meant every click opened the
 * same document.
 */
export function parseRefs(raw: string, byFilename: Record<string, number>):
    (string | Ref)[] {
  const pattern =
    /([A-Za-z0-9._()\-]+\.(?:pdf|docx|xlsx|txt|json|xml))(\s*,\s*(?:page|section|sheet)\s*(\d+))?/gi;
  const out: (string | Ref)[] = [];
  let last = 0;
  let m: RegExpExecArray | null;

  while ((m = pattern.exec(raw)) !== null) {
    const documentId = byFilename[m[1]];
    if (!documentId) continue;
    if (m.index > last) out.push(raw.slice(last, m.index));
    out.push({ documentId, filename: m[1], unit: m[3] ? Number(m[3]) : null,
               text: m[0] });
    last = m.index + m[0].length;
  }
  if (last < raw.length) out.push(raw.slice(last));
  return out;
}

/**
 * What makes two citations the same footnote (18.1).
 *
 * THERE IS NO FOOTNOTE NUMBER in a memorandum. The mark in the text is the
 * COUNT of references in that run, not an ordinal, and a run is keyed by its
 * position in a block - so two blocks citing the same page share nothing at
 * all today. A footnote's identity therefore has to be made from what a
 * citation actually carries: the source and the place in it.
 *
 * THE PLACE IS PART OF IT. accounts.pdf, page 4 and accounts.pdf, page 9 are
 * two different footnotes, because the thing a person is following is a
 * passage rather than a file. A citation with no page - "accounts.pdf" alone -
 * is its own third thing and matches only other bare mentions of that file.
 *
 * Lower-cased, because the filename is a key here and not a display.
 */
export function refKey(ref: Ref): string {
  return ref.filename.toLowerCase() + "#" + (ref.unit ?? "");
}

/** Whether one reference names a document that has been deleted (8.2). */
function refIsGone(raw: string, byFilename: Record<string, number>,
                          gone?: Set<string>): boolean {
  return !!gone?.size && parseRefs(raw, byFilename).some(
    (p) => typeof p !== "string" && gone.has(p.filename));
}

/** The mark a run of citations leaves in the text when they are put away, and
 *  the references themselves when they are out. */
function Citations({ refs, shown, onToggle, byFilename, gone, onOpen,
                     lit, onLight }: {
  refs: string[];
  shown: boolean;
  onToggle: () => void;
  byFilename: Record<string, number>;
  /** Sources whose document has been deleted. The citation still reads - the
   *  memorandum said what it said - and there is nothing behind it to open,
   *  so it is drawn as spent rather than quietly turned back into prose. */
  gone?: Set<string>;
  onOpen: (ref: Ref) => void;
  /** The footnote being followed, as refKey writes it, or null. */
  lit: string | null;
  onLight: (key: string) => void;
}) {
  if (!shown) {
    /* A PUT-AWAY RUN STILL LIGHTS UP (18.1). Most of a memo's runs are away -
       that is the point of them - so a footnote followed in one paragraph
       would otherwise appear to be used nowhere else, which is worse than not
       answering at all. The mark shows that the answer is behind it, and the
       count it already carries says how many are there. */
    const here = lit !== null && refs.some((raw) =>
      parseRefs(raw, byFilename).some(
        (p) => typeof p !== "string" && refKey(p) === lit));
    /* A RUN CITING A DELETED DOCUMENT IS BLACK WHILE PUT AWAY TOO (26
       October 2026). It was black only once shown or followed, so a memo
       resting on a deleted source read as sound until somebody happened to
       open the right footnote - and each of these has to be found and taken
       out before a revision will save. */
    const dead = refs.some((raw) => refIsGone(raw, byFilename, gone));
    return (
      <button type="button"
              className={"cite-mark" + (here ? " lit" : "") + (dead ? " gone" : "")}
              onClick={onToggle}
              title={here ? "The same source is cited here. Show it"
                     : dead ? "Cites a deleted document. Show the sources"
                     : refs.length === 1 ? "Show the source"
                                         : `Show ${refs.length} sources`}>
        {refs.length}
      </button>
    );
  }
  return (
    <span className="cite-run">
      {refs.map((raw, i) => (
        <em className="ref" key={i}>
          [
          {parseRefs(raw, byFilename).map((p, k) =>
            typeof p === "string" ? (
              <span key={k}>{p}</span>
            ) : gone?.has(p.filename) ? (
              /* A DELETED SOURCE LIGHTS AND IS LIT, AND STILL DOES NOT OPEN
                 (18.1). It is found like any other - memo_source keeps the
                 document_id through the delete, so byFilename holds it and
                 refKey resolves it - and a memorandum resting on a document
                 that has since gone is exactly the one somebody needs to
                 see the reach of. Opening is the part that cannot happen:
                 there is nothing behind it. So onLight, and no onOpen. */
              <span key={k}
                    className={refKey(p) === lit ? "cite gone lit" : "cite gone"}
                    onClick={() => onLight(refKey(p))}
                    title={p.filename + " has been deleted. The memorandum is "
                           + "unchanged; there is nothing left to open. Click "
                           + "to mark where else it is cited."}>
                {p.text}
              </span>
            ) : (
              <span key={k}
                    className={refKey(p) === lit ? "cite lit" : "cite"}
                    // FOLLOWING AND OPENING ARE THE SAME CLICK. A second
                    // control beside each citation would be two marks on
                    // every reference in a document made of them; and a
                    // person who has just opened a passage is exactly the
                    // person who wants to know where else it was relied on.
                    onClick={() => { onLight(refKey(p)); onOpen(p); }}
                    title={"Open " + p.filename
                           + ", and show where else it is cited"}>{p.text}</span>
            ))}
          ]
        </em>
      ))}
      <button type="button" className="cite-mark shown" onClick={onToggle}
              title="Put the sources away">&times;</button>
    </span>
  );
}

function Inlines({ nodes, blockId, shown, onToggle, byFilename, gone, onOpen,
                  lit, onLight }: {
  nodes: Inline[];
  blockId: string;
  shown: Record<string, boolean>;
  onToggle: (key: string) => void;
  byFilename: Record<string, number>;
  gone?: Set<string>;
  onOpen: (ref: Ref) => void;
  lit: string | null;
  onLight: (key: string) => void;
}) {
  return (
    <>
      {nodes.map((n, i) => {
        if (n.kind === "text") return <span key={i}>{n.text}</span>;
        if (n.kind === "bold") return <strong key={i}>{n.text}</strong>;
        if (n.kind === "em") return <em key={i}>{n.text}</em>;
        const key = blockId + ":" + i;
        return (
          <Citations key={i} refs={n.refs} shown={!!shown[key]}
                     onToggle={() => onToggle(key)}
                     byFilename={byFilename} gone={gone} onOpen={onOpen}
                     lit={lit} onLight={onLight} />
        );
      })}
    </>
  );
}

/** A gap, a coverage note or a caveat: quoted in the markdown, a callout on
 *  the page. The renderer draws these on a tinted panel; so does this. */
function calloutKind(inlines: Inline[]): string {
  const first = inlines.find((n) => n.kind === "bold");
  const word = (first && first.kind === "bold" ? first.text : "").toLowerCase();
  if (word.startsWith("gap")) return "gap";
  if (word.startsWith("coverage")) return "coverage";
  return "note";
}

/**
 * A block being edited.
 *
 * The content is written into the element ONCE, when it opens, and read out
 * as it changes. React must not re-render it in between: setting the HTML on
 * every keystroke puts the caret back to the start, which is the classic way
 * this goes wrong.
 *
 * Reading it out is the part that has to be reliable. Reading only when the
 * block closed meant relying on an unmount, which React runs after the
 * element has already left the page and which does not run at all if the tab
 * goes first - so an edit took most of the time and occasionally did not,
 * which is worse than no editing. The content is read out on every change, a
 * short pause after typing stops, and again the moment focus leaves. By the
 * time anything else happens the edit is already in.
 */
function Editable({ html, onEdit, onSplit, deferred, className }: {
  html: string;
  onEdit: (root: HTMLElement) => void;
  // A paragraph that does not exist yet is read out only when it is finished,
  // not as it is typed: writing it into the memo on the first letter would
  // replace this element with the block's own and take the caret with it.
  deferred?: boolean;
  // Enter, where the block can be broken in two: what is before the caret
  // stays, what is after it begins the next paragraph or item. Absent -
  // a heading, a table cell - Enter does nothing, because a heading on two
  // lines is not a thing a memorandum has.
  onSplit?: (before: HTMLElement, after: HTMLElement) => void;
  className?: string;
}) {
  // A span, not a div: a paragraph is a <p>, and a block element inside one
  // is invalid HTML the browser silently closes the paragraph to escape.
  const box = useRef<HTMLSpanElement | null>(null);
  // The current reader, so a commit never writes through a stale copy of the
  // document it was mounted with.
  const read = useRef(onEdit);
  read.current = onEdit;
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);

  const commit = () => {
    if (pending.current) { clearTimeout(pending.current); pending.current = null; }
    if (box.current) read.current(box.current);
  };

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.innerHTML = html;
    el.focus();
    // The caret at the end of what is there, not the start: a person clicking
    // into a paragraph is usually adding to it.
    const range = document.createRange();
    range.selectNodeContents(el);
    range.collapse(false);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    // And once more on the way out, for a change that arrived between the
    // last commit and the block closing.
    return () => {
      if (pending.current) clearTimeout(pending.current);
      read.current(el);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <span
      ref={box}
      className={"editable" + (className ? " " + className : "")}
      contentEditable
      suppressContentEditableWarning
      spellCheck
      onInput={() => {
        if (deferred) return;
        if (pending.current) clearTimeout(pending.current);
        pending.current = setTimeout(commit, 400);
      }}
      onBlur={commit}
      onKeyDown={(e) => {
        // Bold and italic are the only marks a memo uses.
        const meta = e.metaKey || e.ctrlKey;
        if (meta && (e.key === "b" || e.key === "i")) {
          e.preventDefault();
          document.execCommand(e.key === "b" ? "bold" : "italic");
          return;
        }
        if (e.key === "Enter") {
          e.preventDefault();
          const el = box.current;
          const selection = window.getSelection();
          if (!el || !onSplit || !selection || selection.rangeCount === 0) {
            commit();
            return;
          }
          // Everything after the caret is lifted out and handed over as the
          // new block; what is left in the element is the old one.
          const caret = selection.getRangeAt(0);
          const tail = document.createRange();
          tail.setStart(caret.endContainer, caret.endOffset);
          tail.setEnd(el, el.childNodes.length);
          const after = document.createElement("span");
          after.appendChild(tail.extractContents());
          if (pending.current) clearTimeout(pending.current);
          onSplit(el, after);
          return;
        }
        // A paste of formatted text arrives as text; see nodesToInlines.
      }}
      onPaste={(e) => {
        // A file - an image - is the document's to place, not this block's
        // to hold: left to bubble to MemoDocument (graphics-insert).
        if (e.clipboardData.files.length > 0) return;
        e.preventDefault();
        const text = e.clipboardData.getData("text/plain");
        document.execCommand("insertText", false, text);
      }}
    />
  );
}

/**
 * Choosing what a footnote cites.
 *
 * THE MEMO'S OWN SOURCES, AND NOTHING ELSE (decided 27 October 2026). The
 * save refuses a citation to any document that is not a source of the memo,
 * so listing the rest of the engagement would offer citations that cannot be
 * kept. A deleted source is left out for the same reason.
 *
 * FOUND BY FACT, BY DOCUMENT TYPE OR BY NAME (29 October 2026), in one search,
 * grouped by type: see footnotefacts.ts. A fact opens to the places it was
 * read, and one of those goes in with its page. A document picked by name
 * takes the page typed, or none; without one the footnote names the file
 * alone, which opens it like any other.
 */
function FootnotePicker({ sources, ready, onPick, onClose }: {
  sources: Source[];
  // False when there was no cursor in the text to put the footnote at.
  ready: boolean;
  onPick: (ref: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState("");
  // Each source's values, asked for once as the picker opens. Until they
  // come, its name is searchable and its facts are not.
  const [details, setDetails] = useState<Record<number, DocumentDetail>>({});
  const [waiting, setWaiting] = useState(sources.length);
  const [failed, setFailed] = useState(0);
  // The fact opened to its places, by type and label.
  const [opened, setOpened] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    for (const s of sources) {
      api.documentValues(s.documentId)
        .then((d) => { if (live) setDetails((m) => ({ ...m, [s.documentId]: d })); })
        .catch(() => { if (live) setFailed((n) => n + 1); })
        .finally(() => { if (live) setWaiting((n) => n - 1); });
    }
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const groups = useMemo(() => groupByType(sources, details, query),
                         [sources, details, query]);
  const documents = groups.flatMap((g) => g.documents);
  const factCount = groups.reduce((n, g) => n + g.facts.length, 0);
  const pageNo = /^\d+$/.test(page.trim()) && Number(page) > 0
    ? Number(page) : null;
  const pageBad = page.trim() !== "" && pageNo === null;
  const pick = (name: string) => {
    if (ready && !pageBad) onPick(footnoteRef(name, pageNo));
  };
  // A fact's place carries its own page; the one typed is for a name.
  const pickPlace = (place: Place) => {
    if (ready) onPick(footnoteRef(place.name, place.page));
  };

  return (
    <div className="panel-backdrop" onClick={onClose}>
      <div className="panel narrow footnote-panel" role="dialog"
           aria-label="Insert a footnote"
           onClick={(e) => e.stopPropagation()}
           onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
        <div className="panel-head">
          <a className="panel-close" onClick={onClose}>Close</a>
          <h3>Insert a footnote</h3>
          {!ready ? (
            <p className="warn">
              Click in the text where the footnote goes, then press Insert
              footnote again.
            </p>
          ) : (
            <p className="muted small">
              It goes where the cursor was. Only this memo's sources can be
              cited.
            </p>
          )}
          <div className="footnote-fields">
            <input type="text" autoFocus
                   placeholder="Search facts, document types or names"
                   aria-label="Search facts, document types or names"
                   value={query}
                   onChange={(e) => { setQuery(e.target.value); setOpened(null); }}
                   // One document left and no fact: Enter takes it.
                   onKeyDown={(e) => {
                     if (e.key === "Enter" && documents.length === 1
                         && factCount === 0) pick(documents[0]);
                   }} />
            <input type="text" inputMode="numeric" placeholder="Page"
                   aria-label="Page, for a document picked by name (optional)"
                   title="For a document picked by name. A fact brings its own page."
                   className="footnote-page"
                   value={page} onChange={(e) => setPage(e.target.value)} />
          </div>
          {pageBad && <p className="warn">A page is a whole number.</p>}
          {waiting > 0 && (
            <p className="muted small">
              Reading the facts held in {waiting} of {sources.length}{" "}
              {sources.length === 1 ? "document" : "documents"}&hellip;
            </p>
          )}
          {failed > 0 && (
            <p className="warn">
              The facts of {failed} {failed === 1 ? "document" : "documents"}{" "}
              could not be read. {failed === 1 ? "Its name" : "Their names"} can
              still be searched.
            </p>
          )}
        </div>
        <div className="panel-body">
          {groups.length === 0 ? (
            <p className="muted">
              {sources.length === 0 ? "This memo has no sources to cite."
                                    : "Nothing matches."}
            </p>
          ) : groups.map((g) => (
            <section key={g.type} className="footnote-group">
              <h4>{g.type}</h4>
              {g.facts.length > 0 && (
                <ul className="footnote-list">
                  {g.facts.map((f) => {
                    const key = g.type + "\u0000" + f.label;
                    const open = opened === key;
                    return (
                      <li key={key}>
                        <button type="button"
                                className={open ? "footnote-fact on" : "footnote-fact"}
                                aria-expanded={open}
                                onClick={() => setOpened(open ? null : key)}>
                          <span className="fact-line">
                            <span className="fact-label">{f.label}</span>{" "}
                            <span className="fact-value">
                              {f.places[0].values[0]}
                            </span>
                          </span>
                        </button>
                        {open && (
                          <ul className="footnote-list footnote-places">
                            {f.places.map((p) => (
                              <li key={p.name + "#" + (p.page ?? "")}>
                                <button type="button" disabled={!ready}
                                        onClick={() => pickPlace(p)}
                                        title={"Cite " + footnoteRef(p.name, p.page)}>
                                  {footnoteRef(p.name, p.page)}
                                  <span className="fact-value">
                                    {p.values.join("; ")}
                                  </span>
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
              {g.documents.length > 0 && (
                <ul className="footnote-list">
                  {g.documents.map((name) => (
                    <li key={name}>
                      <button type="button" disabled={!ready || pageBad}
                              onClick={() => pick(name)}
                              title={"Cite " + footnoteRef(name, pageNo)}>
                        {name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}

/** The file a drop or a paste carries, an image first: the image wins a
 *  mixed paste (graphics-insert N5). Any other file is still handed on, so
 *  the person is told what an image has to be rather than nothing
 *  happening. */
function fileOf(data: DataTransfer | null): File | null {
  const files = Array.from(data?.files ?? []);
  return files.find((f) => f.type.startsWith("image/")) ?? files[0] ?? null;
}

/** A PDF, which opens on its pages rather than being refused as an image
 *  (pdf-page-insert). */
function isPdf(file: File): boolean {
  return file.type === "application/pdf" || /\.pdf$/i.test(file.name);
}

export function MemoDocument({ markdown, byFilename, gone, onOpen, onChange,
                              onOpenChange, imageSrc, onImageError,
                              onImageFile }: {
  markdown: string;
  byFilename: Record<string, number>;
  /** Filenames whose document has been deleted (8.2). */
  gone?: Set<string>;
  onOpen: (ref: Ref) => void;
  // Absent, the memo is read-only. Present, every block carries an edit
  // control and this is called with the whole memo after each change, and
  // the act that made it, which is what undo records (UNDO-01).
  onChange?: (markdown: string, act: Act) => void;
  // Which block is open, or null when none is: everything typed into one
  // block between opening and closing it is one edit to undo, and undo
  // waits while a block is open.
  onOpenChange?: (open: string | null) => void;
  // An image's link by its name: undefined while it is being asked for,
  // null where the memo does not hold it.
  imageSrc?: (image: string) => string | null | undefined;
  // A link that would not load - expired, most likely - to be asked again.
  onImageError?: (image: string) => void;
  // A file dropped or pasted, put into storage: its name, or null where it
  // was refused - the screen says why.
  onImageFile?: (file: File) => Promise<string | null>;
}) {
  // Which runs are out, by block and position. Put away by default: a memo is
  // read far more often than it is checked.
  const [shown, setShown] = useState<Record<string, boolean>>({});
  const toggle = (key: string) =>
    setShown((prev) => ({ ...prev, [key]: !prev[key] }));

  /**
   * The footnote being followed (18.1), as refKey writes it.
   *
   * WHAT IT ANSWERS. A memorandum is an argument, and the question a person
   * checking one asks of a citation is not only what does that say but WHERE
   * ELSE DID THIS COME IN. A source relied on in one paragraph is ordinary; a
   * source carrying four paragraphs and a table row is the thing the whole
   * memo turns on, and that is not visible by reading down the page.
   *
   * IT IS A HIGHLIGHT AND NOT A SELECTION. Nothing is stored, nothing is
   * counted, no control appears. It goes as soon as attention moves, which is
   * the next click anywhere that is not a citation - see below.
   */
  const [lit, setLit] = useState<string | null>(null);

  /** CLEARED BY THE NEXT CLICK ELSEWHERE, wherever that click lands.
   *
   *  On the document rather than on the article, because "elsewhere" includes
   *  the rest of the screen - the passage that has just been opened beside it,
   *  the rail, the header - and a highlight that survived those would be a
   *  selection left lying about.
   *
   *  On mousedown, which runs before React's click: a click on another
   *  citation is let through here by the .cite test and then lights the new
   *  one, so following a second footnote is one click and not two.
   *
   *  A MARK IS LET THROUGH TOO. The lit mark's whole purpose is that there is
   *  something behind it, and clearing the highlight on the click that opens
   *  it would show the reader exactly what they went looking for with the
   *  answer taken off it.
   *
   *  AND SO IS THE PASSAGE PANEL. One click does two things - it opens the
   *  cited passage and marks where else that passage was relied on - and
   *  reading the passage is how a person uses the second half. Every way out
   *  of that panel was a click somewhere that is not a citation: Close, the
   *  scrim, the link to the original. So the panel answered the question and
   *  then took the answer away on the way out, which made the highlight
   *  reachable only by not using it.
   *
   *  .cite-panel is a marker and carries no style rule. Named rather than
   *  .panel-backdrop, which every drawer in the product wears: this exemption
   *  belongs to the one panel a citation opens, and a drawer added to this
   *  screen later should clear the highlight like anything else.
   *
   *  Listening only while something is lit. Nothing is bound to the document
   *  while the memo is merely being read. */
  useEffect(() => {
    if (lit === null) return;
    const clear = (e: MouseEvent) => {
      const at = e.target as Element | null;
      if (at?.closest?.(".cite, .cite-mark, .cite-panel")) return;
      setLit(null);
    };
    document.addEventListener("mousedown", clear);
    return () => document.removeEventListener("mousedown", clear);
  }, [lit]);

  // Which block is open. One at a time: two carets in one document is a way
  // to lose track of which change went where.
  const [editing, setEditing] = useState<string | null>(null);
  // A block just closed, waiting to be judged empty or not.
  const [closed, setClosed] = useState<string | null>(null);
  // Where a block was just added, so it can be opened once the document has
  // been read back and the blocks renumbered.
  const opening = useRef<number | null>(null);
  // Where a new paragraph is being typed, before it is part of the memo.
  const [adding, setAdding] = useState<number | null>(null);
  // A row being dragged by its grip, and the row it is held over with which
  // half of it - above or below is where it would go.
  const dragging = useRef<{ id: string; from: number } | null>(null);
  const [dropRow, setDropRow] = useState<{ r: number; below: boolean } | null>(null);
  // Counts the rows moved, for the rows' key: see the table below.
  const [moved, setMoved] = useState(0);
  // A footnote being chosen, and the cursor it goes at: taken when Insert
  // footnote is pressed, because the search box takes the focus after.
  const [picking, setPicking] = useState(false);
  const caret = useRef<{ host: HTMLElement; range: Range } | null>(null);
  // What a footnote may cite: the sources, less any deleted.
  const citable = useMemo(
    () => Object.entries(byFilename)
      .filter(([name]) => isCitable(name) && !gone?.has(name))
      .map(([name, documentId]) => ({ name, documentId }))
      .sort((a, b) => a.name.localeCompare(b.name)),
    [byFilename, gone]);
  // Pages of a PDF being chosen, and the gap they go into: from a source or
  // a file chosen there, or the PDF dropped or pasted that opened it.
  const [pdfAt, setPdfAt] = useState<{ index: number; file: File | null } | null>(null);
  const pdfSources = useMemo(
    () => citable.filter((s) => /\.pdf$/i.test(s.name)), [citable]);

  // Told to the screen as it changes, and as none when this document goes -
  // a section swapped for its rewrite takes its open block with it.
  const open = editing ?? (adding === null ? null : "new:" + adding);
  const reportOpen = useRef(onOpenChange);
  useEffect(() => { reportOpen.current = onOpenChange; });
  useEffect(() => { reportOpen.current?.(open); }, [open]);
  useEffect(() => () => reportOpen.current?.(null), []);

  // A memorandum is a hundred thousand characters. Parsed on every keystroke
  // it would be, and the whole document laid out again with it.
  const blocks = useMemo(() => parseBlocks(markdown), [markdown]);
  const editable = !!onChange;
  // A reference to a deleted document, for its mark in an open block.
  const goneRef = (ref: string) => refIsGone(ref, byFilename, gone);

  const article = useRef<HTMLElement | null>(null);
  // The gap an image dragged over the memo would go into.
  const [dropAt, setDropAt] = useState<number | null>(null);
  // Gaps with an image on its way into storage.
  const [placing, setPlacing] = useState<number[]>([]);
  // Images in storage, waiting to go into the memo together.
  const [arrived, setArrived] = useState<{ at: number; blocks: Block[] } | null>(null);

  /** An image dropped or pasted: into storage first, then into the memo
   *  between blocks, on a line of its own. One act to undo. */
  async function insertImage(file: File, index: number) {
    await insertImages([{ file, alt: file.name.replace(/\.[^.]*$/, "") }], index);
  }

  /** Pages of a PDF, drawn as images: each into storage in turn, then all
   *  into the memo at once, in order - one act to undo, as one image is.
   *  The first refused stops the rest, and the screen says why. */
  async function insertImages(items: PagePicked[], index: number) {
    if (!onImageFile) return;
    setPlacing((p) => [...p, index]);
    try {
      const stored: Block[] = [];
      for (const { file, alt } of items) {
        const image = await onImageFile(file);
        if (!image) break;
        stored.push({ id: "new", source: "", kind: "image", alt, image });
      }
      if (stored.length > 0) setArrived({ at: index, blocks: stored });
    } finally {
      setPlacing((p) => { const i = p.indexOf(index); return p.filter((_, k) => k !== i); });
    }
  }

  // Put in from here rather than where the upload finished: the memo may
  // have changed while it was on its way, and this render has it as it is.
  const put = useRef<typeof arrived>(null);
  useEffect(() => {
    if (!arrived || put.current === arrived || !onChange) return;
    put.current = arrived;
    const at = Math.min(arrived.at, blocks.length);
    // One blank line after each: a source ending "\n" is its line and one
    // blank one, once joined.
    onChange(serializeBlocks([
      ...blocks.slice(0, at),
      ...arrived.blocks.map((b) => ({ ...b, source: blockToMarkdown(b, "\n") })),
      ...blocks.slice(at),
    ]), "image");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arrived]);

  /** The gap nearest the pointer. Every gap has an insert point. */
  function gapAt(y: number): number {
    let best = blocks.length;
    let distance = Infinity;
    article.current?.querySelectorAll<HTMLElement>("[data-gap]").forEach((el) => {
      const r = el.getBoundingClientRect();
      const d = Math.abs(r.top + r.height / 2 - y);
      if (d < distance) { distance = d; best = Number(el.dataset.gap); }
    });
    return best;
  }

  const takesFiles = (data: DataTransfer) =>
    editable && !!onImageFile && Array.from(data.types).includes("Files");

  /** Write one block back into the memo, leaving every other character of it
   *  alone. */
  function replace(id: string, change: (b: Block) => Block, act: Act = "edit") {
    if (!onChange) return;
    const next = blocks.map((b) => {
      if (b.id !== id) return b;
      const edited = change(b);
      return { ...edited, source: blockToMarkdown(edited, trailingOf(b.source)) };
    });
    const after = serializeBlocks(next);
    if (after !== markdown) onChange(after, act);
  }

  /** A blank row put in at a given place, or a row taken out.
   *
   *  A table is where a memorandum's facts sit, and a fact arrives in the
   *  middle of a list as often as at the end of one - a supplier between two
   *  others, a term between two terms. Appending and then dragging it into
   *  place is two steps where one will do, so the row goes in where it
   *  belongs. */
  function insertRow(id: string, at: number) {
    replace(id, (b) => b.kind !== "table" ? b : {
      ...b, rows: [...b.rows.slice(0, at), b.head.map(() => []),
                   ...b.rows.slice(at)] }, "row");
  }

  function removeRow(id: string, at: number) {
    const block = blocks.find((b) => b.id === id);
    if (block?.kind === "table") {
      const row = block.rows[at] ?? [];
      const written = row.some((c) =>
        c.some((n) => n.kind === "cites" || n.text.trim() !== ""));
      if (written && !window.confirm("Delete this row?")) return;
    }
    replace(id, (b) => b.kind !== "table" ? b
      : { ...b, rows: b.rows.filter((_, i) => i !== at) }, "row");
  }

  /** A row dragged by its grip to another place in its table. `to` is the
   *  gap it is dropped into, counted as the table stood before the move, so
   *  the gaps either side of the row itself are no move at all. */
  function moveRow(id: string, from: number, to: number) {
    if (to === from || to === from + 1) return;
    replace(id, (b) => {
      if (b.kind !== "table") return b;
      const rows = b.rows.slice();
      const [row] = rows.splice(from, 1);
      rows.splice(to > from ? to - 1 : to, 0, row);
      return { ...b, rows };
    }, "row");
    setMoved((n) => n + 1);
  }

  /** Where the cursor is, if it is in the text of the open block. */
  function caretInBlock(): { host: HTMLElement; range: Range } | null {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return null;
    const range = selection.getRangeAt(0);
    const at = range.startContainer;
    const host = (at.nodeType === 1 ? at as Element : at.parentElement)
      ?.closest<HTMLElement>(".editable");
    if (!host || !article.current?.contains(host)) return null;
    return { host, range: range.cloneRange() };
  }

  /** A footnote put in at the cursor, as the same locked mark a citation
   *  wears in the editor, and read back with the rest of the block. A space
   *  goes before it where the word before runs up to it. */
  function insertFootnote(ref: string) {
    const at = caret.current;
    caret.current = null;
    setPicking(false);
    if (!at || !at.host.isConnected) return;
    at.host.focus();
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(at.range);
    const node = at.range.startContainer;
    const before = node.nodeType === 3
      ? (node.nodeValue ?? "").slice(0, at.range.startOffset) : "";
    const space = before && !/\s$/.test(before) ? "&nbsp;" : "";
    document.execCommand("insertHTML", false, space + citeChipHtml(ref));
  }

  /** The gap a row held over row `r` would drop into, by which half of the
   *  row the pointer is in. */
  function rowGap(e: DragEvent<HTMLTableRowElement>, r: number) {
    const box = e.currentTarget.getBoundingClientRect();
    const below = e.clientY > box.top + box.height / 2;
    return { below, to: r + (below ? 1 : 0) };
  }

  /** A new paragraph, typed in place before it exists.
   *
   *  It is not written into the memo as it is typed. An empty paragraph is
   *  nothing at all in the stored form - a blank line between two others - so
   *  a new one put there straight away would vanish on being read back, and
   *  taking the caret with it. It goes in when it is finished, and a new one
   *  left empty was never there. */
  function addParagraph(index: number, root: HTMLElement) {
    if (!onChange) return;
    const inlines = nodesToInlines(root);
    if (!inlines.some((n) => n.kind === "cites" || n.text.trim() !== "")) return;
    const block: Block = { id: "new", source: "", kind: "para", indent: "",
                           inlines };
    // A last block carries no blank line after it; anywhere else does.
    const trailing = index >= blocks.length ? "\n" : "\n\n";
    onChange(serializeBlocks([
      ...blocks.slice(0, index),
      { ...block, source: blockToMarkdown(block, trailing) },
      ...blocks.slice(index),
    ]), "add");
  }

  /** A page break put in at a gap, on a line of its own: the PDF starts a
   *  new page there. One act to undo. */
  function insertPageBreak(index: number) {
    if (!onChange) return;
    const block: Block = { id: "new", source: "", kind: "pagebreak" };
    // A last block carries no blank line after it; anywhere else does.
    const trailing = index >= blocks.length ? "\n" : "\n\n";
    onChange(serializeBlocks([
      ...blocks.slice(0, index),
      { ...block, source: blockToMarkdown(block, trailing) },
      ...blocks.slice(index),
    ]), "page-break");
  }

  useEffect(() => {
    const at = opening.current;
    if (at === null) return;
    opening.current = null;
    const block = blocks[at];
    if (block) setEditing(block.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [markdown]);

  /** Break a block in two at the caret. A paragraph becomes two paragraphs;
   *  a list item becomes two items of the same list. */
  function splitBlock(block: Block, before: HTMLElement, after: HTMLElement,
                      item?: number) {
    if (!onChange) return;
    const head = nodesToInlines(before);
    const tail = nodesToInlines(after);
    const index = blocks.findIndex((b) => b.id === block.id);

    if (block.kind === "list" && item !== undefined) {
      const items = block.items.slice();
      items[item] = { ...items[item], inlines: head };
      items.splice(item + 1, 0, { prefix: items[item].prefix, inlines: tail });
      const next = { ...block, items } as Block;
      opening.current = index;
      onChange(serializeBlocks(blocks.map((b) => b.id !== block.id ? b
        : { ...next, source: blockToMarkdown(next, trailingOf(b.source)) })),
        "split");
      return;
    }

    if (block.kind !== "para") return;
    const first = { ...block, inlines: head } as Block;
    const second = { ...block, id: "new", inlines: tail } as Block;
    opening.current = index + 1;
    onChange(serializeBlocks([
      ...blocks.slice(0, index),
      { ...first, source: blockToMarkdown(first, "\n") },
      { ...second, source: blockToMarkdown(second, trailingOf(block.source)) },
      ...blocks.slice(index + 1),
    ]), "split");
  }

  /** Take a block out of the memo altogether, with the blank lines that
   *  followed it, so the document closes up rather than keeping a hole.
   *
   *  Emptying a block is not the same as removing it: a paragraph typed down
   *  to nothing is still a paragraph, and left there it is an empty box on
   *  the page and a stray blank line in the document. */
  function removeBlock(id: string) {
    if (!onChange) return;
    const block = blocks.find((b) => b.id === id);
    const what = block && "inlines" in block
      ? citationsIn(block.inlines).length : 0;
    if (!window.confirm(
      what > 0
        ? "Delete this, and the " + what
          + (what === 1 ? " reference" : " references") + " in it?"
        : "Delete this?")) return;
    setEditing(null);
    onChange(serializeBlocks(blocks.filter((b) => b.id !== id)), "delete");
  }

  /** True when a block has been typed down to nothing. */
  function isEmpty(block: Block): boolean {
    const words = (nodes: Inline[]) =>
      nodes.some((n) => n.kind === "cites" || n.text.trim() !== "");
    if (block.kind === "table") {
      return ![...block.head, ...block.rows.flat()].some(words);
    }
    if (block.kind === "list") return !block.items.some((i) => words(i.inlines));
    if ("inlines" in block) return !words(block.inlines);
    return false;
  }

  /** Close a block, and drop it if there is nothing left in it.
   *
   *  The check waits for the next render rather than happening here: closing
   *  a block takes focus out of it, and the edit that empties it is still on
   *  its way in when the button is pressed. Judging it now would be judging
   *  the block as it stood a moment ago.  */
  function finish(id: string) {
    setEditing(null);
    setClosed(id);
  }

  useEffect(() => {
    if (!closed) return;
    const block = blocks.find((b) => b.id === closed);
    setClosed(null);
    if (!onChange || !block || !isEmpty(block)) return;
    onChange(serializeBlocks(blocks.filter((b) => b.id !== closed)), "drop-empty");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [closed, markdown]);

  /** Inline content out of an edited element, written back to its block.
   *  Called on every change, so it must be cheap and must write nothing when
   *  nothing differs - which replace() checks. */
  const commitInlines = (id: string, set: (b: Block, nodes: Inline[]) => Block) =>
    (root: HTMLElement) => replace(id, (b) => set(b, nodesToInlines(root)));


  /** Show or put away every run in one block at once. */
  function toggleBlock(block: Block) {
    const inlines = "inlines" in block ? block.inlines : [];
    const keys = inlines.map((n, i) => (n.kind === "cites" ? block.id + ":" + i : ""))
                        .filter(Boolean);
    if (!keys.length) return;
    const anyHidden = keys.some((k) => !shown[k]);
    setShown((prev) => {
      const next = { ...prev };
      keys.forEach((k) => { next[k] = anyHidden; });
      return next;
    });
  }

  const inlinesOf = (block: Block, nodes: Inline[]) => (
    <Inlines nodes={nodes} blockId={block.id} shown={shown} onToggle={toggle}
             byFilename={byFilename} gone={gone} onOpen={onOpen}
             lit={lit} onLight={setLit} />
  );

  /** The per-block controls. Always there, so they are never hunted for. */
  function Tools({ block }: { block: Block }) {
    const inlines = "inlines" in block ? block.inlines : [];
    const refs = citationsIn(inlines);
    const out = inlines.some((n, i) => n.kind === "cites" && shown[block.id + ":" + i]);
    const open = editing === block.id;
    if (!refs.length && !editable) return null;
    return (
      <span className="block-tools">
        {refs.length > 0 && !open && (
          <button type="button" className={out ? "tool on" : "tool"}
                  onClick={() => toggleBlock(block)}
                  title={out ? "Put the sources away"
                             : `Show all ${refs.length} sources`}>
            {out ? "Hide sources" : "Sources"}
          </button>
        )}
        {editable && (
          <button type="button" className={open ? "tool on" : "tool"}
                  onClick={() => (open ? finish(block.id) : setEditing(block.id))}
                  title={open ? "Finish editing" : "Edit this"}>
            {open ? "Done" : block.kind === "table" ? "Edit table" : "Edit"}
          </button>
        )}
        {editable && open && block.kind !== "heading" && (
          <button type="button" className="tool"
                  // Taken on the press, before the button has the focus and
                  // the cursor is gone from the text.
                  onMouseDown={(e) => { e.preventDefault(); caret.current = caretInBlock(); }}
                  // From the keyboard there was no press: the selection is
                  // still in the text, so it is taken here.
                  onClick={() => {
                    if (!caret.current) caret.current = caretInBlock();
                    setPicking(true);
                  }}
                  title="Cite one of this memo's sources where the cursor is">
            Insert footnote
          </button>
        )}
        {editable && open && onImageFile && (
          <button type="button" className="tool"
                  onClick={() => setPdfAt({
                    index: blocks.findIndex((b) => b.id === block.id) + 1,
                    file: null })}
                  title="Put pages of a PDF in after this, as images">
            Insert PDF pages
          </button>
        )}
        {editable && open && (
          <button type="button" className="tool"
                  onClick={() => insertPageBreak(
                    blocks.findIndex((b) => b.id === block.id) + 1)}
                  title="Start a new page of the PDF after this">
            Insert page break
          </button>
        )}
        {editable && open && (
          <button type="button" className="tool danger"
                  onClick={() => removeBlock(block.id)}
                  title="Take this out of the memo">
            Delete
          </button>
        )}
      </span>
    );
  }

  /** A place to start a new paragraph. Between every two blocks and at the
   *  end, quiet until the pointer is near it. */
  function Insert({ index }: { index: number }) {
    if (!editable) return null;
    const uploading = placing.includes(index) && (
      <p className="muted small">Putting the image in&hellip;</p>
    );
    if (adding === index) {
      return (
        <>
        {uploading}
        <p className="new-para" data-gap={index}>
          <Editable html="" deferred
                    onEdit={(root) => addParagraph(index, root)}
                    onSplit={(before) => {
                      addParagraph(index, before);
                      // Enter finishes this one and offers the next.
                      setAdding(index + 1);
                    }} />
          <span className="block-tools">
            <button type="button" className="tool on"
                    onClick={() => setAdding(null)}>Done</button>
          </span>
        </p>
        </>
      );
    }
    return (
      <>
        {uploading}
        <div className={dropAt === index ? "insert-point drop-here" : "insert-point"}
             data-gap={index}>
          <button type="button" onClick={() => { setEditing(null); setAdding(index); }}
                  title="Start a paragraph here, or paste an image into it">+</button>
        </div>
      </>
    );
  }

  return (
    <>
    <article className="memo doc" ref={article}
      // Dropped anywhere on the memo, an image goes into the gap nearest the
      // pointer, marked while it is held over it.
      onDragOver={(e) => {
        if (!takesFiles(e.dataTransfer)) return;
        e.preventDefault();
        const at = gapAt(e.clientY);
        if (at !== dropAt) setDropAt(at);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropAt(null);
      }}
      onDrop={(e) => {
        if (!takesFiles(e.dataTransfer)) return;
        // Not the browser's: an open block would take the file as a picture
        // of its own, and anywhere else the page would leave for the file.
        e.preventDefault();
        const at = dropAt ?? gapAt(e.clientY);
        setDropAt(null);
        const file = fileOf(e.dataTransfer);
        if (file && isPdf(file)) setPdfAt({ index: at, file });
        else if (file) insertImage(file, at);
      }}
      // Pasted, it goes after the block open, or where a paragraph is being
      // started. Text is the block's own and never reaches here.
      onPaste={(e) => {
        const file = fileOf(e.clipboardData);
        if (!file || !editable) return;
        e.preventDefault();
        const open = editing === null ? -1
          : blocks.findIndex((b) => b.id === editing);
        const at = adding ?? (open >= 0 ? open + 1 : null);
        if (at === null) return;
        // A paragraph started for the image is not wanted once it is in.
        setAdding(null);
        if (isPdf(file)) setPdfAt({ index: at, file });
        else insertImage(file, at);
      }}>
      {blocks.map((block, index) => {
        const content = (() => {
        switch (block.kind) {
          case "raw":
            return null;

          case "image": {
            const src = imageSrc?.(block.image);
            return (
              <figure key={block.id} className="doc-image">
                {src ? (
                  <img src={src} alt={block.alt}
                       onError={() => onImageError?.(block.image)} />
                ) : (
                  <span className="muted small">
                    {src === null ? "This image could not be found."
                                  : "Loading the image…"}
                  </span>
                )}
                {/* Nothing to type into: an image is put in or taken out. */}
                {editable && (
                  <span className="block-tools">
                    <button type="button" className="tool danger"
                            onClick={() => removeBlock(block.id)}
                            title="Take this image out of the memo">
                      Delete
                    </button>
                  </span>
                )}
              </figure>
            );
          }

          case "pagebreak":
            // Drawn on the screen as well, so where the PDF turns the page
            // is never a surprise. Nothing to type into: put in or taken out.
            return (
              <div key={block.id} className="doc-pagebreak">
                <span>Page break</span>
                {editable && (
                  <span className="block-tools">
                    <button type="button" className="tool danger"
                            onClick={() => removeBlock(block.id)}
                            title="Take this page break out of the memo">
                      Delete
                    </button>
                  </span>
                )}
              </div>
            );

          case "rule":
            return <hr key={block.id} />;

          case "heading": {
            const H = ("h" + Math.min(block.level + 1, 6)) as "h2";
            return (
              <H key={block.id} className={"doc-h" + block.level}>
                {editing === block.id ? (
                  <Editable html={inlinesToHtml(block.inlines, goneRef)}
                            onEdit={commitInlines(block.id, (b, nodes) =>
                              ({ ...b, inlines: nodes } as Block))} />
                ) : inlinesOf(block, block.inlines)}
                <Tools block={block} />
              </H>
            );
          }

          case "quote":
            return (
              <div key={block.id} className={"callout " + calloutKind(block.inlines)}>
                <p>
                  {editing === block.id ? (
                    <Editable html={inlinesToHtml(block.inlines, goneRef)}
                              onEdit={commitInlines(block.id, (b, nodes) =>
                                ({ ...b, inlines: nodes } as Block))} />
                  ) : inlinesOf(block, block.inlines)}
                  <Tools block={block} />
                </p>
              </div>
            );

          case "list":
            // Keyed by position and count, as the table rows are, and for
            // the same reason: breaking an item in two shifts the ones below.
            const items = block.items.map((it, k) => (
              <li key={k + "/" + block.items.length}>
                {editing === block.id ? (
                  <Editable html={inlinesToHtml(it.inlines, goneRef)}
                            onEdit={(root) => replace(block.id, (b) => {
                              if (b.kind !== "list") return b;
                              const next = b.items.slice();
                              next[k] = { ...next[k], inlines: nodesToInlines(root) };
                              return { ...b, items: next };
                            })}
                            onSplit={(before, after) =>
                              splitBlock(block, before, after, k)} />
                ) : inlinesOf(block, it.inlines)}
              </li>
            ));
            return (
              <div className="list-wrap" key={block.id}>
                {block.ordered ? <ol>{items}</ol> : <ul>{items}</ul>}
                <Tools block={block} />
              </div>
            );

          case "table":
            return (
              <div className="table-wrap" key={block.id}>
                <div className="table-tools"><Tools block={block} /></div>
                <table className={editing === block.id ? "editing" : undefined}>
                  <thead className={block.head.every((c) => c.length === 0)
                                    ? "empty" : undefined}>
                    <tr>
                      {editing === block.id && <th className="row-handle" />}
                      {block.head.map((c, k) => (
                        <th key={k} className={"al-" + (block.align[k] ?? "left")}>
                          {editing === block.id ? (
                            <Editable html={inlinesToHtml(c, goneRef)}
                                      onEdit={(root) => replace(block.id, (b) => {
                                        if (b.kind !== "table") return b;
                                        const head = b.head.slice();
                                        head[k] = nodesToInlines(root);
                                        return { ...b, head };
                                      })} />
                          ) : inlinesOf(block, c)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {/* The count is part of the key on purpose. An editable
                        cell holds its own content and is never re-rendered
                        from the model while it is open, so rows keyed by
                        position alone kept their old text when a row was put
                        in above them - the table shifted and the words did
                        not. Changing the count remounts the rows, and each
                        cell reads its content again. A move leaves the count
                        as it was, so the moves are counted into the key as
                        well. */}
                    {block.rows.map((row, r) => (
                      <tr key={r + "/" + block.rows.length + "/" + moved}
                          className={editing !== block.id || dropRow?.r !== r ? undefined
                                     : dropRow.below ? "drop-below" : "drop-above"}
                          // Only a row of this table, dragged by its grip.
                          // An image held over the memo is the article's.
                          onDragOver={(e) => {
                            const from = dragging.current;
                            if (!from || from.id !== block.id) return;
                            e.preventDefault();
                            e.dataTransfer.dropEffect = "move";
                            const { below, to } = rowGap(e, r);
                            // No line where the drop would leave it as it is.
                            const still = to === from.from || to === from.from + 1;
                            if (still) { if (dropRow) setDropRow(null); return; }
                            if (dropRow?.r !== r || dropRow.below !== below) {
                              setDropRow({ r, below });
                            }
                          }}
                          onDrop={(e) => {
                            const from = dragging.current;
                            if (!from || from.id !== block.id) return;
                            e.preventDefault();
                            e.stopPropagation();
                            dragging.current = null;
                            setDropRow(null);
                            moveRow(block.id, from.from, rowGap(e, r).to);
                          }}>
                        {editing === block.id && (
                          <td className="row-handle">
                            <span className="grip" draggable
                                  title="Drag to move this row"
                                  // A cell still being typed in is written
                                  // back first, so the move carries it.
                                  onMouseDown={() =>
                                    (document.activeElement as HTMLElement | null)?.blur()}
                                  onDragStart={(e) => {
                                    dragging.current = { id: block.id, from: r };
                                    e.dataTransfer.effectAllowed = "move";
                                    // Firefox starts no drag carrying nothing.
                                    // A type of our own, so no other page or
                                    // program takes it as text.
                                    e.dataTransfer.setData("application/x-arqedia-row",
                                                           String(r));
                                    const tr = e.currentTarget.closest("tr");
                                    if (tr) e.dataTransfer.setDragImage(tr, 12, tr.offsetHeight / 2);
                                  }}
                                  onDragEnd={() => {
                                    dragging.current = null;
                                    setDropRow(null);
                                  }}>&#x283F;</span>
                            <button type="button" onClick={() => insertRow(block.id, r)}
                                    title="Put a row in above this one">+</button>
                            <button type="button" className="drop"
                                    onClick={() => removeRow(block.id, r)}
                                    title="Take this row out">&times;</button>
                          </td>
                        )}
                        {row.map((c, k) => (
                          <td key={k} className={"al-" + (block.align[k] ?? "left")}>
                            {editing === block.id ? (
                              <Editable html={inlinesToHtml(c, goneRef)}
                                        onEdit={(root) => replace(block.id, (b) => {
                                          if (b.kind !== "table") return b;
                                          const rows = b.rows.map((x) => x.slice());
                                          rows[r][k] = nodesToInlines(root);
                                          return { ...b, rows };
                                        })} />
                            ) : inlinesOf(block, c)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {editing === block.id && (
                  <div className="row-tools">
                    <button type="button" className="tool"
                            onClick={() => insertRow(block.id, block.rows.length)}>
                      Add a row at the end
                    </button>
                  </div>
                )}
              </div>
            );

          default:
            return (
              <p key={block.id}>
                {editing === block.id ? (
                  <Editable html={inlinesToHtml(block.inlines, goneRef)}
                            onEdit={commitInlines(block.id, (b, nodes) =>
                              ({ ...b, inlines: nodes } as Block))}
                            onSplit={(before, after) =>
                              splitBlock(block, before, after)} />
                ) : inlinesOf(block, block.inlines)}
                <Tools block={block} />
              </p>
            );
        }
        })();
        // A place to start a paragraph before every block, and one at the
        // end, so there is nowhere in the memo a new one cannot go.
        return (
          <Fragment key={block.id}>
            <Insert index={index} />
            {content}
          </Fragment>
        );
      })}
      <Insert index={blocks.length} />
    </article>
    {/* After the memo, not in it: a drawer stacks in document order. */}
    {picking && (
      <FootnotePicker sources={citable} ready={!!caret.current}
                      onPick={insertFootnote}
                      onClose={() => { caret.current = null; setPicking(false); }} />
    )}
    {pdfAt && (
      <PdfPagePicker sources={pdfSources} dropped={pdfAt.file}
                     onInsert={(pages) => {
                       const at = pdfAt.index;
                       setPdfAt(null);
                       insertImages(pages, at);
                     }}
                     onClose={() => setPdfAt(null)} />
    )}
    </>
  );
}
