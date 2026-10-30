import { describe, expect, it } from "vitest";
import { blockToMarkdown, indentLevel, indentOf, MAX_INDENT, parseBlocks,
         reindent, serializeBlocks, toggleBullets, trailingOf,
         type Block } from "./memodoc";

// Bullets and indent in the editor (30 October 2026).

/** The memo with one block swapped for what toggleBullets makes of it, as
 *  MemoDocument writes it. */
function toggled(markdown: string, index: number): string {
  const blocks = parseBlocks(markdown);
  const block = blocks[index];
  const next = toggleBullets(block);
  return serializeBlocks(blocks.flatMap((b) => b.id !== block.id ? [b]
    : next.map((n, k) => ({ ...n, source: blockToMarkdown(n,
        k === next.length - 1 ? trailingOf(block.source) : "\n") }))));
}

describe("an indent", () => {
  it("is two spaces a level, a tab four, and stops at the most", () => {
    expect(indentLevel("")).toBe(0);
    expect(indentLevel("  - ")).toBe(1);
    expect(indentLevel("\t")).toBe(2);
    expect(indentLevel(" ".repeat(20))).toBe(MAX_INDENT);
    expect(indentOf(-1)).toBe("");
    expect(indentOf(MAX_INDENT + 2)).toBe("  ".repeat(MAX_INDENT));
  });

  it("moves a list item and keeps its marker", () => {
    expect(reindent("- ", 2)).toBe("    - ");
    expect(reindent("    3. ", 0)).toBe("3. ");
  });

  it("on a paragraph is read back as the same paragraph", () => {
    const [block] = parseBlocks("    Indented twice.\n");
    expect(block.kind).toBe("para");
    expect(block.kind === "para" && indentLevel(block.indent)).toBe(2);
  });
});

describe("bullets", () => {
  const memo = "## I. Summary\n\nFirst point.\n\nAfter.";

  it("turn a paragraph into a bulleted list of one, spacing kept", () => {
    const after = toggled(memo, 1);
    expect(after).toBe("## I. Summary\n\n- First point.\n\nAfter.");
    const list = parseBlocks(after)[1] as Extract<Block, { kind: "list" }>;
    expect(list.kind).toBe("list");
    expect(list.ordered).toBe(false);
  });

  it("carry an indent across", () => {
    expect(toggled("  Indented.\n\nAfter.", 0)).toBe("  - Indented.\n\nAfter.");
  });

  it("come off as a paragraph per item, each keeping its level", () => {
    const after = toggled("- One\n  - Two\n\nAfter.", 0);
    expect(after).toBe("One\n\n  Two\n\nAfter.");
    expect(parseBlocks(after).map((b) => b.kind))
      .toEqual(["para", "para", "para"]);
  });

  it("turn a numbered list into a bulleted one", () => {
    expect(toggled("1. One\n2. Two\n", 0)).toBe("- One\n- Two\n");
  });

  it("on and off again give the paragraph back", () => {
    expect(toggled(toggled(memo, 1), 1)).toBe(memo);
  });
});
