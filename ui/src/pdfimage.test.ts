import { describe, expect, it } from "vitest";
import { imageMarkdown } from "./memodoc";
import { MAX_SCALE, pageAlt, pageFileName, pageScale, pdfBase } from "./pdfimage";

// A page of a PDF put into a memo as an image (29 October 2026).

// The two patterns revise_memo in lambda/api/app.py reads citations with,
// copied here so the test fails if an alt would trip them. A copy, because
// the server is Python and the rule it enforces is the thing being held.
// The server writes the dash as \- ; at the end of a class it needs no escape.
const SERVER_NAMED_PAGE = /([A-Za-z0-9._()-]{3,})\s*,\s*(?:page|section|sheet)\s+\d+/gi;
const SERVER_FILENAME = /[A-Za-z0-9._()-]+\.(?:pdf|docx|xlsx|txt|json|xml)/g;

function claims(text: string): string[] {
  return [...text.matchAll(SERVER_NAMED_PAGE)].map((m) => m[1])
    .concat([...text.matchAll(SERVER_FILENAME)].map((m) => m[0]));
}

describe("an inserted page's alt text", () => {
  it("names the file and the page", () => {
    expect(pageAlt("Corporate-presentation.pdf", 2)).toBe("Corporate-presentation, p. 2");
  });

  it("makes no citation claim the save would check, whatever the file is called", () => {
    for (const name of ["Term-sheet.pdf", "board pack (final).PDF", "a.pdf.pdf",
                        "Accounts.xlsx.pdf", "report, page 4.pdf", "x.pdf"]) {
      const line = imageMarkdown(pageAlt(name, 12), "a".repeat(32) + ".png");
      expect(claims(line), name).toEqual([]);
    }
  });

  it("falls back to PDF where nothing of the name is left", () => {
    expect(pdfBase(".pdf")).toBe("PDF");
    expect(pdfBase("✓✓✓.pdf")).toBe("PDF");
  });
});

describe("the uploaded file", () => {
  it("is a PNG named for the file and page", () => {
    expect(pageFileName("board pack (final).pdf", 3)).toBe("board-pack-final-p3.png");
  });
});

describe("the scale a page is drawn at", () => {
  it("brings an A4 page, 595 points wide, to 1600 pixels", () => {
    expect(Math.round(595 * pageScale(595))).toBe(1600);
  });

  it("does not blow a small page up past three times", () => {
    expect(pageScale(200)).toBe(MAX_SCALE);
  });
});
