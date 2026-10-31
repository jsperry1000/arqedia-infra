import { describe, expect, it } from "vitest";
import { inlinesToHtml, nodesToInlines } from "./memoedit";
import { inlinesToMarkdown, parseInlines } from "./memodoc";

// Bold and italic at once (31 October 2026).

// There is no DOM under these tests, so the few parts of a node that
// nodesToInlines reads are built by hand: text, or a tag with a style and
// children.
type Fake = { nodeType: number; nodeValue?: string; tagName?: string;
              style?: { fontWeight?: string; fontStyle?: string };
              getAttribute?: (n: string) => string | null; childNodes: Fake[] };
const text = (value: string): Fake => ({ nodeType: 3, nodeValue: value, childNodes: [] });
const tag = (name: string, children: Fake[],
             style: Fake["style"] = {}): Fake => ({
  nodeType: 1, tagName: name.toUpperCase(), style,
  getAttribute: () => null, childNodes: children,
});
const readBack = (...children: Fake[]) =>
  nodesToInlines(tag("span", children) as unknown as Node);

describe("bold and italic together", () => {
  it("are read from three asterisks either side", () => {
    expect(parseInlines("a ***key term*** here")).toEqual([
      { kind: "text", text: "a " },
      { kind: "boldem", text: "key term" },
      { kind: "text", text: " here" },
    ]);
  });

  it("are written back as they came", () => {
    for (const md of ["a ***key term*** here", "**a*****b***", "***a*****b**",
                      "**bold** and *slant*"]) {
      expect(inlinesToMarkdown(parseInlines(md))).toBe(md);
    }
  });

  it("survive the editor, whichever way the marks are nested", () => {
    for (const node of [tag("strong", [tag("em", [text("both")])]),
                        tag("i", [tag("b", [text("both")])]),
                        tag("span", [text("both")],
                            { fontWeight: "bold", fontStyle: "italic" })]) {
      expect(readBack(node)).toEqual([{ kind: "boldem", text: "both" }]);
    }
  });

  it("go into the editor as both marks", () => {
    expect(inlinesToHtml(parseInlines("x ***y*** z")))
      .toBe("x <strong><em>y</em></strong> z");
  });

  it("leave bold alone and italic alone as they were", () => {
    expect(readBack(tag("b", [text("b")]), text(" "), tag("i", [text("i")])))
      .toEqual([
        { kind: "bold", text: "b" },
        { kind: "text", text: " " },
        { kind: "em", text: "i" },
      ]);
  });
});
