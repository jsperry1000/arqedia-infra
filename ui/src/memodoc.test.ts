import { describe, expect, it } from "vitest";
import { blockToMarkdown, footnoteRef, headingText, imageMarkdown, imagesIn,
         isCitable, parseBlocks,
         sectionLabel, serializeBlocks, type Block } from "./memodoc";
import { diffStep, undoStep } from "./undo";

// A person's own image in a memo (graphics-insert): the eighth block kind.

const PNG = "a".repeat(32) + ".png";
const JPG = "b".repeat(32) + ".jpg";

const memo = [
  "# Credit memorandum",
  "",
  "## I. Summary",
  "",
  "The borrower is sound.",
  "",
  `![The group structure](image:${PNG})`,
  "",
  "## II. Risks",
  `![](image:${JPG})`,
].join("\n");

describe("an image", () => {
  it("is a block of its own, with its alt and its name", () => {
    const images = parseBlocks(memo).filter((b) => b.kind === "image");
    expect(images).toEqual([
      expect.objectContaining({ alt: "The group structure", image: PNG }),
      expect.objectContaining({ alt: "", image: JPG }),
    ]);
  });

  it("comes back character for character", () => {
    expect(serializeBlocks(parseBlocks(memo))).toBe(memo);
    expect(serializeBlocks(parseBlocks(memo + "\n"))).toBe(memo + "\n");
  });

  it("ends the paragraph above it", () => {
    const text = `One line.\n![x](image:${PNG})\nAnother.`;
    expect(parseBlocks(text).map((b) => b.kind)).toEqual(["para", "image", "para"]);
    expect(serializeBlocks(parseBlocks(text))).toBe(text);
  });

  it("is only the line the API carries: on its own, by a server name", () => {
    for (const text of [
      `See ![x](image:${PNG}) here.`,          // inside a sentence
      `  ![x](image:${PNG})`,                  // indented
      "![x](image:ab12.png)",                  // not a server name
      `![x](image:${"a".repeat(32)}.gif)`,     // not a type it takes
      `![x](https://example.com/${PNG})`,      // a link, not an image of ours
    ]) {
      expect(parseBlocks(text).some((b) => b.kind === "image")).toBe(false);
      expect(imagesIn(text)).toEqual([]);
    }
  });

  it("is named once however often it is shown", () => {
    expect(imagesIn(memo + `\n\n![again](image:${PNG})`)).toEqual([PNG, JPG]);
  });

  it("is written with an alt that cannot end its own line", () => {
    expect(imageMarkdown("a]b\nc", PNG)).toBe(`![a b c](image:${PNG})`);
    const block: Block = { id: "new", source: "", kind: "image",
                           alt: "Chart", image: PNG };
    expect(blockToMarkdown(block, "\n\n")).toBe(`![Chart](image:${PNG})\n\n`);
  });

  it("put in is one step, and undoing it gives the memo back", () => {
    const blocks = parseBlocks(memo);
    const block: Block = { id: "new", source: "", kind: "image",
                           alt: "Chart", image: JPG };
    const after = serializeBlocks([...blocks.slice(0, 3),
      { ...block, source: blockToMarkdown(block, "\n") }, ...blocks.slice(3)]);
    expect(after).toContain(`sound.\n\n![Chart](image:${JPG})\n\n![The group`);
    const step = diffStep("image", memo, after)!;
    expect(step.before).toHaveLength(0);
    expect(step.after).toEqual([`![Chart](image:${JPG})\n`]);
    expect(undoStep(after, step)).toBe(memo);
  });
});

// A section with no numeral was written "## . Executive Summary" until 26
// October 2026. Shown as the title alone; stored as it was.
describe("a section heading with no numeral", () => {
  const old = "## . Executive Summary\n\nText.\n\n## II. Risks\n\n### . Kept";

  it("shows the title alone, and a numbered one as it was", () => {
    const heads = parseBlocks(old).filter((b) => b.kind === "heading");
    expect(heads.map((b) => b.kind === "heading" && b.inlines)).toEqual([
      [{ kind: "text", text: "Executive Summary" }],
      [{ kind: "text", text: "II. Risks" }],
      // Not a section heading: composition never wrote one there.
      [{ kind: "text", text: ". Kept" }],
    ]);
  });

  it("is written back as stored until somebody edits it", () => {
    expect(serializeBlocks(parseBlocks(old))).toBe(old);
    const head = parseBlocks(old)[0];
    expect(blockToMarkdown(head, "\n\n")).toBe("## Executive Summary\n\n");
  });

  it("is named without the stop wherever a heading is quoted", () => {
    expect(headingText("## . Executive Summary")).toBe("Executive Summary");
    expect(headingText("## II. Risks")).toBe("II. Risks");
    expect(sectionLabel("", "Executive Summary")).toBe("Executive Summary");
    expect(sectionLabel("  ", "Executive Summary")).toBe("Executive Summary");
    expect(sectionLabel("IV", "Returns")).toBe("IV. Returns");
  });
});

// A footnote put in by hand (footnote-insert): one of the memo's sources,
// with a page or without.
describe("a footnote put in by hand", () => {
  it("is offered only for a name the save reads whole", () => {
    expect(isCitable("STG-Short-term-Debt-as-of-07-31-2026.pdf")).toBe(true);
    expect(isCitable("Accounts_(2025).XLSX")).toBe(true);
    expect(isCitable("Inbox J Scott.pdf")).toBe(false);   // read from the space
    expect(isCitable("scan.png")).toBe(false);            // never a citation
  });

  it("names the page where one is given, and the file alone where not", () => {
    expect(footnoteRef("a.pdf", 4)).toBe("a.pdf, page 4");
    expect(footnoteRef("a.pdf", null)).toBe("a.pdf");
  });

  it("reads back as a citation, beside one already there", () => {
    const text = "Interest-free. *b.pdf, page 2* *" + footnoteRef("a.pdf", 4) + "*";
    const para = parseBlocks(text)[0];
    expect(para.kind === "para" && para.inlines).toEqual([
      { kind: "text", text: "Interest-free. " },
      { kind: "cites", refs: ["b.pdf, page 2", "a.pdf, page 4"] },
    ]);
  });
});
