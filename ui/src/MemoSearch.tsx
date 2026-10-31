import { useEffect, useRef, useState, type RefObject } from "react";
import { SearchBox } from "./shell";

/**
 * Search within a memo (UI-01).
 *
 * Every match in the memo is marked, the current one more strongly, with
 * "3 of 11" and a way to the next and the last. The same search covers a
 * paragraph open for editing, because editing happens in the document itself.
 *
 * THE MARKS ARE NOT ELEMENTS. They are the browser's CSS Custom Highlight API
 * (Baseline 2025): ranges over the text that is already there, painted by
 * `::highlight()` in index.css. Wrapping matches in elements would change the
 * DOM React renders and the editor types into, and an edit box would take the
 * wrapping in as part of the text. Where the API is missing the count and the
 * jumps still work; only the marks are not drawn.
 *
 * NOT IN A CITATION, as the backlog item asks: a search for "page 1" would
 * otherwise light every reference and drown what is being looked for. Nor in
 * a control: the block tools, the insert points and every button.
 */

// What is never searched. A shown citation run, a put-away one (a button),
// the tools on a block, the gaps between blocks, and a page break's label.
const SKIP = "button, .cite-run, .block-tools, .insert-point, .doc-pagebreak";

// The text of one block is searched as one string, so a match runs across
// bold or italic within it; it never runs from one block into the next.
const BLOCK = "p, li, td, th, h1, h2, h3, h4, h5, h6, blockquote, pre, "
  + "figcaption, div, article";

const ALL = "memo-search";
const CURRENT = "memo-search-current";

function escaped(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Every match of `query` in the memo documents under `root`, in order. */
export function findMatches(root: ParentNode, query: string): Range[] {
  if (!query.trim()) return [];
  const pattern = new RegExp(escaped(query), "giu");
  const ranges: Range[] = [];

  const search = (run: Text[]) => {
    if (run.length === 0) return;
    const starts: number[] = [];
    let text = "";
    for (const node of run) {
      starts.push(text.length);
      text += node.data;
    }
    // The node holding offset `at`; an end offset may sit at a node's end.
    const place = (at: number, end: boolean): [Text, number] => {
      let k = run.length - 1;
      while (k > 0 && (end ? starts[k] >= at : starts[k] > at)) k--;
      return [run[k], at - starts[k]];
    };
    for (const m of text.matchAll(pattern)) {
      if (m[0].length === 0) continue;
      const range = document.createRange();
      range.setStart(...place(m.index, false));
      range.setEnd(...place(m.index + m[0].length, true));
      ranges.push(range);
    }
  };

  for (const article of Array.from(root.querySelectorAll("article.memo"))) {
    const walker = document.createTreeWalker(article, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => node.parentElement?.closest(SKIP)
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    let run: Text[] = [];
    let block: Element | null = null;
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const at = node.parentElement?.closest(BLOCK) ?? null;
      if (at !== block) {
        search(run);
        run = [];
        block = at;
      }
      run.push(node as Text);
    }
    search(run);
  }
  return ranges;
}

const painted = typeof CSS !== "undefined" && "highlights" in CSS;

function paint(ranges: Range[], at: number) {
  if (!painted) return;
  CSS.highlights.set(ALL, new Highlight(...ranges));
  if (ranges[at]) CSS.highlights.set(CURRENT, new Highlight(ranges[at]));
  else CSS.highlights.delete(CURRENT);
}

function bringIntoView(range: Range | undefined) {
  const el = range?.startContainer.parentElement;
  el?.scrollIntoView({ block: "center" });
}

export function MemoSearch({ within }: { within: RefObject<HTMLElement | null> }) {
  const [query, setQuery] = useState("");
  const [ranges, setRanges] = useState<Range[]>([]);
  const [at, setAt] = useState(0);
  const atRef = useRef(0);
  atRef.current = at;

  // A new search starts at the first match and goes to it.
  useEffect(() => {
    const root = within.current;
    const found = root ? findMatches(root, query) : [];
    setRanges(found);
    setAt(0);
    bringIntoView(found[0]);
  }, [query, within]);

  // The memo changes under a search - a block typed in, opened or closed, a
  // rewrite accepted - so it is searched again, staying on the same match
  // where there still is one, and without moving the page.
  useEffect(() => {
    const root = within.current;
    if (!root || !query.trim()) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const observer = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const found = findMatches(root, query);
        setRanges(found);
        setAt(Math.min(atRef.current, Math.max(found.length - 1, 0)));
      }, 200);
    });
    observer.observe(root, { childList: true, subtree: true,
                             characterData: true });
    return () => { observer.disconnect(); clearTimeout(timer); };
  }, [query, within]);

  useEffect(() => { paint(ranges, at); }, [ranges, at]);

  useEffect(() => () => {
    if (!painted) return;
    CSS.highlights.delete(ALL);
    CSS.highlights.delete(CURRENT);
  }, []);

  function step(by: number) {
    if (ranges.length === 0) return;
    const next = (at + by + ranges.length) % ranges.length;
    setAt(next);
    bringIntoView(ranges[next]);
  }

  return (
    <div className="memo-search" role="search">
      <SearchBox type="search" value={query} placeholder="Search this memo"
                 aria-label="Search this memo"
                 onChange={(e) => setQuery(e.target.value)}
                 onKeyDown={(e) => {
                   if (e.key === "Enter") {
                     e.preventDefault();
                     step(e.shiftKey ? -1 : 1);
                   } else if (e.key === "Escape") {
                     setQuery("");
                   }
                 }} />
      {query.trim() && (
        <>
          <span className="count" aria-live="polite">
            {ranges.length === 0 ? "No matches"
              : `${at + 1} of ${ranges.length}`}
          </span>
          <a onClick={() => step(-1)} aria-disabled={ranges.length === 0}
             title="Previous match (Shift+Enter)">&uarr;</a>
          <a onClick={() => step(1)} aria-disabled={ranges.length === 0}
             title="Next match (Enter)">&darr;</a>
        </>
      )}
    </div>
  );
}
