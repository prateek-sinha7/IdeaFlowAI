import { describe, it, expect } from "vitest";
import { saveErrorMessage } from "./saveError";

const FALLBACK = "Failed to save workflow.";

/** An error shaped like the ApiError that lib/api throws: message plus the parsed `detail`. */
function apiError(detail: unknown, message: string): Error & { detail: unknown } {
  return Object.assign(new Error(message), { detail });
}

describe("saveErrorMessage", () => {
  it("reads the text from detail.error of the connector refusal envelope", () => {
    const err = apiError(
      {
        error: "Connected apps work in your own workflows. Save a copy to use them.",
        code: "connector_grants_not_allowed",
        recoverable: true,
      },
      '{"error":"Connected apps ...","code":"connector_grants_not_allowed","recoverable":true}',
    );

    expect(saveErrorMessage(err, FALLBACK)).toBe(
      "Connected apps work in your own workflows. Save a copy to use them.",
    );
  });

  it("uses the error message when detail is a plain string", () => {
    expect(saveErrorMessage(apiError("Name already exists", "Name already exists"), FALLBACK)).toBe(
      "Name already exists",
    );
  });

  it("uses the error message when detail is a list of validation entries", () => {
    const err = apiError([{ msg: "field required" }], "field required");

    expect(saveErrorMessage(err, FALLBACK)).toBe("field required");
  });

  it.each([
    ["missing", { code: "x" }],
    ["empty", { error: "" }],
    ["blank", { error: "   " }],
    ["not a string", { error: 42 }],
  ])("falls back to the error message when detail.error is %s", (_label, detail) => {
    expect(saveErrorMessage(apiError(detail, "raw message"), FALLBACK)).toBe("raw message");
  });

  it("falls back to the given text when the error carries no message", () => {
    expect(saveErrorMessage(new Error(""), FALLBACK)).toBe(FALLBACK);
    expect(saveErrorMessage(undefined, FALLBACK)).toBe(FALLBACK);
    expect(saveErrorMessage("boom", FALLBACK)).toBe(FALLBACK);
  });

  it("keeps showing a plain Error's message", () => {
    expect(saveErrorMessage(new Error("Network down"), FALLBACK)).toBe("Network down");
  });
});
