import { describe, expect, it } from "vitest";

import { extractStreamingJsonString } from "./streaming-json";

// ─── open-design borrow #2 (31-01 Task 1) — single-field streaming extractor ──
// Show ONE field of a still-streaming JSON tool-arg blob live (the `content`
// being written, the target `path`) before the whole object is closeable.
describe("streaming-json — extractStreamingJsonString", () => {
  it("pulls a truncated value for a leading field", () => {
    expect(extractStreamingJsonString('{"content":"partial cod', "content")).toBe(
      "partial cod",
    );
  });

  it("pulls a field that appears after other keys", () => {
    expect(
      extractStreamingJsonString('{"path":"a.ts","content":"x', "content"),
    ).toBe("x");
  });

  it("returns undefined when the field is absent", () => {
    expect(
      extractStreamingJsonString('{"path":"a.ts","other":"x', "content"),
    ).toBeUndefined();
  });

  it("preserves an escaped quote inside the value", () => {
    expect(extractStreamingJsonString('{"content":"a \\" b', "content")).toBe(
      'a " b',
    );
  });

  it("returns a complete value up to its closing quote", () => {
    expect(
      extractStreamingJsonString('{"content":"done","path":"a.ts"}', "content"),
    ).toBe("done");
  });

  it("tolerates whitespace between key, colon and value", () => {
    expect(extractStreamingJsonString('{ "content" :  "hi', "content")).toBe("hi");
  });

  it("returns undefined when the value is not a string", () => {
    expect(extractStreamingJsonString('{"content":123', "content")).toBeUndefined();
  });

  it("returns undefined for empty inputs", () => {
    expect(extractStreamingJsonString("", "content")).toBeUndefined();
    expect(extractStreamingJsonString('{"content":"x"}', "")).toBeUndefined();
  });
});
