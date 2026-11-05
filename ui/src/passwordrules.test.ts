import { describe, expect, it } from "vitest";
import { isPasswordRefusal, passwordProblem } from "./passwordrules";

describe("passwordProblem", () => {
  it("passes a password with everything", () => {
    expect(passwordProblem("Zq7wTr4mPl9x")).toBeNull();
  });

  it("names the one thing missing: what stopped a real sign-up", () => {
    expect(passwordProblem("zq7wtr4mpl9x"))
      .toBe("Still needs an upper case letter.");
    expect(passwordProblem("ZQ7WTR4MPL9X"))
      .toBe("Still needs a lower case letter.");
    expect(passwordProblem("ZqxwTrxmPlxx")).toBe("Still needs a number.");
    expect(passwordProblem("Zq7wTr4mPl9")).toBe("Still needs at least twelve characters.");
  });

  it("names everything missing at once", () => {
    expect(passwordProblem("")).toBe(
      "Still needs at least twelve characters, an upper case letter, "
      + "a lower case letter and a number.");
  });

  it("does not count a letter the pool might not", () => {
    expect(passwordProblem("Éq7wtr4mpl9x"))
      .toBe("Still needs an upper case letter.");
  });
});

describe("isPasswordRefusal", () => {
  it("knows the server's sentences about a password and no others", () => {
    expect(isPasswordRefusal("That password needs a number.")).toBe(true);
    expect(isPasswordRefusal("That password does not meet the rules.")).toBe(true);
    expect(isPasswordRefusal("That code is not right.")).toBe(false);
  });
});
