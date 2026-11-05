import { describe, expect, it } from "vitest";
import type { ShareGrant } from "./api";
import { recipientSuggestions } from "./recipients";

const g = (recipient_email: string, sent_at: string) =>
  ({ recipient_email, sent_at } as ShareGrant);

describe("recipientSuggestions", () => {
  it("lists each address once, most recent first", () => {
    expect(recipientSuggestions([
      g("a@one.test", "2026-11-01T10:00:00Z"),
      g("b@two.test", "2026-11-03T10:00:00Z"),
      g("a@one.test", "2026-11-02T10:00:00Z"),
    ])).toEqual(["b@two.test", "a@one.test"]);
  });

  it("treats addresses differing only in case as one, kept as last sent", () => {
    expect(recipientSuggestions([
      g("J.Ferrers@Northbank.com", "2026-11-01T10:00:00Z"),
      g("j.ferrers@northbank.com", "2026-11-04T10:00:00Z"),
    ])).toEqual(["j.ferrers@northbank.com"]);
  });

  it("is empty with nothing shared", () => {
    expect(recipientSuggestions([])).toEqual([]);
  });
});
