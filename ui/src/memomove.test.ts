import { describe, expect, it } from "vitest";
import { moveBlock, parseBlocks, sectionBounds } from "./memodoc";
import { diffStep, undoStep } from "./undo";

// Moving a block by its grip, within its own section (9 November 2026).

const memo = [
  "# Credit memorandum",
  "",
  "## I. Summary",
  "",
  "First.",
  "",
  "| A | B |",
  "|---|---|",
  "| 1 | 2 |",
  "",
  "### Detail",
  "",
  "Second.",
  "",
  "## II. Risks",
  "",
  "Third.",
].join("\n");

// 0 h1, 1 h2 Summary, 2 First, 3 table, 4 h3, 5 Second, 6 h2 Risks, 7 Third
const blocks = parseBlocks(memo);

describe("a block's section", () => {
  it("runs from the heading above to the next heading at level two or one", () => {
    expect(blocks.map((b) => b.kind)).toEqual(
      ["heading", "heading", "para", "table", "heading", "para", "heading", "para"]);
    expect(sectionBounds(blocks, 2)).toEqual({ lo: 2, hi: 6 });
    // A level-three heading is inside the section, not a bound of it.
    expect(sectionBounds(blocks, 5)).toEqual({ lo: 2, hi: 6 });
    expect(sectionBounds(blocks, 7)).toEqual({ lo: 7, hi: 8 });
  });
});

describe("moving a block", () => {
  it("moves a paragraph down past a table, every character kept", () => {
    const after = moveBlock(blocks, 2, 4)!;
    expect(after).toBe(memo.replace("First.\n\n| A | B |\n|---|---|\n| 1 | 2 |",
                                    "| A | B |\n|---|---|\n| 1 | 2 |\n\nFirst."));
  });

  it("moves a table up, past a level-three heading", () => {
    const after = moveBlock(blocks, 5, 2)!;
    const kinds = parseBlocks(after).map((b) => b.kind);
    expect(kinds).toEqual(
      ["heading", "heading", "para", "para", "table", "heading", "heading", "para"]);
    expect(parseBlocks(after)[2].source.trim()).toBe("Second.");
  });

  it("will not leave its section", () => {
    expect(moveBlock(blocks, 2, 7)).toBeNull();
    expect(moveBlock(blocks, 7, 3)).toBeNull();
  });

  it("does nothing where it would stay put, and never moves a heading", () => {
    expect(moveBlock(blocks, 2, 2)).toBeNull();
    expect(moveBlock(blocks, 2, 3)).toBeNull();
    expect(moveBlock(blocks, 4, 2)).toBeNull();
  });

  it("keeps the memo's end as it was when the last block moves", () => {
    const tail = parseBlocks("## I. A\n\nOne.\n\nTwo.");
    expect(moveBlock(tail, 2, 1)).toBe("## I. A\n\nTwo.\n\nOne.");
  });

  it("puts a blank line between two blocks that ran straight on", () => {
    // A paragraph running straight into a table: moved apart, the paragraph
    // must not run on into the next one.
    const tight = parseBlocks("## I. A\n\nLead in.\n| A |\n|---|\n| 1 |\n\nAfter.");
    expect(tight.map((b) => b.kind)).toEqual(["heading", "para", "table", "para"]);
    const after = moveBlock(tight, 2, 4)!;
    expect(parseBlocks(after).map((b) => b.kind))
      .toEqual(["heading", "para", "para", "table"]);
  });

  it("is one step to undo", () => {
    const after = moveBlock(blocks, 2, 4)!;
    const step = diffStep("move", memo, after)!;
    expect(undoStep(after, step)).toBe(memo);
  });
});
