import { describe, expect, it } from "vitest";
import {
  MAX_BATCH, NO_FILTER, filterHistory, filterMemos, planBatch, resendsFor,
  sortRows, toggle, type BatchMemo,
} from "./shareBatch";

const memo = (id: number, extra: Partial<BatchMemo> = {}): BatchMemo => ({
  memo_id: id, label: `Lender Brief`, number: `${id}.1`,
  generated_at: `2026-10-0${(id % 9) + 1} 10:00:00`, engagement: `Eng ${id}`,
  subject_name: `Company ${id}`, unsaved: false, ...extra,
});

describe("ticking memoranda", () => {
  it(`takes up to ${MAX_BATCH} and refuses the next with a reason`, () => {
    let selected: number[] = [];
    for (const id of [1, 2, 3, 4, 5]) {
      const r = toggle(selected, memo(id));
      expect(r.refused).toBeNull();
      selected = r.selected;
    }
    const sixth = toggle(selected, memo(6));
    expect(sixth.selected).toEqual([1, 2, 3, 4, 5]);
    expect(sixth.refused).toMatch(/At most 5/);
  });

  it("unticking frees a place", () => {
    const r = toggle([1, 2, 3, 4, 5], memo(3));
    expect(r.selected).toEqual([1, 2, 4, 5]);
    expect(toggle(r.selected, memo(6)).selected).toEqual([1, 2, 4, 5, 6]);
  });

  it("will not tick a memo with unsaved changes", () => {
    const r = toggle([], memo(1, { unsaved: true }));
    expect(r.selected).toEqual([]);
    expect(r.refused).toMatch(/unsaved changes/);
  });
});

describe("the shortfall plan", () => {
  const priced = { allowance: 10, remaining: 2, overage_cents: 100 };

  it("fits the remaining allowance to the first rows and prices the rest", () => {
    const plan = planBatch([5, 3, 9, 1], priced, new Set());
    expect(plan.rows.map((r) => r.kind)).toEqual(
      ["included", "included", "paid", "paid"]);
    expect([plan.included, plan.paid, plan.totalCents]).toEqual([2, 2, 200]);
  });

  it("re-sends are free and take no allowance", () => {
    const plan = planBatch([5, 3, 9], priced, new Set([5]));
    expect(plan.rows.map((r) => r.kind)).toEqual(
      ["resend", "included", "included"]);
    expect(plan.paid).toBe(0);
    expect(plan.totalCents).toBe(0);
  });

  it("no shortfall when everything fits", () => {
    const plan = planBatch([1, 2], priced, new Set());
    expect(plan.paid).toBe(0);
  });

  it("an unlimited plan never has a shortfall", () => {
    const plan = planBatch([1, 2, 3, 4, 5],
                           { allowance: null, remaining: null, overage_cents: 25 },
                           new Set());
    expect(plan.paid).toBe(0);
  });

  it("an unpriced overage is a paid row with no price to accept", () => {
    const plan = planBatch([1, 2, 3],
                           { allowance: 10, remaining: 0, overage_cents: null },
                           new Set());
    expect(plan.paid).toBe(3);
    expect(plan.unitCents).toBeNull();
  });

  it("knows a re-send by the recipient's address, ignoring case", () => {
    const ids = resendsFor(" J.Ferrers@Northbank.com ", [
      { memo_id: 5, recipient_email: "j.ferrers@northbank.com" },
      { memo_id: 6, recipient_email: "someone@else.test" }]);
    expect([...ids]).toEqual([5]);
  });
});

describe("sorting", () => {
  const rows = [
    { name: "b", n: 2, when: "2026-10-02" },
    { name: "a", n: 10, when: null },
    { name: "c", n: 1, when: "2026-10-01" },
  ];

  it("sorts text, numbers and dates both ways", () => {
    expect(sortRows(rows, "name", "asc").map((r) => r.name)).toEqual(["a", "b", "c"]);
    expect(sortRows(rows, "name", "desc").map((r) => r.name)).toEqual(["c", "b", "a"]);
    expect(sortRows(rows, "n", "asc").map((r) => r.n)).toEqual([1, 2, 10]);
  });

  it("puts missing values last whichever way", () => {
    expect(sortRows(rows, "when", "asc").map((r) => r.name)).toEqual(["c", "b", "a"]);
    expect(sortRows(rows, "when", "desc").map((r) => r.name)).toEqual(["b", "c", "a"]);
  });

  it("sorts memo numbers as numbers, not as text", () => {
    const nums = [{ number: "150.2" }, { number: "16.1" }, { number: "9.1" }];
    expect(sortRows(nums, "number", "asc").map((r) => r.number))
      .toEqual(["9.1", "16.1", "150.2"]);
  });
});

describe("filtering Share a memo", () => {
  const memos = [
    memo(1, { label: "Lender Brief", engagement: "Knightsbridge",
              generated_at: "2026-10-01 09:00:00", number: "1.1" }),
    memo(2, { label: "KYC", engagement: "Cocoa Empire",
              generated_at: "2026-10-05 09:00:00", number: "22.3" }),
  ];

  it("filters by name, engagement and number", () => {
    expect(filterMemos(memos, { ...NO_FILTER, text: "kyc" }).map((m) => m.memo_id)).toEqual([2]);
    expect(filterMemos(memos, { ...NO_FILTER, text: "knights" }).map((m) => m.memo_id)).toEqual([1]);
    expect(filterMemos(memos, { ...NO_FILTER, text: "22.3" }).map((m) => m.memo_id)).toEqual([2]);
  });

  it("filters by date generated, inclusive", () => {
    expect(filterMemos(memos, { text: "", from: "2026-10-02", to: "" })
      .map((m) => m.memo_id)).toEqual([2]);
    expect(filterMemos(memos, { text: "", from: "", to: "2026-10-01" })
      .map((m) => m.memo_id)).toEqual([1]);
  });
});

describe("filtering History", () => {
  const grants = [
    { recipient_email: "a@x.test", memo_label: "Lender Brief 1.1",
      subject: "Knightsbridge", sent_at: "2026-10-01T10:00:00Z" },
    { recipient_email: "b@y.test", memo_label: "KYC 2.1",
      subject: "Cocoa", sent_at: "2026-10-07T10:00:00Z" },
  ];

  it("filters by recipient, memorandum and date sent", () => {
    expect(filterHistory(grants, { ...NO_FILTER, text: "b@y" })).toHaveLength(1);
    expect(filterHistory(grants, { ...NO_FILTER, text: "lender" })).toHaveLength(1);
    expect(filterHistory(grants, { text: "", from: "2026-10-05", to: "" })
      .map((g) => g.recipient_email)).toEqual(["b@y.test"]);
  });
});
