import { describe, expect, it } from "vitest";
import type { DocumentDetail, ExtractedValue } from "./api";
import { groupByType, pageOf, TYPE_UNKNOWN, UNCLASSIFIED } from "./footnotefacts";

// The footnote picker, found by fact or by document type (29 October 2026).

function value(label: string, v: string | null, page: number | null,
               kind: string | null = "page"): ExtractedValue {
  return { field_id: label.toLowerCase().replace(/\W+/g, "_"), label, value: v,
           locator_kind: kind, locator_index: page, row: 0 };
}

function detail(id: number, type: string | null,
                values: ExtractedValue[]): DocumentDetail {
  return { document_id: id, filename: "", document_type: type, pages: null,
           method: null, values, missing: [], expected: 0, memos: 0,
           charged: false, read_under: null, revision_in_use: 1,
           not_in_use: [] };
}

const sources = [
  { name: "Term-sheet.pdf", documentId: 1 },
  { name: "Corporate-presentation.pdf", documentId: 2 },
  { name: "Accounts.xlsx", documentId: 3 },
  { name: "Letter.pdf", documentId: 4 },
];

const details = {
  1: detail(1, "Term sheet", [
    value("Facility amount", "USD 2,000,000", 2),
    value("Tenor", "12 months", 3),
  ]),
  2: detail(2, "Corporate presentation", [
    value("Facility amount", "USD 2,000,000", 7),
    value("Facility amount", "USD 2m", 7),
    value("Headquarters", "Geneva", 1),
  ]),
  3: detail(3, "Financial statements", [
    value("Revenue", "USD 14m", 2, "sheet"),
  ]),
  4: detail(4, null, [value("Facility amount", null, 1)]),
};

describe("nothing typed", () => {
  it("is every source under its type, and no facts", () => {
    expect(groupByType(sources, details, "")).toEqual([
      { type: "Corporate presentation", documents: ["Corporate-presentation.pdf"], facts: [] },
      { type: "Financial statements", documents: ["Accounts.xlsx"], facts: [] },
      { type: UNCLASSIFIED, documents: ["Letter.pdf"], facts: [] },
      { type: "Term sheet", documents: ["Term-sheet.pdf"], facts: [] },
    ]);
  });

  it("puts a document whose values have not come back under a type not known, last", () => {
    const groups = groupByType(sources, { 1: details[1] }, "");
    expect(groups.map((g) => g.type)).toEqual(["Term sheet", TYPE_UNKNOWN]);
    expect(groups[1].documents).toEqual(
      ["Accounts.xlsx", "Corporate-presentation.pdf", "Letter.pdf"]);
  });
});

describe("a fact", () => {
  it("is found by its label, with every place it was read and its page", () => {
    const groups = groupByType(sources, details, "facility");
    expect(groups).toEqual([
      { type: "Corporate presentation", documents: [], facts: [
        { label: "Facility amount", places: [
          { name: "Corporate-presentation.pdf", page: 7,
            values: ["USD 2,000,000", "USD 2m"] }] }] },
      { type: "Term sheet", documents: [], facts: [
        { label: "Facility amount", places: [
          { name: "Term-sheet.pdf", page: 2, values: ["USD 2,000,000"] }] }] },
    ]);
  });

  it("is found by its value, every word in any order", () => {
    const groups = groupByType(sources, details, "geneva");
    expect(groups.flatMap((g) => g.facts.map((f) => f.label))).toEqual(["Headquarters"]);
    expect(groupByType(sources, details, "months 12")[0].facts[0].label).toBe("Tenor");
  });

  it("read with no value is not offered", () => {
    expect(groupByType(sources, details, "facility")
      .some((g) => g.documents.includes("Letter.pdf")
                   || g.facts.some((f) => f.places.some((p) => p.name === "Letter.pdf"))))
      .toBe(false);
  });

  it("from a sheet cites its file alone", () => {
    const [group] = groupByType(sources, details, "revenue");
    expect(group.facts[0].places[0]).toEqual(
      { name: "Accounts.xlsx", page: null, values: ["USD 14m"] });
  });
});

describe("a document type", () => {
  it("lists the documents of that type", () => {
    expect(groupByType(sources, details, "term sheet")).toEqual([
      { type: "Term sheet", documents: ["Term-sheet.pdf"], facts: [] },
    ]);
  });

  it("and a name still finds its document, as it did", () => {
    expect(groupByType(sources, details, "corporate-pres")[0].documents)
      .toEqual(["Corporate-presentation.pdf"]);
  });
});

describe("a page", () => {
  it("is a page only where the value was read from one", () => {
    expect(pageOf("page", 4)).toBe(4);
    expect(pageOf("sheet", 2)).toBeNull();
    expect(pageOf("section", 2)).toBeNull();
    expect(pageOf("page", null)).toBeNull();
    expect(pageOf("page", 0)).toBeNull();
  });
});
