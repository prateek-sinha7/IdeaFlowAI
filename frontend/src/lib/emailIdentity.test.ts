import { describe, expect, it } from "vitest";

import { canonicalizeEmail } from "./emailIdentity";

describe("canonicalizeEmail", () => {
  it("returns a lowercase trimmed alias when the input contains case variants", () => {
    expect(canonicalizeEmail("  PrateekS7@gmail.com  ")).toBe("prateeks7@gmail.com");
  });
});
