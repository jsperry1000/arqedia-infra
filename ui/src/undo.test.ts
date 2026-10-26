import { describe, expect, it } from "vitest";
import {
  HISTORY_MAX, diffStep, fitHistory, pushStep, restoreKeys, sourcesOf,
  storedSize, undoStep, type Step,
} from "./undo";

const memo = [
  "# Credit memorandum",
  "",
  "## I. Summary",
  "",
  "The borrower is *accounts.pdf, page 4* sound.",
  "",
  "| Term | Value |",
  "|---|---|",
  "| Tenor | 90 days |",
  "",
  "## II. Risks",
  "",
  "- Concentration",
  "- Currency",
  "",
  "> **Gap:** no audited accounts.",
].join("\n");

const roundTrip = (before: string, after: string) => {
  const step = diffStep("edit", before, after)!;
  expect(step).not.toBeNull();
  expect(undoStep(after, step)).toBe(before);
  return step;
};

describe("blocks", () => {
  it("are the text again when joined", () => {
    expect(sourcesOf(memo).join("\n")).toBe(memo);
    expect(sourcesOf(memo + "\n").join("\n")).toBe(memo + "\n");
  });
});

describe("a step", () => {
  it("is null when nothing changed", () => {
    expect(diffStep("edit", memo, memo)).toBeNull();
  });

  it("holds one block for an edit to one paragraph", () => {
    const step = roundTrip(memo, memo.replace("sound", "unsound"));
    expect(step.before).toHaveLength(1);
    expect(step.after).toHaveLength(1);
  });

  it("undoes an added paragraph", () => {
    const step = roundTrip(memo, memo.replace("## II. Risks",
      "A new paragraph.\n\n## II. Risks"));
    expect(step.before).toHaveLength(0);
  });

  it("undoes a deleted block", () => {
    roundTrip(memo, memo.replace("> **Gap:** no audited accounts.", "")
                        .replace(/\n+$/, "\n"));
    roundTrip(memo, memo.replace("## I. Summary\n\n", ""));
  });

  it("undoes a split paragraph", () => {
    roundTrip(memo, memo.replace("is *accounts", "is\n\n*accounts"));
  });

  it("undoes a table row put in and taken out", () => {
    const added = memo.replace("| Tenor | 90 days |",
                               "| Tenor | 90 days |\n|  |  |");
    roundTrip(memo, added);
    roundTrip(added, memo);
  });

  it("undoes the whole text changed, as Discard does", () => {
    roundTrip(memo, "# Credit memorandum\n\nOnly this.");
    roundTrip("# Credit memorandum\n\nOnly this.", memo);
  });

  it("undoes edits taken back in order", () => {
    const one = memo.replace("sound", "unsound");
    const two = one.replace("Concentration", "Concentration risk");
    const s1 = diffStep("edit", memo, one)!;
    const s2 = diffStep("edit", one, two)!;
    expect(undoStep(undoStep(two, s2)!, s1)).toBe(memo);
  });

  it("refuses when the blocks are no longer what it left", () => {
    const one = memo.replace("sound", "unsound");
    const step = diffStep("edit", memo, one)!;
    expect(undoStep(one.replace("unsound", "sound enough"), step)).toBeNull();
    expect(undoStep("# Short", step)).toBeNull();
  });
});

describe("the history", () => {
  const step = (n: number): Step =>
    ({ act: "edit", at: n, before: ["a" + n], after: ["b" + n] });

  it(`keeps the last ${HISTORY_MAX}`, () => {
    let h: Step[] = [];
    for (let n = 0; n < HISTORY_MAX + 3; n++) h = pushStep(h, step(n));
    expect(h).toHaveLength(HISTORY_MAX);
    expect(h[0].at).toBe(3);
    expect(h[h.length - 1].at).toBe(HISTORY_MAX + 2);
  });

  it("drops the oldest steps until the copy fits, and keeps the text", () => {
    const big = (n: number): Step =>
      ({ act: "edit", at: n, before: ["x".repeat(1000)], after: ["y"] });
    const copy = { text: "z".repeat(500),
                   history: [0, 1, 2, 3, 4].map(big) };
    const fitted = fitHistory(copy, 3000, 100);
    expect(fitted.text).toBe(copy.text);
    expect(fitted.history.length).toBeLessThan(5);
    expect(fitted.history[fitted.history.length - 1].at).toBe(4);
    expect(storedSize(fitted) + 100).toBeLessThanOrEqual(3000);
    expect(fitHistory({ text: "z".repeat(5000), history: [big(0)] }, 3000, 100)
      .history).toHaveLength(0);
  });

  it("is left alone when it fits", () => {
    const copy = { text: "short", history: [step(1)] };
    expect(fitHistory(copy, 4 * 1024 * 1024, 4096)).toBe(copy);
  });
});

describe("the stored size", () => {
  it("counts what Python's json.dumps writes", () => {
    // json.dumps({"a": [1, 2], "b": "é"}, ensure_ascii=False) is
    // '{"a": [1, 2], "b": "é"}' - 24 bytes in UTF-8.
    expect(storedSize({ a: [1, 2], b: "é" })).toBe(24);
    expect(storedSize({ a: undefined, b: 1 })).toBe(8);
  });
});

describe("restoring what an act changed", () => {
  it("puts keys back and takes out the ones that were absent", () => {
    expect(restoreKeys({ a: 1, b: 2 }, { a: 5, b: null, c: 3 }))
      .toEqual({ a: 5, c: 3 });
  });
});
