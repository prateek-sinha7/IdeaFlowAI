import { describe, expect, it } from "vitest";

import { parsePartialJson, repairJsonPrefix } from "./partial-json";

// ─── open-design borrow #1 (31-01 Task 1) — tolerant truncated-JSON repair ────
// Streamed run frames can carry a half-written JSON tool-arg / result blob; this
// turns the incomplete prefix into the best-effort object we render mid-stream.
describe("partial-json — parsePartialJson", () => {
  it("a complete valid JSON object parses to the same object as JSON.parse", () => {
    const raw = '{"a":1,"b":"two","c":[1,2,3],"d":{"e":true,"f":null}}';
    expect(parsePartialJson(raw)).toEqual(JSON.parse(raw));
  });

  it("a complete valid JSON array parses to the same value as JSON.parse", () => {
    const raw = '[{"x":1},{"y":"z"},[4,5]]';
    expect(parsePartialJson(raw)).toEqual(JSON.parse(raw));
  });

  it("a truncated object drops the incomplete trailing key/value", () => {
    // {"a":1,"b":"tex  -> {a:1}  (a is complete, the b pair is truncated)
    expect(parsePartialJson('{"a":1,"b":"tex')).toEqual({ a: 1 });
  });

  it("a truncated array drops its dangling comma and closes", () => {
    expect(parsePartialJson("[1,2,")).toEqual([1, 2]);
  });

  it("an unterminated string value closes the quote when it is the only pair", () => {
    expect(parsePartialJson('{"a":"he')).toEqual({ a: "he" });
  });

  it("preserves an escaped quote inside a truncated string value", () => {
    expect(parsePartialJson('{"a":"he \\" ll')).toEqual({ a: 'he " ll' });
  });

  it("garbage input returns undefined (never throws)", () => {
    expect(parsePartialJson("}{><")).toBeUndefined();
    expect(parsePartialJson("not json at all")).toBeUndefined();
  });

  it("empty / whitespace-only input returns undefined", () => {
    expect(parsePartialJson("")).toBeUndefined();
    expect(parsePartialJson("   \n\t ")).toBeUndefined();
  });

  it("a truncated nested value is salvaged into its parent", () => {
    expect(parsePartialJson('{"outer":{"inner":"par')).toEqual({
      outer: { inner: "par" },
    });
  });
});

describe("partial-json — repairJsonPrefix", () => {
  it("returns a valid JSON string that round-trips through JSON.parse", () => {
    const repaired = repairJsonPrefix('{"a":1,"b":"tex');
    expect(() => JSON.parse(repaired)).not.toThrow();
    expect(JSON.parse(repaired)).toEqual({ a: 1 });
  });

  it("returns an empty string for un-salvageable input", () => {
    expect(repairJsonPrefix("}{")).toBe("");
    expect(repairJsonPrefix("")).toBe("");
  });
});
