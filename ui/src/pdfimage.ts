/**
 * A page or two of a PDF, put into a memo as images (29 October 2026).
 *
 * THE PAGE GOES IN AS A PICTURE OF ITSELF. It is drawn in the browser and
 * uploaded as a PNG, so what the memo holds is an image like any other: the
 * image exception of 26 October covers it, the save checks its bytes, the
 * revision keeps its own copy and the PDF prints it. Nothing on the server
 * knows a PDF was involved. Attaching a whole document as an appendix is the
 * longer answer and is not this.
 *
 * ITS ALT TEXT MUST NOT READ AS A CITATION. The save reads every
 * "name.pdf" and every "name, page 3" in the memo - alt text included - as a
 * claim to cite, and refuses one that is not a source of the memo
 * (revise_memo). A page drawn from a file off somebody's own computer is not
 * a source, so its alt names the file without its extension and the page as
 * "p. 3". The test holds this against the server's two patterns.
 */

// The extensions a citation is read from (CITATION_FILE in memodoc.ts, and
// the save's own pattern).
const CITED_EXTENSION = /\.(?:pdf|docx|xlsx|txt|json|xml)\b/gi;

/** The width a page is drawn at, in pixels: sharp in the memo and its PDF,
 *  and well inside the 10 MB an image may be as a PNG. */
export const PAGE_WIDTH = 1600;

/** Drawn no larger than this, however small the page: a postcard-sized page
 *  at 1600 pixels is mostly enlargement. */
export const MAX_SCALE = 3;

/** A file's name with every extension a citation reads taken out, and
 *  anything that is not a letter, a digit or a plain mark turned to a
 *  space. */
export function pdfBase(filename: string): string {
  return filename.replace(CITED_EXTENSION, "")
    .replace(/[^A-Za-z0-9 ._()-]+/g, " ").replace(/\s+/g, " ").trim()
    || "PDF";
}

/** What an inserted page says it is. */
export function pageAlt(filename: string, page: number): string {
  return pdfBase(filename) + ", p. " + page;
}

/** The name the page's PNG is uploaded under. The server mints its own name
 *  for storage; this is what the browser hands over. */
export function pageFileName(filename: string, page: number): string {
  return pdfBase(filename).replace(/[ ()]+/g, "-").replace(/-+/g, "-")
    .replace(/^-|-$/g, "") + "-p" + page + ".png";
}

/** The scale a page `width` points wide is drawn at. */
export function pageScale(width: number): number {
  return width > 0 ? Math.min(MAX_SCALE, PAGE_WIDTH / width) : 1;
}
