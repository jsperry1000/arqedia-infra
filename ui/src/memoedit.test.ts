import { describe, expect, it } from "vitest";
import { chipLabel, inlinesToHtml, nodesToInlines } from "./memoedit";
import { inlinesToMarkdown, parseInlines } from "./memodoc";

// One mark a reference in the editor, so one can be taken out alone.

const RUN = "The rent is $1,340. *Market-Research-Report.pdf, page 2* "
  + "*Financial-Confirmations.pdf, page 2* *Inspection.pdf, page 1*";
const REFS = ["Market-Research-Report.pdf, page 2",
              "Financial-Confirmations.pdf, page 2", "Inspection.pdf, page 1"];

// What the browser holds for an open block, as the nodes nodesToInlines
// reads: text, and a mark carrying its reference. No DOM in these tests.
const text = (value: string) => ({ nodeType: 3, nodeValue: value });
const chip = (ref: string) => ({
  nodeType: 1, tagName: "SPAN", style: {}, childNodes: [],
  getAttribute: (name: string) => (name === "data-refs" ? JSON.stringify([ref]) : null),
});
const block = (...nodes: object[]) => ({ childNodes: nodes }) as unknown as Node;

describe("a run of citations in the editor", () => {
  it("is a mark for each reference", () => {
    const html = inlinesToHtml(parseInlines(RUN));
    expect(html.match(/class="cite-chip"/g)).toHaveLength(3);
    for (const ref of REFS) expect(html).toContain(JSON.stringify([ref]).replace(/"/g, "&quot;"));
  });

  it("comes back as the same run when nothing is touched", () => {
    const out = nodesToInlines(block(text("The rent is $1,340. "), ...REFS.map(chip)));
    expect(inlinesToMarkdown(out)).toBe(RUN);
  });

  it("loses only the reference whose mark is deleted", () => {
    const out = nodesToInlines(block(text("The rent is $1,340. "),
                                     chip(REFS[0]), chip(REFS[2])));
    expect(inlinesToMarkdown(out)).toBe(
      "The rent is $1,340. *Market-Research-Report.pdf, page 2* "
      + "*Inspection.pdf, page 1*");
  });

  it("keeps marks with a space between as one run", () => {
    const out = nodesToInlines(block(text("Rent. "), chip(REFS[0]), text(" "),
                                     chip(REFS[2]), text(" More.")));
    expect(out.filter((n) => n.kind === "cites")).toHaveLength(1);
  });

  it("marks a reference to a deleted document", () => {
    const html = inlinesToHtml(parseInlines(RUN),
                               (r) => r.startsWith("Market-Research"));
    expect(html.match(/class="cite-chip gone"/g)).toHaveLength(1);
    expect(html.indexOf("cite-chip gone")).toBeLessThan(html.indexOf("Financial"));
  });

  it("says which reference it is", () => {
    expect(chipLabel("Inspection.pdf, page 1")).toBe("Inspection, p. 1");
    expect(chipLabel("Meridian-Place-Market-Research-Report-Mock.pdf, page 2"))
      .toBe("…Market-Research-Report-Mock, p. 2");
    // Two files of one deal, told apart.
    expect(chipLabel("Meridian-Place-Property-Inspection-Report-Mock.pdf, page 1"))
      .not.toBe(chipLabel("Meridian-Place-Property-Appraisal-Valuation-Report-Mock.pdf, page 1"));
  });
});
